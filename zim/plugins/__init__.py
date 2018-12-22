
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
object that is being extended. Typical classes to extend in a plugin
are e.g. the L{MainWindow}, the L{PageView} and the L{Notebook} classes.

To define an extension, you need to subclass the extension class that relates
to the object you want to extend. E.g. the L{MainWindowExtension}, the
L{PageViewExtension} or the L{NotebookExtension}.

Each extension object that is instantiated is linked to the plugin object
that it belongs to. So it can access functions of the plugin object and
it can use the plugin object to find other extension objects if it
needs to cooperate. All extension classes defined in the same module
file as the plugin object are automatically linked to the plugin.

See the various standard plugins for examples how to define a plugin
object and use extensions.

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




from gi.repository import GObject
import types
import os
import sys
import logging
import inspect
import collections

from zim.newfs import LocalFolder, LocalFile

from zim.signals import SignalEmitter, ConnectorMixin, SIGNAL_AFTER, SignalHandler
from zim.utils import classproperty, get_module, lookup_subclass, lookup_subclasses, WeakSet
from zim.actions import hasaction

from zim.config import data_dirs, XDG_DATA_HOME, ConfigDict, String, ConfigManager


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

#~ print("PLUGIN PATH:", __path__)


PLUGIN_FOLDER = XDG_DATA_HOME.subdir('zim/plugins')


class PluginManagerClass(ConnectorMixin, collections.Mapping):
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

	def load_plugins_from_preferences(self, names):
		'''Calls L{load_plugin()} for each plugin in C{names} but does not
		raise an exception when loading fails.
		'''
		for name in names:
			try:
				self.load_plugin(name)
			except:
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
			try:
				plugin.extend(obj)
			except:
				logger.exception('Exception in plugin: %s', name)

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


PluginManager = PluginManagerClass()  # singleton


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

	@ivar extension_classes: a dictionary with extension classes found
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

		self.load_insertedobject_types()
		self.load_extensions_classes()

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

	def load_insertedobject_types(self):
		'''Loads L{InsertedObjectType} classes defined in the same modul
		as the plugin.
		'''
		from zim.objectmanager import ObjectManager
		self._objecttypes = [
			objtype(self)
				for objtype in self.discover_classes(InsertedObjectType)
		]
		for obj in self._objecttypes:
			ObjectManager.register_object(obj)

	def load_extensions_classes(self):
		'''Instantiates the C{extension_classes} dictionary with classes
		found in the same module as the plugin object.
		Called directly by the constructor.
		'''
		self.extension_classes = {}
		for klass in self.discover_classes(ExtensionBase):
			extends = klass.__extends__
			if extends in self.extension_classes:
				raise AssertionError('Extension point %s already in use' % name)
			self.extension_classes[extends] = klass

	@classmethod
	def discover_classes(pluginklass, baseclass):
		'''Yields a list of classes derived from C{baseclass} and
		defined in the same module as the plugin
		'''
		module = get_module(pluginklass.__module__)
		for klass in lookup_subclasses(module, baseclass):
			yield klass

	def extend(self, obj):
		'''This method will look through the extensions defined for this
		plugin and construct a new extension object if a match is found
		for C{obj}.
		@param obj: the object to be extended
		'''
		name = obj.__class__.__name__
		if name in self.extension_classes:
			try:
				ext = self.extension_classes[name](self, obj)
			except ExtensionNotApplicable:
				pass
			except:
				logger.exception('Failed loading extension %s for plugin %s', self.extension_classes[name], self)
			else:
				self.extensions.add(ext)

	def destroy(self):
		'''Destroy the plugin object and all extensions
		It is only called when a user actually disables the plugin,
		not when the application exits.

		Destroys all active extensions and disconnects all signals.
		This should revert any changes the plugin made to the
		application (although preferences etc. can be left in place).
		'''
		from zim.objectmanager import ObjectManager

		for obj in self.extensions:
			obj.destroy()

		for obj in self._objecttypes:
			ObjectManager.unregister_object(obj)

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
	for e in obj.__zim_extension_objects__:
		if isinstance(e, klass):
			return e
	else:
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
		for e in obj.__zim_extension_objects__:
			if hasaction(e, actionname):
				return getattr(e, actionname)
		else:
			raise ValueError('Action not found: %s' % actionname)


class ExtensionNotApplicable(ValueError):
	'''Exception that can be raised from an extension constructor to
	abort loading the extension.
	'''
	pass


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


class DialogExtension(ExtensionBase):
	'''Base class for extending Gtk dialogs based on C{Gtk.Dialog}

	The class attribute C{__dialog_class_name__} must be set to select the
	dialog to be extended.

	@ivar dialog: the C{Gtk.Dialog} object
	'''

	__dialog_class_name__ = None

	@classproperty
	def __extends__(cls):
		return cls.__dialog_class_name__

	def __init__(self, plugin, dialog):
		assert self.__dialog_class_name__ is not None, 'Class attribute must be set to'
		if dialog.__class__.__name__ != self.__dialog_class_name__:
			raise ExtensionNotApplicable()

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


class InsertedObjectType(ConnectorMixin):
	'''Base class for defining "objects" that can be inserted in a wiki page

	This class is called "InsertedObjectType" instead of "InsertedObject"
	because it does *not* represent a single inserted object, but defines a
	type of object of which many instances can occur. The instances themselves
	are represented by a series of tokens for the parser and a model plus a
	widget for the user interface.
	'''

	# TODO: API to communicate whether this is an inline object or a block
	#       level object. This could change while editing so must be a model
	#       property somehow.

	name = None

	label = None
	verb_icon = None

	object_attr = {}

	def __init__(self, plugin):
		assert self.name is not None
		assert self.label is not None
		self.plugin = plugin
		self.object_attr['type'] = String(self.name)

		for name in ('model_from_data', 'data_from_model', 'format'):
			orig = getattr(self, name)
			wrapper = getattr(self, '_' + name + '_wrapper')
			setattr(self, '_inner_' + name, orig)
			setattr(self, name, wrapper)

	def parse_attrib(self, attrib):
		'''Convenience method to enforce the supported attributes and their
		types.
		@returns: a L{ConfigDict} using the C{object_attr} dict as definition
		'''
		if not isinstance(attrib, ConfigDict):
			attrib = ConfigDict(attrib)
			attrib.define(self.object_attr)
		return attrib

	def new_object(self):
		'''Create a new empty object
		@returns: a 2-tuple C{(attrib, data)}
		'''
		attrib = self.parse_attrib({})
		return attrib, ''

	def new_object_interactive(self, parent):
		'''Create a new object interactively
		Interactive means that we can use e.g. a dialog to prompt for input.
		The default behavior is to use L{new_object()}.
		@param parent: Gtk widget to use as parent widget for dialogs
		@returns: a 2-tuple C{(attrib, data)}
		@raises: ValueError: if user cancelled the action
		'''
		return self.new_object()

	def _model_from_data_wrapper(self, attrib, data):
		attrib = self.parse_attrib(attrib)
		return self._inner_model_from_data(attrib, data)

	def model_from_data(self, attrib, data):
		'''Returns a model for the object

		The main purpose for the model is that it is shared between widgets that
		show the same object. See e.g. C{Gtk.TextBuffer} or C{Gtk.TreeModel}
		for examples.

		No API is expected of the model object other than that it can be used as
		argument for L{create_widget()} and L{data_from_model()} and a
		"changed" signal that should be emitted when the content has changed, so
		the pageview knows that the page has changed and should be saved before
		closing.

		This method should always be robust for missing attributes and body
		contents. The C{attrib} will automatically be checked by L{parse_attrib}
		before being given to this method.

		@param attrib: dict with object attributes
		@param data: string with object content
		@returns: a model object
		'''
		raise NotImplementedError

	def _data_from_model_wrapper(self, model):
		attrib, data = self._inner_data_from_model(model)
		return attrib.copy(), data # Enforce shallow copy

	def data_from_model(self, model):
		'''Returns the object data for a model object
		This method is used to serialize the model object back into a form that
		can be handled when parsing wiki content.
		@param model: an object created with L{model_from_data()}
		@returns: a 2-tuple C{(attrib, data)}
		'''
		raise NotImplementedError

	def create_widget(self, model):
		'''Return a Gtk widget for the given model
		@param model: an object created with L{model_from_data()}
		@returns: a Gtk widget object derived from L{InsertedObjectWidget}
		'''
		raise NotImplementedError

	def _format_wrapper(self, format, dumper, attrib, data):
		attrib = self.parse_attrib(attrib)
		return self._inner_format(format, dumper, attrib, data)

	def format(self, format, dumper, attrib, data):
		'''Format the object using a specific output format
		Intended to improve rendering of the object on exporting.

		This method should always be robust for missing attributes and body
		contents. The C{attrib} will automatically be checked by L{parse_attrib}
		before being given to this method.

		Implementing this method is optional, default checks for a specific
		method per format (e.g. C{format_html()} for the "html" formatal) and
		raises C{ValueError} if no such method is defined.

		@param format: name of the output format
		@param dumper: L{Dumper} object
		@param attrib: dict with object attributes
		@param data: string with object content
		@returns: a list of strings
		@raises ValueError: if no specific formatting for "format" is available
		'''
		try:
			method = getattr(self, 'format_' + format)
		except AttributeError:
			raise ValueError('No "%s" formatting defined for objecttype "%s"' % (format, self.name))
		else:
			return method(dumper, attrib, data)

	def destroy(self):
		'''Called when unloading the plugin'''
		self.disconnect_all()
