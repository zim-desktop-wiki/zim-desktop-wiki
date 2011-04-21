# -*- coding: utf-8 -*-

# Copyright 2011 Greg Warner <gdwarner@gmail.com>
# (Pretty much copied from diagrameditor.py)

import gtk

from zim.fs import File, TmpFile
from zim.plugins import PluginClass
from zim.config import data_file
from zim.applications import Application
from zim.gui.imagegeneratordialog import ImageGeneratorDialog

# TODO put these commands in preferences
diagcmd = ('seqdiag', '-o')

ui_xml = '''
<ui>
	<menubar name='menubar'>
		<menu action='insert_menu'>
			<placeholder name='plugin_items'>
				<menuitem action='insert_seqdiagram'/>
			</placeholder>
		</menu>
	</menubar>
</ui>
'''

ui_actions = (
	# name, stock id, label, accelerator, tooltip, read only
	('insert_seqdiagram', None, _('Se_quence Diagram...'), '', _('Insert sequence diagram'), False),
		# T: menu item for insert diagram plugin
)


class InsertSequenceDiagramPlugin(PluginClass):

	plugin_info = {
		'name': _('Insert Sequence Diagram'), # T: plugin name
		'description': _('''\
This plugin provides a sequence diagram editor for zim based on seqdiag.

This is not a core plugin shipping with zim.
'''), # T: plugin description
		'help': ':Plugins:Sequence Diagram Editor',
		'author': 'Greg Warner',
	}

	@classmethod
	def check_dependencies(klass):
		return [("seqdiag",Application(diagcmd).tryexec())]

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		if self.ui.ui_type == 'gtk':
			self.ui.add_actions(ui_actions, self)
			self.ui.add_ui(ui_xml, self)
			self.register_image_generator_plugin('seqdiagram')

	def insert_seqdiagram(self):
		dialog = InsertSequenceDiagramDialog.unique(self, self.ui)
		dialog.show_all()

	def edit_object(self, buffer, iter, image):
		dialog = InsertSequenceDiagramDialog(self.ui, image=image)
		dialog.show_all()

	def do_populate_popup(self, menu, buffer, iter, image):
		menu.prepend(gtk.SeparatorMenuItem())

		item = gtk.MenuItem(_('_Edit Sequence Diagram')) # T: menu item in context menu
		item.connect('activate',
			lambda o: self.edit_object(buffer, iter, image))
		menu.prepend(item)



class InsertSequenceDiagramDialog(ImageGeneratorDialog):

	def __init__(self, ui, image=None):
		generator = SequenceDiagramGenerator()
		ImageGeneratorDialog.__init__(self, ui, _('Insert Sequence Diagram'), # T: dialog title
			generator, image, help=':Plugins:Sequence Diagram Editor')


class SequenceDiagramGenerator(object):

	# TODO: generic base class for image generators

	type = 'seqdiagram'
	basename = 'seqdiagram.diag'

	def __init__(self):
		self.diagfile = TmpFile('diagram-editor.diag')
		self.diagfile.touch()
		self.pngfile = File(self.diagfile.path[:-5] + '.png') # len('.diag') == 5

	def generate_image(self, text):
		if isinstance(text, basestring):
			text = text.splitlines(True)

		# Write to tmp file
		self.diagfile.writelines(text)

		# Call seqdiag
		diag = Application(diagcmd)
		diag.run((self.pngfile, self.diagfile))

		return self.pngfile, None

	def cleanup(self):
		self.diagfile.remove()
		self.pngfile.remove()
