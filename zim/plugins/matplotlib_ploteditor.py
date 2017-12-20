# -*- coding: utf-8 -*-
#
# ploteditor.py
#
# This is a plugin for Zim, which allows inserting GNU R scripts to
# have Zim generate plots from them.
#
# Author: Olivier Scholder <o.scholder@gmail.com>
# Date: 2016-08-03
# Copyright (c) 2010, released under the GNU GPL v2 or higher
#
# Heavily based on gnu_r_ploteditor.py plugin as of v0.65

import glob
import re

from zim.plugins.base.imagegenerator import ImageGeneratorPlugin, ImageGeneratorClass
from zim.fs import File, TmpFile
from zim.config import data_file
from zim.templates import get_template
from zim.applications import Application

class InsertMatplotlibPlotPlugin(ImageGeneratorPlugin):

	plugin_info = {
		'name': _('Insert Matplotlib Plot'), # T: plugin name
		'description': _('''\
This plugin provides a plot editor for zim based on Matplotlib.
'''), # T: plugin description
		'help': 'Plugins:Matplotlib Plot Editor',
		'author': 'Olivier Scholder',
	}

	object_type = 'matplotlib_plot'
	short_label = _('Matplotlib Plot') # T: menu item
	insert_label = _('Insert Matplotlib Plot') # T: menu item
	edit_label = _('_Edit Matplotlib Plot') # T: menu item
	syntax = 'python'

	@classmethod
	def check_dependencies(klass):
		try:
			import matplotlib.pyplot as plt
			has_matplotlib = True
		except:
			has_matplotlib = False
		try:
			import numpy as np
			has_numpy = True
		except:
			has_numpy = False

		return has_matplotlib and has_numpy, [('Matplotlib', has_matplotlib, True),('Numpy',has_numpy, True)]


class MatplotlibPlotGenerator(ImageGeneratorClass):

	uses_log_file = True

	object_type = 'matplotlib_plot'
	scriptname = 'matplotlib_plot.py'
	imagename = 'matplotlib_plot.png'

	def __init__(self, plugin):
		ImageGeneratorClass.__init__(self, plugin)
		self.template = get_template('plugins','matplotlib_editor.py')
		self.plotscriptfile = TmpFile(self.scriptname)

	def generate_image(self, text):
		plotscriptfile = self.plotscriptfile
		pngfile = File(plotscriptfile.path[:-3] + '.png')

		template_vars = {
			'matplotlib_script': text,
			'png_fname': pngfile.path.replace('\\','/'),
		}

		# Write to tmp file usign the template for the header / footer
		lines = []
		self.template.process(lines, template_vars)
		plotscriptfile.writelines(lines)

		logfile = File(plotscriptfile.path[:-3] + '.log')
		try:
			p = Application(('C:\\Python27\\python.exe',))
			p.run(args=(plotscriptfile.basename,), cwd=plotscriptfile.dir)
		except Exception as ex:
			logfile.write(str(ex))
			return None, logfile
		return pngfile, None

	def cleanup(self):
		pass
#		path = self.plotscriptfile.path
#		for path in glob.glob(path[:-2]+'.*'):
#			File(path).remove()
