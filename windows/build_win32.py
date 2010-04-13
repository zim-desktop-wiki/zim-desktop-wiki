import os, sys, shutil
import py2exe
from distutils.core import setup

# If run without args, build executables, in quiet mode.
if len(sys.argv) == 1:
    sys.argv.append("py2exe")
	
# update "data" folder
shutil.rmtree("windows/release/data", True)
shutil.copytree("data", "windows/release/data")

# If you installed GTK to a different folder, change these lines:
shutil.rmtree("windows/release/etc", True)
shutil.copytree("c:/Program Files/Common Files/GTK/2.0/etc", "windows/release/etc")
shutil.rmtree("windows/release/lib", True)
shutil.copytree("c:/Program Files/Common Files/GTK/2.0/lib", "windows/release/lib")
shutil.rmtree("windows/release/share", True)
shutil.copytree("c:/Program Files/Common Files/GTK/2.0/share", "windows/release/share")

# copy plugins folder so Preferences dialog can iterate through them
shutil.rmtree("windows/release/zim", True)
shutil.copytree("zim/plugins", "windows/release/zim/plugins")

# create main.exe
setup(
    options = {"py2exe": {"compressed": 0,
                          "optimize": 2,
                          "ascii": 1,
                          "bundle_files": 3,
                          "packages": ["encodings", "cairo", "atk", "pangocairo", "zim", "bzrlib"],
                          "dist_dir" : "windows/release"
                          }},
    zipfile = None,
    windows = [{
            "script": "zim.py",
            "icon_resources": [(1, "data/pixmaps/favicon.ico")]
        }],
)
