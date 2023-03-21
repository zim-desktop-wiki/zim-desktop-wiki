
# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import logging

from zim.plugins import PluginClass
from zim.plugins.base.imagegenerator import \
	ImageGeneratorClass, BackwardImageGeneratorObjectType

from zim.newfs import LocalFile, TmpFile
from zim.applications import Application, ApplicationError
from zim.gui.widgets import supports_image_format

logger = logging.getLogger('zim.plugins.diagrameditor')

def get_cmd(fmt):
	return ('dot', f'-T{fmt}', '-o')


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

	plugin_preferences = (
		# key, type, label, default
		(
			'prefer_svg',
			'bool',
			_('Generate diagrams in SVG format'),
			supports_image_format('svg')
		),
	)

	@classmethod
	def check_dependencies(klass):
		has_dotcmd = Application(get_cmd('png')).tryexec()
		return has_dotcmd, [("GraphViz", has_dotcmd, True)]


class BackwardDiagramImageObjectType(BackwardImageGeneratorObjectType):

	name = 'image+diagram'
	label = _('Diagram') # T: menu item
	syntax = 'dot'
	scriptname = 'diagram.dot'


class DiagramGenerator(ImageGeneratorClass):

	@property
	def _pref_format(self):
		return 'svg' if self.plugin.preferences['prefer_svg'] else 'png'

	@property
	def imagefile_extension(self):
		return '.' + self._pref_format

	@property
	def dotcmd(self):
		return get_cmd(self._pref_format)

	def __init__(self, plugin, notebook, page):
		ImageGeneratorClass.__init__(self, plugin, notebook, page)
		self.dotfile = TmpFile('diagram.dot')
		self.dotfile.touch()

	def generate_image(self, text):
		# Write to tmp file
		self.dotfile.write(text)
		self.imgfile = LocalFile(self.dotfile.path[:-4] + self.imagefile_extension) # len('.dot') == 4
		logger.debug('Writing diagram to temp file: %s', self.imgfile)

		# Call GraphViz
		try:
			dot = Application(self.dotcmd)
			dot.run((self.imgfile, self.dotfile))
		except ApplicationError:
			return None, None # Sorry, no log
		else:
			if self.imgfile.exists():
				return self.imgfile, None
			else:
				# When supplying a dot file with a syntax error, the dot command
				# doesn't return an error code (so we don't raise
				# ApplicationError), but we still don't have a png file to
				# return, so return None.
				return None, None

	def cleanup(self):
		self.dotfile.remove()
		try:
			self.imgfile.remove()
		except AttributeError:
			logger.debug('Closed dialog before generating image, nothing to remove')
