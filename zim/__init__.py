# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

# Bunch of meta data, used at least in the about dialog
__version__ = '0.42'
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

import gobject
#import zim.plugins


class Component(object):
	'''FIXME'''

	def __init__(self, app):
		self.app = app

	def debug(self, *msg):
		msg = map(unicode, msg)
		lines = ' '.join(msg).encode('utf8').strip().split('\n')
		for line in lines:
			print '# %i %s' % (self.app.pid, line.strip())

	info = debug # TODO separate logging for verbose messages

class Application(gobject.GObject, Component):
	'''FIXME'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'open-notebook': (gobject.SIGNAL_RUN_LAST, None, (object,)),
	}

	def __init__(self, executable='zim', verbose=False, debug=False):
		gobject.GObject.__init__(self)
		self.app = self # make Component methods work
		self.pid = os.getpid()
		self.executable = executable
		self.notebook = None
		self.plugins = []

		if verbose or debug:
			self.info('This is zim %s' % __version__)
			try:
				from zim._version import version_info
				self.debug(
					'branch: %(branch_nick)s\n'
					'revision: %(revno)d %(revision_id)s\n'
					'date: %(date)s\n'
						% version_info )
			except:
				self.debug('No bzr version-info found')
		self.load_config()
		self.load_plugins()

	def load_config(self):
		'''FIXME'''

	def load_plugins(self):
		'''FIXME'''
		plugins = []
		for plugin in plugins:
			self.load_plugin(plugin)

	def load_plugin(self, pluginname):
		'''FIXME'''
		klass = zim.plugins.get_plugin(pluginname)
		plugin = klass(self)
		self.plugins.append(plugin)

	def unload_plugin(self, plugin):
		'''FIXME'''

	def open_notebook(self, notebook):
		'''FIXME'''
		import zim.notebook
		notebook = zim.notebook.get_notebook(notebook)
		self.emit('open-notebook', notebook)

	def do_open_notebook(self, notebook):
		'''FIXME'''
		self.notebook = notebook

	def spawn(self, *argv):
		'''FIXME'''
		argv = list(argv)
		if argv[0] == 'zim':
			argv[0] = self.executable
		self.debug('Spawn process: '+' '.join(['"%s"' % a for a in argv]))
		try:
			pid = os.spawnvp(os.P_NOWAIT, argv[0], argv)
		except AttributeError:
			# spawnvp is not available on windows
			# TODO path lookup ?
			pid = os.spawnv(os.P_NOWAIT, argv[0], argv)
		self.debug('New process: %i' % pid)


# Need to register classes defining gobject signals
gobject.type_register(Application)

