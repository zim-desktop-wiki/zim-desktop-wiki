# Copyright 2024 Radu Potop <radu@wooptoo.com>

import logging
import os
import shutil

from zim.plugins import PluginClass
from zim.plugins.base.imagegenerator import (
	ImageGeneratorClass,
	BackwardImageGeneratorObjectType,
)

from zim.newfs import LocalFile, TmpFile
from zim.applications import Application, ApplicationError

logger = logging.getLogger('zim.plugins.mermaiddiagrameditor')


def get_cmd(fmt):
	# On Windows, npm installs mmdc as "mmdc.cmd", which Popen won't find by its
	# bare name, so use the full path of whichever mmdc file is on PATH
	mmdc = shutil.which('mmdc') if os.name == 'nt' else None
	mmdc = os.path.abspath(mmdc) if mmdc else 'mmdc'
	return (mmdc, '-q', '-e', fmt, '-b', 'transparent', '-i')


class InsertMermaidDiagramPlugin(PluginClass):
	plugin_info = {
		'name': _('Insert Mermaid Diagram'),  # T: plugin name
		'description': _('''\
This plugin provides a Mermaid diagram editor for zim.
It allows easy editing of Mermaid diagrams.
'''),  # T: plugin description
		'help': 'Plugins:Mermaid Diagram Editor',
		'author': 'Radu Potop',
	}

	## Disabled because generating SVGs is buggy.
	## Sequence diagrams work fine, but Flowcharts and Class diagrams fail to
	## render labels.
	##
	## Bug report: https://github.com/mermaid-js/mermaid-cli/issues/691

	# plugin_preferences = (
	#	  # key, type, label, default
	#	  (
	#		  'prefer_svg',
	#		  'bool',
	#		  _('Generate diagrams in SVG format'),	 # T: plugin preference
	#		  supports_image_format('svg'),
	#	  ),
	# )

	@classmethod
	def check_dependencies(klass):
		has_diagcmd = Application(get_cmd('png')).tryexec()
		return has_diagcmd, [('mmdc', has_diagcmd, True)]


class BackwardMermaidDiagramImageObjectType(BackwardImageGeneratorObjectType):
	name = 'image+mermaid'
	label = _('Mermaid Diagram')  # T: menu item
	syntax = None
	scriptname = 'mermaid-diagram.mmd'


class MermaidDiagramGenerator(ImageGeneratorClass):
	@property
	def _pref_format(self):
		return 'png'

	@property
	def imagefile_extension(self):
		return '.' + self._pref_format

	@property
	def diagcmd(self):
		return get_cmd(self._pref_format)

	def __init__(self, plugin, notebook, page):
		ImageGeneratorClass.__init__(self, plugin, notebook, page)
		self.mmdfile = TmpFile('mermaid-diagram.mmd')
		self.mmdfile.touch()

	def generate_image(self, text):
		# Write to tmp file
		self.mmdfile.write(text)
		self.imgfile = LocalFile(self.mmdfile.path[:-4] + self.imagefile_extension)
		logger.debug('Writing diagram to temp file: %s', self.imgfile)

		# Call mmdc
		try:
			diag = Application(self.diagcmd)
			diag.run((self.mmdfile, '-o', self.imgfile))
		except ApplicationError as e:
			logger.debug('Generating diagram failed with error: %s', e)
			return None, None
		else:
			return self.imgfile, None

	def cleanup(self):
		self.mmdfile.remove()
		try:
			self.imgfile.remove()
		except AttributeError:
			logger.debug('Closed dialog before generating image, nothing to remove')
