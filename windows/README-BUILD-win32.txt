How to Build pyzim on Windows
=============================


Overview
--------

To build Zim for Windows, you must install all the requirements listed
below. Then follow the steps in the "Building Zim" section.

To make the regular desktop installer package, see "Packaging the
Regular Installer".

To make the portable package, see "Packaging the PortableApps.com
Installer".


Requirements
------------

1. Install Python 2.6 or greater for Windows from

   http://www.python.org/download/

   Note: Python version must be 2.6 or greater, but less than 3.0

2. Install the py2exe library from

   http://sourceforge.net/projects/py2exe/files/

3. Download GTK+ Bundle from

   http://ftp.gnome.org/pub/gnome/binaries/win32/gtk+/2.22/

   Or a newer version if one exists. Extract this Zip file to a
   convenient place such as

   C:\Program Files (x86)\Common Files\GTK+ Bundle

4. Install PyCairo, PyGObject, and PyGTK from

   http://ftp.gnome.org/pub/GNOME/binaries/win32/pycairo/[newest version]/pycairo-VERSION.win32-pyVER.msi
   http://ftp.gnome.org/pub/GNOME/binaries/win32/pygobject/[newest version]/pygobject-VERSION.win32-pyVER.msi
   http://ftp.gnome.org/pub/GNOME/binaries/win32/pygtk/[newest version]/pygtk-VERSION.win32-pyVER.msi

   Make sure that the Python version matches the one you're using, and
   that you don't download a pygtk library with a version newer than
   the bundle from the previous step.

5. Jpeg for Windows

   http://gnuwin32.sourceforge.net/packages/jpeg.htm

   Get jpeg62.dll and put it in ./windows .

6. Install Bazaar using the PYTHON-BASED installer from

   http://wiki.bazaar.canonical.com/WindowsDownloads

   The build script depends on Python Bazaar.

7. Install NSIS from

   http://nsis.sourceforge.net/Download

7a. You will also want to download Venis IX if you want to edit the
    NSIS script in an IDE. (The script is a plain text file, though,
    if you don't want to use an IDE.)
    http://nsis.sourceforge.net/Venis_IX

8. For the PortableApps.com build, additionally install these three
   utilities:

   http://portableapps.com/apps/development/nsis_portable (Unicode version)
   http://portableapps.com/apps/development/portableapps.com_installer
   http://portableapps.com/apps/development/portableapps.com_launcher

   These tools default to installing in ~/Desktop, but I personally
   put them in ~/Apps. Be sure to put them all in the same folder.


Building the application icon
-----------------------------

If the Zim application icon has changed, you must manually rebuild it
before running the Windows build scripts. Otherwise skip this section.

1. Using IcoFX (free software), import Zim's zim16.png, zim32.png, and
zim48.png to a fresh ICO file.

2. Using InkScape, convert zim48.svg to a temporary 256x256 PNG file
and import that into the same ICO file as step 1.

3. Save as ./icons/zim.ico .


Building Zim
------------

1. Add your Python root folder and your "GTK+ Bundle\bin" folder to
   your $PATH environment variable.

2. At the command prompt, CD into the Zim project's root folder.

3. Run "python.exe windows\build_win32.py" in the command prompt.
   NOTE: Sometimes I get "Access denied" errors in this step. Closing
   all windows except the command prompt usually helps.

4. Make sure it built okay by running
   ".\windows\build\ZimDesktopWikiPortable\App\ZimDesktopWiki\zim.exe"


Packaging the Regular Installer
-------------------------------

1. Build zim.exe (see steps above).

2. Run "./windows/create-zim-setup.nsi".

3. Find its output in "./dist/Zim-setup-*.exe" and test it.


Packaging the PortableApps.com Installer
----------------------------------------

1. Build zim.exe (see steps above).

2. Run the PortableApps.comLauncher app on the folder
   "./windows/build/ZimDesktopWikiPortable".

2a. Test the launcher built in "./windows/build/ZimDesktopWikiPortable".

3. Run the PortableApps.comInstaller app on the folder
   "./windows/build/ZimDesktopWikiPortable".

4. You will find the installer named as
   "./windows/build/ZimDesktopWikiPortable_VERSION.paf.exe"/
