# -*- coding: utf-8 -*-

# Copyright 2009-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import gobject
import gtk

import logging

from zim.plugins import PluginClass, WindowExtension
from zim.config import data_file, ConfigManager
from zim.command import Command
from zim.ipc import start_server_if_not_running, ServerProxy, RemoteObject
from zim.notebook import get_notebook_list, NotebookInfo, NotebookInfoList
from zim.gui.widgets import gtk_window_set_default_icon


# Try if we are on Ubunutu with app-indicator support
try:
	import appindicator
except ImportError:
	appindicator = None


logger = logging.getLogger('zim.plugins.trayicon')


class TrayIconPluginCommand(Command):
	'''Class to handle "zim --plugin trayicon" '''

	def run(self):
		start_server_if_not_running()

		config = ConfigManager()
		preferences = config.get_config_dict('preferences.conf')['TrayIconPlugin']
		preferences.setdefault('classic', False)

		if appindicator and not preferences['classic']:
			obj = RemoteObject('zim.plugins.trayicon.AppIndicatorTrayIcon')
		else:
			obj = RemoteObject('zim.plugins.trayicon.DaemonTrayIcon')

		server = ServerProxy()
		if not server.has_object(obj):
			server.init_object(obj)



class TrayIconPlugin(PluginClass):

	plugin_info = {
		'name': _('Tray Icon'), # T: plugin name
		'description': _('''\
This plugin adds a tray icon for quick access.

This plugin depends on Gtk+ version 2.10 or newer.

This is a core plugin shipping with zim.
'''), # T: plugin description
		'author': 'Jaap Karssenberg',
		'help': 'Plugins:Tray Icon',
	}

	plugin_preferences = (
		# key, type, label, default
		('classic', 'bool', _('Classic trayicon,\ndo not use new style status icon on Ubuntu'), False), # T: preferences option
		('standalone', 'bool', _('Show a separate icon for each notebook'), False), # T: preferences option
	)

	@classmethod
	def check_dependencies(klass):
		version_ok = (gtk.gtk_version >= (2, 10, 0))
		return (version_ok, [
			('GTK >= 2.10', version_ok, True),
			('Unity appindicator', bool(appindicator), False),
		])

	def __init__(self, config=None):
		PluginClass.__init__(self, config)
		self.preferences.connect('changed', self.on_preferences_changed)
		self.on_preferences_changed(self.preferences)

	def on_preferences_changed(self, preferences):
		klass = self.get_extension_class()
		self.set_extension_class('MainWindow', klass)

	def get_extension_class(self):
		import zim.ipc
		if zim.ipc.in_child_process() \
		and not self.preferences['standalone']:
			if appindicator and not self.preferences['classic']:
				extension = AppIndicatorMainWindowExtension
			else:
				extension = DaemonMainWindowExtension
		else:
			extension = StandAloneMainWindowExtension
		logger.debug('Trayicon using class: %s', extension.__name__)
		return extension


class TrayIconBase(object):
	'''Base class for the zim tray icon.
	Contains code to create the tray icon menus.
	'''

	def get_trayicon_menu(self):
		'''Returns the main 'tray icon menu'''
		menu = gtk.Menu()

		item = gtk.MenuItem(_('_Quick Note...')) # T: menu item in tray icon menu
		item.connect_object('activate', self.__class__.do_quick_note, self)
		menu.append(item)

		menu.append(gtk.SeparatorMenuItem())

		notebooks = self.list_all_notebooks()
		self.populate_menu_with_notebooks(menu, notebooks)

		item = gtk.MenuItem('  '+_('_Other...'))  # Hack - using '  ' to indent visually
			# T: menu item in tray icon menu
		item.connect_object('activate', self.__class__.do_open_notebook, self)
		menu.append(item)

		menu.append(gtk.SeparatorMenuItem())

		item = gtk.MenuItem(_('_Quit')) # T: menu item in tray icon menu
		item.connect_object('activate', self.__class__.do_quit, self)
		menu.append(item)

		return menu

	def list_open_notebooks(self):
		'''Returns a list of open notebook.

		This method is to be implemented in child classes.

		@returns: a list of L{NotebookInfo} objects
		'''
		# should return (name, uri) pairs
		raise NotImplementedError

	def list_all_notebooks(self):
		'''Returns a list of all notebooks known in the current context

		This method mixes notebooks from L{list_open_notebooks()} with
		input from L{get_notebook_list()}. Open notebooks will have
		the C{active} attribute set.

		@returns: a list of L{NotebookInfo} objects
		'''
		uris = set()
		notebooks = [info for info in get_notebook_list()]
		for info in self.list_open_notebooks():
			if info in notebooks:
				# info from notebook list is updated already
				i = notebooks.index(info)
				notebooks[i].active = True
			else:
				info.update()
				info.active = True
				notebooks.append(info)

		for info in notebooks:
			if not info.active:
				info.active = False # None -> False

		return notebooks

	def populate_menu_with_notebooks(self, menu, notebooks):
		'''Populate a menu with a list of notebooks'''
		# TODO put checkbox behind open notebooks when we run in daemon mode
		item = gtk.MenuItem(_('Notebooks')) # T: menu item in tray icon menu
		item.set_sensitive(False)
		menu.append(item)

		if isinstance(notebooks, NotebookInfoList):
			notebooks = [info for info in notebooks] # copy

		notebooks.sort(key=lambda info: info.name)

		for info in notebooks:
			#~ print '>>>', info
			item = gtk.MenuItem('  ' + info.name)
				# Hack - using '  ' to indent visually
			if info.active:
				child = item.get_child()
				if isinstance(child, gtk.Label):
					# FIXME this doesn't seem to work in Ubuntu menu :(
					child.set_markup('  <b>' + info.name + '</b>')
						# Hack - using '  ' to indent visually
			item.connect('activate', lambda o, u: self.do_activate_notebook(u), info.uri)
			menu.append(item)

	def do_activate_notebook(self, uri):
		'''Open a specific notebook.
		To be overloaded in child class.
		'''
		raise NotImplementedError

	def do_quit(self):
		'''Quit zim.
		To be overloaded in child class.
		'''
		raise NotImplementedError

	def do_open_notebook(self):
		'''Opens the notebook dialogs'''
		from zim.gui.notebookdialog import NotebookDialog
		NotebookDialog.unique(self, self, callback=self.do_activate_notebook).show()

	def do_quick_note(self):
		'''Show the dialog from the quicknote plugin'''
		from zim.plugins.quicknote import QuickNoteDialog
		dialog = QuickNoteDialog(None)
		dialog.show()


class StatusIconTrayIcon(TrayIconBase, gtk.StatusIcon):
	'''Base class for a tray icon based on gtk.StatusIcon'''

	def __init__(self):
		gtk.StatusIcon.__init__(self)

		icon_theme = gtk.icon_theme_get_default()
		if icon_theme.has_icon('zim-panel'):
		    self.set_from_icon_name('zim-panel')
		else:
			icon = data_file('zim.png').path
			self.set_from_file(icon)

		self.set_tooltip(_('Zim Desktop Wiki')) # T: tooltip for tray icon
		self.connect('popup-menu', self.__class__.do_popup_menu)

	def do_activate(self):
		open_notebooks = list(self.list_open_notebooks())
		if len(open_notebooks) == 0:
			# No open notebooks, open default or prompt full list
			notebooks = get_notebook_list()
			if notebooks.default:
				self.do_activate_notebook(notebooks.default)
			else:
				self.do_popup_menu_notebooks(notebooks)
		elif len(open_notebooks) == 1:
			# Only one open notebook - present it
			self.do_activate_notebook(open_notebooks[0].uri)
		else:
			# Let the user choose from the open notebooks
			self.do_popup_menu_notebooks(open_notebooks)

	def do_popup_menu_notebooks(self, list, button=1, activate_time=0):
		menu = gtk.Menu()
		self.populate_menu_with_notebooks(menu, list)
		menu.show_all()
		menu.popup(None, None, gtk.status_icon_position_menu, button, activate_time, self)

	def do_popup_menu(self, button=3, activate_time=0):
		#~ print '>>', button, activate_time
		menu = self.get_trayicon_menu()
		menu.show_all()
		menu.popup(None, None, gtk.status_icon_position_menu, button, activate_time, self)

# Need to register classes overriding gobject signals
gobject.type_register(StatusIconTrayIcon)


class StandAloneTrayIcon(StatusIconTrayIcon):
	'''This class defines the tray icon used for a
	single stand-alone notebook.
	'''

	def __init__(self, window):
		StatusIconTrayIcon.__init__(self)
		self.window = window
		self.notebook = self.window.ui.notebook # XXX
		self.set_tooltip(self.notebook.name)
		if self.notebook.icon:
			self.set_from_file(self.notebook.icon)

	def list_open_notebooks(self):
		# No daemon, so we only know one open notebook
		info = NotebookInfo(self.notebook.uri, name=self.notebook.name)
		info.active = True
		return [ info ]

	def do_activate_notebook(self, uri):
		# Open a notebook using the ui object
		if uri == self.notebook.uri:
			self.window.ui.toggle_present() # XXX
		else:
			self.window.ui.open_notebook(uri) # XXX
			# Can not toggle, so just open it

	def do_quit(self):
		self.window.ui.quit() # XXX


class DaemonTrayIconMixin(object):
	'''Mixin class for using the tray icon in combination with the
	background process. Sub classes should run as a separate child process.
	'''

	def __init__(self):
		self.server = ServerProxy()

	def main(self):
		# Set window icon in case we open the notebook dialog
		gtk_window_set_default_icon()
		gtk.main()

	def quit(self):
		gtk.main_quit()

	def list_open_notebooks(self):
		for uri in self.server.list_notebooks():
			info = NotebookInfo(uri)
			info.active = True
			yield info

	def do_activate_notebook(self, uri):
		self.server.get_notebook(uri).toggle_present()

	def do_quit(self):
		self.server.quit()


class DaemonTrayIcon(DaemonTrayIconMixin, StatusIconTrayIcon):
	'''Trayicon using the daemon and based on gtk.StatusIcon'''

	def __init__(self):
		StatusIconTrayIcon.__init__(self)
		DaemonTrayIconMixin.__init__(self)


class AppIndicatorTrayIcon(DaemonTrayIconMixin, TrayIconBase):
	'''Trayicon using the daemon and based on appindicator'''

	def __init__(self):
		DaemonTrayIconMixin.__init__(self)

		# Note that even though we specify the icon "zim", the
		# ubuntu appindicator framework will first check for an icon
		# "zim-panel". This way it finds the mono color icons.
		self.appindicator = appindicator.Indicator(
			'zim-desktop-wiki', 'zim', appindicator.CATEGORY_APPLICATION_STATUS)
		self.appindicator.set_status(appindicator.STATUS_ACTIVE)

	def main(self):
		ServerProxy().connect('notebook-list-changed', self)
		self.on_notebook_list_changed()
		DaemonTrayIconMixin.main(self)

	def on_notebook_list_changed(self):
		menu = self.get_trayicon_menu()
		menu.show_all()
		self.appindicator.set_menu(menu)



class StandAloneMainWindowExtension(WindowExtension):

	def __init__(self, plugin, window):
		WindowExtension.__init__(self, plugin, window)
		self.window.ui.hideonclose = True # XXX
		self.icon = StandAloneTrayIcon(self.window)

	def teardown(self):
		self.window.ui.hideonclose = False # XXX
		self.icon.set_property('visible', False)
		self.icon = None


class DaemonMainWindowExtension(WindowExtension):

	trayiconclass = DaemonTrayIcon

	def __init__(self, plugin, window):
		WindowExtension.__init__(self, plugin, window)
		self.window.ui.hideonclose = True # XXX
		self.proxyobject = None

		obj = RemoteObject('zim.plugins.trayicon.' + self.trayiconclass.__name__)
		server = ServerProxy()
		self.proxyobject = server.get_proxy(obj)
			# getting the object implicitly starts it, if it didn't exist yet

	def on_destroy(self, window):
		pass # Maybe other processes still running - wait for daemon

	def teardown(self):
		self.window.ui.hideonclose = False # XXX
		self.proxyobject.quit()


class AppIndicatorMainWindowExtension(DaemonMainWindowExtension):

	trayiconclass = AppIndicatorTrayIcon
