# -*- coding: utf-8 -*-

# Copyright 2008-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Base class and API for plugins

Zim plugins are simply python modules that contain a sub-class of
L{PluginClass}. They get a reference the the main application object
running the interface and from there can link to various objects and
widgets. The base class has convenience methods for common actions
for plugins.

Also see the HACKING notebook in the source distribution for some
notes on writing new plugins.

@note: sub-modules T should contain one and exactly one subclass of
L{PluginClass}. This is because this class is detected automatically
when loading the plugin. This means you can also not import classes of
other plugins directly into the module.
'''


import gobject
import types
import os
import sys
import logging
import inspect
import collections

import zim.fs
from zim.fs import Dir

from zim.signals import SignalEmitter, ConnectorMixin, SIGNAL_AFTER
from zim.actions import action, toggle_action, get_gtk_actiongroup
from zim.utils import classproperty, get_module, lookup_subclass, WeakSet

from zim.config import VirtualConfigManager


logger = logging.getLogger('zim.plugins')


def user_site_packages_directory():
	'''Get the per user site-packages directory

	In Python 2.6 the "Per-user site-packages Directory" feature has
	been introduced, see
	U{http://docs.python.org/whatsnew/2.6.html#pep-370-per-user-site-packages-directory}.
	This function backports this feature to Python 2.5.

	@returns: the per user site-packages directory.
	This directoy is part of the search path for plugin modules, so users
	can install plugins in locally.
	'''
	from zim.environ import environ
	if os.name == 'nt':
		appdata = environ.get('APPDATA')
		if appdata:
			dir = Dir((appdata, 'Python/Python25/site-packages'))
			return dir.path
		else:
			return None
	else:
		dir = Dir('~/.local/lib/python2.5/site-packages')
		return dir.path

# Add the per-user site-packages directory to the system path
if sys.version_info[0:2] == (2, 5):
	userdir = user_site_packages_directory()
	if userdir and not userdir in sys.path:
		sys.path.insert(0, userdir)


def set_plugin_search_path():
	'''Initialize C{__path__} variable with the search path for plugins

	Sets C{__path__} for the C{zim.plugins} module. This determines what
	directories are searched when importing plugin packages in the
	zim.plugins namespace. This function looks at C{sys.path} and would
	need to be run again if C{sys.path} is modified after loading this
	module.
	'''
	global __path__
	__path__ = [] # flush completely
	# We don't even keep the directory of this source file because we
	# want order in __path__ match order in sys.path, so per-user
	# folder takes proper precedence

	for dir in sys.path:
		try:
			dir = dir.decode(zim.fs.ENCODING)
		except UnicodeDecodeError:
			logger.exception('Could not decode path "%s"', dir)
			continue

		if os.path.basename(dir) == 'zim.exe':
			# path is an executable, not a folder -- examine containing folder
			dir = os.path.dirname(dir)

		if dir == '':
			dir = '.'

		dir = os.path.sep.join((dir, 'zim', 'plugins'))
		#~ print '>> PLUGIN DIR', dir
		__path__.append(dir)

# extend path for importing and searching plugins
set_plugin_search_path()


def get_plugin_class(name):
	'''Get the plugin class for a given name

	@param name: the plugin module name (e.g. "calendar")
	@returns: the plugin class object
	'''
	mod = get_module('zim.plugins.' + name)
	return lookup_subclass(mod, PluginClass)


def list_plugins():
	'''List available plugin module names

	@returns: a set of available plugin names that can be loaded
	using L{get_plugin_class()}.
	'''
	# Only listing folders in __path__ because this parameter determines
	# what folders will considered when importing sub-modules of the
	# this package once this module is loaded.

	plugins = set()

	for dir in __path__:
		dir = Dir(dir)
		for candidate in dir.list(): # returns [] if dir does not exist
			if candidate.startswith('_') or candidate == 'base':
				continue
			elif candidate.endswith('.py'):
				#~ print '>> FOUND %s.py in %s' % (candidate, dir.path)
				plugins.add(candidate[:-3])
			elif zim.fs.isdir(dir.path+'/'+candidate) \
			and os.path.exists(dir.path+'/'+candidate+'/__init__.py'):
				#~ print '>> FOUND %s/__init__.py in %s' % (candidate, dir.path)
				plugins.add(candidate)
			else:
				pass

	return sorted(plugins)


class PluginManager(ConnectorMixin, collections.Mapping):
	'''Manager that maintains a set of active plugins
	Handles loading and destroying plugins and is the entry point
	for extending application components.

	This object behaves as a dictionary with plugin object names as
	keys and plugin objects as value
	'''

	# Note that changes to "config['plugins']" do not trigger the
	# changed signal on the dict. If this changes in the future, we
	# need to block the callback when modifying this list.

	def __init__(self, config=None):
		self.config = config or VirtualConfigManager()
		self._preferences = \
			self.config.get_config_dict('<profile>/preferences.conf')
		self.general_preferences = self._preferences['General']
		self.general_preferences.setdefault('plugins', [])

		self._plugins = {}
		self._extendables = WeakSet()

		self._load_plugins()

		self.connectto(self._preferences, 'changed',
			self.on_preferences_changed)

	def __getitem__(self, name):
		return self._plugins[name]

	def __iter__(self):
		return iter(sorted(self._plugins.keys()))
			# sort to make operation predictable - easier debugging

	def __len__(self):
		return len(self._plugins)

	def _load_plugins(self):
		'''Load plugins based on config'''
		for name in sorted(self.general_preferences['plugins']):
			try:
				self.load_plugin(name)
			except:
				logger.exception('Exception while loading plugin: %s', name)
				self.general_preferences['plugins'].remove(name)

	def on_preferences_changed(self, o):
		current = set(self._plugins.keys())
		new = set(self.general_preferences['plugins'])

		for name in current - new:
			try:
				self.remove_plugin(name)
			except:
				logger.exception('Exception while loading plugin: %s', name)

		for name in new - current:
			try:
				self.load_plugin(name)
			except:
				logger.exception('Exception while loading plugin: %s', name)
				self.general_preferences['plugins'].remove(name)

	def load_plugin(self, name):
		'''Load a single plugin by name

		When the plugin was loaded already the existing object
		will be returned. Thus for each plugin only one instance can be
		active.

		@param name: the plugin module name
		@returns: the plugin object
		@raises Exception: when loading the plugin failed
		'''
		assert isinstance(name, basestring)
		if name in self._plugins:
			return self._plugins[name]

		logger.debug('Loading plugin: %s', name)
		klass = get_plugin_class(name)
		if not klass.check_dependencies_ok():
			raise AssertionError, 'Dependencies failed for plugin %s' % name

		plugin = klass(self.config)
		self.connectto(plugin, 'extension-point-changed')
		self._plugins[name] = plugin

		for obj in self._extendables:
			try:
				plugin.extend(obj)
			except:
				logger.exception('Exception in plugin: %s', name)

		if not name in self.general_preferences['plugins']:
			self.general_preferences['plugins'].append(name)

		return plugin

	def remove_plugin(self, name):
		'''Remove a plugin and it's extensions
		Fails silently if the plugin is not loaded.
		@param name: the plugin module name
		'''
		if name in self.general_preferences['plugins']:
			# Do this first regardless of exceptions etc.
			self.general_preferences['plugins'].remove(name)

		try:
			plugin = self._plugins.pop(name)
			self.disconnect_from(plugin)
		except KeyError:
			pass
		else:
			logger.debug('Unloading plugin %s', name)
			plugin.destroy()

	def _foreach(self, func):
		# sort to make operation predictable - easier debugging
		for name, plugin in sorted(self._plugins.items()):
			try:
				func(plugin)
			except:
				logger.exception('Exception in plugin: %s', name)

	def extend(self, obj):
		'''Let any plugin extend the object instance C{obj}
		Will also remember object (by a weak reference) such that
		plugins loaded after this call will also be called to extend
		C{obj} on their construction
		@param obj: arbitrary object that can be extended by plugins
		'''
		self._foreach(lambda p: p.extend(obj))
		self._extendables.add(obj)

	def on_extension_point_changed(self, plugin, name):
		for obj in self._extendables:
			if obj.__class__.__name__ == name:
				try:
					plugin.extend(obj)
				except:
					logger.exception('Exception in plugin: %s', name)


class PluginClass(ConnectorMixin, SignalEmitter):
	'''Base class for plugins. Every module containing a plugin should
	have exactly one class derived from this base class. That class
	will be initialized when the plugin is loaded.

	Plugin classes should define two class attributes: L{plugin_info} and
	L{plugin_preferences}.

	This class inherits from L{ConnectorMixin} and calls
	L{ConnectorMixin.disconnect_all()} when the plugin is destroyed.
	Therefore it is highly recommended to use the L{ConnectorMixin}
	methods in sub-classes.

	@cvar plugin_info: A dict with basic information about the plugin,
	it should contain at least the following keys:

		- C{name}: short name
		- C{description}: one paragraph description
		- C{author}: name of the author
		- C{help}: page name in the manual (optional)

	This info will be used e.g. in the plugin tab of the preferences
	dialog.

	@cvar plugin_preferences: A tuple or list defining the global
	preferences for this plugin. Each preference is defined by a 4-tuple
	containing the following items:

		1. the key in the config file
		2. an option type (see InputForm.add_inputs for more details)
		3. a label to show in the dialog
		4. a default value

	These preferences will be initialized to their default value if not
	configured by the user and the values can be found in the
	L{preferences} dict. The type and label will be used to render a
	default configure dialog when triggered from the preferences dialog.
	Changes to these preferences will be stored in a config file so
	they are persistent.

	@ivar ui: the main application object, e.g. an instance of
	L{zim.gui.GtkInterface} or L{zim.www.WWWInterface}
	@ivar preferences: a C{ConfigDict()} with plugin preferences

	Preferences are the global configuration of the plugin, they are
	stored in the X{preferences.conf} config file.

	@ivar uistate: a C{ConfigDict()} with plugin ui state

	The "uistate" is the per notebook state of the interface, it is
	intended for stuff like the last folder opened by the user or the
	size of a dialog after resizing. It is stored in the X{state.conf}
	file in the notebook cache folder.

	@signal: C{extension-point-changed (name)}: emitted when extension
	point C{name} changes
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__signals__ = {
		'extension-point-changed': (None, None, (basestring,))
	}

	plugin_info = {}

	plugin_preferences = ()

	@classproperty
	def config_key(klass):
		return klass.__name__

	@classmethod
	def check_dependencies_ok(klass):
		'''Checks minimum dependencies are met

		@returns: C{True} if this plugin can be loaded
		'''
		check, dependencies = klass.check_dependencies()
		return check

	@classmethod
	def check_dependencies(klass):
		'''Checks what dependencies are met and gives details

		@returns: a boolean telling overall dependencies are met,
		followed by a list with details.

		This list consists of 3-tuples consisting of a (short)
		description of the dependency, a boolean for dependency being
		met, and a boolean for this dependency being optional or not.

		@implementation: must be implemented in sub-classes that have
		one or more (external) dependencies.
		'''
		return (True, [])

	def __init__(self, config=None):
		assert 'name' in self.plugin_info
		assert 'description' in self.plugin_info
		assert 'author' in self.plugin_info
		self.extensions = WeakSet()

		if self.plugin_preferences:
			assert isinstance(self.plugin_preferences[0], tuple), 'BUG: preferences should be defined as tuples'

		self.config = config or VirtualConfigManager()
		self.preferences = self.config.get_config_dict('<profile>/preferences.conf')[self.config_key]

		for pref in self.plugin_preferences:
				if len(pref) == 4:
					key, type, label, default = pref
					self.preferences.setdefault(key, default)
					#~ print ">>>>", key, default, '--', self.preferences[key]
				else:
					key, type, label, default, check = pref
					self.preferences.setdefault(key, default, check=check)
					#~ print ">>>>", key, default, check, '--', self.preferences[key]

		self.load_extensions_classes()

	@classmethod
	def lookup_subclass(pluginklass, klass):
		'''Returns first subclass of C{klass} found in the module of
		this plugin. (Similar to L{zim.utils.lookup_subclass})
		@param pluginklass: plugin class
		@param klass: base class of the wanted class
		'''
		module = get_module(pluginklass.__module__)
		return lookup_subclass(module, klass)

	def load_extensions_classes(self):
		self.extension_classes = {}
		for name, klass in self.discover_extensions_classes():
			self.add_extension_class(name, klass)

	@classmethod
	def discover_extensions_classes(pluginklass):
		# Find related extension classes in same module
		# any class with the "__extends__" field will be added
		# (Being subclass of ObjectExtension is optional)
		module = get_module(pluginklass.__module__)
		for n, klass in inspect.getmembers(module, inspect.isclass):
			if hasattr(klass, '__extends__') and klass.__extends__:
				yield klass.__extends__, klass

	def set_extension_class(self, name, klass):
		if name in self.extension_classes:
			if self.extension_classes[name] == klass:
				pass
			else:
				self.remove_extension_class(name)
				self.add_extension_class(name, klass)
		else:
			self.add_extension_class(name, klass)

	def add_extension_class(self, name, klass):
		if name in self.extension_classes:
			raise AssertionError, 'Extension point %s already in use' % name
		self.extension_classes[name] = klass
		self.emit('extension-point-changed', name)

	def remove_extension_class(self, name):
		klass = self.extension_classes.pop(name)
		for obj in self.get_extensions(klass):
			obj.destroy()

	def extend(self, obj, name=None):
		# TODO also check parent classes
		# name should only be used for testing
		name = name or obj.__class__.__name__
		if name in self.extension_classes:
			ext = self.extension_classes[name](self, obj)
			self.extensions.add(ext)

	def get_extension(self, klass, **attr):
		ext = self.get_extensions(klass)
		for key, value in attr.items():
			ext = filter(lambda e: getattr(e, key) == value, ext)

		if len(ext) > 1:
			raise AssertionError, 'BUG: multiple extensions of class %s found' % klass
		elif ext:
			return ext[0]
		else:
			return None

	def get_extensions(self, klass):
		return [e for e in self.extensions if isinstance(e, klass)]

	def destroy(self):
		'''Destroy the plugin object and all extensions
		It is only called when a user actually disables the plugin,
		not when the application exits.

		Destroys all active extensions and disconnects all signals.
		This should revert any changes the plugin made to the
		application (although preferences etc. can be left in place).
		'''
		for obj in self.extensions:
			obj.destroy()

		try:
			self.disconnect_all()
		except:
			logger.exception('Exception while disconnecting %s', self)


def extends(klass, autoload=True):
	'''Decorator for extension classes
	Use this decorator to add extensions to the plugin.
	Takes either a class or a class name for the class to be
	extended. When the plugin gets an object of this class a new
	extension object will be constructed.
	'''
	if isinstance(klass, basestring):
		name = klass
	else:
		name = klass.__name__

	def inner(myklass):
		if autoload:
			myklass.__extends__ = name
		# else: do nothing for now
		return myklass

	return inner


class ObjectExtension(SignalEmitter, ConnectorMixin):

	def __init__(self, plugin, obj):
		self.plugin = plugin
		self.obj = obj

		# Make sure extension has same lifetime as object being extended
		if not hasattr(obj, '__zim_extension_objects__'):
			obj.__zim_extension_objects__ = []
		obj.__zim_extension_objects__.append(self)

	def destroy(self):
		'''Called when the plugin is being destroyed
		Calls L{teardown()} followed by the C{teardown()} methods of
		base classes.
		'''
		def walk(klass):
			yield klass
			for base in klass.__bases__:
				if issubclass(base, ObjectExtension):
					for k in walk(base): # recurs
						yield k

		for klass in walk(self.__class__):
			try:
				klass.teardown(self)
			except:
				logger.exception('Exception while disconnecting %s (%s)', self, klass)
			# in case you are wondering: issubclass(Foo, Foo) evaluates True

		try:
			self.obj.__zim_extension_objects__.remove(self)
		except AttributeError:
			pass
		except ValueError:
			pass

		self.plugin.extensions.discard(self)
			# HACK avoid waiting for garbage collection to take place

	def teardown(self):
		'''Remove changes made by B{this} class from the extended object
		To be overloaded by child classes
		@note: do not call parent class C{remove()} here, that is
		already taken care of by C{destroy()}
		'''
		self.disconnect_all()


class WindowExtension(ObjectExtension):

	def __init__(self, plugin, window):
		ObjectExtension.__init__(self, plugin, window)
		self.window = window

		if hasattr(window, 'ui') and hasattr(window.ui, 'uistate') and window.ui.uistate: # XXX
			self.uistate = window.ui.uistate[plugin.config_key]
		else:
			self.uistate = None

		if hasattr(self, 'uimanager_xml'):
			# XXX TODO move uimanager to window
			actiongroup = get_gtk_actiongroup(self)
			self.window.ui.uimanager.insert_action_group(actiongroup, 0)
			self._uimanager_id = self.window.ui.uimanager.add_ui_from_string(self.uimanager_xml)

		self.connectto(window, 'destroy')

	def on_destroy(self, window):
		self.destroy()

	def teardown(self):
		# TODO move uimanager to window
		if hasattr(self, '_uimanager_id') \
		and self._uimanager_id is not None:
			self.window.ui.uimanager.remove_ui(self._uimanager_id)
			self._uimanager_id = None

		if hasattr(self, 'actiongroup'):
			self.window.ui.uimanager.remove_action_group(self.actiongroup)


class DialogExtension(WindowExtension):

	def __init__(self, plugin, window):
		assert hasattr(window, 'action_area'), 'Not a dialog: %s' % window
		WindowExtension.__init__(self, plugin, window)
		self._dialog_buttons = []

	def add_dialog_button(self, button):
		# This logic adds the button to the action area and places
		# it left of the left most primary button by reshuffling all
		# other buttons after adding the new one
		#
		# TODO: check if this works correctly in RTL configuration
		self.window.action_area.pack_end(button, False) # puts button in right most position
		self._dialog_buttons.append(button)
		buttons = [b for b in self.window.action_area.get_children()
			if not self.window.action_area.child_get_property(b, 'secondary')]
		for b in buttons:
			if b is not button:
				self.window.action_area.reorder_child(b, -1) # reshuffle to the right

	def teardown(self):
		for b in self._dialog_buttons:
			self.window.action_area.remove(b)
