How to Build Zim Destkop Wiki on Windows
========================================


Overview
--------

To build Zim for Windows, you must install all the requirements listed below. Then follow the steps in the "Building Zim" section.


Requirements
------------

1. Install Python 2.7 for Windows from

http://www.python.org/download/

Note: Zim has not yet been ported to Python 3.

2. Install the py2exe library from

http://sourceforge.net/projects/py2exe/files/

3. Install PyGTK All-in-One from

http://ftp.gnome.org/pub/GNOME/binaries/win32/pygtk/2.24/pygtk-all-in-one-2.24.2.win32-py2.7.msi

Be sure to include "PyGTKSourceView" when you run the installer.

4. Jpeg for Windows

http://gnuwin32.sourceforge.net/packages/jpeg.htm

Get jpeg62.dll and put it in ./windows/lib .

5. Install PyWin32 from

http://sourceforge.net/projects/pywin32/files/pywin32/

6. Install NSIS 3.x from

http://nsis.sourceforge.net/Download

6a. You will also want to download Venis IX if you want to edit the NSIS script in an IDE. (The script is a plain text file, though, if you don't want to use an IDE.)
http://nsis.sourceforge.net/Venis_IX


Building the application icon
-----------------------------

If the Zim application icon has changed, you must manually rebuild it before running the Windows build scripts. Otherwise skip this section.

1. Using IcoFX (free software), import Zim's zim16.png, zim32.png, and zim48.png to a fresh ICO file.

2. Using InkScape, convert zim48.svg to a temporary 256x256 PNG file and import that into the same ICO file as step 1.

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
   ".\windows\build\ZimDesktopWiki\App\ZimDesktopWiki\zim.exe"


Packaging the Installer
-------------------------------

1. Build zim.exe (see steps above).

2. Run "./windows/create-zim-setup.nsi".

3. Find its output in "./dist/Zim-setup-*.exe" and test it.
