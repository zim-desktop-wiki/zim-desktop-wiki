import os, sys, shutil
import py2exe
import datetime
from distutils.core import setup
sys.path.append(".")
from zim import __version__

# For the complete Windows build procedure, please read
# README-BUILD-win32.txt

# If run without args, build executables, in quiet mode.
if len(sys.argv) == 1:
    sys.argv.append("py2exe")

# update "data" folder
shutil.rmtree("windows/zim/data", True)
shutil.copytree("data", "windows/zim/data")

# If you installed GTK to a different folder, change these lines:
shutil.rmtree("windows/zim/etc", True)
shutil.copytree("c:/Program Files/Common Files/GTK/2.0/etc", "windows/zim/etc")
shutil.rmtree("windows/zim/lib", True)
shutil.copytree("c:/Program Files/Common Files/GTK/2.0/lib", "windows/zim/lib")
shutil.rmtree("windows/zim/share", True)
shutil.copytree("c:/Program Files/Common Files/GTK/2.0/share", "windows/zim/share")

# copy plugins folder so Preferences dialog can iterate through them
shutil.rmtree("windows/zim/zim", True)
shutil.copytree("zim/plugins", "windows/zim/zim/plugins")

# print out version number
f = open("windows/version-and-date.nsi", "w")
f.write('!define VER "%s"\n' % __version__)
f.write('!define BUILDDATE "%s"\n' % datetime.datetime.now().strftime("%Y-%m-%d"))
f.close()

# NSIS script compiles to "dist" folder but compiler won't create it if it's needed
if not os.path.exists("dist"):
    os.mkdir("dist")

# create main.exe
setup(
    options = {"py2exe": {"compressed": 0,
                          "optimize": 2,
                          "ascii": 1,
                          "bundle_files": 3,
                          "packages": ["encodings", "cairo", "atk", "pangocairo", "zim", "bzrlib"],
                          "dist_dir" : "windows/zim"
                          }},
    zipfile = None,
    windows = [{
            "script": "zim.py",
            "icon_resources": [(1, "data/pixmaps/favicon.ico")]
        }],
)
