import os
import sys
import shutil
import datetime
import subprocess
import distutils.dir_util

sys.path.append(".")
from zim import __version__

# For the complete Windows build procedure, please read
# README-BUILD-win32.txt

#  Clean up the build directory
shutil.rmtree("windows/build", True)

# update "data" folder
shutil.copytree("data", "windows/build/data")

# If you installed GTK to a different folder, change these lines:
shutil.copytree("c:/Program Files/Common Files/GTK/2.0/etc", "windows/build/etc")
shutil.copytree("c:/Program Files/Common Files/GTK/2.0/lib", "windows/build/lib")
shutil.copytree("c:/Program Files/Common Files/GTK/2.0/share", "windows/build/share")

# Copy translation files
# Use function from distutils because shutil.copytree fails when destination folder exists
distutils.dir_util.copy_tree("locale", "windows/build/share/locale", update=1)

# Copy plugins folder so Preferences dialog can iterate through them
shutil.rmtree("windows/build/zim", True)
shutil.copytree("zim/plugins", "windows/build/zim/plugins")

# Copy the hicolor icon theme from windows folder because it's missing from Gtk/win32 distro
os.makedirs("windows/build/share/icons/hicolor")
shutil.copyfile(
	"windows/hicolor-icon-theme__index.theme",
	"windows/build/share/icons/hicolor/index.theme"
)

# print out version number
f = open("windows/version-and-date.nsi", "w")
f.write('!define VER "%s"\n' % __version__)
f.write('!define BUILDDATE "%s"\n' % datetime.datetime.now().strftime("%Y-%m-%d"))
f.close()

# create main.exe
subprocess.check_call(['python.exe', 'setup.py', 'py2exe'])

# NSIS script compiles to "dist" folder but compiler won't create it if it's needed
if not os.path.exists("dist"):
    os.mkdir("dist")
