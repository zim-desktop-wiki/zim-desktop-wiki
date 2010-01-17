# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>
# Copyright 2010 John Drinkwater <john@nextraweb.com>

import gobject
import gtk
import appindicator

from zim.plugins import PluginClass
from zim.config import data_file
from zim.notebook import get_notebook_list


class ApplicationIndicatorPlugin(PluginClass):

	plugin_info = {
		'name': _('App Indicator'), # T: plugin name
		'description': _('''\
This plugin adds an indicator icon to the indicator applet.
'''), # T: plugin description
		'author': 'John Drinkwater',
		'help': 'Plugins:App Indicator',
	}


	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		self.icon = None
		self.proxyobject = None

		if self.ui.ui_type == 'gtk':
			if ui.usedaemon:
			#~ and not self.preferences['standalone']
				from zim.daemon import DaemonProxy
				self.proxyobject = DaemonProxy().get_object(
					'zim.plugins.appindicatoricon.DaemonApplicationIndicator', 'ApplicationIndicator')
				self.ui.hideonclose = True
			else:
				self.icon = StandAloneApplicationIndicator(self.ui)


	def disconnect(self):
		if self.icon:
			self.icon.set_visible(False)
			self.icon = None

		if self.proxyobject:
			self.proxyobject.quit()

		self.ui.hideonclose = False

class ApplicationIndicator:
	'''Base class for the zim application indicator'''

	def __init__(self):
        	self.ind = appindicator.Indicator('zim-desktop-wiki', 'zim', appindicator.CATEGORY_APPLICATION_STATUS)
	        self.ind.set_status(appindicator.STATUS_ACTIVE)
		# do we ever need attention?
        	# self.ind.set_attention_icon ("zim-new")

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
	
		menu.show()

		self.ind.set_menu(menu)

	def _populate_menu_notebooks(self, menu, list):
		# Populate the menu with a list of notebooks
		for name, uri in list:
			# support custom notebook items here?
			item = gtk.MenuItem(name)
			# item.set_image()
			item.connect('activate', lambda o, u: self.do_present(u), uri)
			menu.append(item)

	def do_present(self, uri):
		raise NotImplementedError

	def do_quit(self):
		raise NotImplementedError

	def do_open_notebook(self):
		from zim.gui.notebookdialog import NotebookDialog
		NotebookDialog.unique(self, self, callback=self.do_present).show()

class StandAloneApplicationIndicator(ApplicationIndicator):
	'''This class defines the app indicator used for a
	single stand-alone notebook.
	'''

	def __init__(self, ui):
		ApplicationIndicator.__init__(self)
		self.ui = ui
		self.ui.connect('open-notebook', self.on_open_notebook)

	def on_open_notebook(self, ui, notebook):
		# TODO enable this
		#self.set_tooltip(notebook.name)
		#if notebook.icon:
		#	self.set_from_file(notebook.icon)
		pass

	def do_present(self, uri):
		if uri == self.ui.notebook.uri:
			self.ui.present()
		else:
			# this triggers another indicator applet..
			self.ui.open_notebook(uri)
			# so we close the current instance as another is busy loading
			self.ui.quit()
			# TODO may fail?

	def do_quit(self):
		self.ui.quit()


class DaemonApplicationIndicator(ApplicationIndicator):
	'''This class defines the app indicator used in combination with the
	daemon process. It runs as a separate child process.
	'''

	def __init__(self):
		from zim.daemon import DaemonProxy
		ApplicationIndicator.__init__(self)
		self.daemon = DaemonProxy()

	def main(self):
		# Set window icon in case we open the notebook dialog
		# TODO use stock icons like appindicator does
		icon = data_file('zim.png').path
		gtk.window_set_default_icon(gtk.gdk.pixbuf_new_from_file(icon))

		gtk.main()

	def quit(self):
		gtk.main_quit()

	def do_present(self, uri):
		self.daemon.get_notebook(uri).present()

	def do_quit(self):
		self.daemon.quit()

