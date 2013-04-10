# -*- coding: utf-8 -*-
#
# ditaaeditor.py
#
# This is a plugin for Zim, which allows coverting ASCII art into proper bitmap
# graphics.
#
#
# Author: Yao-Po Wang <blue119@gmail.com>
# Date: 2012-03-11
# Copyright (c) 2012, released under the GNU GPL v2 or higher
#
#

import gtk

from zim.fs import File, TmpFile
from zim.plugins import PluginClass
from zim.config import data_file
from zim.applications import Application, ApplicationError
from zim.gui.imagegeneratordialog import ImageGeneratorClass, ImageGeneratorDialog
from zim.gui.widgets import populate_popup_add_separator

# TODO put these commands in preferences
dotcmd = ('ditaa')

ui_xml = '''
<ui>
	<menubar name='menubar'>
		<menu action='insert_menu'>
			<placeholder name='plugin_items'>
				<menuitem action='insert_ditaa'/>
			</placeholder>
		</menu>
	</menubar>
</ui>
'''

ui_actions = (
	# name, stock id, label, accelerator, tooltip, read only
	('insert_ditaa', None, _('Ditaa...'), '', _('Insert ditaa'), False),
		# T: menu item for insert diagram plugin
)


class InsertDitaaPlugin(PluginClass):

	plugin_info = {
		'name': _('Insert Ditaa'), # T: plugin name
		'description': _('''\
This plugin provides a diagram editor for zim based on Ditaa.

This is a core plugin shipping with zim.
'''), # T: plugin description
        'help': 'Plugins:Ditaa Editor',
		'author': 'Yao-Po Wang',
	}

	@classmethod
	def check_dependencies(klass):
		has_dotcmd = Application(dotcmd).tryexec()
		return has_dotcmd, [("Ditaa", has_dotcmd, True)]

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		if self.ui.ui_type == 'gtk':
			self.ui.add_actions(ui_actions, self)
			self.ui.add_ui(ui_xml, self)
			self.register_image_generator_plugin('ditaa')

	def insert_ditaa(self):
		dialog = InsertDitaaDialog.unique(self, self.ui)
		dialog.run()

	def edit_object(self, buffer, iter, image):
		dialog = InsertDitaaDialog(self.ui, image=image)
		dialog.run()

	def do_populate_popup(self, menu, buffer, iter, image):
		populate_popup_add_separator(menu, prepend=True)

		item = gtk.MenuItem(_('_Edit Ditaa')) # T: menu item in context menu
		item.connect('activate',
			lambda o: self.edit_object(buffer, iter, image))
		menu.prepend(item)



class InsertDitaaDialog(ImageGeneratorDialog):

	def __init__(self, ui, image=None):
		generator = DitaaGenerator()
		ImageGeneratorDialog.__init__(self, ui, _('Insert Ditaa'), # T: dialog title
            generator, image, help=':Plugins:Ditaa Editor' )


class DitaaGenerator(ImageGeneratorClass):

	uses_log_file = False

	type = 'ditaa'
	scriptname = 'ditaa.dia'
	imagename = 'ditaa.png'

	def __init__(self):
		self.dotfile = TmpFile(self.scriptname)
		self.dotfile.touch()
		self.pngfile = File(self.dotfile.path[:-4] + '.png') # len('.dot') == 4

	def generate_image(self, text):
		if isinstance(text, basestring):
			text = text.splitlines(True)

		# Write to tmp file
		self.dotfile.writelines(text)

		# Call GraphViz
		try:
			dot = Application(dotcmd)
			dot.run((self.dotfile, '-o', self.pngfile))
		except ApplicationError:
			return None, None # Sorry, no log
		else:
			return self.pngfile, None

	def cleanup(self):
		self.dotfile.remove()
		self.pngfile.remove()
