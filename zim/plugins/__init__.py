
# Copyright 2008-2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''API documentation of the zim plugin framework.

This file contains the base classes used to write plugins for zim. Each
plugin is defined as a sub-module in the "zim.plugins" namespace.

To be recognized as a plugin, a submodule of "zim.plugins" needs to
define one (and only one) sub-class of L{PluginClass}. This class
will define the main plugin object and contains meta data about the
plugin and e.g. plugin preferences.

The plugin object itself doesn't directly interact with the rest of the
zim application. To actually add functionality to zim, the plugin module
will also need to define one or more "extension" classes. These classes
act as decorators for specific objects that appear in the application.
They will be instantiated automatically whenever the target object is
created. The extension object then has direct access to the API of the
object that is being extended.

Each extension object that is instantiated is linked to the plugin object
that it belongs to. So it can access functions of the plugin object and
it can use the plugin object to find other extension objects if it
needs to cooperate.

Also defined here is the L{PluginManager} class. This class is the
interface towards the rest of the application to load/unload plugins and
to let plugins extend specific application objects.
'''


from gi.repository import GObject
import types
import os
import sys
import logging
import inspect

try:
	import collections.abc as abc
except ImportError:
	# python < version 3.3
	import collections as abc

from zim.newfs import LocalFolder, LocalFile

from zim.signals import SignalEmitter, ConnectorMixin, SIGNAL_AFTER, SIGNAL_RUN_LAST, SignalHandler
from zim.utils import classproperty, get_module, lookup_subclass, lookup_subclasses, WeakSet
from zim.actions import hasaction

from zim.config import data_dirs, XDG_DATA_HOME, ConfigManager
from zim.insertedobjects import InsertedObjectType


logger = logging.getLogger('zim.plugins')


# Extend path for importing and searching plugins
#
# Set C{__path__} for the C{zim.plugins} module. This determines what
# directories are searched when importing plugin packages in the
# C{zim.plugins} namespace.
#
# Originally this added to the C{__path__} folders based on C{sys.path}
# however this leads to conflicts when multiple zim versions are
# installed. By switching to XDG_DATA_HOME this conflict is removed
# by separating custom plugins and default plugins from other versions.
# Also this switch makes it easier to have a single instruction for
# users where to put custom plugins.

PLUGIN_FOLDER = XDG_DATA_HOME.subdir('zim/plugins')

for dir in data_dirs('plugins'):
	__path__.append(dir.path)

__path__.append(__path__.pop(0)) # reshuffle real module path to the end
__path__.insert(0, PLUGIN_FOLDER.path) # Should be redundant, but need to be sure

#print("PLUGIN PATH:", __path__)

class _BootstrapPluginManager(object):

	def __init__(self):
		self._extendables = []

	def _new_extendable(self, extendable):
		self._extendables.append(extendable)


_bootstrappluginmanager = _BootstrapPluginManager()
PluginManager = _bootstrappluginmanager


def extendable(*extension_bases):
	'''Class decorator to mark a class as "extendable"
	@param extension_bases: base classes for extensions
	'''
	assert all(issubclass(ec, ExtensionBase) for ec in extension_bases)

	def _extendable(cls):
		orig_init = cls.__init__

		def _init_wrapper(self, *arg, **kwarg):
			orig_init(self, *arg, **kwarg)
			self.__zim_extension_bases__ = extension_bases
			self.__zim_extension_objects__ = []
			PluginManager._new_extendable(self)

		cls.__init__ = _init_wrapper

		return cls

	return _extendable


def find_extension(obj, klass):
	'''Lookup an extension object
	This function allows finding extension classes defined by any plugin.
	So it can be used to find an defined by the same plugin, but also allows
	cooperation by other plugins.
	The lookup uses C{isinstance()}, so abstract classes can be used to define
	interfaces between plugins if you don't want to depent on the exact
	implementation class.
	@param obj: the extended object
	@param klass: the class of the extention object
	@returns: a single extension object, if multiple extensions match, the
	first is returned
	@raises ValueError: if no extension was found
	'''
	if hasattr(obj, '__zim_extension_objects__'):
		for e in obj.__zim_extension_objects__:
			if isinstance(e, klass):
				return e

	raise ValueError('No extension of class found: %s' % klass)


def find_action(obj, actionname):
	'''Lookup an action method
	Returns an action method (defined with C{@action} or C{@toggle_action})
	for either the object itself, or any of it's extensions.
	This allows cooperation between plugins by calling actions defined by
	an other plugin action.
	@param obj: the extended object
	@param actionname: the name of the action
	@returns: an action method
	@raises ValueError: if no action was found
	'''
	actionname = actionname.replace('-', '_')
	if hasaction(obj, actionname):
		return getattr(obj, actionname)
	else:
		if hasattr(obj, '__zim_extension_objects__'):
			for e in obj.__zim_extension_objects__:
				if hasaction(e, actionname):
					return getattr(e, actionname)
		raise ValueError('Action not found: %s' % actionname)


class ExtensionBase(SignalEmitter, ConnectorMixin):
	'''Base class for all extensions classes
	@ivar plugin: the plugin object to which this extension belongs
	'''

	__signals__ = {}

	def __init__(self, plugin, obj):
		'''Constructor
		@param plugin: the plugin object to which this extension belongs
		@param obj: the object being extended
		'''
		self.plugin = plugin
		obj.__zim_extension_objects__.append(self)

	def destroy(self):
		'''Called when the plugin is being destroyed
		Calls L{teardown()} followed by the C{teardown()} methods of
		parent base classes.
		'''
		def walk(klass):
			yield klass
			for base in klass.__bases__:
				if issubclass(base, ExtensionBase):
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
			# Avoid waiting for garbage collection to take place

	def teardown(self):
		'''Remove changes made by B{this} class from the extended object
		To be overloaded by child classes
		@note: do not call parent class C{teardown()} here, that is
		already taken care of by C{destroy()}
		'''
		self.disconnect_all()


class DialogExtensionBase(ExtensionBase):
	'''Base class for extending Gtk dialogs based on C{Gtk.Dialog}
	@ivar dialog: the C{Gtk.Dialog} object
	'''

	def __init__(self, plugin, dialog):
		ExtensionBase.__init__(self, plugin, dialog)
		self.dialog = dialog
		self._dialog_buttons = []
		self.connectto(dialog, 'destroy')

	def on_destroy(self, dialog):
		self.destroy()

	def add_dialog_button(self, button):
		'''Add a new button to the bottom area of the dialog
		The button is placed left of the standard buttons like the
		"OK" / "Cancel" or "Close" button of the dialog.
		@param button: a C{Gtk.Button} or similar widget
		'''
		# This logic adds the button to the action area and places
		# it left of the left most primary button by reshuffling all
		# other buttons after adding the new one
		#
		# TODO: check if this works correctly in RTL configuration
		self.dialog.action_area.pack_end(button, False, True, 0) # puts button in right most position
		self._dialog_buttons.append(button)
		buttons = [b for b in self.dialog.action_area.get_children()
			if not self.dialog.action_area.child_get_property(b, 'secondary')]
		for b in buttons:
			if b is not button:
				self.dialog.action_area.reorder_child(b, -1) # reshuffle to the right

	def teardown(self):
		for b in self._dialog_buttons:
			self.dialog.action_area.remove(b)


class InsertedObjectTypeExtension(InsertedObjectType, ExtensionBase):

	def __init__(self, plugin, objmap):
		InsertedObjectType.__init__(self)
		ExtensionBase.__init__(self, plugin, objmap)
		objmap.register_object(self)
		self._objmap = objmap

	def teardown(self):
		self._objmap.unregister_object(self)


@extendable(InsertedObjectTypeExtension)
class InsertedObjectTypeMap(SignalEmitter):
	'''Mapping of L{InsertedObjectTypeExtension} objects.
	This is a proxy for loading object types defined in plugins.
	For convenience you can use C{PluginManager.insertedobjects} to access
	an instance of this mapping.
	'''

	# Note: Wanted to inherit from collections.abc.Mapping
	#       but conflicts with metaclass use for SignalEmitter

	__signals__ = {
		'changed': (SIGNAL_RUN_LAST, None, ()),
	}

	def __init__(self):
		self._objects = {}

	def __getitem__(self, name):
		return self._objects[name.lower()]

	def __iter__(self):
		return iter(sorted(self._objects.keys()))
			# sort to make operation predictable - easier debugging

	def __len__(self):
		return len(self._objects)

	def __contains__(self, name):
		return name.lower() in self._objects

	def keys(self):
		return [k for k in self]

	def items(self):
		return [(k, self[v]) for k in self]

	def values(self):
		return [self[k] for k in self]

	def get(self, name, default=None):
		return self._objects.get(name.lower(), default)

	def register_object(self, objecttype):
		'''Register an object type
		@param objecttype: an object derived from L{InsertedObjectType}
		@raises AssertionError: if another object already uses the same name
		'''
		key = objecttype.name.lower()
		if key in self._objects:
			raise AssertionError('InsertedObjectType "%s" already defined by %s' % (key, self._objects[key]))
		else:
			self._objects[key] = objecttype
			self.emit('changed')

	def unregister_object(self, objecttype):
		'''Unregister a specific object type.
		@param objecttype: an object derived from L{InsertedObjectType}
		'''
		key = objecttype.name.lower()
		if key in self._objects and self._objects[key] is objecttype:
			self._objects.pop(key)
			self.emit('changed')


class PluginManagerClass(ConnectorMixin, abc.Mapping):
	'''Manager that maintains a set of active plugins

	This class is the interface towards the rest of the application to
	load/unload plugins. It behaves as a dictionary with plugin object names as
	keys and plugin objects as value
	'''

	def __init__(self):
		'''Constructor
		Constructor will directly load a list of default plugins
		based on the preferences in the config. Failures while loading
		these plugins will be logged but not raise errors.

		@param config: a L{ConfigManager} object that is passed along
		to the plugins and is used to load plugin preferences.
		Defaults to a L{VirtualConfigManager} for testing.
		'''
		self._reset()

	def _reset(self):
		self._preferences = ConfigManager.preferences['General']
		self._preferences.setdefault('plugins', [])

		self._plugins = {}
		self._extendables = WeakSet()
		self.failed = set()

		self.insertedobjects = InsertedObjectTypeMap()

	def load_plugins_from_preferences(self, names):
		'''Calls L{load_plugin()} for each plugin in C{names} but does not
		raise an exception when loading fails.
		'''
		for name in names:
			try:
				self.load_plugin(name)
			except Exception as exc:
				if isinstance(exc, ImportError):
					logger.info('No such plugin: %s', name)
				else:
					logger.exception('Exception while loading plugin: %s', name)
				if name in self._preferences['plugins']:
					self._preferences['plugins'].remove(name)
				self.failed.add(name)

	def __call__(self):
		return self # singleton behavior if called as class

	def __getitem__(self, name):
		return self._plugins[name]

	def __iter__(self):
		return iter(sorted(self._plugins.keys()))
			# sort to make operation predictable - easier debugging

	def __len__(self):
		return len(self._plugins)

	@classmethod
	def list_installed_plugins(klass):
		'''Lists plugin names for all installed plugins
		@returns: a set of plugin names
		'''
		# List "zim.plugins" sub modules based on __path__ because this
		# parameter determines what folders will considered when importing
		# sub-modules of the this package once this module is loaded.
		plugins = set() # THIS LINE IS REPLACED BY SETUP.PY - DON'T CHANGE IT
		for folder in [f for f in map(LocalFolder, __path__) if f.exists()]:
			for child in folder:
				name = child.basename
				if name.startswith('_') or name == 'base':
					continue
				elif isinstance(child, LocalFile) and name.endswith('.py'):
					plugins.add(name[:-3])
				elif isinstance(child, LocalFolder) \
					and child.file('__init__.py').exists():
						plugins.add(name)
				else:
					pass

		return plugins

	@classmethod
	def get_plugin_class(klass, name):
		'''Get the plugin class for a given name

		@param name: the plugin module name
		@returns: the plugin class object
		'''
		modname = 'zim.plugins.' + name
		mod = get_module(modname)
		return lookup_subclass(mod, PluginClass)

	def _new_extendable(self, obj):
		'''Let any plugin extend the object instance C{obj}
		Will also remember the object (by a weak reference) such that
		plugins loaded after this call will also be called to extend
		C{obj} on their construction
		@param obj: arbitrary object that can be extended by plugins
		'''
		logger.debug("New extendable: %s", obj)
		assert not obj in self._extendables

		for name, plugin in sorted(self._plugins.items()):
			# sort to make operation predictable
			self._extend(plugin, obj)

		self._extendables.add(obj)

	def _extend(self, plugin, obj):
		for ext_class in plugin.extension_classes:
			if issubclass(ext_class, obj.__zim_extension_bases__):
				logger.debug("Load extension: %s", ext_class)
				try:
					ext = ext_class(plugin, obj)
				except:
					logger.exception('Failed loading extension %s for plugin %s', ext_class, plugin)
				else:
					plugin.extensions.add(ext)

	def load_plugin(self, name):
		'''Load a single plugin by name

		When the plugin was loaded already the existing object
		will be returned. Thus for each plugin only one instance can be
		active.

		@param name: the plugin module name
		@returns: the plugin object
		@raises Exception: when loading the plugin failed
		'''
		assert isinstance(name, str)
		if name in self._plugins:
			return self._plugins[name]

		logger.debug('Loading plugin: %s', name)
		klass = self.get_plugin_class(name)
		if not klass.check_dependencies_ok():
			raise AssertionError('Dependencies failed for plugin %s' % name)

		plugin = klass()
		self._plugins[name] = plugin

		for obj in self._extendables:
			self._extend(plugin, obj)

		if not name in self._preferences['plugins']:
			self._preferences['plugins'].append(name)
			self._preferences.changed()

		return plugin

	def remove_plugin(self, name):
		'''Remove a plugin and it's extensions
		Fails silently if the plugin is not loaded.
		@param name: the plugin module name
		'''
		if name in self._preferences['plugins']:
			# Do this first regardless of exceptions etc.
			self._preferences['plugins'].remove(name)
			self._preferences.changed()

		try:
			plugin = self._plugins.pop(name)
			self.disconnect_from(plugin)
		except KeyError:
			pass
		else:
			logger.debug('Unloading plugin %s', name)
			plugin.destroy()


PluginManager = PluginManagerClass()  # singleton
for _extendable in _bootstrappluginmanager._extendables:
	PluginManager._new_extendable(_extendable)
del _bootstrappluginmanager
del _extendable


def resetPluginManager():
	# used in test suite to reset singleton internal state
	PluginManager._reset()


class PluginClass(ConnectorMixin):
	'''Base class for plugins objects.

	To be recognized as a plugin, a submodule of "zim.plugins" needs to
	define one (and only one) sub-class of L{PluginClass}. This class
	will define the main plugin object and contains meta data about the
	plugin and e.g. plugin preferences.

	The plugin object itself doesn't directly interact with the rest of the
	zim application. To actually add functionality to zim, the plugin module
	will also need to define one or more "extension" classes. These classes
	act as decorators for specific objects that appear in the application.

	All extension classes defined in the same module
	file as the plugin object are automatically linked to the plugin.

	This class inherits from L{ConnectorMixin} and calls
	L{ConnectorMixin.disconnect_all()} when the plugin is destroyed.
	Therefore it is highly recommended to use the L{ConnectorMixin}
	methods in sub-classes.

	Plugin classes should at minimum define two class attributes:
	C{plugin_info} and C{plugin_preferences}. When these are defined
	no other code is needed to have a basic plugin up and running.

	@cvar plugin_info: A dict with basic information about the plugin,
	it should contain at least the following keys:

		- C{name}: short name
		- C{description}: one paragraph description
		- C{author}: name of the author
		- C{help}: page name in the manual (optional)

	This info will be used e.g. in the plugin tab of the preferences
	dialog.

	@cvar plugin_preferences: A tuple or list defining the global
	preferences for this plugin (if any). Each preference is defined
	by a 4-tuple containing the following items:

		1. the dict key of the option (used in the config file and in
		   the preferences dict)
		2. an option type (see L{InputForm.add_inputs(){} for more details)
		3. a (translatable) label to show in the preferences dialog for
		   this option
		4. a default value

	These preferences will be initialized to their default value if not
	configured by the user and the values can be found in the
	L{preferences} dict of the plugin object. The type and label will be
	used to render a default config dialog when triggered from the
	preferences dialog.
	Changes to these preferences will be stored in a config file so
	they are persistent.

	@ivar preferences: a L{ConfigDict} with plugin preferences

	Preferences are the global configuration of the plugin, they are
	stored in the X{preferences.conf} config file.

	@ivar config: a L{ConfigManager} object that can be used to lookup
	additional config files for the plugin

	@ivar extension_classes: a list with extension classes found
	in the plugin module

	@ivar extensions: a set with extension objects loaded by this plugin.
	'''

	# define signals we want to use - (closure type, return type and arg types)
	plugin_info = {}

	plugin_preferences = ()
	plugin_notebook_properties = ()

	@classproperty
	def config_key(klass):
		'''The name of section used in the config files to store the
		preferences for this plugin.
		'''
		return klass.__name__

	@classmethod
	def check_dependencies_ok(klass):
		'''Checks minimum dependencies are met

		@returns: C{True} if this plugin can be loaded based on
		L{check_dependencies()}
		'''
		check, dependencies = klass.check_dependencies()
		return check

	@classmethod
	def check_dependencies(klass):
		'''Checks what dependencies are met and gives details for
		display in the preferences dialog

		@returns: a boolean telling overall dependencies are met,
		followed by a list with details.

		This list consists of 3-tuples consisting of a (short)
		description of the dependency, a boolean for dependency being
		met, and a boolean for this dependency being optional or not.

		@implementation: must be implemented in sub-classes that have
		one or more (external) dependencies. Default always returns
		C{True} with an empty list.
		'''
		return (True, [])

	def __init__(self):
		assert 'name' in self.plugin_info, 'Missing "name" in plugin_info'
		assert 'description' in self.plugin_info, 'Missing "description" in plugin_info'
		assert 'author' in self.plugin_info, 'Missing "author" in plugin_info'
		self.extensions = WeakSet()

		if self.plugin_preferences:
			assert isinstance(self.plugin_preferences[0], tuple), 'BUG: preferences should be defined as tuples'

		self.preferences = ConfigManager.preferences[self.config_key]
		self._init_config(self.preferences, self.plugin_preferences)
		self._init_config(self.preferences, self.plugin_notebook_properties) # defaults for the properties are preferences

		self.extension_classes = list(self.discover_classes(ExtensionBase))

	@staticmethod
	def _init_config(config, definitions):
		for pref in definitions:
			if len(pref) == 4:
				key, type, label, default = pref
				config.setdefault(key, default)
			else:
				key, type, label, default, check = pref
				config.setdefault(key, default, check=check)

	@staticmethod
	def form_fields(definitions):
		fields = []
		for pref in definitions:
			if len(pref) == 4:
				key, type, label, default = pref
			else:
				key, type, label, default, check = pref

			if type in ('int', 'choice'):
				fields.append((key, type, label, check))
			else:
				fields.append((key, type, label))

		return fields

	def notebook_properties(self, notebook):
		properties = notebook.config[self.config_key]
		if not properties:
			self._init_config(properties, self.plugin_notebook_properties)

			# update defaults based on preference
			for key, definition in properties.definitions.items():
				try:
					definition.default = definition.check(self.preferences[key])
				except ValueError:
					pass

		return properties

	@classmethod
	def lookup_subclass(pluginklass, klass):
		'''Returns first subclass of C{klass} found in the module of
		this plugin. (Similar to L{zim.utils.lookup_subclass}).
		@param pluginklass: plugin class
		@param klass: base class of the wanted class
		'''
		module = get_module(pluginklass.__module__)
		return lookup_subclass(module, klass)

	@classmethod
	def discover_classes(pluginklass, baseclass):
		'''Yields a list of classes derived from C{baseclass} and
		defined in the same module as the plugin
		'''
		module = get_module(pluginklass.__module__)
		for klass in lookup_subclasses(module, baseclass):
			yield klass

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
			self.teardown()
		except:
			logger.exception('Exception while disconnecting %s', self)

	def teardown(self):
		'''Cleanup method called by C{destroy()}.
		Can be implemented by sub-classes.
		'''
		pass
