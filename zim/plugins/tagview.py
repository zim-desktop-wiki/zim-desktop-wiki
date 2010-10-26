# -*- coding: utf-8 -*-

import gtk

from zim.plugins import PluginClass


class TagviewPlugin(PluginClass):

	plugin_info = {
		'name': _('Tagview'), # T: plugin name
		'description': _('''\
This plugin loads the tag user interface.
'''), # T: plugin description
		'author': 'Fabian Moser',
		'help': 'Plugins:Tagview',
	}

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		self.sidepane_widget = None # For the embedded version

	def initialize_ui(self, ui):
		if self.ui.ui_type == 'gtk':
			self.connect_embedded_widget()

	def disconnect(self):
		self.disconnect_embedded_widget()
		PluginClass.disconnect(self)

	def connect_embedded_widget(self):
		if not self.sidepane_widget:
			sidepane = self.ui.mainwindow.sidepane
			self.sidepane_widget = TagviewPluginWidget(self)
			sidepane.pack_start(self.sidepane_widget, False)
			sidepane.reorder_child(self.sidepane_widget, 0)
			self.sidepane_widget.show_all()

	def disconnect_embedded_widget(self):
		if self.sidepane_widget:
			sidepane = self.ui.mainwindow.sidepane
			sidepane.remove(self.sidepane_widget)
			self.sidepane_widget = None


class TagviewPluginWidget(gtk.VBox):

	def __init__(self, plugin):
		gtk.VBox.__init__(self)
		self.plugin = plugin

		label = gtk.Label('Tags')
		self.pack_start(label, False)

		sw = gtk.ScrolledWindow()
		sw.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
		sw.set_shadow_type(gtk.SHADOW_IN)
		textview = gtk.TextView()
		self.textbuffer = textview.get_buffer()
		sw.add(textview)
		sw.show()
		textview.show()
		self.pack_start(sw, False)

		self.notebook_connected = False
		self.plugin.ui.connect('open-page', self.on_open_page)	

	def on_open_page(self, ui, page, path):
		self.update_view(page)
		if not self.notebook_connected:
			ui.notebook.index.connect('page-indexed', self.on_page_indexed)
		
	def on_page_indexed(self, o, path, page):
		self.update_view(page)
		
	def update_view(self, page):
		self.textbuffer.delete(*self.textbuffer.get_bounds())
		index = self.plugin.ui.notebook.index
		for _, attrib in page.get_tags():
			name = attrib['name']
			line = name + " ("
			for tagged in index.get_tagged(name):
				line += tagged.source.name + ", "
			line += ")\n"
			self.textbuffer.insert_at_cursor(line)
		