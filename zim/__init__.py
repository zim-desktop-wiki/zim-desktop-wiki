# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

__version__ = '0.60'
__author__ = 'Jaap Karssenberg <pardus@cpan.org>'
__copyright__ = '''\
Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

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
		print '# %i %s' % (self.app.pid, ' '.join(msg).encode('utf8'))


class Application(gobject.GObject, Component):
	'''FIXME'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'open-notebook': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE,
			(gobject.TYPE_PYOBJECT,) ),
	}

	def __init__(self, **opts):
		gobject.GObject.__init__(self)
		self.app = self # make Component methods work
		self.pid = os.getpid()
		self.notebook = None
		self.plugins = []
		# TODO use opts['verbose']
		# TODO use opts['debug']
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


# Need to register classes defining gobject signals
gobject.type_register(Application)

