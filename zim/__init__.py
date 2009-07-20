# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

# Bunch of meta data, used at least in the about dialog
__version__ = '0.42-alpha2'
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
import sys
import gettext
import gobject
import logging

from getopt import gnu_getopt, GetoptError

from zim.fs import *
from zim.config import log_basedirs, data_file, config_file, ConfigDictFile, ZIM_DATA_DIR

if ZIM_DATA_DIR:
	# We are running from a source dir - use the locale data included there
	localedir = ZIM_DATA_DIR.dir.subdir('locale').path
	#~ print "Set localdir to: %s" % localedir
else:
	# Hope the system knows where to find the data
	localedir = None

gettext.install('zim', localedir, unicode=True, names=('_', 'gettext', 'ngettext'))

logger = logging.getLogger('zim')

executable = 'zim'

# All commandline options in various groups
longopts = ('verbose', 'debug')
commands = ('help', 'version', 'gui', 'server', 'export', 'index', 'manual')
commandopts = {
	'gui': (),
	'server': ('port=', 'template=', 'gui'),
	'export': ('format=', 'template=', 'output='),
	'index': ('output=',),
}
shortopts = {
	'v': 'version', 'h': 'help',
	'V': 'verbose', 'D': 'debug',
	'o': 'output='
}
maxargs = {
	'gui': 2, 'server': 1, 'manual': 1,
	'export': 2, 'index': 1
}

# Inline help - do not use __doc__ for this !
usagehelp = '''\
usage: zim [OPTIONS] [NOTEBOOK [PAGE]]
   or: zim --export [OPTIONS] NOTEBOOK [PAGE]
   or: zim --index  [OPTIONS] NOTEBOOK
   or: zim --server [OPTIONS] [NOTEBOOK]
   or: zim --manual [OPTIONS] [PAGE]
   or: zim --help
'''
optionhelp = '''\
General Options:
  --gui           run the editor (this is the default)
  --server        run the web server
  --export        export to a different format
  --index         build an index for a notebook
  --manual        open the user manual
  -V, --verbose   print information to terminal
  -D, --debug     print debug messages
  -v, --version   print version and exit
  -h, --help      print this text

Server Options:
  --port          port to use (defaults to 8080)
  --template      name of the template to use
  --gui           run the gui wrapper for the server

Export Options:
  --format        format to use (defaults to 'html')
  --template      name of the template to use
  -o, --output    output directory

  You can use the export option to print a single page to stdout.
  When exporting a whole notebook you need to provide a directory.

Index Options:
  --output    output file

Try 'zim --manual' for more help.
'''

class UsageError(Exception):
	pass


def main(argv):
	'''Run the main program.'''

	global executable
	executable = argv[0]

	# Let getopt parse the option list
	short = ''.join(shortopts.keys())
	for s, l in shortopts.items():
		if l.endswith('='): short = short.replace(s, s+':')
	long = list(longopts) + list(commands)
	for opts in commandopts.values():
		long.extend(opts)

	opts, args = gnu_getopt(argv[1:], short, long)

	# First figure out which command to execute
	cmd = 'gui' # default
	if opts:
		o = opts[0][0].lstrip('-')
		if o in shortopts:
			o = shortopts[o].rstrip('=')
		if o in commands:
			opts.pop(0)
			cmd = o

	# If it is a simple command execute it and return
	if cmd == 'version':
		print 'zim %s\n' % __version__
		print __copyright__, '\n'
		print __license__
		return
	elif cmd == 'help':
		print usagehelp.replace('zim', executable)
		print optionhelp
		return

	# Otherwise check the number of arguments
	if len(args) > maxargs[cmd]:
		raise UsageError

	# --manual is an alias for --gui _manual_
	if cmd == 'manual':
		cmd = 'gui'
		args.insert(0, '_manual_')

	# Now figure out which options are allowed for this command
	allowedopts = list(longopts)
	allowedopts.extend(commandopts[cmd])

	# Convert options into a proper dict
	optsdict = {}
	for o, a in opts:
		o = o.lstrip('-')
		if o in shortopts:
			o = shortopts[o].rstrip('=')

		if o+'=' in allowedopts:
			optsdict[o] = a
		elif o in allowedopts:
			optsdict[o] = True
		else:
			raise GetoptError, ("--%s no allowed in combination with --%s" % (o, cmd), o)

	# --port is the only option that is not of type string
	if 'port' in optsdict and not optsdict['port'] is None:
		try:
			optsdict['port'] = int(optsdict['port'])
		except ValueError:
			raise GetoptError, ("--port takes an integer argument", 'port')

	# set loggin output level for logging root
	level = logging.WARNING
	if optsdict.pop('verbose', False): level = logging.INFO
	if optsdict.pop('debug', False): level = logging.DEBUG # no "elif" !
	logging.basicConfig(level=level, format='%(levelname)s: %(message)s')

	logger.info('This is zim %s', __version__)
	if level == logging.DEBUG:
		logger.debug('Python version is %s' % str(sys.version_info))
		try:
			from zim._version import version_info
			logger.debug(
				'Zim revision is:\n'
				'\tbranch: %(branch_nick)s\n'
				'\trevision: %(revno)d %(revision_id)s\n'
				'\tdate: %(date)s\n',
				version_info )
		except ImportError:
			logger.debug('No bzr version-info found')

		log_basedirs()

	# Now we determine the class to handle this command
	# and start the application ...
	logger.debug('Running command: %s', cmd)
	if cmd in ('export', 'index'):
		if not len(args) >= 1:
			raise UsageError
		handler = NotebookInterface(notebook=args[0])
		if len(args) == 2: optsdict['page'] = args[1]
		method = getattr(handler, 'cmd_' + cmd)
		method(**optsdict)
	elif cmd == 'gui':
		import zim.gui
		handler = zim.gui.GtkInterface(*args, **optsdict)
		handler.main()
	elif cmd == 'server':
		import zim.www
		handler = zim.www.Server(*args, **optsdict)
		handler.main()



class NotebookInterface(gobject.GObject):
	'''Application wrapper for a notebook. Base class for GtkInterface
	and WWWInterface classes.

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

		self.preferences = config_file('preferences.conf')
		self.uistate = None

		if not notebook is None:
			self.open_notebook(notebook)

	def load_plugins(self):
		'''Load the plugins defined in the preferences'''
		plugins = ['calendar', 'spell', 'linkmap', 'printtobrowser'] # FIXME: get from config
		for plugin in plugins:
			self.load_plugin(plugin)

	def load_plugin(self, plugin):
		'''Load a single plugin.
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
		'''Remove a plugin'''
		print 'TODO: unload plugin', plugin
		#~ logger.debug('Unloaded plugin %s', pluginname)

	def open_notebook(self, notebook):
		'''Open a notebook if no notebook was set already.
		'noetbook' can be either a string or a notebook object.
		'''
		import zim.notebook
		if isinstance(notebook, basestring):
			notebook = zim.notebook.get_notebook(notebook)
		self.emit('open-notebook', notebook)

	def do_open_notebook(self, notebook):
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
		'''Spawn a sub process'''
		argv = list(argv)
		argv = map(lambda a: unicode(a).encode('utf-8'), argv)
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


