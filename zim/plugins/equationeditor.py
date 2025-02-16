
# Copyright 2009-2019 Jaap Karssenberg <jaap.karssenberg@gmail.com>
# Copyright 2025 Nimrod Maclomair <nimrod4garoa@gmail.com>

import glob

from zim.plugins import PluginClass
from zim.plugins.base.imagegenerator import \
	ImageGeneratorClass, BackwardImageGeneratorObjectType, \
	ImageGeneratorObjectType

from zim.newfs import LocalFile, TmpFile
from zim.templates import get_template
from zim.applications import Application, ApplicationError

# TODO put these commands in preferences
latexcmd = 'latex'
dvipngcmd = 'dvipng'

class InsertEquationPlugin(PluginClass):

	plugin_info = {
		'name': _('Insert Equation'), # T: plugin name
		'description': _('''\
This plugin provides an equation editor for zim based on latex.
Equations are stored as separate files in the attachments folder,
or in the wiki page itself.

This is a core plugin shipping with zim.
'''), # T: plugin description
		'help': 'Plugins:Equation Editor',
		'author': 'Jaap Karssenberg',
	}

	plugin_preferences = (
		# key, type, label, default
		('dark_mode', 'bool', _('Use font color for dark theme'), False), # T: plugin preference
		('font_size', 'int', _('Font size'), 12, (6, 24)), # T: plugin preference
		('output_dpi', 'choice', _('Equation image DPI'), "96", ("96","120","150","200","300","400","600")), # T: plugin preference
    )

	@classmethod
	def check_dependencies(klass):
		has_latex = Application(latexcmd).tryexec()
		has_dvipng = Application(dvipngcmd).tryexec()
		return (has_latex and has_dvipng), \
				[('latex', has_latex, True), ('dvipng', has_dvipng, True)]


class BackwardEquationImageObjectType(BackwardImageGeneratorObjectType):

	name = 'image+equation'
	label = _('Equation as file') # T: menu item
	syntax = 'latex'
	scriptname = 'equation.tex'
	widget_style = 'inline'

	def format_latex(self, dumper, attrib, data):
		if attrib['src'] and not attrib['src'] == '_new_':
			script_name = attrib['src'][:-3] + 'tex'
			script_file = dumper.linker.resolve_source_file(script_name)
			if script_file.exists():
				text = script_file.read().strip()
				return ['\\begin{math}\n', text, '\n\\end{math}']

		raise ValueError('missing source') # parent class will fall back to image


class EquationImageObjectType(ImageGeneratorObjectType):

	name = 'equationembedded'
	label = _('Equation') # T: menu item
	syntax = 'latex'
	widget_style = 'inline'
	is_inline = True

	def format_latex(self, dumper, attrib, data):
		return ['\\begin{math}\n', data, '\n\\end{math}']


class EquationGenerator(ImageGeneratorClass):

	imagefile_extension = '.png'

	def __init__(self, plugin, notebook, page):
		ImageGeneratorClass.__init__(self, plugin, notebook, page)
		self.preferences = plugin.preferences
		self.template = get_template('plugins', 'equationeditor.tex')
		self.texfile = TmpFile('equation.tex')

	def generate_image(self, text):

		# Filter out empty lines, not allowed in latex equation blocks
		if isinstance(text, str):
			text = text.splitlines(True)
		text = (line for line in text if line and not line.isspace())
		text = ''.join(text)
		#~ print('>>>%s<<<' % text)

		# Write to tmp file using the template for the header / footer
		lines = []
		self.template.process(lines, {
			'equation': text,
			'font_size': self.preferences['font_size'],
			'dark_mode': self.preferences['dark_mode']
		})
		self.texfile.writelines(lines)
		#~ print('>>>%s<<<' % self.texfile.read())

		# Call latex
		logfile = LocalFile(self.texfile.path[:-4] + '.log') # len('.tex') == 4
		#~ print(">>>", self.texfile, logfile)
		try:
			latex = Application('%s -no-shell-escape -halt-on-error' % (latexcmd))
			latex.run((self.texfile.basename,), cwd=self.texfile.parent())
		except ApplicationError:
			# log should have details of failure
			return None, logfile

		# Call dvipng
		dvifile = LocalFile(self.texfile.path[:-4] + '.dvi') # len('.tex') == 4
		pngfile = LocalFile(self.texfile.path[:-4] + '.png') # len('.tex') == 4
		dvipng = Application('%s -q -bg Transparent -T tight -D %s -o' % (dvipngcmd,self.preferences['output_dpi']))
		dvipng.run((pngfile, dvifile)) # output, input
		# No try .. except here - should never fail
		# TODO dvipng can start processing before latex finished - can we win speed there ?

		return pngfile, logfile

	def cleanup(self):
		path = self.texfile.path
		for path in glob.glob(path[:-4] + '.*'):
			LocalFile(path).remove()
