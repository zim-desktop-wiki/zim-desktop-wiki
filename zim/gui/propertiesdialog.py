# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

import gtk
from zim.gui.widgets import Dialog

class PropertiesDialog(Dialog):

	def __init__(self, ui):
		Dialog.__init__(self, ui, _('Properties')) # T: Dialog title
		label = gtk.Label()
		label.set_markup('<b>'+_('Notebook Properties')+'</b>')
			# T: Section in notbook dialog
		label.set_alignment(0.0, 0.5)
		self.vbox.pack_start(label, False)
		fields = []
		config = self.ui.notebook.config['Notebook']
		for name, type, label in self.ui.notebook.properties:
			fields.append((name, type, label, config[name]))
		self.add_fields(fields)
		if self.ui.readonly:
			for widget in self.inputs.values():
				widget.set_sensitive(False)

	def do_response_ok(self):
		if not self.ui.readonly:
			properties = self.get_fields()
			self.ui.notebook.save_properties(**properties)
		return True
