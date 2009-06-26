# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

# Bunch of meta data, used at least in the about dialog
__version__ = '0.42-alpha1'
__url__='http://www.zim-wiki.org'
__author__ = 'Jaap Karssenberg <pardus@cpan.org>'
__copyright__ = 'Copyright 2008 Jaap Karssenberg <pardus@cpan.org>'
__license__='''\
This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
'''

import os
import logging
import gobject

from zim.fs import *
from zim.config import config_file, ConfigDictFile

logger = logging.getLogger('zim')
executable = 'zim'

class NotebookInterface(gobject.GObject):
	'''FIXME

	Subclasses can prove a class attribute "ui_type" to tell plugins what
	interface they support. This can be "gtk" or "html". If "ui_type" is None
	we run without interface (e.g. commandline export).
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'open-notebook': (gobject.SIGNAL_RUN_LAST, None, (object,)),
	}

	ui_type = None

	def __init__(self, notebook=None):
		gobject.GObject.__init__(self)
		self.notebook = None
		self.plugins = []

		logger.info('This is zim %s', __version__)
		try:
			from zim._version import version_info
			logger.debug(
				'branch: %(branch_nick)s\n'
				'revision: %(revno)d %(revision_id)s\n'
				'date: %(date)s\n',
				version_info )
		except ImportError:
			logger.debug('No bzr version-info found')

		self.preferences = config_file('preferences.conf')
		self.uistate = {}

		if not notebook is None:
			self.open_notebook(notebook)

	def load_plugins(self):
		'''FIXME'''
		plugins = ['spell', 'linkmap', 'printtobrowser'] # FIXME: get from config
		for plugin in plugins:
			self.load_plugin(plugin)

	def load_plugin(self, plugin):
		'''FIXME
		"plugin" can either be a pluginname or a plugin class
		'''
		if isinstance(plugin, basestring):
			import zim.plugins
			klass = zim.plugins.get_plugin(plugin)
		else:
			klass = plugin
		plugin = klass(self)
		self.plugins.append(plugin)
		logger.debug('Loaded plugin %s', plugin)

	def unload_plugin(self, plugin):
		'''FIXME'''
		print 'TODO: unload plugin', plugin
		#~ logger.debug('Unloaded plugin %s', pluginname)

	def open_notebook(self, notebook):
		'''FIXME'''
		import zim.notebook
		if isinstance(notebook, basestring):
			notebook = zim.notebook.get_notebook(notebook)
		self.emit('open-notebook', notebook)

	def do_open_notebook(self, notebook):
		'''FIXME'''
		self.notebook = notebook
		if notebook.cache_dir:
			# may not exist during tests
			self.uistate = ConfigDictFile(
				notebook.cache_dir.file('state.conf') )
		# TODO read profile preferences file if one is set in the notebook

	def cmd_export(self, format='html', template=None, page=None, output=None):
		'''Method called when doing a commandline export'''
		import zim.exporter
		exporter = zim.exporter.Exporter(self.notebook, format, template)

		if page:
			path = self.notebook.resolve_path(page)
			page = self.notebook.get_page(path)

		if page and output is None:
			import sys
			exporter.export_page_to_fh(sys.stdout, page)
		elif not output:
			logger.error('Need output directory to export notebook')
		else:
			dir = Dir(output)
			if page:
				exporter.export_page(dir, page)
			else:
				self.notebook.index.update()
				exporter.export_all(dir)

	def cmd_index(self, output=None):
		'''Method called when doing a commandline index re-build'''
		if not output is None:
			import zim.index
			index = zim.index.Index(self.notebook, output)
		else:
			index = self.notebook.index
		index.flush()
		def on_callback(path):
			logger.info('Indexed %s', path.name)
			return True
		index.update(callback=on_callback)

	def spawn(self, *argv):
		'''FIXME'''
		argv = list(argv)
		if argv[0] == 'zim':
			argv[0] = executable
		logger.info('Spawn process: %s', ' '.join(['"%s"' % a for a in argv]))
		try:
			pid = os.spawnvp(os.P_NOWAIT, argv[0], argv)
		except AttributeError:
			# spawnvp is not available on windows
			# TODO path lookup ?
			pid = os.spawnv(os.P_NOWAIT, argv[0], argv)
		logger.debug('New process: %i', pid)


# Need to register classes defining gobject signals
gobject.type_register(NotebookInterface)
