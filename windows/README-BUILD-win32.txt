How to Build pyzim on Windows


Requirements

1. Install Python 2.6 or greater for Windows from
   http://www.python.org/download/

   Note: Python version must be 2.6 or greater, but less than 3.0

2. Install the py2exe library from
   http://sourceforge.net/projects/py2exe/files/

3. Download the latest GTK+ bundle for Windows from
   http://ftp.gnome.org/pub/GNOME/binaries/win32/gtk+/[newest version]/gtk+-bundle*.zip
   Extract that Zip file to
   C:\Program Files\Common Files\GTK\2.22

4. Install PyCairo, PyGObject, and PyGTK from
   http://ftp.gnome.org/pub/GNOME/binaries/win32/pycairo/[newest version]/pycairo-*.win32*.exe
   http://ftp.gnome.org/pub/GNOME/binaries/win32/pygobject/[newest version]/pygobject-*.win32*.exe
   http://ftp.gnome.org/pub/GNOME/binaries/win32/pygtk/[newest version]/pygtk-*.win32*.exe

5. Jpeg for Windows
   http://gnuwin32.sourceforge.net/packages/jpeg.htm
   Get jpeg62.dll and put it in ./windows .

6. Install Bazaar using the PYTHON-BASED installer from
   http://wiki.bazaar.canonical.com/WindowsDownloads
   The build script depends on Bazaar.

7. Install NSIS from
   http://nsis.sourceforge.net/Download

7a. You will also want to download Venis IX if you want to edit the 
    NSIS script in an IDE. (The script is a plain text file, though, 
    if you don't want to use an IDE.) 
    http://nsis.sourceforge.net/Venis_IX


Building Zim

1. Look at "windows\env.cmd" -- make sure that your paths to GTK and 
   Python binaries are correct.

2. Run "windows\env.cmd" to initialize your $PATH environment variable..

3. Run "python.exe windows\build_win32.py".

   Note: If you installed GTK to another path than suggested, you must change it also in the
         file build_win32.py.

4. Make sure it built okay by running ".\windows\build\zim.exe".


Packaging the Installer

1. Build zim.exe (see steps above)

2. Create or modify ./windows/version-and-date.nsi . (Fill in the appropriate values.)

   !define VER "version_number_goes_here"
   !define BUILDDATE "yyyy-mm-dd"

3. Run ./windows/create-zim-setup.nsi .

4. Find its output in ./dist/Zim-setup-*.exe and test it.
