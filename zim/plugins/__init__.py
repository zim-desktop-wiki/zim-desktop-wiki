# -*- coding: utf-8 -*-

# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

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
object that is being extended. Typical classes to extend in a plugin
are e.g. the L{MainWindow}, the L{PageView}, the L{Notebook} and the
L{Index} classes.

To define a new extension, you can either write a direct sub-class of
L{ObjectExtension} or use the L{WindowExtension} or L{DialogExtension}
classes as base. E.g. the L{WindowExtension} has functions to easily
add menu items in the main window menu bar.

Each extension object that is instantiated is linked to the plugin object
that it belongs to. So it can access functions of the plugin object and
it can use the plugin object to find other extension objects if it
needs to cooperate. All extension classes defined in the same module
file as the plugin object are automatically linked to the plugin.

Not every object in the application can be extended. Only objects that
are send to the plugin manager will be available. However all windows
and dialogs and all "main" objects in the application should be
available (or made available by a patch if they are not yet extendable).
Short lived objects like individual pages, files, etc. will typically
not be extended. To do something with them you need to extend the object
that creates them.

See the various standard plugins for examples how to define a plugin
object and use extensions. E.g. L{zim.plugins.printtobrowser} and
L{zim.plugins.screenshot} are simple plugins that illustrate how to add
a single function to zim.

A special case are the so-called "image generator" plugins. These are
plugins like the equation editor (see L{zim.plugins.equationeditor})
that use an external tool with a specialized language (e.g. latex)
to generate images that can be inserted in zim. Since there are multiple
of these plugins, a base plugin has been defined that does most of the
work. The only thing needed to define a new plugin of this type is a
plugin object (derived from L{ImageGeneratorPlugin}) and an object that
knows how to generate the image (derived from L{ImageGeneratorClass})

Some plugins also want to add commandline options, such that they can
be called directly with "zim --plugin PLUGIN_NAME [OPTIONS]", an example
is the quicknote plugin. To make this work, all that is needed is to
define a class that derives from the L{Command} class (see L{zim.command}).

Also defined here is the L{PluginManager} class. This class is the
interface towards the rest of the application to load/unload plugins and
to let plugins extend specific application objects.


To allow plugins to be installed locally, the
C{$XDG_DATA_HOME/zim/plugins} and all C{$XDG_DATA_DIRS/zim/plugins}
are added to the search path for C{zim.plugins}.
'''

from __future__ import with_statement


import gobject
import types
import os
import sys
import logging
import inspect
import collections

import zim.fs
from zim.fs import Dir

from zim.signals import SignalEmitter, ConnectorMixin, SIGNAL_AFTER, SignalHandler
from zim.actions import action, toggle_action, get_gtk_actiongroup
from zim.utils import classproperty, get_module, lookup_subclass, WeakSet

from zim.config import data_dirs, VirtualConfigManager


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

for dir in data_dirs('plugins'):
	__path__.append(dir.path)

__path__.append(__path__.pop(0)) # reshuffle real module path to the end

#~ print "PLUGIN PATH:", __path__


class PluginManager(ConnectorMixin, collections.Mapping):
	'''Manager that maintains a set of active plugins

	This class is the interface towards the rest of the application to
	load/unload plugins and to let plugins extend specific application
	objects.

	All object that want to instantiate new objects that are extendable
	need a reference to the plugin manager object that is instantiated
	when the application starts. When you instatiate a new object and
	want to present it for plugin extension, call the L{extend()} method.

	This object behaves as a dictionary with plugin object names as
	keys and plugin objects as value
	'''

	def __init__(self, config=None):
		'''Constructor
		Constructor will directly load a list of default plugins
		based on the preferences in the config. Failures while loading
		these plugins will be logged but not raise errors.

		@param config: a L{ConfigManager} object that is passed along
		to the plugins and is used to load plugin preferences.
		Defaults to a L{VirtualConfigManager} for testing.
		'''
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

	@classmethod
	def list_installed_plugins(klass):
		'''Lists plugin names for all installed plugins
		@returns: a set of plugin names
		'''
		# List "zim.plugins" sub modules based on __path__ because this
		# parameter determines what folders will considered when importing
		# sub-modules of the this package once this module is loaded.
		plugins = set()
		for dir in __path__:
			dir = Dir(dir)
			for candidate in dir.list(): # returns [] if dir does not exist
				if candidate.startswith('_') or candidate == 'base':
					continue
				elif candidate.endswith('.py'):
					plugins.add(candidate[:-3])
				elif zim.fs.isdir(dir.path+'/'+candidate) \
				and os.path.exists(dir.path+'/'+candidate+'/__init__.py'):
					plugins.add(candidate)
				else:
					pass

		return plugins

	@classmethod
	def get_plugin_class(klass, name):
		'''Get the plugin class for a given name

		@param name: the plugin name (e.g. "calendar")
		@returns: the plugin class object
		'''
		modname = 'zim.plugins.' + name
		mod = get_module(modname)
		return lookup_subclass(mod, PluginClass)

	@SignalHandler
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
		klass = self.get_plugin_class(name)
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
			with self.on_preferences_changed.blocked():
				self.general_preferences['plugins'].append(name)
				self.general_preferences.changed()

		return plugin

	def remove_plugin(self, name):
		'''Remove a plugin and it's extensions
		Fails silently if the plugin is not loaded.
		@param name: the plugin module name
		'''
		if name in self.general_preferences['plugins']:
			# Do this first regardless of exceptions etc.
			with self.on_preferences_changed.blocked():
				self.general_preferences['plugins'].remove(name)
				self.general_preferences.changed()

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
		Will also remember the object (by a weak reference) such that
		plugins loaded after this call will also be called to extend
		C{obj} on their construction
		@param obj: arbitrary object that can be extended by plugins
		'''
		if not obj in self._extendables:
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

	@ivar extension_classes: a dictionary with extension classes found
	in the plugin module

	@ivar extensions: a set with extension objects loaded by this plugin.
	The lookup extensions objects it is usually better to use the methods
	L{get_extension()} or L{get_extensions()} rather than using this
	set directly.

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

	def __init__(self, config=None):
		'''Constructor
		@param config: a L{ConfigManager} object that is used to load
		plugin preferences.
		Defaults to a L{VirtualConfigManager} for testing.
		'''
		assert 'name' in self.plugin_info, 'Missing "name" in plugin_info'
		assert 'description' in self.plugin_info, 'Missing "description" in plugin_info'
		assert 'author' in self.plugin_info, 'Missing "author" in plugin_info'
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
		this plugin. (Similar to L{zim.utils.lookup_subclass}).
		@param pluginklass: plugin class
		@param klass: base class of the wanted class
		'''
		module = get_module(pluginklass.__module__)
		return lookup_subclass(module, klass)

	def load_extensions_classes(self):
		'''Instantiates the C{extension_classes} dictionary with classes
		found in the same module as the plugin object.
		Called directly by the constructor.
		'''
		self.extension_classes = {}
		for extends, klass in self.discover_extensions_classes():
			self.add_extension_class(extends, klass)

	@classmethod
	def discover_extensions_classes(pluginklass):
		'''Find extension classes in same module as the plugin
		object class.
		@returns: yields 2-tuple of the name of the object class to be
		extended (as set by the L{extends} decorator) and the extension
		class object
		'''
		# Any class with the "__extends__" field will be added
		# (Being subclass of ObjectExtension is optional)
		module = get_module(pluginklass.__module__)
		for n, klass in inspect.getmembers(module, inspect.isclass):
			if hasattr(klass, '__extends__') and klass.__extends__:
				yield klass.__extends__, klass

	def set_extension_class(self, extends, klass):
		'''Set the extension class for a specific target object class

		This method can be used to dynamically set extension classes
		on run time. E.g. of the extension class depends on a preference.
		If another extension class was already defined for the same
		target object, it is removed.

		When the plugin is managed by a L{PluginManager} and that
		manager is aware of objects of the target class, extensions
		will immediatly be instantiated for those objects.

		@param extends: class name of the to-be-extended object
		@param klass: the extension class

		@emits: extension-point-changed
		'''
		if extends in self.extension_classes:
			if self.extension_classes[extends] == klass:
				pass
			else:
				self.remove_extension_class(extends)
				self.add_extension_class(extends, klass)
		else:
			self.add_extension_class(extends, klass)

	def add_extension_class(self, extends, klass):
		'''Add an extension class for a specific target object class

		When the plugin is managed by a L{PluginManager} and that
		manager is aware of objects of the target class, extensions
		will immediatly be instantiated for those objects.

		@param extends: class name of the to-be-extended object
		@param klass: the extension class

		@emits: extension-point-changed
		'''
		if extends in self.extension_classes:
			raise AssertionError, 'Extension point %s already in use' % name
		self.extension_classes[extends] = klass
		self.emit('extension-point-changed', extends)

	def remove_extension_class(self, extends):
		'''Remove the extension class for a specific target object class
		Will result in all extension objects for this object class to be destroyed.
		@param extends: class name of the to-be-extended object
		'''
		klass = self.extension_classes.pop(extends)
		for obj in self.get_extensions(klass):
			obj.destroy()

	def extend(self, obj, _name=None):
		'''This method will look through the extensions defined for this
		plugin and construct a new extension object if a match is found
		for C{obj}.
		@param obj: the obejct to be extended
		@param _name: lookup name to use when extending the object.
		To be used for testing only. Normally the class name of C{obj}
		is used.
		'''
		name = _name or obj.__class__.__name__
		if name in self.extension_classes:
			ext = self.extension_classes[name](self, obj)
			self.extensions.add(ext)

	def get_extension(self, klass, **attr):
		'''Look up an extension object instatiation
		@param klass: the class of the extention object (_not_ the to-be-extended
		klass)
		@param attr: any object attributes that should match
		@returns: a single extension object or C{None}
		'''
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
		'''Look up extension object instatiations
		@param klass: the class of the extention object (_not_ the to-be-extended
		klass)
		@returns: a list of extension objects (if any)
		'''
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


def extends(eklass, autoload=True):
	'''Class decorator to define extension classes
	Use this decorator to add extensions to the plugin.

	@param eklass: either a class or a class name for the class to be
	extended by this extension. When the plugin gets an object of this
	class a new extension object will be constructed.

	@param autoload: When C{False} this extension is not loaded
	automatically. This is used for extensions that are loaded on run
	time using C{PluginClass.set_extension_class()}.
	'''
	if isinstance(eklass, basestring):
		name = eklass
	else:
		name = eklass.__name__

	def inner(myklass):
		if autoload:
			myklass.__extends__ = name
		# else: do nothing for now
		return myklass

	return inner


class ObjectExtension(SignalEmitter, ConnectorMixin):
	'''Base class for all object extensions
	Extension objects should derive from this class and use the
	L{extends()} class decorator to define their target class.
	Extension objects act as a kind of decorators for their target class
	and can use the API of the target class object to add all kind of
	functionality.

	Typical target classes is the main window in the user interface
	or a specific dialog in the applicaiton. For these the
	L{WindowExtension} and L{DialogExtension} base classes are available.

	Other objects that are typically exted are the Notebook and Index
	classes. For these you use this base class directly.

	@ivar plugin: the plugin object to which this extension belongs
	@ivar obj: the object being extended
	'''

	def __init__(self, plugin, obj):
		'''Constructor
		@param plugin: the plugin object to which this extension belongs
		@param obj: the object being extended
		'''
		self.plugin = plugin
		self.obj = obj

		# Make sure extension has same lifetime as object being extended
		if not hasattr(obj, '__zim_extension_objects__'):
			obj.__zim_extension_objects__ = []
		obj.__zim_extension_objects__.append(self)

	def destroy(self):
		'''Called when the plugin is being destroyed
		Calls L{teardown()} followed by the C{teardown()} methods of
		parent base classes.
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
	'''Base class for extending gtk windows based on C{gtk.Window}

	The main use of this base class it that it helps adding menu items
	to the menubar and/or toolbar of the window (if it has any). To do this you need
	to define a class attribute "uimanager_xml" and define "action"
	methods in the class.

	An action method is any object method of the extension method that
	is decorated by the L{action()} or L{toggle_action()} decorators
	(see L{zim.actions}). Such a method is called when the user clicks
	to correcponding menu item or presses the corresponding key binding.
	The decorator is used to define the text to display in the menu
	and the key binding.

	The "uimanager_xml" is used to specify the layout of the menubar
	and toolbar. Is is a piece of XML that defines the position of the
	now menu and toolbar items. Each new item should have a name
	corresponding with a "action" method defined in the same class.
	See documentation of C{gtk.UIManager} for the XML definition.

	@ivar window: the C{gtk.Window}

	@ivar uistate: a L{ConfigDict} o store the extensions ui state or
	C{None} if the window does not maintain ui state

	The "uistate" is the per notebook state of the interface, it is
	intended for stuff like the last folder opened by the user or the
	size of a dialog after resizing. It is stored in the X{state.conf}
	file in the notebook cache folder. It differs from the preferences,
	which are stored globally and dictate the behavior of the application.
	(To access the preference use C{plugin.preferences}.)
	'''

	def __init__(self, plugin, window):
		'''Constructor
		@param plugin: the plugin object to which this extension belongs
		@param window: the C{gtk.Window} being extended
		'''
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

		if hasattr(self, 'actiongroup') \
		and self.actiongroup is not None:
			self.window.ui.uimanager.remove_action_group(self.actiongroup)


class DialogExtension(WindowExtension):
	'''Base class for extending gtk dialogs based on C{gtk.Dialog}'''

	def __init__(self, plugin, window):
		assert hasattr(window, 'action_area'), 'Not a dialog: %s' % window
		WindowExtension.__init__(self, plugin, window)
		self._dialog_buttons = []

	def add_dialog_button(self, button):
		'''Add a new button to the bottom area of the dialog
		The button is placed left of the standard buttons like the
		"OK" / "Cancel" or "Close" button of the dialog.
		@param button: a C{gtk.Button} or similar widget
		'''
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
