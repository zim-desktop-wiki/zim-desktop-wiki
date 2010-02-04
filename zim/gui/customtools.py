# -*- coding: utf-8 -*-

# Copyright 2010 Jaap Karssenberg <pardus@cpan.org>

'''This module contains code for defining and managing custom
commands.
'''

import gtk

from zim.gui.applications import CustomTool
from zim.gui.widgets import Dialog


class CustomToolManagerDialog(Dialog):

	def __init__(self, ui):
		Dialog.__init__(self, ui, _('Custom Tools')) # T: Title export dialog
		self.set_help(':Help:Custom Tools')

		self.add_fields((
			('name', 'string', _('Name'), ''),
			('description', 'string', _('Description'), ''),
			('command', 'string', _('Command'), ''),
			('readonly', 'bool', _('Command does not modify data'), False),
			#~ ('showintoolbar', 'bool', _('Show in the toolbar'), False),
		), trigger_response=False)

		# TODO icon - needed for show in toolbar

		self.vbox.pack_start(
			gtk.Label( '\n' + _('''\
When defining a command, you can use the following codes:

	%f for page source as a temporary file
	%d for the attachment directory of the current page
	%s for the real page source file (if any)
	%n for the notebook location (file or folder)
	%D for the document root (if any)
	%t for the selected text or word under cursor
''') ), False)

		# Set X-Zim-ShowInContextMenu based on %f, %d, %s or %t in the command
