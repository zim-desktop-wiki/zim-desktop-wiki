# -*- coding: utf8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import gtk

from zim.gui import Dialog
from zim.gui.widgets import Button, BrowserTreeView
import zim.plugins

class PluginsDialog(Dialog):
	'''FIXME'''

	def __init__(self, ui):
		Dialog.__init__(self, ui, 'Plugins', buttons=gtk.BUTTONS_CLOSE)
		self.set_help(':Usage:Plugins')
		hbox = gtk.HBox(spacing=12)
		self.vbox.add(hbox)

		treeview = PluginsTreeView(ui)
		treeview.connect('row-activated', self.do_row_activated)
		hbox.pack_start(treeview, False) # FIXME insert scrollwindow

		vbox = gtk.VBox()
		hbox.add(vbox)

		def heading(text):
			label = gtk.Label()
			label.set_markup('<b>%s</b>' % text)
			label.set_alignment(0.0, 0.5)
			return label

		vbox.pack_start(heading('Name'), False)
		self.name_label = gtk.Label()
		self.name_label.set_alignment(0.0, 0.5)
		vbox.pack_start(self.name_label, False)
		vbox.pack_start(heading('\nDescription'), False)
		self.description_label = gtk.Label()
		self.description_label.set_alignment(0.0, 0.5)
		vbox.pack_start(self.description_label, False) # TODO run through plain format to make links
		vbox.pack_start(heading('\nAuthor'), False)
		self.author_label= gtk.Label()
		self.author_label.set_alignment(0.0, 0.5)
		vbox.pack_start(self.author_label, False) # TODO idem

		hbox = gtk.HBox(spacing=5)
		vbox.pack_end(hbox, False)
		self.plugin_help_button = \
			Button(stock=gtk.STOCK_HELP, label='_More')
		hbox.pack_start(self.plugin_help_button, False)
		self.configure_button = \
			Button(stock=gtk.STOCK_PREFERENCES, label='C_onfigure')
		hbox.pack_start(self.configure_button, False)

		self.do_row_activated(treeview, (0,), 0)

	def do_row_activated(self, treeview, path, col):
		klass = treeview.get_model()[path][2]
		self.name_label.set_text(klass.info['name'].strip())
		self.description_label.set_text(klass.info['description'].strip())
		self.author_label.set_text(klass.info['author'].strip() + '\n')
		self.configure_button.set_sensitive(False) # TODO allow plugin config
		self.plugin_help_button.set_sensitive(False) # TODO allow plugin help


class PluginsTreeModel(gtk.ListStore):

	def __init__(self, ui):
		gtk.ListStore.__init__(self, bool, str, object)
		self.ui = ui
		loaded = [p.__class__ for p in self.ui.plugins]
		for klass in map(zim.plugins.get_plugin, zim.plugins.list_plugins()):
			l = klass in loaded
			self.append((l, klass.info['name'], klass))

	def do_toggle_path(self, path):
		loaded, name, klass = self[path]
		if loaded:
			classes = [p.__class__ for p in self.ui.plugins]
			i = classes.index(klass)
			self.ui.unload_plugin(self.ui.plugins[i])
			self[path][0] = False
		else:
			self.ui.load_plugin(klass)
			self[path][0] = True


class PluginsTreeView(BrowserTreeView):

	def __init__(self, ui):
		BrowserTreeView.__init__(self)

		model = PluginsTreeModel(ui)
		self.set_model(model)

		cellrenderer = gtk.CellRendererToggle()
		cellrenderer.connect('toggled', lambda o, p: model.do_toggle_path(p))
		self.append_column(
			gtk.TreeViewColumn('Enabled', cellrenderer, active=0))
		self.append_column(
			gtk.TreeViewColumn('Plugin', gtk.CellRendererText(), text=1))
