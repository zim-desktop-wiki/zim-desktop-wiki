# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import gobject
import gtk

from zim.plugins import PluginClass
from zim.config import data_file, config_file
from zim.notebook import get_notebook_list, NotebookInfo, NotebookInfoList
from zim.gui.widgets import gtk_window_set_default_icon


# Try if we are on Ubunutu with app-indicator support
try:
	import appindicator
except ImportError:
	appindicator = None



def main(daemonproxy, *args):
	assert daemonproxy is None, 'Not (yet) intended as daemon child'

	import os
	assert not os.name == 'nt', 'RPC not supported on windows'

	# HACK to start daemon from separate process
	# we are not allowed to fork since we already loaded gtk
	from subprocess import check_call
	from zim import ZIM_EXECUTABLE
	check_call([ZIM_EXECUTABLE, '--daemon'])

	preferences = config_file('preferences.conf')['TrayIconPlugin']
	preferences.setdefault('classic', False)

	from zim.daemon import DaemonProxy
	if appindicator and not preferences['classic']:
		klass = 'zim.plugins.trayicon.AppIndicatorTrayIcon'
	else:
		klass = 'zim.plugins.trayicon.DaemonTrayIcon'
	DaemonProxy().run(klass, 'TrayIcon')


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
		return [('GTK >= 2.10',gtk.gtk_version >= (2, 10, 0))]

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		self._trayicon_class = None
		self.icon = None
		self.proxyobject = None

	def initialize_ui(self, ui):
		if self.ui.ui_type == 'gtk':
			self.connect_trayicon()
			self.ui.hideonclose = True

	def connect_trayicon(self):
			klass = self.get_trayicon_class()
			if issubclass(klass, DaemonTrayIconMixin):
				string = 'zim.plugins.trayicon.' + klass.__name__
				from zim.daemon import DaemonProxy
				self.proxyobject = DaemonProxy().get_object(string, 'TrayIcon')
					# getting the object implicitly starts it, if it didn't exist yet
			else:
				self.icon = klass(self.ui)

			self._trayicon_class = klass

	def get_trayicon_class(self):
			if self.ui.usedaemon and not self.preferences['standalone']:
				if appindicator and not self.preferences['classic']:
					return AppIndicatorTrayIcon
				else:
					return DaemonTrayIcon
			else:
				return StandAloneTrayIcon

	def disconnect(self):
		self.disconnect_trayicon()
		self.ui.hideonclose = False

	def disconnect_trayicon(self):
		if self.icon:
			self.icon.set_property('visible', False)
			self.icon = None

		if self.proxyobject:
			self.proxyobject.quit()

	def do_preferences_changed(self):
		if self.ui.ui_type == 'gtk':
			klass = self.get_trayicon_class()
			if not klass is self._trayicon_class:
				self.disconnect_trayicon()
				self.connect_trayicon()


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
		dialog = QuickNoteDialog(None, {})
		dialog.show()


class StatusIconTrayIcon(TrayIconBase, gtk.StatusIcon):
	'''Base class for a tray icon based on gtk.StatusIcon'''

	def __init__(self):
		gtk.StatusIcon.__init__(self)
		self.set_from_icon_name('zim')
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

	def __init__(self, ui):
		StatusIconTrayIcon.__init__(self)
		self.ui = ui
		self.ui.connect('open-notebook', self.on_open_notebook)

	def on_open_notebook(self, ui, notebook):
		# TODO hook this to finalize_notebook in the plugin
		self.set_tooltip(notebook.name)
		if notebook.icon:
			self.set_from_file(notebook.icon)

	def list_open_notebooks(self):
		# No daemon, so we only know one open notebook
		notebook = self.ui.notebook
		info = NotebookInfo(notebook.uri, name=notebook.name)
		info.active = True
		return [ info ]

	def do_activate_notebook(self, uri):
		# Open a notebook using the ui object
		if uri == self.ui.notebook.uri:
			self.ui.toggle_present()
		else:
			self.ui.open_notebook(uri)
			# Can not toggle, so just open it

	def do_quit(self):
		self.ui.quit()


class DaemonTrayIconMixin(object):
	'''Mixin class for using the tray icon in combination with the
	daemon process. Sub classes should run as a separate child process.
	'''

	def __init__(self):
		from zim.daemon import DaemonProxy
		self.daemon = DaemonProxy()

	def main(self):
		# Set window icon in case we open the notebook dialog
		gtk_window_set_default_icon()
		gtk.main()

	def quit(self):
		gtk.main_quit()

	def list_open_notebooks(self):
		for uri in self.daemon.list_notebooks():
			info = NotebookInfo(uri)
			info.active = True
			yield info

	def do_activate_notebook(self, uri):
		self.daemon.get_notebook(uri).toggle_present()

	def do_quit(self):
		self.daemon.quit()


class DaemonTrayIcon(DaemonTrayIconMixin, StatusIconTrayIcon):
	'''Trayicon using the daemon and based on gtk.StatusIcon'''

	def __init__(self):
		StatusIconTrayIcon.__init__(self)
		DaemonTrayIconMixin.__init__(self)


class AppIndicatorTrayIcon(DaemonTrayIconMixin, TrayIconBase):
	'''Trayicon using the daemon and based on appindicator'''

	def __init__(self):
		DaemonTrayIconMixin.__init__(self)

		self.appindicator = appindicator.Indicator(
			'zim-desktop-wiki', 'zim', appindicator.CATEGORY_APPLICATION_STATUS)
		self.appindicator.set_status(appindicator.STATUS_ACTIVE)

		self.on_notebook_list_changed()
		self.daemon.connect_object('notebook-list-changed', self)

	def on_notebook_list_changed(self):
		menu = self.get_trayicon_menu()
		menu.show_all()
		self.appindicator.set_menu(menu)

