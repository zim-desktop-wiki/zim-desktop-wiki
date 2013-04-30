# -*- coding: utf-8 -*-

# Copyright 2008-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

'''
This module contains the base class for the zim application and the main
function. The rest of the implementation is divided over it's sub-modules.

B{NOTE:} There is also some generic development documentation in the
"HACKING" folder in the source distribution. Please also have a look
at that if you want to help with zim development.

In this API documentation many of the methods with names starting with
C{do_} and C{on_} are not documented. The reason is that these are
signal handlers that are not part of the external API. They act upon
a signal but should never be called directly by other objects.


Overview
========

The script C{zim.py} is a thin wrapper around the L{main()} function
defined here. THe main function validates commandline options and if
all is well it either calls the background process to connect to some
running instance of zim, or it instantiates a L{NotebookInterface}
object, or an object of a subclass like L{GtkInterface} (for the
graphic user interface) or L{WWWInterface} (for the webinterface).

The L{NotebookInterface} class takes care of connecting to a L{Notebook}
object and help with e.g. loading plugins and config files. It's
subclasses build on top of this to implement specific user interfaces.
The graphical user interface is implemented in the L{zim.gui} module
and it's sub-modules. The webinterface is implemented in L{zim.www}.

The graphical interface uses a background process to coordinate
between instances, this is implemented in L{zim.ipc}.

Regardsless of the interface choosen there is a L{Notebook} object
which implements a generic API for accessing and storing pages and
other data in the notebook. The notebook object is agnostic about the
actual source of the data (files, database, etc.), this is implemented
by "store" objects which handle a specific storage model. Storage models
live below the L{zim.stores} module; e.g. the default mapping of a
notebook to a folder with one file per page is implemented in the module
L{zim.stores.files}.

The notebook works together with an L{Index} object which keeps a
database of all the pages to speed up notebook access and allows us
to e.g. show a list of pages in the side pane of the user interface.

Another aspect of the notebook is the parsing of the wiki text in the
pages and contruct a tree model of the formatting that can be shown
in the interface or exported to another format like HTML. There are
several parsers which live below L{zim.formats}. The exporting is done
by L{zim.exporter} and L{zim.templates} implements the template
engine.

Many classes in zim have signals which allow other objects to connect
to a listen for specific events. This allows for an event driven chain
of control, which is mainly used in the graphical interface. If you are
not familiar with event driven programs please refer to a Gtk manual.


Infrastructure classes
======================

All functions and objects to interact with the file system can be
found in L{zim.fs}. For all functionality related to config files
see L{zim.config}. For executing external applications see
L{zim.applications} or L{zim.gui.applications}.

For asynchronous actions see L{zim.async}.



@newfield signal: Signal, Signals
@newfield emits: Emits, Emits
@newfield implementation: Implementation
'''
# New epydoc fields defined above are inteded as follows:
# @signal: signal-name (param1, param2): description
# @emits: signal
# @implementation: must implement / optional for sub-classes


# Bunch of meta data, used at least in the about dialog
__version__ = '0.60'
__url__='http://www.zim-wiki.org'
__author__ = 'Jaap Karssenberg <jaap.karssenberg@gmail.com>'
__copyright__ = 'Copyright 2008 - 2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>'
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

from zim.fs import File, Dir
from zim.errors import Error
from zim.config import data_dir, config_file, get_config, log_basedirs, \
	ZIM_DATA_DIR, ConfigDictFile


logger = logging.getLogger('zim')


if ZIM_DATA_DIR:
	# We are running from a source dir - use the locale data included there
	localedir = ZIM_DATA_DIR.dir.subdir('locale').path
	#~ print "Set localdir to: %s" % localedir
else:
	# Hope the system knows where to find the data
	localedir = None

gettext.install('zim', localedir, unicode=True, names=('_', 'gettext', 'ngettext'))


#: This parameter can be set by ./setup.py, can be e.g. "maemo"
PLATFORM = None

#: Executable for starting new zim instances, set by main()
ZIM_EXECUTABLE = 'zim'


# All commandline options in various groups
longopts = ('verbose', 'debug')
commands = (
	'help', 'version', 'gui', 'server', 'export', 'search',
	'index', 'manual', 'plugin', 'ipc-server',
)
commandopts = {
	'gui': ('list', 'geometry=', 'fullscreen', 'standalone'),
	'server': ('port=', 'template=', 'gui', 'standalone'),
	'export': ('format=', 'template=', 'output=', 'root-url=', 'index-page='),
	'search': (),
	'index': ('output=',),
	'plugin': (),
}
shortopts = {
	'v': 'version', 'h': 'help',
	'V': 'verbose', 'D': 'debug',
	'o': 'output='
}
maxargs = {
	'gui': 2, 'server': 1, 'manual': 1,
	'export': 2, 'index': 1, 'search': 2,
}

# Inline help - do not use __doc__ for this !
usagehelp = '''\
usage: zim [OPTIONS] [NOTEBOOK [PAGE]]
   or: zim --server [OPTIONS] [NOTEBOOK]
   or: zim --export [OPTIONS] NOTEBOOK [PAGE]
   or: zim --search NOTEBOOK QUERY
   or: zim --index  [OPTIONS] NOTEBOOK
   or: zim --plugin PLUGIN [ARGUMENTS]
   or: zim --manual [OPTIONS] [PAGE]
   or: zim --help
'''
optionhelp = '''\
General Options:
  --gui           run the editor (this is the default)
  --server        run the web server
  --export        export to a different format
  --search        run a search query on a notebook
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
  --standalone     start a single instance, no background process

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

Search Options:
  None

Index Options:
  -o, --output    output file

Try 'zim --manual' for more help.
'''


class UsageError(Error):
	'''Error when commandline usage is not correct'''

	def __init__(self):
		self.msg = usagehelp.replace('zim', ZIM_EXECUTABLE)


class NotebookLookupError(Error):
	'''Error when failing to locate a notebook'''

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


def get_zim_revision():
	'''Returns multiline string with bazaar revision info, if any.
	Otherwise a string saying no info was found. Intended for debug
	logging.
	'''
	try:
		from zim._version import version_info
		return '''\
Zim revision is:
  branch: %(branch_nick)s
  revision: %(revno)s %(revision_id)s
  date: %(date)s''' % version_info
	except ImportError:
		return 'No bzr version-info found'


def main(argv):
	'''Run the main program

	Depending on the commandline given and whether or not there is
	an instance of zim running already, this method may return
	immediatly, or go into the mainloop untill the program is exitted.

	@param argv: commandline arguments, e.g. from C{sys.argv}

	@raises UsageError: when number of arguments is not correct
	@raises GetOptError: when invalid options are found
	'''
	global ZIM_EXECUTABLE

	# FIXME - this returns python.exe on my windows test
	ZIM_EXECUTABLE = argv[0]
	zim_exec_file = File(ZIM_EXECUTABLE)
	if zim_exec_file.exists():
		# We were given an absolute path, e.g. "python ./zim.py"
		ZIM_EXECUTABLE = zim_exec_file.path

	# Check for special commandline args for ipc, does not return
	# if handled
	import zim.ipc
	zim.ipc.handle_argv()

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
		logger.debug(get_zim_revision())
		log_basedirs()

	# Now we determine the class to handle this command
	# and start the application ...
	logger.debug('Running command: %s', cmd)
	if cmd in ('export', 'index', 'search'):
		if not len(args) >= 1:
			default = _get_default_or_only_notebook()
			if not default:
				raise UsageError
			handler = NotebookInterface(notebook=default)
		else:
			handler = NotebookInterface(notebook=args[0])

		handler.load_plugins() # should this go somewhere else ?

		if cmd == 'search':
			if not len(args) == 2: raise UsageError
			optsdict['query'] = args[1]
		elif len(args) == 2:
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

		if 'standalone' in optsdict:
			import zim.gui
			del optsdict['standalone']
			if not notebook:
				import zim.gui.notebookdialog
				notebook = zim.gui.notebookdialog.prompt_notebook()
				if not notebook:
					return # User canceled notebook dialog
			handler = zim.gui.GtkInterface(notebook, page, **optsdict)
			handler.main()
		else:
			from zim.ipc import start_server_if_not_running, ServerProxy
			if not notebook:
				import zim.gui.notebookdialog
				notebook = zim.gui.notebookdialog.prompt_notebook()
				if not notebook:
					return # User canceled notebook dialog

			start_server_if_not_running()
			server = ServerProxy()
			gui = server.get_notebook(notebook)
			gui.present(page, **optsdict)

			logger.debug('''
NOTE FOR BUG REPORTS:
	At this point zim has send the command to open a notebook to a
	background process and the current process will now quit.
	If this is the end of your debug output it is probably not useful
	for bug reports. Please close all zim windows, quit the
	zim trayicon (if any), and try again.
''')
	elif cmd == 'server':
		standalone = optsdict.pop('standalone', False)
			# No daemon support for server, so no option doesn't
			# do anything for now
		gui = optsdict.pop('gui', False)
		if gui:
			import zim.gui.server
			zim.gui.server.main(*args, **optsdict)
		else:
			import zim.www
			zim.www.main(*args, **optsdict)
	elif cmd == 'plugin':
		import zim.plugins
		try:
			pluginname = args.pop(0)
		except IndexError:
			raise UsageError
		module = zim.plugins.get_plugin_module(pluginname)
		module.main(*args)


def ZimCmd(args=None):
	'''Constructor to get a L{Application} object for zim itself
	Use this object to spawn new instances of zim.
	When C{args} is given the options "--standalone" and "-V" or "-D"
	will be added automatically.
	@param args: arguments to give to zim
	@returns: a L{Application} object for zim itself
	'''
	from zim.applications import Application
	if ZIM_EXECUTABLE.endswith('.exe'):
		cmd = (ZIM_EXECUTABLE,)
	elif sys.executable:
		# If not an compiled executable, we assume it is python
		# (Application class only does this automatically for scripts
		# ending in .py)
		cmd = (sys.executable, ZIM_EXECUTABLE)

	if not args:
		return Application(cmd)

	# TODO: if not standalone, call IPC directly rather than
	#       first spawning a process
	import zim.ipc
	if not zim.ipc.in_child_process():
		args = args + ('--standalone',)

	# more detailed logging has lower number, so WARN > INFO > DEBUG
	loglevel = logging.getLogger().getEffectiveLevel()
	if loglevel <= logging.DEBUG:
		args = args + ('-D',)
	elif loglevel <= logging.INFO:
		args = args + ('-V',)

	return Application(cmd + args)



class NotebookInterface(gobject.GObject):
	'''Base class for the application object

	This is the base class for application classes like L{GtkInterface}
	and L{WWWInterface}. It can also be instantiated on it's own, which
	should only be done for running commandline commands like export
	and index.

	In the current design an application object can only open one
	notebook. Also it is not possible to close the notebook and open
	another one in the same interface. In practise this means that
	each notebook that is opened runs in it's own process with it's
	own application object.

	@signal: C{open-notebook (notebook)}:
	Emitted to open a notebook in this interface

	@signal: C{preferences-changed ()}:
	Emitted when preferences have changed

	@cvar ui_type: string to tell plugins what interface is supported
	by this class. Currently this can be "gtk" or "html". If "ui_type"
	is None we run without interface (e.g. commandline export).

	@ivar notebook: the L{Notebook} that is open in this interface
	@ivar plugins: list of L{plugin<zim.plugins>} objects that are
	active
	@ivar preferences: a L{ConfigDict} for the user preferences
	(the C{X{preferences.conf}} config file)
	@ivar uistate:  L{ConfigDict} with notebook specific interface state
	(the C{X{state.conf}} file in the notebook cache folder)
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'open-notebook': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'preferences-changed': (gobject.SIGNAL_RUN_LAST, None, ()),
		'initialize-notebook': (gobject.SIGNAL_RUN_LAST, None, (object,)),
	}
		# Consider making initialize-notebook a hook where handlers
		# return a resolved notebook

	ui_type = None

	def __init__(self, notebook=None):
		'''Constructor

		@keyword notebook: the L{Notebook} object to open in this
		interface. If not specified here you can call L{open_notebook()}
		to open one later.
		'''
		gobject.GObject.__init__(self)
		self.notebook = None
		self.plugins = []

		self.preferences = get_config('preferences.conf')
		self.preferences['General'].setdefault('plugins',
			['calendar', 'insertsymbol', 'printtobrowser', 'versioncontrol'])

		self.uistate = None

		self.load_early_plugins()

		if not notebook is None:
			self.open_notebook(notebook)

	def load_early_plugins(self):
		'''Load all plugins that need to be loaded early
		(For now these are notebook independent plugins only)
		'''
		import zim.plugins
		# Plugins should not have dependency on order of being added
		# but sort them here to make behavior predictable.
		plugins = self.preferences['General']['plugins']
		for name in sorted(plugins):
			try:
				klass = zim.plugins.get_plugin(name)
			except:
				logger.exception('Failed to load plugin klass for plugin "%s"', name)
			else:
				if klass.is_profile_independent:
					self.load_plugin(name)

	def load_plugins(self, independent_only=False):
		'''Loads all the plugins defined in the preferences that are
		not yet loaded.
		'''
		# Plugins should not have dependency on order of being added
		# but sort them here to make behavior predictable.
		plugins = self.preferences['General']['plugins']
		for name in sorted(plugins):
			self.load_plugin(name)

	def load_plugin(self, name):
		'''Load a single plugin by name

		Load an plugin object and attach it to the current application
		object. And add it to the preferences.

		When the plugin was loaded already the already active object
		will be returned. Thus for each plugin only one instance can be
		active.

		@param name: the plugin name as understood by
		L{zim.plugins.get_plugin()}

		@returns: the plugin object or C{None} when failed

		@todo: make load_plugin raise exception on failure
		'''
		assert isinstance(name, basestring)
		import zim.plugins

		loaded = [p.plugin_key for p in self.plugins]
		if name in loaded:
			return self.plugins[loaded.index(name)]

		try:
			klass = zim.plugins.get_plugin(name)
			if not klass.check_dependencies_ok():
				raise AssertionError, 'Dependencies failed for plugin %s' % name
			plugin = klass(self)
		except:
			logger.exception('Failed to load plugin "%s"', name)
			try:
				self.preferences['General']['plugins'].remove(name)
				self.preferences.set_modified(True)
			except ValueError:
				pass
			return None
		else:
			self.plugins.append(plugin)
			logger.debug('Loaded plugin "%s" (%s)', name, plugin)

		plugin.plugin_key = name
		if not name in self.preferences['General']['plugins']:
			self.preferences['General']['plugins'].append(name)
			self.preferences.set_modified(True)

		return plugin

	def unload_plugin(self, plugin):
		'''Remove a plugin

		De-attached the plugin from to the current application
		object. And remove it from the preferences.

		@param plugin: a plugin name or plugin object
		'''
		if isinstance(plugin, basestring):
			name = plugin
			plugin = self.get_plugin(name)
			assert plugin is not None
		else:
			assert plugin in self.plugins
			name = plugin.plugin_key

		plugin.destroy()
		self.plugins.remove(plugin)
		logger.debug('Unloaded plugin %s', name)

		try:
			self.preferences['General']['plugins'].remove(name)
			self.preferences.set_modified(True)
		except ValueError:
			pass

	def get_plugin(self, name):
		'''Returns plugin object if this plugin is loaded, C{None}
		otherwise.
		'''
		try:
			return filter(lambda p: p.plugin_key == name, self.plugins)[0]
		except IndexError:
			return None

	def save_preferences(self):
		'''Save the preferences config file if modified
		@emits: preferences-changed
		'''
		# For profile independent plugins, sync back to default
		# preferences
		if self.notebook and self.notebook.profile:
			independent = []
			for plugin in self.plugins:
				if plugin.is_profile_independent:
					independent.append(plugin.plugin_key)

			if independent:
				default = get_config('preferences.conf')
				for name in independent:
					if name not in default['General']['plugins']:
						default['General']['plugins'].append(name)
						default.set_modified(True)

					section = plugin.__class__.__name__
					if default[section] != plugin.preferences:
						default[section].update(plugin.preferences)

				if default.modified:
					default.write()

		# First emit, than write - avoid getting stuck with a set
		# that crashes the application
		if self.preferences.modified:
			self.emit('preferences-changed')

		self.preferences.write()

	def open_notebook(self, notebook):
		'''Open the notebook object

		Open the notebook object for this interface if no notebook was
		set already.

		@param notebook: either a string, a L{File} or L{Dir} object,
		or a L{Notebook} object.

		When the notebook is not given as a Notebook object,
		L{zim.notebook.resolve_notebook()} is used to resolve it.
		If this method returns a page as well it is returned here
		so it can be handled in a sub-class.

		The reason that we call C{resolve_notebook()} from here (instead
		of resolving it first and than calling this method only with a
		notebook object) is that we want to allow active plugins to
		handle the notebook uri before loading the Notebook object
		(e.g. to auto-mount the notebook folder).

		@emits: open-notebook

		@returns: a L{Path} if any was specified in the notebook spec
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
				self.emit('initialize-notebook', nb.uri)
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
		else:
			from zim.config import ConfigDict
			self.uistate = ConfigDict()

		if notebook.profile:
			# the profile will determine what plugins to load
			self.on_profile_changed(notebook)
		else:
			# load the rest of the plugins for the default prefences
			self.load_plugins()

		notebook.connect('profile-changed', self.on_profile_changed)

	def on_profile_changed(self, notebook):
		# Copy config for independent plugins
		independent_preferences = {}
		for plugin in self.plugins[:]:
			if plugin.is_profile_independent:
				independent_preferences[plugin.plugin_key] = \
					plugin.preferences.copy()

		# Switch config
		if self.notebook.profile:
			# Load the preferences for the profile
			# In case new profile does not exist or is incomplete
			# we cary over any settings from the current one
			logger.debug('Profile changed to: %s', notebook.profile)
			basename = self.notebook.profile.lower() + '.conf'
			file = config_file(('profiles', basename))
			self.preferences.change_file(file)
			self.preferences.write()
		else:
			# Load default preferences
			# We do a full flush to reset to default
			logger.debug('Profile reset to default')
			preferences = get_config('preferences.conf')
			file = preferences.file
			self.preferences.change_file(file)
			for section in self.preferences.values():
				section.clear()
			self.preferences.read() # HACK Forces reading default as well

		# Notify ui objects
		self.emit('preferences-changed')

		# notify plugins of possible new preferences
		# and remove old plugins
		for plugin in self.plugins[:]:
			if plugin.plugin_key in self.preferences['General']['plugins']:
				plugin.emit('preferences-changed')
			elif plugin.is_profile_independent:
				self.preferences['General']['plugins'].append(plugin.plugin_key)
				plugin.preferences.update(independent_preferences[plugin.plugin_key])
			else:
				self.unload_plugin(plugin)

		# load new plugins
		self.load_plugins()

	def cmd_export(self, format='html', template=None, page=None, output=None, root_url=None, index_page=None):
		'''Convenience method hat wraps L{zim.exporter.Exporter} for
		commandline export

		@keyword format: the format name
		@keyword template: the template path or name
		@keyword page: the page name or C{None} to export the full notebook
		@keyword output: the output folder or C{None} to print to stdout
		@keyword root_url: the url to map the document root if any
		@keyword index_page: the index page name if any
		'''
		import zim.exporter
		exporter = zim.exporter.Exporter(self.notebook, format, template, document_root_url=root_url, index_page=index_page)

		if page:
			path = self.notebook.resolve_path(page)
			page = self.notebook.get_page(path)

		if page and output is None:
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

	def cmd_search(self, query):
		from zim.search import SearchSelection, Query
		query = query.strip()
		if not query: raise AssertionError, 'Empty query'
		logger.info('Searching for: %s', query)
		selection = SearchSelection(self.notebook)
		query = Query(query)
		selection.search(query)
		for path in sorted(selection, key=lambda p: p.name):
			print path.name

	def cmd_index(self, output=None):
		'''Convenience method for the commandline 'index' command

		@keyword output: the index file to update, defaults to the
		default index s used by the notebook
		'''
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


# Need to register classes defining gobject signals
gobject.type_register(NotebookInterface)
