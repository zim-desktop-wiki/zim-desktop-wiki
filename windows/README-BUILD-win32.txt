How to Build pyzim on Windows


Requirements

1. Install Python 2.6 or greater for Windows from
   http://www.python.org/download/

2. Download the latest GTK+ bundle for Windows from
   http://ftp.gnome.org/pub/GNOME/binaries/win32/gtk+/[newest version]/gtk+-bundle*.zip
   Extract that Zip file to
   C:\Program Files\Common Files\GTK\2.22

3. Install PyCairo, PyGObject, and PyGTK from
   http://ftp.gnome.org/pub/GNOME/binaries/win32/pycairo/[newest version]/pycairo-*.win32*.exe
   http://ftp.gnome.org/pub/GNOME/binaries/win32/pygobject/[newest version]/pygobject-*.win32*.exe
   http://ftp.gnome.org/pub/GNOME/binaries/win32/pygtk/[newest version]/pygtk-*.win32*.exe

4. Install Bazaar using the PYTHON-BASED installer from
   http://wiki.bazaar.canonical.com/WindowsDownloads
   The build script depends on Bazaar.

5. Install NSIS from
   http://nsis.sourceforge.net/Download

5a. You will also want to download Venis IX if you want to edit the 
    NSIS script in an IDE. (The script is a plain text file, though, 
    if you don't want to use an IDE.) 
    http://nsis.sourceforge.net/Venis_IX


Building Zim

1. Look at "windows\env.cmd" -- make sure that your paths to GTK and 
   Python binaries are correct.

2. Run "windows\env.cmd" to initialize your $PATH environment variable..

3. Run "python.exe windows\build_win32.py".

4. Make sure it built okay by running ".\windows\build\zim.exe".


Packaging the Installer

1. Build zim.exe (see steps above)

2. Create or modify ./windows/version-and-date.nsi . (Fill in the appropriate values.)

   !define VER "version_number_goes_here"
   !define BUILDDATE "yyyy-mm-dd"

3. Run ./windows/create-zim-setup.nsi .

4. Find its output in ./dist/Zim-setup-*.exe and test it.
