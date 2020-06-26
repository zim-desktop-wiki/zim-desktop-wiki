# Windows Installer build scripts

We use msys2 any PyInstaller for creating the Windows installer.

- Download msys2 64-bit from https://www.msys2.org
- Follow instructions on https://msys2.org
- Execute `C:\msys64\mingw64.exe`
- Run `pacman -Syu` to update packages
- Run `pacman -S git` to install git
- Run `git clone https://github.com/zim-desktop-wiki/zim-desktop-wiki.git`
- Change directory with `cd zim-desktop-wiki/windows`
- Execute `./build.sh` to install all the needed dependencies and build the installer in the `dist` directory.
