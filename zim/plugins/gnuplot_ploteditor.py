# -*- coding: utf-8 -*-
#
# gnuplot_ploteditor.py
#
# This is a plugin for Zim, which allows inserting Gnuplot scripts to
# have Zim generate plots from them.
#
# Author: Alessandro Magni <magni@inrim.it>
# Date: 2010-10-12
# Copyright (c) 2010, released under the GNU GPL v2 or higher
#
#

import glob

from zim.plugins.base.imagegenerator import \
	ImageGeneratorPlugin, ImageGeneratorClass, MainWindowExtensionBase
from zim.fs import File, TmpFile
from zim.config import data_file
from zim.templates import get_template
from zim.applications import Application, ApplicationError


# TODO put these commands in preferences
gnuplot_cmd = ('gnuplot',)


class InsertGnuplotPlugin(ImageGeneratorPlugin):

	plugin_info = {
		'name': _('Insert Gnuplot'), # T: plugin name
		'description': _('''\
This plugin provides a plot editor for zim based on Gnuplot.
'''), # T: plugin description
		'help': 'Plugins:Gnuplot Editor',
		'author': 'Alessandro Magni',
	}

	object_type = 'gnuplot'
	short_label = _('Gnuplot') # T: menu item
	insert_label = _('Insert Gnuplot') # T: menu item
	edit_label = _('_Edit Gnuplot') # T: menu item
	syntax = None

	@classmethod
	def check_dependencies(klass):
		has_gnuplot = Application(gnuplot_cmd).tryexec()
		return has_gnuplot, [('Gnuplot', has_gnuplot, True)]


class MainWindowExtension(MainWindowExtensionBase):

	def build_generator(self):
		page = self.window.ui.page # XXX
		notebook = self.window.ui.notebook # XXX
		attachment_folder = notebook.get_attachments_dir(page)
		#~ print ">>>", notebook, page, attachment_folder
		return GnuplotGenerator(self.plugin, attachment_folder)


class GnuplotGenerator(ImageGeneratorClass):

	uses_log_file = False

	object_type = 'gnuplot'
	scriptname = 'gnuplot.gnu'
	imagename = 'gnuplot.png'

	def __init__(self, plugin, attachment_folder=None):
		ImageGeneratorClass.__init__(self, plugin)
		self.template = get_template('plugins', 'gnuploteditor.gnu')
		self.attachment_folder = attachment_folder
		self.plotscriptfile = TmpFile(self.scriptname)

	def generate_image(self, text):

		plotscriptfile = self.plotscriptfile
		pngfile = File(plotscriptfile.path[:-4] + '.png')

		plot_script = "".join(text)

		template_vars = { # they go in the template
			'gnuplot_script': plot_script,
			'png_fname': pngfile.path,
		}
		if self.attachment_folder and self.attachment_folder.exists():
			template_vars['attachment_folder'] = self.attachment_folder.path
		else:
			template_vars['attachment_folder'] = ''

		# Write to tmp file using the template for the header / footer
		lines = []
		self.template.process(lines, template_vars)
		plotscriptfile.writelines(lines)
		#~ print '>>>\n%s<<<' % plotscriptfile.read()

		# Call Gnuplot
		try:
			gnu_gp = Application(gnuplot_cmd)
			gnu_gp.run(args=( plotscriptfile.basename, ), cwd=plotscriptfile.dir)
							# you call it as % gnuplot output.plt

		except ApplicationError:
			return None, None # Sorry - no log
		else:
			return pngfile, None

	def cleanup(self):
		path = self.plotscriptfile.path
		for path in glob.glob(path[:-4]+'.*'):
			File(path).remove()
