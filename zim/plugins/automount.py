# -*- coding: utf-8 -*-

# Copyright 2011 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Plugin to auto-mount notebooks when needed'''

from zim.plugins import PluginClass

from zim.fs import Dir
from zim.config import get_config
from zim.applications import Application


class AutomountPlugin(PluginClass):

	plugin_info = {
		'name': _('Automount'), # T: plugin name
		'description': _('''\
This plugin can automatically "mount" notebooks when needed. It can
e.g. be used to connect with remote drives or unlock an encrypted drive
when zim is trying to open a specific notebook.

This is a core plugin shipping with zim.
'''), # T: plugin description
		'author': 'Jaap Karssenberg',
		'help': 'Plugins:Automount',
	}

	# this plugin is profile independent
	is_profile_independent = True

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		self.connectto(ui, 'initialize-notebook')

	def get_config(self, uri):
		'''Return the automount config for a specific notebook uri or C{None}
		@param uri: a notebook uri
		@returns: a config dict
		'''
		config = get_config('automount.conf')
		groups = [k for k in config.keys() if k.startswith('Path')]
		for group in groups:
			path = group[4:].strip() # len('Path') = 4
			myuri = Dir(path).uri # Allow "~/Folder" syntax
			if uri.startswith(myuri):
				return config[group]
		else:
			return None

	def on_initialize_notebook(self, ui, uri):
		# check if the notebook exists
		if not uri.startswith('file:') \
		or Dir(uri).file('notebook.zim').exists():
			return

		# if it doesn't, see if we know how to mount it
		config = self.get_config(uri)
		if config and 'mount' in config:
			if 'passwd' in config:
				passwd = self.prompt
			Application(config['mount']).run()
