# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

import gtk
from zim.gui.widgets import Dialog

class PropertiesDialog(Dialog):

	def __init__(self, ui):
		Dialog.__init__(self, ui, _('Properties')) # T: Dialog title
		fields = []
		config = self.ui.notebook.config['Notebook']
		for name, type, label in self.ui.notebook.properties:
			fields.append((name, type, label, config[name]))
		self.add_fields(fields)

	def do_response_ok(self):
		properties = self.get_fields()
		self.ui.notebook.save_properties(**properties)
		return True
