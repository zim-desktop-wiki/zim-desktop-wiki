# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import gtk
from zim.gui.widgets import Dialog

class PropertiesDialog(Dialog):

	def __init__(self, ui):
		Dialog.__init__(self, ui, _('Properties'), help='Help:Properties') # T: Dialog title
		label = gtk.Label()
		label.set_markup('<b>'+_('Notebook Properties')+'</b>')
			# T: Section in notebook dialog
		label.set_alignment(0.0, 0.5)
		self.vbox.pack_start(label, False)
		fields = []
		config = self.ui.notebook.config['Notebook']
		for item in self.ui.notebook.properties:
			fields.append(item)
		self.add_form(fields, values=config)
		self.form.widgets['icon'].set_use_relative_paths(self.ui.notebook)
		if self.ui.readonly:
			for widget in self.form.widgets.values():
				widget.set_sensitive(False)

	def do_response_ok(self):
		if not self.ui.readonly:
			properties = self.form.copy()
			self.ui.notebook.save_properties(**properties)
		return True

## TODO: put a number of properties in an expander with a lable "Advanced"
