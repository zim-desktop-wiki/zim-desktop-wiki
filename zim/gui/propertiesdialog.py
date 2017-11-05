# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import gtk
from zim.gui.widgets import Dialog

class PropertiesDialog(Dialog):

	def __init__(self, widget, config, notebook):
		Dialog.__init__(self, widget, _('Properties'), help='Help:Properties') # T: Dialog title
		self.notebook = notebook
		self.config = config

		label = gtk.Label()
		label.set_markup('<b>' + _('Notebook Properties') + '</b>')
			# T: Section in notebook dialog
		label.set_alignment(0.0, 0.5)
		self.vbox.pack_start(label, False)

		self.add_form(
			notebook.properties,
			values=notebook.config['Notebook']
		)
		self.form.widgets['icon'].set_use_relative_paths(self.notebook)
		if self.notebook.readonly:
			for widget in self.form.widgets.values():
				widget.set_sensitive(False)

	def do_response_ok(self):
		if not self.notebook.readonly:
			properties = self.form.copy()

			# XXX this should be part of notebook.save_properties
			# which means notebook should also own a ref to the ConfigManager
			if 'profile' in properties and properties['profile'] != self.notebook.profile:
				assert isinstance(properties['profile'], (basestring, type(None)))
				self.config.set_profile(properties['profile'])

			self.notebook.save_properties(**properties)
		return True

## TODO: put a number of properties in an expander with a lable "Advanced"
