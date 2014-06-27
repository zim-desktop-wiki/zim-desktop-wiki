# -*- coding: utf-8 -*-

# Copyright 2011 Greg Warner <gdwarner@gmail.com>
# (Pretty much copied from diagrameditor.py)


from zim.plugins import PluginClass
from zim.plugins.base.imagegenerator import ImageGeneratorPlugin, ImageGeneratorClass

from zim.fs import File, TmpFile
from zim.applications import Application, ApplicationError


# TODO put these commands in preferences
diagcmd = ('seqdiag', '-o')


class InsertSequenceDiagramPlugin(ImageGeneratorPlugin):

	plugin_info = {
		'name': _('Insert Sequence Diagram'), # T: plugin name
		'description': _('''\
This plugin provides a sequence diagram editor for zim based on seqdiag.
It allows easy editing of sequence diagrams.
'''), # T: plugin description
		'help': 'Plugins:Sequence Diagram Editor',
		'author': 'Greg Warner',
	}

	object_type = 'seqdiagram'
	short_label = _('Sequence Diagram') # T: menu item
	insert_label = _('Insert Sequence Diagram') # T: menu item
	edit_label = _('_Edit Sequence Diagram') # T: menu item
	syntax = None

	@classmethod
	def check_dependencies(klass):
		has_diagcmd = Application(diagcmd).tryexec()
		return has_diagcmd, [("seqdiag", has_diagcmd, True)]


class SequenceDiagramGenerator(ImageGeneratorClass):

	uses_log_file = False

	object_type = 'seqdiagram'
	scriptname = 'seqdiagram.diag'
	imagename = 'seqdiagram.png'

	def __init__(self, plugin):
		ImageGeneratorClass.__init__(self, plugin)
		self.diagfile = TmpFile(self.scriptname)
		self.diagfile.touch()
		self.pngfile = File(self.diagfile.path[:-5] + '.png') # len('.diag') == 5

	def generate_image(self, text):
		if isinstance(text, basestring):
			text = text.splitlines(True)

		# Write to tmp file
		self.diagfile.writelines(text)

		# Call seqdiag
		try:
			diag = Application(diagcmd)
			diag.run((self.pngfile, self.diagfile))
		except ApplicationError:
			return None, None # Sorry, no log
		else:
			return self.pngfile, None

	def cleanup(self):
		self.diagfile.remove()
		self.pngfile.remove()
