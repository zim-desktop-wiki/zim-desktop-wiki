# -*- coding: utf-8 -*-
#
# ploteditor.py
#
# This is a plugin for Zim, which allows inserting GNU R scripts to
# have Zim generate plots from them.
#
# Author: Lee Braiden <lee.b@irukado.org>
# Date: 2010-03-13
# Copyright (c) 2010, released under the GNU GPL v2 or higher
#
# Heavily based on equationeditor.py plugin as of:
# bzr revno 212, (2010-03-10), marked as
# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>
#

import glob
import re

from zim.plugins.base.imagegenerator import ImageGeneratorPlugin, ImageGeneratorClass
from zim.fs import File, TmpFile
from zim.config import data_file
from zim.templates import get_template
from zim.applications import Application

# TODO put these commands in preferences
gnu_r_cmd = ('R',)


class InsertGNURPlotPlugin(ImageGeneratorPlugin):

	plugin_info = {
		'name': _('Insert GNU R Plot'), # T: plugin name
		'description': _('''\
This plugin provides a plot editor for zim based on GNU R.
'''), # T: plugin description
		'help': 'Plugins:GNU R Plot Editor',
		'author': 'Lee Braiden',
	}

	object_type = 'gnu_r_plot'
	short_label = _('GNU _R Plot') # T: menu item
	insert_label = _('Insert GNU R Plot') # T: menu item
	edit_label = _('_Edit GNU R Plot') # T: menu item
	syntax = 'r'

	@classmethod
	def check_dependencies(klass):
		has_gnur = Application(gnu_r_cmd).tryexec()
		return has_gnur, [('GNU R', has_gnur, True)]


class GNURPlotGenerator(ImageGeneratorClass):

	uses_log_file = False

	object_type = 'gnu_r_plot'
	scriptname = 'gnu_r_plot.r'
	imagename = 'gnu_r_plot.png'

	def __init__(self, plugin):
		ImageGeneratorClass.__init__(self, plugin)
		self.template = get_template('plugins', 'gnu_r_editor.r')
		self.plotscriptfile = TmpFile(self.scriptname)

	def generate_image(self, text):

		plotscriptfile = self.plotscriptfile
		pngfile = File(plotscriptfile.path[:-2] + '.png')

		plot_script = "".join(text)
		
		plot_width = 480 # default image width (px)
		plot_height = 480 # default image height (px)

		# LOOK for image size in comments of the script
		r=re.search(r"^#\s*WIDTH\s*=\s*([0-9]+)$",plot_script,re.M)
		if r:
			plot_width=int(r.group(1))
		r=re.search(r"^#\s*HEIGHT\s*=\s*([0-9]+)$",plot_script,re.M)
		if r:
			plot_height=int(r.group(1))

		template_vars = {
			'gnu_r_plot_script': plot_script,
			'r_width': plot_width,
			'r_height': plot_height,
			'png_fname': pngfile.path.replace('\\', '/'),
				# Even on windows, GNU R expects unix path seperator
		}

		# Write to tmp file usign the template for the header / footer
		lines = []
		self.template.process(lines, template_vars)
		plotscriptfile.writelines(lines)
		#print '>>>%s<<<' % plotscriptfile.read()

		# Call GNU R
		try:
			gnu_r = Application(gnu_r_cmd)
			#~ gnu_r.run(args=('-f', plotscriptfile.basename, ), cwd=plotscriptfile.dir)
			gnu_r.run(args=('-f', plotscriptfile.basename, '--vanilla'), cwd=plotscriptfile.dir)
		except:
			return None, None # Sorry, no log
		else:
			return pngfile, None

	def cleanup(self):
		path = self.plotscriptfile.path
		for path in glob.glob(path[:-2]+'.*'):
			File(path).remove()
