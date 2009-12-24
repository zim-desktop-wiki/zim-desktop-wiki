# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

import gobject
import gtk

from zim.plugins import PluginClass
from zim.config import data_file
from zim.notebook import get_notebook_list


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

	#~ plugin_preferences = (
		# key, type, label, default
		#~ ('standalone', 'bool', _('Show a separate tray icon for each notebook'), False), # T: preferences option
	#~ )

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		self.icon = None
		self.proxyobject = None
		if self.ui.ui_type == 'gtk':
			if ui.usedaemon:
			#~ and not self.preferences['standalone']
				from zim.daemon import DaemonProxy
				self.proxyobject = DaemonProxy().get_object(
					'zim.plugins.trayicon.DaemonTrayIcon', 'TrayIcon')
				self.ui.hideonclose = True
			else:
				self.icon = StandAloneTrayIcon(self.ui)

	def disconnect(self):
		if self.icon:
			self.icon.set_visible(False)
			self.icon = None

		if self.proxyobject:
			self.proxyobject.quit()

		self.ui.hideonclose = False

	#~ def do_preferences_changed(self):
		#~ pass


class TrayIcon(gtk.StatusIcon):
	'''Base class for the zim tray icon'''

	def __init__(self):
		gtk.StatusIcon.__init__(self)
		self.set_from_file(data_file('zim.png').path)
		self.set_tooltip(_('Zim Desktop Wiki')) # T: tooltip for tray icon
		self.connect('popup-menu', self.__class__.do_popup_menu)

	def do_activate(self):
		notebooks = list(self._list_open_notebooks())
		if len(notebooks) == 0:
			# No open notebooks, prompt full list
			self.do_popup_menu(button=1)
		elif len(notebooks) == 1:
			# Only one open notebook - present it
			self.do_present(notebooks[0][1])
		else:
			# Let the user choose from the open notebooks
			self.do_popup_menu_open_notebooks(list=notebooks)

	def _list_open_notebooks(self):
		raise NotImplementedError

	def do_popup_menu_open_notebooks(self, button=1, activate_time=0, list=None):
		if list is None:
			list = self._list_open_notebooks()

		menu = gtk.Menu()
		self._populate_menu_notebooks(menu, list)
		menu.show_all()
		menu.popup(None, None, gtk.status_icon_position_menu, button, activate_time, self)

	def do_popup_menu(self, button=3, activate_time=0):
		menu = gtk.Menu()

		list = get_notebook_list()
		self._populate_menu_notebooks(menu, list.get_names())

		item = gtk.MenuItem(_('_Other...')) # T: menu item in tray icon menu
		item.connect_object('activate', self.__class__.do_open_notebook, self)
		menu.append(item)

		menu.append(gtk.SeparatorMenuItem())

		item = gtk.MenuItem(_('_Quit')) # T: menu item in tray icon menu
		item.connect_object('activate', self.__class__.do_quit, self)
		menu.append(item)

		menu.show_all()
		menu.popup(None, None, gtk.status_icon_position_menu, button, activate_time, self)

	def _populate_menu_notebooks(self, menu, list):
		# Populate the menu with a list of notebooks
		for name, uri in list:
			#~ print '>>>', name, uri
			item = gtk.MenuItem(name)
			item.connect('activate', lambda o, u: self.do_present(u), uri)
			menu.append(item)

	def do_present(self, uri):
		raise NotImplementedError

	def do_quit(self):
		raise NotImplementedError

	def do_open_notebook(self):
		from zim.gui.notebookdialog import NotebookDialog
		NotebookDialog.unique(self, self, callback=self.do_present).show()


# Need to register classes defining gobject signals
gobject.type_register(TrayIcon)


class StandAloneTrayIcon(TrayIcon):
	'''This class defines the tray icon used for a
	single stand-alone notebook.
	'''

	def __init__(self, ui):
		TrayIcon.__init__(self)
		self.ui = ui
		self.ui.connect('open-notebook', self.on_open_notebook)

	def on_open_notebook(self, ui, notebook):
		self.set_tooltip(notebook.name)
		if notebook.icon:
			self.set_from_file(notebook.icon)

	def _list_open_notebooks(self):
		notebook = self.ui.notebook
		return [(notebook.name, notebook.uri)]

	def do_present(self, uri):
		if uri == self.ui.notebook.uri:
			self.ui.present()
		else:
			self.ui.open_notebook(uri)

	def do_quit(self):
		self.ui.quit()


class DaemonTrayIcon(TrayIcon):
	'''This class defines the tray icon used in combination with the
	daemon process. It runs as a separate child process.
	'''

	def __init__(self):
		from zim.daemon import DaemonProxy
		TrayIcon.__init__(self)
		self.daemon = DaemonProxy()

	def main(self):
		# Set window icon in case we open the notebook dialog
		icon = data_file('zim.png').path
		gtk.window_set_default_icon(gtk.gdk.pixbuf_new_from_file(icon))

		gtk.main()

	def quit(self):
		gtk.main_quit()

	def _list_open_notebooks(self):
		list = get_notebook_list()
		for uri in self.daemon.list_notebooks():
			name = list.get_name(uri) or uri
			yield name, uri

	def do_present(self, uri):
		self.daemon.get_notebook(uri).present()

	def do_quit(self):
		self.daemon.quit()

