# -*- mode: python ; coding: utf-8 -*-

import os.path
import subprocess
import sys

block_cipher = None
binaries = []

if sys.platform == "win32":
    posix2win = lambda cyg_path: subprocess.check_output(["cygpath", "-w", cyg_path]).strip(b"\n").decode()

    binaries.append((posix2win('/mingw64/bin/gspawn-win64-helper'), '.'))
    binaries.append((posix2win('/mingw64/bin/gspawn-win64-helper-console'), '.'))

a = Analysis( # noqa
    ['../build/venv/bin/zim_launch.py'],
    pathex=['../build'],
    binaries=binaries,
    datas=[
        ('../build/venv/share', 'share'),
        ('../../zim/plugins', 'share/zim/plugins'),
    ],
    hiddenimports=[
        'zim.plugins.arithmetic',
        'zim.plugins.attachmentbrowser',
        'zim.plugins.backlinkpane',
        'zim.plugins.base',
        'zim.plugins.bookmarksbar',
        'zim.plugins.diagrameditor',
        'zim.plugins.ditaeditor',
        'zim.plugins.equationeditor',
        'zim.plugins.gnu_r_ploteditor',
        'zim.plugins.gnuplot_ploteditor',
        'zim.plugins.inlinecalculator',
        'zim.plugins.insertsymbol',
        'zim.plugins.journal',
        'zim.plugins.linesorter',
        'zim.plugins.linkmap',
        'zim.plugins.pageindex',
        'zim.plugins.pathbar',
        'zim.plugins.printtobrowser',
        'zim.plugins.quicknote',
        'zim.plugins.scoreeditor',
        'zim.plugins.screenshot',
        'zim.plugins.sequencediagrameditor',
        'zim.plugins.sourceview',
        'zim.plugins.spell',
        'zim.plugins.tableeditor',
        'zim.plugins.tableofcontents',
        'zim.plugins.tags',
        'zim.plugins.tasklist',
        'zim.plugins.trayicon',
        'zim.plugins.versioncontrol'
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['lib2to3', 'tcl', 'tk',
              '_tkinter', 'tkinter', 'Tkinter'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False)

# Filter icons
include_icons = {
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
}


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
        return os.path.splitext(os.path.basename(x[0]))[0] in include_icons
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
