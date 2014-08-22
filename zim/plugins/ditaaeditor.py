# -*- coding: utf-8 -*-
#
# ditaaeditor.py
#
# This is a plugin for Zim, which allows coverting ASCII art into proper bitmap
# graphics.
#
#
# Author: Yao-Po Wang <blue119@gmail.com>
# Date: 2012-03-11
# Copyright (c) 2012, released under the GNU GPL v2 or higher
#
#

from zim.plugins.base.imagegenerator import ImageGeneratorPlugin, ImageGeneratorClass
from zim.fs import File, TmpFile
from zim.config import data_file
from zim.applications import Application, ApplicationError


# TODO put these commands in preferences
dotcmd = ('ditaa')


class InsertDitaaPlugin(ImageGeneratorPlugin):

	plugin_info = {
		'name': _('Insert Ditaa'), # T: plugin name
		'description': _('''\
This plugin provides a diagram editor for zim based on Ditaa.

This is a core plugin shipping with zim.
'''), # T: plugin description
        'help': 'Plugins:Ditaa Editor',
		'author': 'Yao-Po Wang',
	}

	object_type = 'ditaa'
	short_label = _('Ditaa') # T: menu item
	insert_label = _('Insert Ditaa') # T: menu item
	edit_label = _('_Edit Ditaa') # T: menu item
	syntax = None

	@classmethod
	def check_dependencies(klass):
		has_dotcmd = Application(dotcmd).tryexec()
		return has_dotcmd, [("Ditaa", has_dotcmd, True)]


class DitaaGenerator(ImageGeneratorClass):

	uses_log_file = False

	object_type = 'ditaa'
	scriptname = 'ditaa.dia'
	imagename = 'ditaa.png'

	def __init__(self, plugin):
		ImageGeneratorClass.__init__(self, plugin)
		self.dotfile = TmpFile(self.scriptname)
		self.dotfile.touch()
		self.pngfile = File(self.dotfile.path[:-4] + '.png') # len('.dot') == 4

	def generate_image(self, text):

		# Write to tmp file
		self.dotfile.writelines(text)

		# Call GraphViz
		try:
			dot = Application(dotcmd)
			dot.run((self.dotfile, '-o', self.pngfile))
		except ApplicationError:
			return None, None # Sorry, no log
		else:
			return self.pngfile, None

	def cleanup(self):
		self.dotfile.remove()
		self.pngfile.remove()
