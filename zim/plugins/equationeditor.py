
# Copyright 2009-2019 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import glob

from zim.plugins import PluginClass
from zim.plugins.base.imagegenerator import \
	ImageGeneratorClass, BackwardImageGeneratorObjectType

from zim.fs import File, TmpFile
from zim.templates import get_template
from zim.applications import Application, ApplicationError


# TODO put these commands in preferences
latexcmd = ('latex', '-no-shell-escape', '-halt-on-error')
dvipngcmd = ('dvipng', '-q', '-bg', 'Transparent', '-T', 'tight', '-o')


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


class BackwardEquationImageObjectType(BackwardImageGeneratorObjectType):

	name = 'image+equation'
	label = _('Equation') # T: menu item
	syntax = 'latex'
	scriptname = 'equation.tex'
	imagefile_extension = '.png'

	def format_latex(self, dumper, attrib, data):
		if attrib['src'] and not attrib['src'] == '_new_':
			script_name = attrib['src'][:-3] + 'tex'
			script_file = dumper.linker.resolve_source_file(script_name)
			if script_file.exists():
				text = script_file.read().strip()
				return ['\\begin{math}\n', text, '\n\\end{math}']

		raise ValueError('missing source') # parent class will fall back to image


class EquationGenerator(ImageGeneratorClass):

	def __init__(self, plugin, notebook, page):
		ImageGeneratorClass.__init__(self, plugin, notebook, page)
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
		self.template.process(lines, {'equation': text})
		self.texfile.writelines(lines)
		#~ print('>>>%s<<<' % self.texfile.read())

		# Call latex
		logfile = File(self.texfile.path[:-4] + '.log') # len('.tex') == 4
		#~ print(">>>", self.texfile, logfile)
		try:
			latex = Application(latexcmd)
			latex.run((self.texfile.basename,), cwd=self.texfile.dir)
		except ApplicationError:
			# log should have details of failure
			return None, logfile

		# Call dvipng
		dvifile = File(self.texfile.path[:-4] + '.dvi') # len('.tex') == 4
		pngfile = File(self.texfile.path[:-4] + '.png') # len('.tex') == 4
		dvipng = Application(dvipngcmd)
		dvipng.run((pngfile, dvifile)) # output, input
			# No try .. except here - should never fail
		# TODO dvipng can start processing before latex finished - can we win speed there ?

		return pngfile, logfile

	def cleanup(self):
		path = self.texfile.path
		for path in glob.glob(path[:-4] + '.*'):
			File(path).remove()
