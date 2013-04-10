# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import gtk

from zim.fs import File, TmpFile
from zim.plugins import PluginClass
from zim.config import data_file
from zim.applications import Application, ApplicationError
from zim.gui.imagegeneratordialog import ImageGeneratorClass, ImageGeneratorDialog
from zim.gui.widgets import populate_popup_add_separator

# TODO put these commands in preferences
dotcmd = ('dot', '-Tpng', '-o')

ui_xml = '''
<ui>
	<menubar name='menubar'>
		<menu action='insert_menu'>
			<placeholder name='plugin_items'>
				<menuitem action='insert_diagram'/>
			</placeholder>
		</menu>
	</menubar>
</ui>
'''

ui_actions = (
	# name, stock id, label, accelerator, tooltip, read only
	('insert_diagram', None, _('Dia_gram...'), '', _('Insert diagram'), False),
		# T: menu item for insert diagram plugin
)


class InsertDiagramPlugin(PluginClass):

	plugin_info = {
		'name': _('Insert Diagram'), # T: plugin name
		'description': _('''\
This plugin provides a diagram editor for zim based on GraphViz.

This is a core plugin shipping with zim.
'''), # T: plugin description
		'help': 'Plugins:Diagram Editor',
		'author': 'Jaap Karssenberg',
	}

	@classmethod
	def check_dependencies(klass):
		has_dotcmd = Application(dotcmd).tryexec()
		return has_dotcmd, [("GraphViz", has_dotcmd, True)]

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		if self.ui.ui_type == 'gtk':
			self.ui.add_actions(ui_actions, self)
			self.ui.add_ui(ui_xml, self)
			self.register_image_generator_plugin('diagram')

	def insert_diagram(self):
		dialog = InsertDiagramDialog.unique(self, self.ui)
		dialog.run()

	def edit_object(self, buffer, iter, image):
		dialog = InsertDiagramDialog(self.ui, image=image)
		dialog.run()

	def do_populate_popup(self, menu, buffer, iter, image):
		populate_popup_add_separator(menu, prepend=True)

		item = gtk.MenuItem(_('_Edit Diagram')) # T: menu item in context menu
		item.connect('activate',
			lambda o: self.edit_object(buffer, iter, image))
		menu.prepend(item)



class InsertDiagramDialog(ImageGeneratorDialog):

	def __init__(self, ui, image=None):
		generator = DiagramGenerator()
		ImageGeneratorDialog.__init__(self, ui, _('Insert Diagram'), # T: dialog title
			generator, image, help=':Plugins:Diagram Editor' )


class DiagramGenerator(ImageGeneratorClass):

	uses_log_file = False

	type = 'diagram'
	scriptname = 'diagram.dot'
	imagename = 'diagram.png'

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
			dot.run((self.pngfile, self.dotfile))
		except ApplicationError:
			return None, None # Sorry, no log
		else:
			return self.pngfile, None

	def cleanup(self):
		self.dotfile.remove()
		self.pngfile.remove()
