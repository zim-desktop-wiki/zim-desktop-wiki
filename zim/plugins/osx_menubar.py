
# Copyright 2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# To install this plugin:
# 1. in zim go to the preferences dialog, plugins tab
# 2. click "open plugin folder"
#    this should open ~/.local/share/zim/plugins or similar
# 3. copy this file to the folder presented
# 4. restart zim (quit and then start again, don't just close the window)
# 5. go back to the plugins tab, plugin should now show up

# TODO: at this moment the plugin does not restore the menubar if disabled,
#       requires a restart of zim. If the plugin fails but the menubar is gone,
#       need to manually edit "preferences.conf" to remove the plugin; then
#       restart zim.

# TODO: test initialization of global items (about, prefs, ..)

# TODO: hide "help" menu from the menubar ?

from gi.repository import Gtk

from zim.gui.mainwindow import MainWindowExtension

from zim.plugins import PluginClass

try:
	from gi.repository import GtkosxApplication
except ImportError:
	GtkosxApplication = None


if False: #pragma: no cover

	# This code defines a "mock" object for testing this plugin on systems
	# that do not actually have "GtkosxApplication", should be disabled for
	# production code.
	# Switch by setting above statement to "True" or "False"

	class MockOSXAppModule(object):

		@staticmethod
		def Application():
			return MockOSXAppObject()

	class MockOSXAppObject(object):

		def __getattr__(self, name):
			def method(*a):
				print(">>> OSX call:", name, a)
			return method

	if GtkosxApplication is None:
		GtkosxApplication = MockOSXAppModule


if GtkosxApplication:
	# Global for all notebooks / windows, once per process
	_global_osx_application = GtkosxApplication.Application()
	_global_items_initialized = False
else:
	_global_osx_application = None
	_global_items_initialized = False



class OSXmenubarPlugin(PluginClass):
	# This object just provides some information for the plugin manager
	# no real logic happening here.

	plugin_info = {
		'name': _('macOS Menubar'), # T: plugin name
		'description': _('This plugin provides a macOS menubar for zim.'), # T: plugin description
		'author': 'Brecht Machiels, Jaap Karssenberg',
		'help': 'Plugins:macOS Menubar'
	}

	@classmethod
	def check_dependencies(klass):
		# "is_ok" must be True, else won't be able to select the plugin in
		# the plugin manager
		is_ok = GtkosxApplication is not None
		return is_ok, [('GtkosxApplication', is_ok, True)]



class OSXMenuBarMainWindowExtension(MainWindowExtension):
	# This object is created once for each "main window", this means once for
	# each notebook opened in zim. If this is the first window, also do
	# global intialization, else just capture the menubar and keep it ourselves.
	# We hook to the signal that a window has recieved focus and on that signal
	# insert the menubar for that window. So may change often when switching
	# windows.

	def __init__(self, plugin, window):
		MainWindowExtension.__init__(self, plugin, window)

		# Define OS X menu bar for this window and remove menubar from window
		self.menubar = self.window.menubar
		self.window._zim_window_main.remove(self.menubar) # XXX - use private arg, should patch Window.remove() instead ...

		# Define global items - one time action for process
		global _global_osx_application
		_global_osx_application.set_use_quartz_accelerators(False)

		quit = self.window.uimanager.get_widget('/menubar/file_menu/quit')
		quit.hide()

		_global_osx_application.set_menu_bar(self.menubar)
		help = self.window.uimanager.get_widget('/menubar/help_menu')
		_global_osx_application.set_help_menu(help)

		about = self.window.uimanager.get_widget('/menubar/help_menu/show_about')
		_global_osx_application.insert_app_menu_item(about, 0)

		prefs = self.window.uimanager.get_widget('/menubar/edit_menu/show_preferences')
		_global_osx_application.insert_app_menu_item(Gtk.SeparatorMenuItem(), 1)
		_global_osx_application.insert_app_menu_item(prefs, 2)
		_global_osx_application.insert_app_menu_item(Gtk.SeparatorMenuItem(), 3)

		_global_osx_application.ready()
