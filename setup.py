#!/usr/bin/env python3

import setuptools, sys

setuptools.setup(
    name = 'pytyle1x',
    version = '1.0.3',
    author = 'zehkira',
    description = 'A tiling manager for EWMH compliant window managers',
    long_description = open('README.md', 'r').read(),
    long_description_content_type = 'text/markdown',
    url = 'https://github.com/zehkira/pytyle1x',
    packages = setuptools.find_packages(),
    install_requires = ['python-xlib'],
    classifiers = [
        'Programming Language :: Python :: 3.6',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Operating System :: POSIX :: Linux',
        'Topic :: Desktop Environment :: Window Managers'
    ],
    scripts = ['bin/pytyle1x'],
    python_requires = '>=3.6',
)
