# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# Bunch of meta data, used at least in the about dialog
__version__ = '0.52'
__url__='http://www.zim-wiki.org'
__author__ = 'Jaap Karssenberg <jaap.karssenberg@gmail.com>'
__copyright__ = 'Copyright 2008 - 2011 Jaap Karssenberg <jaap.karssenberg@gmail.com>'
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

import zim.fs
from zim.fs import *
from zim.errors import Error
from zim.config import data_dir, config_file, log_basedirs, ZIM_DATA_DIR


logger = logging.getLogger('zim')

if ZIM_DATA_DIR:
	# We are running from a source dir - use the locale data included there
	localedir = ZIM_DATA_DIR.dir.subdir('locale').path
	#~ print "Set localdir to: %s" % localedir
else:
	# Hope the system knows where to find the data
	localedir = None

gettext.install('zim', localedir, unicode=True, names=('_', 'gettext', 'ngettext'))

ZIM_EXECUTABLE = 'zim'


# All commandline options in various groups
longopts = ('verbose', 'debug')
commands = ('help', 'version', 'gui', 'server', 'export', 'index', 'manual', 'plugin', 'daemon')
commandopts = {
	'gui': ('list', 'geometry=', 'fullscreen', 'no-daemon'),
	'server': ('port=', 'template=', 'gui', 'no-daemon'),
	'export': ('format=', 'template=', 'output=', 'root-url=', 'index-page='),
	'index': ('output=',),
	'plugin': (),
	'daemon': (),
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
   or: zim --plugin PLUGIN [ARGUMENTS]
   or: zim --manual [OPTIONS] [PAGE]
   or: zim --help
'''
optionhelp = '''\
General Options:
  --gui           run the editor (this is the default)
  --server        run the web server
  --export        export to a different format
  --index         build an index for a notebook
  --plugin        call a specific plugin function
  --manual        open the user manual
  -V, --verbose   print information to terminal
  -D, --debug     print debug messages
  -v, --version   print version and exit
  -h, --help      print this text

GUI Options:
  --list          show the list with notebooks instead of
                  opening the default notebook
  --geometry      window size and position as WxH+X+Y
  --fullscreen    start in fullscreen mode
  --no-daemon     start a single instance, no daemon

Server Options:
  --port          port to use (defaults to 8080)
  --template      name of the template to use
  --gui           run the gui wrapper for the server

Export Options:
  --format        format to use (defaults to 'html')
  --template      name of the template to use
  -o, --output    output directory
  --root-url      url to use for the document root
  --index-page    index page name

  You can use the export option to print a single page to stdout.
  When exporting a whole notebook you need to provide a directory.

Index Options:
  -o, --output    output file

Try 'zim --manual' for more help.
'''


class UsageError(Error):
	pass


class NotebookLookupError(Error):

	description = _('Could not find the file or folder for this notebook')
		# T: Error verbose description


def _get_default_or_only_notebook():
	# Helper used below to decide a good default to open
	from zim.notebook import get_notebook_list
	notebooks = get_notebook_list()
	if notebooks.default:
		return notebooks.default.uri
	elif len(notebooks) == 1:
		return notebooks[0].uri
	else:
		return None


def main(argv):
	'''Run the main program.'''
	global ZIM_EXECUTABLE

	# FIXME - this returns python.exe on my windows test
	ZIM_EXECUTABLE = argv[0]
	zim_exec_file = File(ZIM_EXECUTABLE)
	if zim_exec_file.exists():
		# We were given an absolute path, e.g. "python ./zim.py"
		ZIM_EXECUTABLE = zim_exec_file.path

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
		print usagehelp.replace('zim', argv[0])
		print optionhelp
		return

	# Otherwise check the number of arguments
	if cmd in maxargs and len(args) > maxargs[cmd]:
		raise UsageError

	# --manual is an alias for --gui /usr/share/zim/manual
	if cmd == 'manual':
		cmd = 'gui'
		args.insert(0, data_dir('manual').path)

	# Now figure out which options are allowed for this command
	allowedopts = list(longopts)
	allowedopts.extend(commandopts[cmd])

	# Convert options into a proper dict
	optsdict = {}
	for o, a in opts:
		o = str(o.lstrip('-')) # str() -> no unicode for keys
		if o in shortopts:
			o = shortopts[o].rstrip('=')

		if o+'=' in allowedopts:
			o = o.replace('-', '_')
			optsdict[o] = a
		elif o in allowedopts:
			o = o.replace('-', '_')
			optsdict[o] = True
		else:
			raise GetoptError, ("--%s is not allowed in combination with --%s" % (o, cmd), o)

	# --port is the only option that is not of type string
	if 'port' in optsdict and not optsdict['port'] is None:
		try:
			optsdict['port'] = int(optsdict['port'])
		except ValueError:
			raise GetoptError, ("--port takes an integer argument", 'port')

	# set logging output level for logging root (format has been set in zim.py)
	if not ZIM_EXECUTABLE[-4:].lower() == '.exe':
		# for most platforms
		level = logging.WARN
	else:
		# if running from Windows compiled .exe
		level = logging.ERROR
	if optsdict.pop('verbose', False): level = logging.INFO
	if optsdict.pop('debug', False): level = logging.DEBUG # no "elif" !
	logging.getLogger().setLevel(level)

	logger.info('This is zim %s', __version__)
	if level == logging.DEBUG:
		logger.debug('Python version is %s', str(sys.version_info))
		logger.debug('Platform is %s', os.name)
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
			default = _get_default_or_only_notebook()
			handler = NotebookInterface(notebook=default)
		else:
			handler = NotebookInterface(notebook=args[0])

		handler.load_plugins() # should this go somewhere else ?

		if len(args) == 2:
			optsdict['page'] = args[1]

		method = getattr(handler, 'cmd_' + cmd)
		method(**optsdict)
	elif cmd == 'gui':
		notebook = None
		page = None
		if args:
			from zim.notebook import resolve_notebook
			notebook, page = resolve_notebook(args[0])
			if not notebook:
				notebook = File(args[0]).uri
				# make sure daemon approves of this uri and proper
				# error dialog is shown as a result by GtkInterface
			if len(args) == 2:
				page = args[1]

		if 'list' in optsdict:
			del optsdict['list'] # do not use default
		elif not notebook:
			import zim.notebook
			default = _get_default_or_only_notebook()
			if default:
				notebook = default
				logger.info('Opening default notebook')

		if 'no_daemon' in optsdict or os.name == 'nt':
			import zim.gui
			try:
				del optsdict['no_daemon']
			except KeyError:
				pass
			if not notebook:
				import zim.gui.notebookdialog
				notebook = zim.gui.notebookdialog.prompt_notebook()
				if not notebook:
					return # User cancelled notebook dialog
			handler = zim.gui.GtkInterface(notebook, page, **optsdict)
			handler.main()
		else:
			import zim.daemon
			proxy = zim.daemon.DaemonProxy()
			if not notebook:
				# Need to call this after spawning the daemon, else we
				# have gtk loaded in the daemon process, and that causes
				# problems with using gtk in child processes.
				import zim.gui.notebookdialog
				notebook = zim.gui.notebookdialog.prompt_notebook()
				if not notebook:
					proxy.quit_if_nochild()
					return # User cancelled notebook dialog
			gui = proxy.get_notebook(notebook)

			gui.present(page, **optsdict)
	elif cmd == 'server':
		try:
			del optsdict['no_daemon']
		except KeyError:
			pass

		import zim.www
		handler = zim.www.Server(*args, **optsdict)
		handler.main()
	elif cmd == 'daemon':
		# just start the daemon, nothing else
		import zim.daemon
		proxy = zim.daemon.DaemonProxy()
		proxy.ping()
	elif cmd == 'plugin':
		import zim.plugins
		try:
			pluginname = args.pop(0)
		except IndexError:
			raise UsageError
		module = zim.plugins.get_plugin_module(pluginname)
		module.main(None, *args)


class NotebookInterface(gobject.GObject):
	'''Application wrapper for a notebook. Base class for GtkInterface
	and WWWInterface classes.

	Subclasses can prove a class attribute "ui_type" to tell plugins what
	interface they support. This can be "gtk" or "html". If "ui_type" is None
	we run without interface (e.g. commandline export).

	Signals:
	* open-notebook (notebook)
	  Emitted to open a notebook in this interface
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
		default = ['calendar', 'insertsymbol', 'printtobrowser', 'versioncontrol']
		self.preferences['General'].setdefault('plugins', default)
		plugins = self.preferences['General']['plugins']
		plugins = set(plugins) # Eliminate doubles
		# Plugins should not have dependency on order of being added
		# just add sort to make behavior predictable.
		for name in sorted(plugins):
			self.load_plugin(name)

		loaded = [p.plugin_key for p in self.plugins]
		if set(loaded) != plugins:
			self.preferences['General']['plugins'] = sorted(loaded)

	def load_plugin(self, name):
		'''Load a single plugin by name, returns boolean for success'''
		assert isinstance(name, basestring)
		import zim.plugins
		try:
			klass = zim.plugins.get_plugin(name)
			if not klass.check_dependencies_ok():
				raise AssertionError, 'Dependencies failed for plugin %s' % name
			plugin = klass(self)
		except:
			logger.exception('Failed to load plugin %s', name)
			return None
		else:
			self.plugins.append(plugin)
			logger.debug('Loaded plugin %s (%s)', name, plugin)

		plugin.plugin_key = name
		if not name in self.preferences['General']['plugins']:
			self.preferences['General']['plugins'].append(name)

		return plugin

	def unload_plugin(self, plugin):
		'''Remove a plugin'''
		if isinstance(plugin, basestring):
			name = plugin
			assert name in map(lambda p: p.plugin_key, self.plugins)
			plugin = filter(lambda p: p.plugin_key == name, self.plugins)[0]
		else:
			assert plugin in self.plugins
			name = plugin.plugin_key

		plugin.disconnect()
		self.plugins.remove(plugin)
		logger.debug('Unloaded plugin %s', name)

		self.preferences['General']['plugins'].remove(name)
		self.preferences.write()

	def open_notebook(self, notebook):
		'''Open a notebook if no notebook was set already.
		'notebook' can be either a string, a File or Dir object or a
		Notebook object.

		If the notebook is a string which also specifies a page the page
		path is returned so it can be handled in a sub-class.
		'''
		from zim.notebook import resolve_notebook, get_notebook, Notebook
		assert self.notebook is None, 'BUG: other notebook opened already'
		assert not notebook is None, 'BUG: no notebook specified'

		logger.debug('Opening notebook: %s', notebook)
		if isinstance(notebook, (basestring, File, Dir)):
			if isinstance(notebook, basestring):
				nb, path = resolve_notebook(notebook)
			else:
				nb, path = notebook, None

			if not nb is None:
				for plugin in self.plugins:
					uri = nb.uri
					plugin.initialize_notebook(uri)
				nb = get_notebook(nb)

			if nb is None:
				raise NotebookLookupError, _('Could not find notebook: %s') % notebook
					# T: Error when looking up a notebook

			self.emit('open-notebook', nb)
			return path
		else:
			assert isinstance(notebook, Notebook)
			self.emit('open-notebook', notebook)
			return None

	def do_open_notebook(self, notebook):
		assert self.notebook is None, 'BUG: other notebook opened already'
		self.notebook = notebook
		if notebook.cache_dir:
			# may not exist during tests
			from zim.config import ConfigDictFile
			self.uistate = ConfigDictFile(
				notebook.cache_dir.file('state.conf') )
		# TODO read profile preferences file if one is set in the notebook

	def cmd_export(self, format='html', template=None, page=None, output=None, root_url=None, index_page=None):
		'''Method called when doing a commandline export'''
		import zim.exporter
		exporter = zim.exporter.Exporter(self.notebook, format, template, document_root_url=root_url, index_page=index_page)

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

	def spawn(self, *args):
		'''Spawn a new instance of zim'''
		# TODO: after implementing the daemon, put this in that module
		from zim.applications import Application
		zim = Application((ZIM_EXECUTABLE,) + args)
		zim.spawn()

# Need to register classes defining gobject signals
gobject.type_register(NotebookInterface)


