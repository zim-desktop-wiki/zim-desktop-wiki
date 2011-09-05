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

3. Install PyCairo, PyGObject, and PyGTK from

   http://ftp.gnome.org/pub/GNOME/binaries/win32/pygtk/[newest version]/pygtk-all-in-one-VERSION.win32-pyVERSION.msi

4. Jpeg for Windows

   http://gnuwin32.sourceforge.net/packages/jpeg.htm

   Get jpeg62.dll and put it in ./windows .

5. Install Bazaar using the PYTHON-BASED installer from

   http://wiki.bazaar.canonical.com/WindowsDownloads

   The build script depends on Python Bazaar.

6. Install NSIS from

   http://nsis.sourceforge.net/Download

6a. You will also want to download Venis IX if you want to edit the 
    NSIS script in an IDE. (The script is a plain text file, though, 
    if you don't want to use an IDE.) 
    http://nsis.sourceforge.net/Venis_IX

7. For the PortableApps.com build, additionally install these three
   utilities:

   http://portableapps.com/apps/development/nsis_portable (Unicode version)
   http://portableapps.com/apps/development/portableapps.com_installer
   http://portableapps.com/apps/development/portableapps.com_launcher

   These tools default to installing in ~/Desktop, but I personally
   put them in ~/Apps. Be sure to put them all in the same folder.


Building Zim
------------

1. Look at "windows\env.cmd" -- make sure that your path to the Python
   folder is correct. Or if Python is already in your system $PATH,
   you can skip this step.

2. At the command prompt, CD into the Zim project's root folder.

3. Run "windows\env.cmd" in the command prompt to initialize your
   $PATH environment variable.

4. Run "python.exe windows\build_win32.py" in the command prompt.

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
