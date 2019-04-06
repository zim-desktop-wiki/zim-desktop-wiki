
# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from zim.plugins import PluginClass
from zim.plugins.base.imagegenerator import \
	ImageGeneratorClass, BackwardImageGeneratorObjectType

from zim.fs import File, TmpFile
from zim.config import data_file
from zim.applications import Application, ApplicationError


# TODO put these commands in preferences
dotcmd = ('dot', '-Tpng', '-o')


class InsertDiagramPlugin(PluginClass):

	plugin_info = {
		'name': _('Insert Diagram'), # T: plugin name
		'description': _('''\
This plugin provides a diagram editor for zim based on GraphViz.

This is a core plugin shipping with zim.
'''), # T: plugin description
		'help': 'Plugins:Diagram Editor',
		'author': 'Jaap Karssenberg',
	}

	@classmethod
	def check_dependencies(klass):
		has_dotcmd = Application(dotcmd).tryexec()
		return has_dotcmd, [("GraphViz", has_dotcmd, True)]


class BackwardDiagramImageObjectType(BackwardImageGeneratorObjectType):

	name = 'image+diagram'
	label = _('Diagram') # T: menu item
	syntax = 'dot'
	scriptname = 'diagram.dot'
	imagefile_extension = '.png'


class DiagramGenerator(ImageGeneratorClass):

	def __init__(self, plugin, notebook, page):
		ImageGeneratorClass.__init__(self, plugin, notebook, page)
		self.dotfile = TmpFile('diagram.dot')
		self.dotfile.touch()
		self.pngfile = File(self.dotfile.path[:-4] + '.png') # len('.dot') == 4

	def generate_image(self, text):
		# Write to tmp file
		self.dotfile.write(text)

		# Call GraphViz
		try:
			dot = Application(dotcmd)
			dot.run((self.pngfile, self.dotfile))
		except ApplicationError:
			return None, None # Sorry, no log
		else:
			if self.pngfile.exists():
				return self.pngfile, None
			else:
				# When supplying a dot file with a syntax error, the dot command
				# doesn't return an error code (so we don't raise
				# ApplicationError), but we still don't have a png file to
				# return, so return None.
				return None, None

	def cleanup(self):
		self.dotfile.remove()
		self.pngfile.remove()
