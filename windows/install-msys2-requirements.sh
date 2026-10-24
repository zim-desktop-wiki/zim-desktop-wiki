#!/usr/bin/env bash

# Install requirements to build zim windows installer
# Common between github build actions and build.sh script

# Skip font cache update
#export MSYS2_FC_CACHE_SKIP=1

# Install build dependencies
pacman --noconfirm -S --needed \
    git \
    make \
    mingw-w64-ucrt-x86_64-gtk3 \
    mingw-w64-ucrt-x86_64-cairo \
    mingw-w64-ucrt-x86_64-python \
    mingw-w64-ucrt-x86_64-python-gobject \
    mingw-w64-ucrt-x86_64-python-cairo \
    mingw-w64-ucrt-x86_64-python-setuptools \
    mingw-w64-ucrt-x86_64-gobject-introspection \
    mingw-w64-ucrt-x86_64-gtksourceview3 \
    mingw-w64-ucrt-x86_64-python-numpy \
    mingw-w64-ucrt-x86_64-python-pip \
    mingw-w64-ucrt-x86_64-nsis \
    mingw-w64-ucrt-x86_64-pkg-config
