# --------------------------------------------------------------------
# For the complete Windows build procedure, please read
# README-BUILD-win32.txt .
#
# Some general advice for building PyGTK-based Windows .EXEs can be
# found here:
# http://www.no-ack.org/2010/09/complete-guide-to-py2exe-for-pygtk.html
# --------------------------------------------------------------------

import os
from os import path
import datetime
import re
import subprocess

os.chdir(path.dirname(path.dirname(path.realpath(__file__))))

# --------------------------------------
# CONFIG AND PATHS
# --------------------------------------

# Parse '__version__' out of zim package since simply importing __version__ from zim fails as of 0.61

f = open("zim/__init__.py", "r")
text = f.read()
f.close()
match = re.search(r"^\s*__version__\s*=\s*['\"]([\d\.]+)['\"]\s*$", text, re.MULTILINE)
if match:
	ZIM_VERSION = match.group(1)
else:
	raise RuntimeError("Can't parse Zim version from zim/__init__.py .")

# NSIS compiler

MAKENSIS = path.join(os.environ["PROGRAMFILES"], r"NSIS\makensis.exe")
if not path.exists(MAKENSIS):
	if "PROGRAMFILES(X86)" in os.environ:
		MAKENSIS = path.join(os.environ["PROGRAMFILES(x86)"], r"NSIS\makensis.exe")
	if not path.exists(MAKENSIS):
		raise RuntimeError("Can't find makensis.exe")

# --------------------------------------
# NSIS STUFF
# --------------------------------------

# Print out version number to NSIS include file

f = open(r"windows\build\version-and-date.nsi", "w")
print >>f, '!define VER "%s"' % ZIM_VERSION
print >>f, '!define BUILDDATE "%s"' % datetime.datetime.now().strftime("%Y-%m-%d")
f.close()

# NSIS script compiles to "dist" folder but compiler won't create it if it's needed

if not path.exists("dist"): os.mkdir("dist")

subprocess.check_call([MAKENSIS, "windows\src\zim-installer"])
