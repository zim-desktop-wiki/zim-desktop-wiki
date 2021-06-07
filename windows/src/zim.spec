# -*- mode: python ; coding: utf-8 -*-

import os
import sys
import re
import subprocess

block_cipher = None

assert sys.platform == "win32", 'TODO: port spec file for other platforms'

posix2win = lambda cyg_path: subprocess.check_output(["cygpath", "-w", cyg_path]).strip(b"\n").decode()


def list_modules(path, prefix):
    modules = []
    for name in os.listdir(path):
        if name.endswith('.py') and not name.startswith('_'):
            modules.append(prefix + '.' + name[:-3])
        elif not '.' in name and not name.startswith('_'):
            modules.append(prefix + '.' + name) # folder

    assert len(modules) > 0, 'Did not find any modules in %s ?' % path
    return modules

hiddenimports = \
    list_modules('../zim/formats', 'zim.formats') + \
    list_modules('../zim/plugins', 'zim.plugins')

def find_potential_icons(path):
    # Will capture much more strings than just icon names, but that is OK,
    # we match them against actual icons in the theme when filtering, so the
    # noise drops out
    names = set()
    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
            if filename.endswith('.py'):
                code = open(dirpath + '/' + filename).read()
                for match in re.findall('[\'"]\w+(?:-\w+)+[\'"]', code):
                    names.add(match[1:-1])

    assert len(names) > 0, 'Did not find any potential icon names in %s ?' % path
    return names

icon_names = find_potential_icons('../zim')
icon_names.update({
    # Hardcoded names for Gtk.STOCK_... constants (deprecated)
    # and icons that are used by the Gtk toolkit directly
    # below */places/* is whitelisted as well to ensure file dialogs look ok
    'dialog-information',
    'dialog-warning',
    'document-open',
    'edit-clear',
    'edit-copy',
    'edit-delete',
    'edit-find',
    'format-justify-center',
    'format-justify-left',
    'format-justify-right',
    'format-text-bold',
    'format-text-italic',
    'format-text-strikethrough',
    'format-text-underline',
    'go-down',
    'go-home',
    'go-jump',
    'go-next',
    'go-previous',
    'go-up',
    'icon-theme',
    'image-missing',
    'index',
    'list-add',
    'list-remove',
    'system-help',
    'text-x-generic',
    'view-fullscreen',
    'view-refresh',
    'window-close',
    'zoom-fit-best',
    'zoom-in',
    'zoom-original',
    'zoom-out',
    'pan-start-symbolic',
    'pan-end-symbolic',
    'pan-down-symbolic',
    'pan-up-symbolic',
    'process-working-symbolic',
    'folder-new',
    'drive-harddisk',
})

a = Analysis( # noqa
    ['../build/venv/bin/zim_launch.py'],
    pathex=['../build'],
    binaries=[
        (posix2win('/mingw64/bin/gspawn-win64-helper'), '.'),
        (posix2win('/mingw64/bin/gspawn-win64-helper-console'), '.'),
    ],
    datas=[
        ('../build/venv/share', 'share'),
        ('../../zim/plugins', 'share/zim/plugins'),
        (posix2win('/mingw64/lib/girepository-1.0/HarfBuzz-0.0.typelib'), 'gi_typelibs'), # Imported automatically with latest pyinstaller, but hardcoded as part of bug workaround
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=['lib2to3', 'tcl', 'tk',
              '_tkinter', 'tkinter', 'Tkinter'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False)


# Determine existing translations
translations = []
for x in a.datas:
    if x[0].startswith('share/locale') and x[0].endswith('zim.mo'):
        dirs = os.path.normpath(x[0]).split(os.path.sep)
        translations.append(dirs[2])
translations = set(translations)


# Filter data resources
def keepdata(x):
    if x[0].startswith('share/icons/Adwaita'):
        return ('/places' in x[0]) \
            or (os.path.splitext(os.path.basename(x[0]))[0] in icon_names)
    elif x[0].startswith('share/locale'):
        dirs = os.path.normpath(x[0]).split(os.path.sep)
        return (len(dirs) < 3) or (dirs[2] in translations)
    return True

a.datas = TOC([x for x in a.datas if keepdata(x)]) # noqa


pyz = PYZ( # noqa
    a.pure, a.zipped_data,
    cipher=block_cipher)

exe = EXE( # noqa
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='zim',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    icon='../../icons/zim.ico',
    version='../build/file_version_info.txt',
    console=False)

coll = COLLECT( # noqa
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='zim')
