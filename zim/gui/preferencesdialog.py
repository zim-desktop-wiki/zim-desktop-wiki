# -*- coding: utf8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import gtk

from zim.gui import Dialog
from zim.gui.widgets import Button, BrowserTreeView
import zim.plugins

class PreferencesDialog(Dialog):
	'''Preferences dialog consisting of tabs with various options and
	a tab with plugins. Options are not defined here, but need to be
	registered using GtkInterface.register_preferences().
	'''

	def __init__(self, ui):
		Dialog.__init__(self, ui, 'Preferences')
		gtknotebook = gtk.Notebook()
		self.vbox.add(gtknotebook)
		for category, preferences in ui.preferences_register.items():
			table = gtk.Table()
			table.set_border_width(5)
			table.set_row_spacings(5)
			table.set_col_spacings(12)
			gtknotebook.append_page(table, gtk.Label(category))
			fields = []
			for p in preferences:
				section, key, type, label = p
				value = ui.preferences[section][key]
				fields.append(((section, key), type, label, value))
				# a tuple is hashable and can be used as field name...
			self.add_fields(fields, table=table, trigger_response=False)

		gtknotebook.append_page(PluginsTab(self), gtk.Label('Plugins'))

	def do_response_ok(self):
		fields = self.get_fields()
		#~ print fields
		for key, value in fields.items():
			section, key = key
			self.ui.preferences[section][key] = value
		self.ui.save_preferences()
		return True


class PluginsTab(gtk.HBox):

	def __init__(self, dialog):
		gtk.HBox.__init__(self, spacing=12)
		self.set_border_width(12)
		self.dialog = dialog

		treeview = PluginsTreeView(self.dialog.ui)
		treeview.connect('row-activated', self.do_row_activated)
		self.pack_start(treeview, False) # FIXME insert scrollwindow

		vbox = gtk.VBox()
		self.add(vbox)

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
		vbox.pack_start(self.description_label, False) # FIXME run through plain format to make links
		vbox.pack_start(heading('\nAuthor'), False)
		self.author_label= gtk.Label()
		self.author_label.set_alignment(0.0, 0.5)
		vbox.pack_start(self.author_label, False) # FIXME idem

		hbox = gtk.HBox(spacing=5)
		vbox.pack_end(hbox, False)

		self.plugin_help_button = \
			Button(stock=gtk.STOCK_HELP, label='_More')
		self.plugin_help_button.connect('clicked', self.on_help_button_clicked)
		hbox.pack_start(self.plugin_help_button, False)
		
		self.configure_button = \
			Button(stock=gtk.STOCK_PREFERENCES, label='C_onfigure')
		self.configure_button.connect('clicked', self.on_configure_button_clicked)
		hbox.pack_start(self.configure_button, False)

		self.do_row_activated(treeview, (0,), 0)

	def do_row_activated(self, treeview, path, col):
		active = treeview.get_model()[path][0]
		klass = treeview.get_model()[path][2]
		self._klass = klass
		self.name_label.set_text(klass.plugin_info['name'].strip())
		self.description_label.set_text(klass.plugin_info['description'].strip())
		self.author_label.set_text(klass.plugin_info['author'].strip() + '\n')
		self.configure_button.set_sensitive(active and bool(klass.plugin_preferences))
		self.plugin_help_button.set_sensitive('manualpage' in klass.plugin_info)

	def on_help_button_clicked(self, button):
		self.dialog.ui.show_help(self._klass.plugin_info['manualpage'])

	def on_configure_button_clicked(self, button):
		PluginConfigureDialog(self.dialog, self._klass).run()


class PluginsTreeModel(gtk.ListStore):

	def __init__(self, ui):
		gtk.ListStore.__init__(self, bool, str, object)
		self.ui = ui
		loaded = [p.__class__ for p in self.ui.plugins]
		for klass in map(zim.plugins.get_plugin, zim.plugins.list_plugins()):
			l = klass in loaded
			self.append((l, klass.plugin_info['name'], klass))

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


class PluginConfigureDialog(Dialog):

	def __init__(self, dialog, klass):
		Dialog.__init__(self, dialog, 'Configure Plugin')
		self.ui = dialog.ui

		label = gtk.Label('Options for plugin %s' % klass.plugin_info['name'])
		self.vbox.add(label)

		fields = []
		self.preferences = dialog.ui.preferences[klass.__name__]
		for key, type, label, default in klass.plugin_preferences:
			self.preferences.setdefault(key, default) # just to be sure
			fields.append((key, type, label, self.preferences[key]))
		self.add_fields(fields)

	def do_response_ok(self):
		self.preferences.update(self.get_fields())
		self.ui.save_preferences()
		return True
