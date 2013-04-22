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
__version__ = '0.59'
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



# FIXME remove the class
class NotebookLookupError(Error):
	'''Error when failing to locate a notebook'''

	description = _('Could not find the file or folder for this notebook')
		# T: Error verbose description



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


def set_executable(self, path):
	global ZIM_EXECUTABLE

	# FIXME - this returns python.exe on my windows test
	ZIM_EXECUTABLE = argv[0]
	zim_exec_file = File(ZIM_EXECUTABLE)
	if zim_exec_file.exists():
		# We were given an absolute path, e.g. "python ./zim.py"
		ZIM_EXECUTABLE = zim_exec_file.path


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
		from zim.notebook import Notebook
		assert self.notebook is None, 'BUG: other notebook opened already'
		assert not notebook is None, 'BUG: no notebook specified'
		logger.debug('Opening notebook: %s', notebook)
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

# Need to register classes defining gobject signals
gobject.type_register(NotebookInterface)
