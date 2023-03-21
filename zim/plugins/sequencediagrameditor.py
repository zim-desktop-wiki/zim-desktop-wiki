
# Copyright 2011 Greg Warner <gdwarner@gmail.com>
# (Pretty much copied from diagrameditor.py)

import logging

from zim.plugins import PluginClass
from zim.plugins.base.imagegenerator import \
	ImageGeneratorClass, BackwardImageGeneratorObjectType

from zim.newfs import LocalFile, TmpFile
from zim.applications import Application, ApplicationError
from zim.gui.widgets import supports_image_format

logger = logging.getLogger('zim.plugins.sequencediagrameditor')

def get_cmd(fmt):
	return ('seqdiag', '-T', fmt, '-o')


class InsertSequenceDiagramPlugin(PluginClass):

	plugin_info = {
		'name': _('Insert Sequence Diagram'), # T: plugin name
		'description': _('''\
This plugin provides a sequence diagram editor for zim based on seqdiag.
It allows easy editing of sequence diagrams.
'''), # T: plugin description
		'help': 'Plugins:Sequence Diagram Editor',
		'author': 'Greg Warner',
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
		has_diagcmd = Application(get_cmd('png')).tryexec()
		return has_diagcmd, [("seqdiag", has_diagcmd, True)]


class BackwardSequenceDiagramImageObjectType(BackwardImageGeneratorObjectType):

	name = 'image+seqdiagram'
	label = _('Sequence Diagram') # T: menu item
	syntax = None
	scriptname = 'seqdiagram.diag'


class SequenceDiagramGenerator(ImageGeneratorClass):
	@property
	def _pref_format(self):
		return 'svg' if self.plugin.preferences['prefer_svg'] else 'png'

	@property
	def imagefile_extension(self):
		return '.' + self._pref_format

	@property
	def diagcmd(self):
		return get_cmd(self._pref_format)

	def __init__(self, plugin, notebook, page):
		ImageGeneratorClass.__init__(self, plugin, notebook, page)
		self.diagfile = TmpFile('seqdiagram.diag')
		self.diagfile.touch()

	def generate_image(self, text):
		# Write to tmp file
		self.diagfile.write(text)
		self.imgfile = LocalFile(self.diagfile.path[:-5] + self.imagefile_extension) # len('.diag') == 5
		logger.debug('Writing diagram to temp file: %s', self.imgfile)

		# Call seqdiag
		try:
			diag = Application(self.diagcmd)
			diag.run((self.imgfile, self.diagfile))
		except ApplicationError:
			return None, None # Sorry, no log
		else:
			return self.imgfile, None

	def cleanup(self):
		self.diagfile.remove()
		try:
			self.imgfile.remove()
		except AttributeError:
			logger.debug('Closed dialog before generating image, nothing to remove')
