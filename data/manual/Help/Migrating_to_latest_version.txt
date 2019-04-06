Content-Type: text/x-zim-wiki
Wiki-Format: zim 0.4
Creation-Date: 2019-03-14T20:42:02+01:00

====== Migrating to latest version ======


===== Zim 0.69 to 0.70 =====

**Prerequisites**
Zim 0.70 depends on Gtk3 and python3, which means both Gtk and python dependencies have changed

**Plugins**
* Core features like the page index and the pathbar are now plugins. If they disappeared you can enable them through the preferences dialog.
* The "linkmap" plugin now depends on the "xdot" application instead of a packaged version of the library.

**Accelmap**
You can define your own shortcuts at ''~/.config/zim/accelmap'' . Since Zim moved to Gtk3, you have to update your keybindigs accordingly (ex: ''<Actions>/MainWindowExtension'' to either ''<Actions>/BookmarksBarMainWindowExtension'' or ''<Actions>/VersionControlMainWindowExtension'' etc. or <Actions>/GtkInterface to either ''<Actions>/UIActions'' or ''<Actions>/GtkInterface/'' etc.). You may just delete the old ''accelmap'' file and let it regenerate.

**Profiles**
The support for configuration profiles is removed. Plugins like "journal" and "tasklist" now use notebook options for per-notebook configuration.
