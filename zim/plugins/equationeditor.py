# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import glob

from zim.plugins.base.imagegenerator import ImageGeneratorPlugin, ImageGeneratorClass
from zim.fs import File, TmpFile
from zim.config import data_file
from zim.templates import GenericTemplate
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
	short_label = _('E_quation')
	insert_label = _('Insert Equation')
	edit_label = _('_Edit Equation')
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
		file = data_file('templates/plugins/equationeditor.tex')
		assert file, 'BUG: could not find templates/plugins/equationeditor.tex'
		self.template = GenericTemplate(file.readlines(), name=file)
		self.texfile = TmpFile(self.scriptname)

	def generate_image(self, text):

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
