#!/usr/bin/python3
#
# Modify data search path at runtime

import sys, os

if getattr(sys, 'frozen', False):
        # we are running in a bundle
        bundle_dir = sys._MEIPASS
        data_dir = os.path.join(bundle_dir, "share")
else:
        # we are running in a normal Python environment
        bundle_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(bundle_dir, "..", "share")

os.environ["XDG_DATA_DIRS"] = data_dir
