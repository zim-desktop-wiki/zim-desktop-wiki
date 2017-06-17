How to Build Zim Destkop Wiki on Windows
========================================


Overview
--------

To build Zim for Windows, you must install all the requirements listed below. Then follow the steps in the "Building Zim" section.


Requirements
------------

1. Install Python 2.7 for Windows from

http://www.python.org/download/

During installation, be sure to add the non-default option "Add python.exe to Path."

NOTE: Zim has not yet been ported to Python 3.

2. Install the py2exe library from

http://sourceforge.net/projects/py2exe/files/

3. Install PyGTK All-in-One from

http://ftp.gnome.org/pub/GNOME/binaries/win32/pygtk/2.24/pygtk-all-in-one-2.24.2.win32-py2.7.msi

Be sure to include "PyGTKSourceView" and "PyRsvg" when you run the installer.

4. Jpeg for Windows

http://gnuwin32.sourceforge.net/packages/jpeg.htm

Get jpeg62.dll and put it in ./windows/lib .

5. Install PyWin32 from

http://sourceforge.net/projects/pywin32/files/pywin32/

6. Install the Visual C++ 2008 Redistributable Package (x86) from

http://www.microsoft.com/en-us/download/details.aspx?id=29

Be sure to use the November 2007 version from that URL, not the SP1 version. This one goes with Python 2.7.

7. Install NSIS 3.x from

http://nsis.sourceforge.net/Download

7a. You will also want to download Venis IX if you want to edit the NSIS script in an IDE. (The script is a plain text file, though, if you don't want to use an IDE.)

http://nsis.sourceforge.net/Venis_IX


Building the Application Icon
-----------------------------

If the Zim application icon has changed, you must manually rebuild it before running the Windows build scripts. Otherwise skip this section.

1. Using IcoFX (version 2.x, the old free version), import Zim's zim16.png, zim32.png, and zim48.png to a fresh ICO file.

2. Using InkScape, convert zim48.svg to a temporary 256x256 PNG file and import that into the same ICO file as step 1.

3. Save as .\icons\zim.ico .


Building Zim
------------

1. At the command prompt, CD into the Zim project's root folder.

2. Run "python windows\build_win32.py".

NOTE: Sometimes I get "Access denied" errors in this step. Closing all windows except the command prompt usually helps.

3. Make sure it built okay by running ".\windows\build\ZimDesktopWiki\zim.exe"


Packaging the Installer
-----------------------

1. Build zim.exe (see steps above).

2. At the command prompt, CD into the Zim Project's root folder.

3. Run "python windows\make_installer_win32.py" to create the desktop installer.

4. Run "python windows\make_installer_win32_portable.py" to create the portable installer.

5. Find the NSIS installers in ".\dist\zim-desktop-wiki-*.exe" and test them.
