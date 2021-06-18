from Xlib.display import Display
from Xlib import X, XK, Xatom, Xutil, protocol
from Xlib.ext import xinerama
import sys, math


class Probe:
    # There should only be one Probe instance at any given time. Upon init,
    # instantiate the display object and fetch the root window. We also need to
    # listen to certain events on the root window:
    #    1. KeyPressMask - For mapping our hot keys
    #    2. SubstructureNotifyMask - For Create/Destroy window notification
    #    3. PropertyChangeMask - For desktop change notification
    def __init__(self):
        self._display = Display()
        self._root = self.get_display().screen().root
        self._wm = ''
        self.determine_window_manager()
        self.get_root().change_attributes(
            event_mask = X.KeyPressMask | X.SubstructureNotifyMask | X.PropertyChangeMask
        )

    # Alias to save some typing.
    # Display.intern_atom takes a string representation of an atom, and converts
    # it to its proper integer representation- which is what the X protocol uses.
    def atom(self, name):
        return self.get_display().intern_atom(name)

    # Finds the name of the current window manager.
    def determine_window_manager(self):
        cid = self.get_root().get_full_property(
            self.atom('_NET_SUPPORTING_WM_CHECK'),
            0
        )

        if not cid or not hasattr(cid, 'value'):
            return

        cid = cid.value[0]

        win = self.get_display().create_resource_object('window', cid)
        if not win:
            return

        name = win.get_full_property(self.atom('_NET_WM_NAME'), 0)
        if not name or not hasattr(name, 'value'):
            return

        self._wm = name.value.lower()

    # Takes a string representation of a key and turns it into a key code for
    # use with grab_key. See Xlib/keysymdef/latin1.py and
    # Xlib/keysymdef/miscellany.py for available key code strings.
    def generate_keycode(self, key):
        return self.get_display().keysym_to_keycode(XK.string_to_keysym(key))

    # Takes a list of string modifiers and converts them to their proper mask
    # form. Essentially the equivalent of generate_keycode for key modifiers.
    # Currently the only modifiers supported are Shift, Ctrl, Alt, and Super.
    def generate_modmask(self, mods):
        modmask = 0
        if len(mods) >= 1:
            for mod in mods:
                if mod == 'Shift':
                    modmask = modmask | X.ShiftMask
                elif mod == 'Ctrl':
                    modmask = modmask | X.ControlMask
                elif mod == 'Alt':
                    modmask = modmask | X.Mod1Mask
                elif mod == 'Super':
                    modmask = modmask | X.Mod4Mask
                else:
                    print('Could not use modifier %s' % mod, file = sys.stderr)
        else:
            modmask = X.AnyModifier

        return modmask

    # Queries the window manager for the currently active window. This is
    # what is *always* used to find the active window. We only rely on X events
    # to tell us when to use this (since the events can come from the root
    # window, and thus give us unknown id's for any given window).
    #
    # Note: It's possible that we won't have an active window.
    def get_active_window_id(self):
        active = self.get_root().get_full_property(
            self.atom('_NET_ACTIVE_WINDOW'),
            0
        )

        if hasattr(active, 'value'):
            return hex(active.value[0])
        else:
            return None

    # Queries the window manager for the currently active desktop.
    def get_desktop(self):
        dsk = self.get_root().get_full_property(
            self.atom('_NET_CURRENT_DESKTOP'),
            0
        )

        # sometimes there's no active desktop for some reason
        if dsk:
            dsk = dsk.value[0]
        else:
            print('Warning: assuming active desktop 0')
            dsk = 0

        return dsk

    # Queries the window manager for all available desktops. It also stores each
    # desktop name, which serves no function in PyTyle currently. (Good for easy
    # debugging though, I guess.) This is also where we query for our workarea
    # information such as the resolution, and the workarea accounting for panels
    # and/or docks. (See _NET_WM_STRUT and _NET_WM_STRUT_PARTIAL)
    def get_desktops(self):
        info = {}
        desktops = self.get_root().get_full_property(
            self.atom('_NET_NUMBER_OF_DESKTOPS'),
            0
        ).value[0]
        workarea = self.get_root().get_full_property(
            self.atom('_NET_WORKAREA'),
            0
        ).value
        resolution = self.get_root().get_full_property(
            self.atom('_NET_DESKTOP_GEOMETRY'),
            0
        ).value

        for i in range(desktops):
            info[i] = {
                'id': int(i), 'x': workarea[0], 'y': workarea[1],
                'width': workarea[2], 'height': workarea[3],
                'resx': resolution[0], 'resy': resolution[1], 'name': 'None'
            }

        return info

    # Returns the current display object - our connection to X.
    def get_display(self):
        return self._display

    # Returns the current root window.
    def get_root(self):
        return self._root

    # Tries to use xinerama to find multiple heads. The only thing xinerama
    # gives us are the x/y/width/height values of each screen. That means
    # we need to calculate which screen every window is on ourselves. You
    # can find this logic in the Screen class. Additionally, if xinerama
    # is not available, we simply build our own 'Screen 0' with the
    # desktop geometry reported from the window manager. Don't forget, if
    # there is only one screen, the tiling algorithms will use the proper
    # workarea so that it accounts for panels/docks and the like, however,
    # if there is more than one screen, we need to manually specify docks
    # and panels in the configuration file. Why? Because it seems OpenBox
    # doesn't report the proper workarea back with multiple screens.
    #
    # Note: In fact, I have a feeling that this could get messy if there are
    # two panels (top/bottom, for instance)- so I'm going to enable the
    # config for docks/panels to take effect regardless of the number of
    # screens.
    def get_screens(self):
        ret = []

        if self.has_xinerama():
            screens = self.get_display().xinerama_query_screens().screens
            for i in range(len(screens)):
                screen = screens[i]
                ret.append({
                    'id': i,
                    'x': screen.x,
                    'y': screen.y,
                    'width': screen.width,
                    'height': screen.height
                })

        if not ret:
            resolution = self.get_root().get_full_property(
                self.atom('_NET_DESKTOP_GEOMETRY'),
                0
            ).value
            ret = [{
                'id': 0,
                'x': 0,
                'y': 0,
                'width': resolution[0],
                'height': resolution[1]
            }]

        return ret

    # Retrieves the current viewport. This is necessary for resizing
    # windows in managers like Compiz! Compiz thinks about windows
    # *relative* to the current viewport, so whenever we resize in a
    # window manager like that, we need to know the current viewport.
    def get_viewport(self):
        viewport = self.get_root().get_full_property(
            self.atom('_NET_DESKTOP_VIEWPORT'),
            Xatom.CARDINAL
        )
        if viewport and hasattr(viewport, 'value'):
            return {'x': viewport.value[0], 'y': viewport.value[1]}
        return None

    # Retrieves all available viewports. It uses some math trickery, but here's
    # the general gist:
    #    1. Ask the WM for the desktop geometry
    #    2. Ask the WM for the workarea.
    #    3. Divide the workarea into the desktop geometry, and floor it
    #        A. floor(desktop_width / workarea_width)
    #        B. floor(desktop_height / workarea_height)
    #        NOTE: We floor because the workarea might be smaller than the
    #        screen resolutions (struts).
    #    4. Calculations will give us number of horizontal and vertical
    #       viewports, respectively.
    #    5. Assigns id's: go vertical first, then wind back up to the
    #       next column.
    def get_viewports(self):
        geom = self.get_root().get_full_property(
            self.atom('_NET_DESKTOP_GEOMETRY'),
            Xatom.CARDINAL
        )
        if self.is_compiz():
            workarea = self.get_root().get_full_property(
                self.atom('_NET_WORKAREA'),
                Xatom.CARDINAL
            )

            if not geom or not workarea:
                return None

            verts = int(math.floor(geom.value[1] / workarea.value[3]))
            horz = int(math.floor(geom.value[0] / workarea.value[2]))
            inc = 0
            viewports = []

            for v in range(verts):
                for h in range(horz):
                    viewports.append({
                        'id': inc,
                        'x': (geom.value[0] / horz) * h,
                        'y': (geom.value[1] / verts) * v
                    })
                    inc += 1
        else:
            viewports = [{
                'id': 0,
                'x': 0,
                'y': 0
            }]

        return viewports

    # This will query the window manager for all necessary information for the
    # given window. This method takes a resource object created via
    # 'create_resource_object'- or alternatively, straight from an event.
    # (Although, I don't recommend pulling a window straight from an event, as
    # it could be out of sync with PyTyle.) This method is called when a window
    # changes- we want to know its new state. (i.e., hidden, resized, desktop
    # or screen changed, etc.)
    #
    # Note: There is a lot that goes into this method, so please see the comments
    # below as well.
    #
    # Note 2: We don't calculate which screen the window is on from here. We do
    # that later (Window.load_window, essentially). However, this method supplies
    # what we need for that calculation- the window's x,y coordinates.
    def get_window(self, win):
        # We don't really need the window name, but it's useful for debugging.
        # If a window doesn't have a name, or the window manager doesn't
        # listen to us, then we can still move on.
        winname = win.get_full_property(self.atom('_NET_WM_NAME'), 0)

        # Another way to find the window name.
        if not winname:
            winname = win.get_full_property(Xatom.WM_NAME, 0)
            if not winname:
                winname = ''

        if winname:
            winname = winname.value

        # Fetch the desktop that the window is on.
        windesk = win.get_full_property(
            self.atom('_NET_WM_DESKTOP'),
            0
        )

        # mutter/budgie-wm sometimes refuses to tell us the desktop
        if windesk:
            windesk = windesk.value[0]
        else:
            print('Warning: assuming desktop 0 for window', winname)
            windesk = 0 # might cause problems

        # Fetch the window geometry- see the method below for more info.
        wingeom = self.get_window_geometry(win)

        # Extents are *hopefully* the window decoration sizes. PyTyle will
        # take these into account when sizing the windows. So far, support
        # seems pretty good for this from WM's.
        extents = win.get_full_property(self.atom('_NET_FRAME_EXTENTS'), 0)

        if not extents:
            extents = [0, 0, 0, 0]
        else:
            extents = extents.value

        # We use the normal hints to find the window's gravity. If the
        # gravity is static, then we need to change it to NorthWest at
        # some point if we expect the window to behave like we want it to.
        #
        # Note: This is obviously a hack. It would be better if we could
        # *account* for static gravity. Especially since static gravity
        # is set by the application itself, and if we don't let it have what
        # it wants, we might get unexpected behavior. So far so good, though.
        # If anyone has a better understanding of gravity than I do (that is,
        # beyond the usual man page), then I'd love to talk to you.
        norm_hints = win.get_wm_normal_hints()

        if norm_hints and norm_hints['win_gravity'] == X.StaticGravity:
            static = True
        else:
            static = False

        # So the transient will tell us a window's parent window. Why do we
        # care? Because if a top level window creates a child window (i.e.
        # a popup), then it will hopefully set that child window's transient
        # property as itself. If we come across transient windows, I don't
        # think we want to tile them. Sometimes the transient is set to the
        # root window, in which case it is obviously a window we want to tile.
        transient = win.get_wm_transient_for()

        if not transient or transient == self.get_root():
            popup = False
        else:
            popup = True

        # If a window is hidden, we don't want to tile it. (Or more importantly,
        # we don't want PyTyle to *think* there is a window that's there and
        # isn't.) Check for dock/panel/skip taskbar, etc...
        #
        # Note: We check both the '_NET_WM_STATE' (different from 'WM_STATE' which
        # tells us about iconification and stuff) and the '_NET_WM_WINDOW_TYPE'.
        state = win.get_full_property(self.atom('_NET_WM_STATE'), Xatom.ATOM)
        dock = win.get_full_property(
            self.atom('_NET_WM_WINDOW_TYPE'),
            Xatom.ATOM
        )

        hidden = (state and (self.atom('_NET_WM_STATE_HIDDEN') in state.value or self.atom('_NET_WM_STATE_SKIP_TASKBAR') in state.value or self.atom('_NET_WM_STATE_SKIP_PAGER') in state.value)) or (dock and (self.atom('_NET_WM_WINDOW_TYPE_DOCK') in dock.value or self.atom('_NET_WM_WINDOW_TYPE_TOOLBAR') in dock.value or self.atom('_NET_WM_WINDOW_TYPE_MENU') in dock.value or self.atom('_NET_WM_WINDOW_TYPE_SPLASH') in dock.value or self.atom('_NET_WM_WINDOW_TYPE_DIALOG') in dock.value))

        # Construct the window data structure. This is passed to the
        # update_attributes method.
        return {
            'id': hex(win.id),
            'desktop': int(windesk),
            'x': wingeom['x'], 'y': wingeom['y'],
            'width': wingeom['width'], 'height': wingeom['height'],
            'd_left': extents[0], 'd_right': extents[1],
            'd_top': extents[2], 'd_bottom': extents[3],
            'title': winname, 'class': win.get_wm_class(),
            'static': static,
            'popup': popup,
            'hidden': hidden,
            'xobj': win
        }

    # Simply fetchs a list of windows from the window manager. The list is
    # given to us as window id's- we then use that id to create a resource
    # object from which we can query.
    def get_windows(self):
        info = {}
        windows = self.get_window_list()

        for window in windows:
            info[hex(window)] = self.get_window_by_id(window)

        return info

    # Creates a window resource object from a given window id (decimal).
    def get_window_by_id(self, window_id):
        win = self.get_display().create_resource_object('window', window_id)
        return self.get_window(win)

    # It took me a little bit to figure this one out. So apparently, the
    # get_geometry window method returns coordinates that we don't care about.
    # (That is, they are relative to the root window?) So in order to
    # rectify this, we need to 'translate' the x,y coordinates relative to
    # that root window. Not very intuitive at all. Kudos to wmctrl for showing
    # me the light here.
    #
    # Note: More testing has revealed different behavior for different window
    # managers here. For instance, with Compiz, we actually want the raw x,y
    # coordinates from get_geometry- translating them is bad! We end up with
    # some pretty big figures. (Viewports..?) I haven't investigated Compiz
    # thoroughly, but was able to get some minimal functionality by simply
    # removing the call to translate_coords.
    def get_window_geometry(self, win):
        wingeom = win.get_geometry()

        wintrans = win.translate_coords(self.get_root(), wingeom.x, wingeom.y)
        wintrans.x = -wintrans.x
        wintrans.y = -wintrans.y

        # This is for compiz (and any other viewport-style WM?)...
        # looks like we don't need to translate
        if self.is_compiz():
            viewport = self.get_viewport()
            if viewport:
                wintrans = wingeom
                wintrans.x += viewport['x']
                wintrans.y += viewport['y']

        return {
            'x': wintrans.x,
            'y': wintrans.y,
            'width': wingeom.width,
            'height': wingeom.height
        }

    # Queries the window manager for a list of window id's. These window id's
    # are then used to create a window resource object from which we can query
    # for information about that specific window.
    def get_window_list(self):
        return self.get_root().get_full_property(
            self.atom('_NET_CLIENT_LIST'),
            Xatom.WINDOW
        ).value

    # Returns the current window manager name.
    def get_wm_name(self):
        return self._wm

    # Another one that took forever to figure out. Grabbing a key *itself* is
    # pretty straight-forward. Unfortunately, I had number lock on. Ug. So
    # for each key we want to grab, we need to grab it normally, and then we
    # need to grab it three more times with the following masks:
    #    Mod2Mask (Number lock)
    #    LockMask (Caps lock)
    #    Mod2Mask | LockMask (Number lock and Caps lock)
    #
    # What about scroll lock? o_O
    def grab_key(self, keycode, mask):
        self.get_root().grab_key(
            keycode,
            mask,
            1,
            X.GrabModeAsync,
            X.GrabModeAsync
        )
        self.get_root().grab_key(
            keycode,
            mask | X.Mod2Mask,
            1,
            X.GrabModeAsync,
            X.GrabModeAsync
        )
        self.get_root().grab_key(
            keycode,
            mask | X.LockMask,
            1,
            X.GrabModeAsync,
            X.GrabModeAsync
        )
        self.get_root().grab_key(
            keycode,
            mask | X.Mod2Mask | X.LockMask,
            1,
            X.GrabModeAsync,
            X.GrabModeAsync
        )

    # Checks if the xinerama extension is enabled.
    def has_xinerama(self):
        return self.get_display().has_extension('XINERAMA')

    # Checks to see if Compiz is running. It needs unique attention.
    def is_compiz(self):
        return self.get_wm_name() == 'compiz'

    # Reports if the window manager is running or not
    def is_wm_running(self):
        try:
            PROBE.get_desktops()
        except:
            return False
        return True

    # Ungrabs a key (and all its modifiers). This allows us to dynamically reload
    # keybindings as PyTyle is running.
    def ungrab_key(self, keycode, mask):
        self.get_root().ungrab_key(keycode, mask)
        self.get_root().ungrab_key(keycode, mask | X.Mod2Mask)
        self.get_root().ungrab_key(keycode, mask | X.LockMask)
        self.get_root().ungrab_key(keycode, mask | X.Mod2Mask | X.LockMask)

    # Activates the given window. This will also pull it above all other
    # windows.
    def window_activate(self, win):
        win.set_input_focus(X.RevertToNone, X.CurrentTime)
        self.window_stackabove(win)
        self.get_display().flush()

    # Props to devilspie for this one.
    def window_add_decorations(self, win):
        self._send_event(
            win,
            self.atom('_NET_WM_STATE'),
            [0, self.atom('_OB_WM_STATE_UNDECORATED')]
        )
        self.get_display().flush()

    # This sets up the event mask on the given window. This will tell the
    # X server to send us only the events we're interested in (however,
    # we still get a boat load more than what we really care about).
    # They are as follows:
    #    FocusChangeMask    Whenever a window changes focus. We only use
    #                       this to detect FocusIn events, and I'm thinking
    #                       about using PropertyChange on the root window
    #                       instead of this.
    #    StructureNotifyMask    For when a window changes x/y/width/height.
    #    PropertyChangeMask     For when a window changes desktops.
    #
    # Note: See Event.py for more information on events.
    def window_listen(self, win):
        win.change_attributes(
            event_mask = (
                X.FocusChangeMask | X.StructureNotifyMask | X.PropertyChangeMask
            )
        )

    # Simply maximizes a window. We must send a client message event to the
    # root window for this. (Or any other _NET_WM_STATE_* property.)
    def window_maximize(self, win):
        self._send_event(
            win,
            self.atom('_NET_WM_STATE'),
            [
                1,
                self.atom('_NET_WM_STATE_MAXIMIZED_VERT'),
                self.atom('_NET_WM_STATE_MAXIMIZED_HORZ')
            ]
        )
        self.get_display().flush()

    def window_remove_decorations(self, win):
        self._send_event(
            win,
            self.atom('_NET_WM_STATE'),
            [1, self.atom('_OB_WM_STATE_UNDECORATED')]
        )
        self.get_display().flush()

    # Attempts to set window gravity to NorthWest. So far this has been
    # working well, although changing a window's gravity is a hack. See
    # get_window for more information on this gravity stuff as it
    # relates to PyTyle.
    def window_remove_static(self, window):
        window.set_wm_normal_hints(
            flags = Xutil.PWinGravity,
            win_gravity = X.NorthWestGravity
        )
        self.get_display().flush()

    # This 'unmaximizes' or 'restores' a window. We need to do this
    # every time we resize a window because it could have been maximized
    # by the user (which then could not be resized).
    def window_reset(self, win):
        self._send_event(
            win,
            self.atom('_NET_WM_STATE'),
            [
                0,
                self.atom('_NET_WM_STATE_MAXIMIZED_VERT'),
                self.atom('_NET_WM_STATE_MAXIMIZED_HORZ')
            ]
        )
        self.get_display().flush()

    # Resizes the window with the given x/y/width/height pixel values.
    # Don't forget to flush after and reset the window before.
    def window_resize(self, win, x, y, width, height):
        self.window_reset(win)

        # This is for compiz (and any other viewport-style WM?)...
        # looks like we don't need to translate
        if self.is_compiz():
            viewport = self.get_viewport()
            if viewport:
                x -= viewport['x']
                y -= viewport['y']

        win.configure(x = x, y = y, width = width, height = height)
        self.get_display().flush()

    # Puts window at the top of the stack.
    def window_stackabove(self, win):
        win.configure(stack_mode = X.Above)

    # Puts window at the bottom of the stack.
    def window_stackbelow(self, win):
        win.configure(stack_mode = X.Below)

    # Stop listening to a window. PyTyle does not currently use this,
    # but I was toying with it when I was hitting positive feedback
    # in my main event loop. Yuck.
    def window_unlisten(self, win):
        win.change_attributes(event_mask = 0)


    # Another tricky one to figure out- this will allow you to send
    # a client message to the root window (necessary for removing
    # decorations, maximizing, etc).
    #
    # Props to PyPanel for this little snippet.
    def _send_event(self, win, ctype, data, mask = None):
        data = (data + ([0] * (5 - len(data))))[:5]
        ev = protocol.event.ClientMessage(
            window = win,
            client_type = ctype,
            data = (32, (data))
        )
        self.get_root().send_event(ev, event_mask = X.SubstructureRedirectMask)


# Instantiate the PROBE instance. This is what we import.
PROBE = Probe()
