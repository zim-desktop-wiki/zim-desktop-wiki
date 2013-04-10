# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import gtk
import glob

from zim.fs import File, TmpFile
from zim.plugins import PluginClass
from zim.config import data_file
from zim.templates import GenericTemplate
from zim.applications import Application, ApplicationError
from zim.gui.imagegeneratordialog import ImageGeneratorClass, ImageGeneratorDialog
from zim.gui.widgets import populate_popup_add_separator

# TODO put these commands in preferences
latexcmd = ('latex', '-no-shell-escape', '-halt-on-error')
dvipngcmd = ('dvipng', '-q', '-bg', 'Transparent', '-T', 'tight', '-o')

ui_xml = '''
<ui>
	<menubar name='menubar'>
		<menu action='insert_menu'>
			<placeholder name='plugin_items'>
				<menuitem action='insert_equation'/>
			</placeholder>
		</menu>
	</menubar>
</ui>
'''

ui_actions = (
	# name, stock id, label, accelerator, tooltip, read only
	('insert_equation', None, _('E_quation...'), '', _('Insert equation'), False),
		# T: menu item for insert equation plugin
)


class InsertEquationPlugin(PluginClass):

	plugin_info = {
		'name': _('Insert Equation'), # T: plugin name
		'description': _('''\
This plugin provides an equation editor for zim based on latex.

This is a core plugin shipping with zim.
'''), # T: plugin description
		'help': 'Plugins:Equation Editor',
		'author': 'Jaap Karssenberg',
	}

	@classmethod
	def check_dependencies(klass):
		has_latex = Application(latexcmd).tryexec()
		has_dvipng = Application(dvipngcmd).tryexec()
		return (has_latex and has_dvipng), \
				[('latex', has_latex, True), ('dvipng', has_dvipng, True)]

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		if self.ui.ui_type == 'gtk':
			self.ui.add_actions(ui_actions, self)
			self.ui.add_ui(ui_xml, self)
			self.register_image_generator_plugin('equation')

	def insert_equation(self):
		dialog = InsertEquationDialog.unique(self, self.ui)
		dialog.run()

	def edit_object(self, buffer, iter, image):
		dialog = InsertEquationDialog(self.ui, image=image)
		dialog.run()

	def do_populate_popup(self, menu, buffer, iter, image):
		populate_popup_add_separator(menu, prepend=True)

		item = gtk.MenuItem(_('_Edit Equation')) # T: menu item in context menu
		item.connect('activate',
			lambda o: self.edit_object(buffer, iter, image))
		menu.prepend(item)



class InsertEquationDialog(ImageGeneratorDialog):

	def __init__(self, ui, image=None):
		generator = EquationGenerator()
		ImageGeneratorDialog.__init__(self, ui, _('Insert Equation'), # T: dialog title
			generator, image, help=':Plugins:Equation Editor', syntax="latex" )


class EquationGenerator(ImageGeneratorClass):

	type = 'equation'
	scriptname = 'equation.tex'
	imagename = 'equation.png'

	def __init__(self):
		file = data_file('templates/plugins/equationeditor.tex')
		assert file, 'BUG: could not find templates/plugins/equationeditor.tex'
		self.template = GenericTemplate(file.readlines(), name=file)
		self.texfile = TmpFile(self.scriptname)

	def generate_image(self, text):
		if isinstance(text, basestring):
			text = text.splitlines(True)

		# Filter out empty lines, not allowed in latex equation blocks
		text = (line for line in text if line and not line.isspace())
		text = ''.join(text)
		#~ print '>>>%s<<<' % text

		# Write to tmp file using the template for the header / footer
		texfile = self.texfile
		texfile.writelines(
			self.template.process({'equation': text}) )
		#~ print '>>>%s<<<' % texfile.read()

		# Call latex
		logfile = File(texfile.path[:-4] + '.log') # len('.tex') == 4
		try:
			latex = Application(latexcmd)
			latex.run((texfile.basename,), cwd=texfile.dir)
		except ApplicationError:
			# log should have details of failure
			return None, logfile

		# Call dvipng
		dvifile = File(texfile.path[:-4] + '.dvi') # len('.tex') == 4
		pngfile = File(texfile.path[:-4] + '.png') # len('.tex') == 4
		dvipng = Application(dvipngcmd)
		dvipng.run((pngfile, dvifile)) # output, input
			# No try .. except here - should never fail
		# TODO dvipng can start processing before latex finished - can we win speed there ?

		return pngfile, logfile

	def cleanup(self):
		path = self.texfile.path
		for path in glob.glob(path[:-4]+'.*'):
			File(path).remove()
