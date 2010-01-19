import os, sys, shutil
import py2exe
from distutils.core import setup

# If run without args, build executables, in quiet mode.
if len(sys.argv) == 1:
    sys.argv.append("py2exe")
	
# update "data" folder
shutil.rmtree("windows/release/data", True)
shutil.copytree("data", "windows/release/data")

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
            "icon_resources": [(1, "website/files/favicon.ico")]
        }],
)
