# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

import gobject
import gtk

from zim.plugins import PluginClass
from zim.config import data_file, config_file
from zim.notebook import get_notebook_list


def main(daemonproxy, *args):
	assert daemonproxy is None, 'Not (yet) intended as daemon child'

	import os
	assert not os.name == 'nt', 'RPC not supported on windows'

	# HACK to start daemon from separate process
	# we are not allowed to fork since we already loaded gtk
	from subprocess import check_call
	from zim import ZIM_EXECUTABLE
	check_call([ZIM_EXECUTABLE, '--daemon'])

	from zim.daemon import DaemonProxy
	DaemonProxy().run('zim.plugins.trayicon.DaemonTrayIcon', 'TrayIcon')


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
		('classic', 'bool', _('Classic trayicon, no menu on left click'), False), # T: preferences option
		#~ ('standalone', 'bool', _('Show a separate icon for each notebook'), False), # T: preferences option
	)

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		self.icon = None
		self.proxyobject = None

	def initialize_ui(self, ui):
		if self.ui.ui_type == 'gtk':
			if ui.usedaemon :
			#~ and not self.preferences['standalone']:
				from zim.daemon import DaemonProxy
				self.proxyobject = DaemonProxy().get_object(
					'zim.plugins.trayicon.DaemonTrayIcon', 'TrayIcon')
			else:
				self.icon = StandAloneTrayIcon(self.ui, self.preferences)

			self.ui.hideonclose = True

	@classmethod
	def check_dependencies(klass):
		return [('GTK >= 2.10',gtk.gtk_version >= (2, 10, 0))]

	def disconnect(self):
		if self.icon:
			self.icon.set_visible(False)
			self.icon = None

		if self.proxyobject:
			self.proxyobject.quit()

		self.ui.hideonclose = False

	def do_preferences_changed(self):
		if self.proxyobject:
			self.proxyobject.on_preferences_changed(self.preferences)


class TrayIcon(gtk.StatusIcon):
	'''Base class for the zim tray icon'''

	def __init__(self):
		gtk.StatusIcon.__init__(self)
		self.set_from_file(data_file('zim.png').path)
		self.set_tooltip(_('Zim Desktop Wiki')) # T: tooltip for tray icon
		self.connect('popup-menu', self.__class__.do_popup_menu)

	def do_activate(self):
		open_notebooks = list(self._list_open_notebooks())
		if self.preferences['classic']:
			# Classic behavior, try show crrent notebook
			if len(open_notebooks) == 0:
				# No open notebooks, open default or prompt full list
				notebooks = get_notebook_list()
				if notebooks.default:
					self.do_activate_notebook(notebooks.default)
				else:
					self.do_popup_menu_notebooks(notebooks)
			elif len(open_notebooks) == 1:
				# Only one open notebook - present it
				self.do_activate_notebook(open_notebooks[0][1])
			else:
				# Let the user choose from the open notebooks
				self.do_popup_menu_notebooks(open_notebooks)
		else:
			# New (app-indicator style) behavior, always show the menu
			# FIXME menu pops down immediatly on button-up -- need time ??
			self.do_popup_menu(button=1)

	def _list_open_notebooks(self):
		raise NotImplementedError

	def do_popup_menu_notebooks(self, list, button=1, activate_time=0):
		menu = gtk.Menu()

		item = gtk.MenuItem(_('Notebooks')) # T: menu item in tray icon menu
		item.set_sensitive(False)
		menu.append(item)

		self._populate_menu_notebooks(menu, list)
		menu.show_all()
		menu.popup(None, None, gtk.status_icon_position_menu, button, activate_time, self)

	def do_popup_menu(self, button=3, activate_time=0):
		#~ print '>>', button, activate_time
		menu = gtk.Menu()

		item = gtk.MenuItem(_('_Create Note...')) # T: menu item in tray icon menu
		item.connect_object('activate', self.__class__.do_create_note, self)
		menu.append(item)

		menu.append(gtk.SeparatorMenuItem())

		item = gtk.MenuItem(_('Notebooks')) # T: menu item in tray icon menu
		item.set_sensitive(False)
		menu.append(item)

		list = get_notebook_list()
		self._populate_menu_notebooks(menu, list.get_names())

		item = gtk.MenuItem('  '+_('_Other...'))  # Hack - using '  ' to indent visually
			# T: menu item in tray icon menu
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
		# TODO put checkbox behind open notebooks when we run in daemon mode
		for name, uri in list:
			#~ print '>>>', name, uri
			item = gtk.MenuItem('  ' + name) # Hack - using '  ' to indent visually
			item.connect('activate', lambda o, u: self.do_activate_notebook(u), uri)
			menu.append(item)

	def do_activate_notebook(self, uri):
		raise NotImplementedError

	def do_quit(self):
		raise NotImplementedError

	def do_open_notebook(self):
		from zim.gui.notebookdialog import NotebookDialog
		NotebookDialog.unique(self, self, callback=self.do_activate_notebook).show()

	def do_create_note(self):
		from zim.plugins.dropwindow import DropWindowDialog
		dialog = DropWindowDialog(None, {})
		dialog.show()


# Need to register classes defining gobject signals
gobject.type_register(TrayIcon)


class StandAloneTrayIcon(TrayIcon):
	'''This class defines the tray icon used for a
	single stand-alone notebook.
	'''

	def __init__(self, ui, preferences):
		TrayIcon.__init__(self)
		self.ui = ui
		self.ui.connect('open-notebook', self.on_open_notebook)
		self.preferences = preferences

	def on_open_notebook(self, ui, notebook):
		self.set_tooltip(notebook.name)
		if notebook.icon:
			self.set_from_file(notebook.icon)

	def _list_open_notebooks(self):
		notebook = self.ui.notebook
		return [(notebook.name, notebook.uri)]

	def do_activate_notebook(self, uri):
		if uri == self.ui.notebook.uri:
			self.ui.toggle_present()
		else:
			self.ui.open_notebook(uri)
			# Can not toggle, so just open it

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

		# init preferences
		preferences = config_file('preferences.conf')
		self.preferences = preferences['TrayIconPlugin']
		for key, type, label, default in TrayIconPlugin.plugin_preferences:
			self.preferences.setdefault(key, default)

	def main(self):
		# Set window icon in case we open the notebook dialog
		icon = data_file('zim.png').path
		gtk.window_set_default_icon(gtk.gdk.pixbuf_new_from_file(icon))
		gtk.main()

	def on_preferences_changed(self, preferences):
		self.preferences = preferences

	def quit(self):
		gtk.main_quit()

	def _list_open_notebooks(self):
		list = get_notebook_list()
		for uri in self.daemon.list_notebooks():
			name = list.get_name(uri) or uri
			yield name, uri

	def do_activate_notebook(self, uri):
		self.daemon.get_notebook(uri).toggle_present()

	def do_quit(self):
		self.daemon.quit()

