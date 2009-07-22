# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

import gtk
from zim.gui.widgets import Dialog

class VersionsDialog(Dialog):

	def __init__(self, ui):
		Dialog.__init__(self, ui, _('Versions')) # T: Dialog title
		self.vbox.add(gtk.Label('TODO'))

	def do_response_ok(self):
		return True
