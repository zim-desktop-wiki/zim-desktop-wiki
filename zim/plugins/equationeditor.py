# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import glob

from zim.plugins.base.imagegenerator import ImageGeneratorPlugin, ImageGeneratorClass
from zim.fs import File, TmpFile
from zim.config import data_file
from zim.templates import get_template
from zim.applications import Application, ApplicationError


# TODO put these commands in preferences
latexcmd = ('latex', '-no-shell-escape', '-halt-on-error')
dvipngcmd = ('dvipng', '-q', '-bg', 'Transparent', '-T', 'tight', '-o')

class InsertEquationPlugin(ImageGeneratorPlugin):

	plugin_info = {
		'name': _('Insert Equation'), # T: plugin name
		'description': _('''\
This plugin provides an equation editor for zim based on latex.

This is a core plugin shipping with zim.
'''), # T: plugin description
		'help': 'Plugins:Equation Editor',
		'author': 'Jaap Karssenberg',
	}

	object_type = 'equation'
	short_label = _('E_quation') # T: menu item
	insert_label = _('Insert Equation') # T: menu item
	edit_label = _('_Edit Equation') # T: menu item
	syntax = 'latex'

	@classmethod
	def check_dependencies(klass):
		has_latex = Application(latexcmd).tryexec()
		has_dvipng = Application(dvipngcmd).tryexec()
		return (has_latex and has_dvipng), \
				[('latex', has_latex, True), ('dvipng', has_dvipng, True)]


class EquationGenerator(ImageGeneratorClass):

	object_type = 'equation'
	scriptname = 'equation.tex'
	imagename = 'equation.png'

	def __init__(self, plugin):
		ImageGeneratorClass.__init__(self, plugin)
		self.template = get_template('plugins', 'equationeditor.tex')
		self.texfile = TmpFile(self.scriptname)

	def generate_image(self, text):

		# Filter out empty lines, not allowed in latex equation blocks
		text = (line for line in text if line and not line.isspace())
		text = ''.join(text)
		#~ print '>>>%s<<<' % text

		# Write to tmp file using the template for the header / footer
		lines = []
		self.template.process(lines, {'equation': text})
		self.texfile.writelines(lines)
		#~ print '>>>%s<<<' % self.texfile.read()

		# Call latex
		logfile = File(self.texfile.path[:-4] + '.log') # len('.tex') == 4
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
		for path in glob.glob(path[:-4]+'.*'):
			File(path).remove()
