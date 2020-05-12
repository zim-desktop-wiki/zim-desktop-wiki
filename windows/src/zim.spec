# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(['../build/venv/bin/zim_launch.py'],
             pathex=['../build'],
             binaries=[],
             datas=[ 
               ( '../build/venv/share', 'share' ),
               ( '../../zim/plugins', 'share/zim/plugins' ),
             ],
             hiddenimports=[ 'zim.plugins.spell' ],
             hookspath=[],
             runtime_hooks=['src/hook-data.py'],
             excludes=['lib2to3', 'tcl', 'tk', '_tkinter', 'tkinter', 'Tkinter'],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
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
          console=False )
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=False,
               upx_exclude=[],
               name='zim')
