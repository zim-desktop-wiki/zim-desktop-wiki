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
import weakref
import logging
import inspect

import zim.fs
from zim.fs import Dir
from zim.config import ListDict, get_environ

from zim.signals import ConnectorMixin, SIGNAL_AFTER
from zim.actions import action, toggle_action, get_actiongroup


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
	if os.name == 'nt':
		appdata = get_environ('APPDATA')
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


def get_module(name):
	'''Import a module

	@param name: the module name
	@returns: module object
	@raises ImportError: if the given name does not exist

	@note: don't actually use this method to get plugin modules, see
	L{get_plugin_module()} instead.
	'''
	# __import__ has some quirks, see the reference manual
	mod = __import__(name)
	for part in name.split('.')[1:]:
		mod = getattr(mod, part)
	return mod


def lookup_subclass(module, klass):
	'''Look for a subclass of klass in the module

	This function is used in several places in zim to get extension
	classes. Typically L{get_module()} is used first to get the module
	object, then this lookup function is used to locate a class that
	derives of a base class (e.g. PluginClass).

	@param module: module object
	@param klass: base class

	@note: don't actually use this method to get plugin classes, see
	L{get_plugin()} instead.
	'''
	subclasses = lookup_subclasses(module, klass)
	if len(subclasses) > 1:
		raise AssertionError, 'BUG: Multiple subclasses found of type: %s' % klass
	elif subclasses:
		return subclasses[0]
	else:
		return None


def lookup_subclasses(module, klass):
	'''Look for all subclasses of klass in the module

	@param module: module object
	@param klass: base class
	'''
	subclasses = []
	for name, obj in inspect.getmembers(module, inspect.isclass):
		if issubclass(obj, klass) \
		and obj.__module__.startswith(module.__name__):
			subclasses.append(obj)

	return subclasses


def get_plugin_module(name):
	'''Get the plugin module for a given name

	@param name: the plugin module name (e.g. "calendar")
	@returns: the plugin module object
	'''
	return get_module('zim.plugins.' + name.lower())


def get_plugin(name):
	'''Get the plugin class for a given name

	@param name: the plugin module name (e.g. "calendar")
	@returns: the plugin class object
	'''
	mod = get_plugin_module(name)
	obj = lookup_subclass(mod, PluginClass)
	obj.plugin_key = name
	return obj


def list_plugins():
	'''List available plugin module names

	@returns: a set of available plugin names that can be loaded
	using L{get_plugin()}.
	'''
	# Only listing folders in __path__ because this parameter determines
	# what folders will considered when importing sub-modules of the
	# this package once this module is loaded.

	plugins = set()

	for dir in __path__:
		dir = Dir(dir)
		for candidate in dir.list(): # returns [] if dir does not exist
			if candidate.startswith('_'):
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

	return plugins


class PluginClassMeta(gobject.GObjectMeta):
	'''Meta class for objects inheriting from PluginClass.
	It adds a wrapper to the constructor to call secondairy initialization
	methods.
	'''

	def __init__(klass, name, bases, dictionary):
		originit = klass.__init__

		#~ print 'DECORATE INIT', klass
		def decoratedinit(self, ui, *arg, **kwarg):
			# Calls initialize_ui and finalize_notebook *after* __init__
			#~ print 'INIT', self
			originit(self, ui, *arg, **kwarg)
			if not self.__class__ is klass:
				return # Avoid wrapping both base class and sub classes

			if self.ui.notebook:
				self.initialize_ui(ui)
				self.finalize_notebook(self.ui.notebook)
			else:
				self.initialize_ui(ui)

				def after_open_notebook(*a):
					self._merge_uistate()
					self.finalize_notebook(self.ui.notebook)

				self.connectto(self.ui, 'open-notebook',
					after_open_notebook, order=SIGNAL_AFTER)
					# FIXME with new plugin API should not need this merging

		klass.__init__ = decoratedinit


		origfinalize = klass.finalize_ui

		def decoratedfinalize(self, ui, *arg, **kwarg):
			origfinalize(self, ui, *arg, **kwarg)
			if not self.__class__ is klass:
				return # Avoid wrapping both base class and sub classes
			#~ print 'FINALIZE UI', self
			for window in ui.windows:
				self.do_decorate_window(window)
			self.connectto(ui, 'new-window', lambda u,w: self.do_decorate_window(w))

		klass.finalize_ui = decoratedfinalize


class PluginClass(ConnectorMixin, gobject.GObject):
	'''Base class for plugins. Every module containing a plugin should
	have exactly one class derived from this base class. That class
	will be initialized when the plugin is loaded.

	Plugin classes should define two class attributes: L{plugin_info} and
	L{plugin_preferences}. Optionally, they can also define the class
	attribute L{is_profile_independent}.

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

	@cvar is_profile_independent: A boolean indicating that the plugin
	configuration is global and not meant to change between notebooks.
	The default value (if undefined) is False. Plugins that set
	L{is_profile_independent} to True will be initialized before
	opening the notebook. All other plugins will only be loaded after
	the notebook is initialized.

	@ivar ui: the main application object, e.g. an instance of
	L{zim.gui.GtkInterface} or L{zim.www.WWWInterface}
	@ivar preferences: a C{ListDict()} with plugin preferences

	Preferences are the global configuration of the plugin, they are
	stored in the X{preferences.conf} config file.

	@ivar uistate: a C{ListDict()} with plugin ui state

	The "uistate" is the per notebook state of the interface, it is
	intended for stuff like the last folder opened by the user or the
	size of a dialog after resizing. It is stored in the X{state.conf}
	file in the notebook cache folder.

	@signal: C{preferences-changed ()}: emitted after the preferences
	were changed, triggers the L{do_preferences_changed} handler
	'''

	__metaclass__ = PluginClassMeta

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'preferences-changed': (gobject.SIGNAL_RUN_LAST, None, ()),
	}

	plugin_info = {}

	plugin_preferences = ()

	is_profile_independent = False

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

	def __init__(self, ui):
		'''Constructor

		@param ui: a L{NotebookInterface} object

		@implementation: sub-classes may override this constructor,
		but it is advised instead to do the work of initializing the
		plugin in the methods L{initialize_ui()}, L{initialize_notebook()},
		L{finalize_ui()} and L{finalize_notebook()} where apropriate.
		'''
		# NOTE: this method is decorated by the meta class
		gobject.GObject.__init__(self)
		self.ui = ui
		assert 'name' in self.plugin_info, 'Plugins should provide a name in the info dict'
		assert 'description' in self.plugin_info, 'Plugins should provide a description in the info dict'
		assert 'author' in self.plugin_info, 'Plugins should provide a author in the info dict'
		if self.plugin_preferences:
			assert isinstance(self.plugin_preferences[0], tuple), 'BUG: preferences should be defined as tuples'
		section = self.__class__.__name__
		self.preferences = self.ui.preferences[section]
		for pref in self.plugin_preferences:
				if len(pref) == 4:
					key, type, label, default = pref
					self.preferences.setdefault(key, default)
				else:
					key, type, label, default, check = pref
					self.preferences.setdefault(key, default, check=check)

		self._is_image_generator_plugin = False

		if self.ui.notebook:
			section = self.__class__.__name__
			self.uistate = self.ui.uistate[section]
		else:
			self.uistate = ListDict()

		# Find related extension classes in same module
		# any class with the "__extends__" field will be added
		# (Being subclass of Extension is optional)
		self.extension_classes = {}
		self._extensions = []
		module = get_module(self.__class__.__module__)
		for name, klass in inspect.getmembers(module, inspect.isclass):
			if hasattr(klass, '__extends__') and klass.__extends__:
				assert klass.__extends__ not in self.extension_classes, \
					'Extension point %s used multiple times in %s' % (klass.__extends__, module.__name__)
				self.extension_classes[klass.__extends__] = klass

	def _merge_uistate(self):
		# As a convenience we provide a uistate dict directly after
		# initialization of the plugin. However, in reality this
		# config file is only available after the notebook is opened.
		# Therefore we need to link the actual file and merge back
		# any defaults that were set during plugin intialization etc.
		if self.ui.uistate:
			section = self.__class__.__name__
			defaults = self.uistate
			self.uistate = self.ui.uistate[section]
			for key, value in defaults.items():
				self.uistate.setdefault(key, value)

	def _extension_point(self, obj):
		# TODO also check parent classes
		name = obj.__class__.__name__
		if name in self.extension_classes:
			ext = self.extension_classes[name](self, obj)
			ref = weakref.ref(obj, self._del_extension)
			self._extensions.append(ref)

	def _del_extension(self, ref):
		if ref in self._extensions:
			self._extensions.remove(ref)

	@property
	def extensions(self):
		extensions = [ref() for ref in self._extensions]
		return [e for e in extensions if e] # Filter out None values

	def initialize_ui(self, ui):
		'''Callback called during construction of the ui.

		Called after construction of the plugin when the application
		object is available. At this point the construction of the the
		interface itself does not yet need to be complete. Typically
		used to initialize any interface components of the plugin.

		@note: the plugin should check the C{ui_type} attribute of the
		application object to distinguish the Gtk from the WWW
		interface and only do something for the correct interface.

		@param ui: a L{NotebookInterface} object, e.g.
		L{zim.gui.GtkInterface}

		@implementation: optional, may be implemented by subclasses.
		'''
		pass

	def initialize_notebook(self, notebookuri):
		'''Callback called before construction of the notebook

		This callback is called before constructing the notebook object.
		It is intended for a fairly specific type of plugins that
		may want to do some manipulation of the notebook location
		before actually loading the notebook, e.g. auto-mounting
		a filesystem.

		Not called when plugin is constructed while notebook already
		exists.

		@param notebookuri: the URI of the notebook location

		@implementation: optional, may be implemented by subclasses.
		'''
		pass

	def finalize_notebook(self, notebook):
		'''Callback called once the notebook object is created

		This callback is called once the notebook object is constructed
		and loaded in the application object. This is a logical point
		to do any intialization that requires the notebook the be
		available.

		@param notebook: the L{Notebook} object

		@implementation: optional, may be implemented by subclasses.
		'''
		self._extension_point(notebook)

	def finalize_ui(self, ui):
		'''Callback called just before entering the main loop

		Called after the interface is fully initialized and has a
		notebook object loaded. Typically used for any initialization
		that needs the full application to be ready.

		@note: the plugin should check the C{ui_type} attribute of the
		application object to distinguish the Gtk from the WWW
		interface and only do something for the correct interface.

		@param ui: a L{NotebookInterface} object, e.g.
		L{zim.gui.GtkInterface}

		@implementation: optional, may be implemented by subclasses.
		'''
		# NOTE: this method is decorated by the meta class
		pass

	def do_decorate_window(self, window):
		'''Callback which is called for each window and dialog that
		opens in zim.
		May be overloaded by sub classes
		'''
		self._extension_point(window)

		# HACK
		if hasattr(window, 'pageview'):
			self._extension_point(window.pageview)

	def do_preferences_changed(self):
		'''Handler called when preferences are changed by the user

		@implementation: optional, may be implemented by subclasses.
		to apply relevant changes.
		'''
		pass

	def destroy(self):
		'''Destroy the plugin object and all extensions
		It is only called when a user actually disables the plugin,
		not when the application exits.

		Destroys all active extensions and disconnects all signals.
		This should revert any changes the plugin made to the
		application (although preferences etc. can be left in place).
		'''
		### TODO clean up this section when all plugins are ported
		if self.ui.ui_type == 'gtk':
			try:
				self.ui.remove_ui(self)
				self.ui.remove_actiongroup(self)
			except:
				logger.exception('Exception while disconnecting %s', self)

			if self._is_image_generator_plugin:
				try:
					self.ui.mainpage.pageview.unregister_image_generator_plugin(self)
				except:
					logger.exception('Exception while disconnecting %s', self)
		###

		while self._extensions:
			ref = self._extensions.pop()
			obj = ref()
			if obj:
				obj.destroy()

		try:
			self.disconnect_all()
		except:
			logger.exception('Exception while disconnecting %s', self)

	def toggle_action(self, action, active=None):
		'''Trigger a toggle action.

		This is a convenience method to help defining toggle actions
		in the menu or toolbar. It helps to keep the menu item
		or toolbar item in sync with your internal state.
		A typical usage to define a handler for a toggle action called
		'show_foo' would be::

			def show_foo(self, show=None):
				self.toggle_action('show_foo', active=show)

			def do_show_foo(self, show=None):
				if show is None:
					show = self.actiongroup.get_action('show_foo').get_active()

				# ... the actual logic for toggling on / off 'foo'

		This way you have a public method C{show_foo()} that can be
		called by anybody and a handler C{do_show_foo()} that is
		called when the user clicks the menu item. The trick is that
		when C{show_foo()} is called, the menu item is also updates.

		@param action: the name of the action item
		@param active: when C{None} the item is toggled with respect
		to it's current state, when C{True} or C{False} forces a state
		'''
		name = action
		action = self.actiongroup.get_action(name)
		if active is None or active != action.get_active():
			action.activate()
		else:
			method = getattr(self, 'do_'+name)
			method(active)

	#~ def remember_decorated_window(self, window):
		#~ import weakref
		#~ if not hasattr(self, '_decorated_windows'):
			#~ self._decorated_windows = []
		#~ ref = weakref.ref(window, self._clean_decorated_windows_list)
		#~ self._decorated_windows.append(ref)

	#~ def _clean_decorated_windows_list(self, *a):
		#~ self._decorated_windows = [
			#~ ref for ref in self._decorated_windows
				#~ if not ref() is None ]

	#~ def get_decorated_windows(self):
		#~ if not hasattr(self, '_decorated_windows'):
			#~ return []
		#~ else:
			#~ self._clean_decorated_windows_list()
			#~ return [ref() for ref in self._decorated_windows]

	def register_image_generator_plugin(self, type):
		'''Convenience method to register a plugin that adds a type
		of image objects

		@param type: the type of the objects (e.g. "equation")

		@todo: document image geneartor plugins
		'''
		self.ui.mainwindow.pageview.register_image_generator_plugin(self, type)
		self._is_image_generator_pluging = True


# Need to register classes defining gobject signals
gobject.type_register(PluginClass)


def extends(klass):
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
		myklass.__extends__ = name
		return myklass

	return inner


class Extension(ConnectorMixin):

	# TODO, maybe add try .. except wrapper for destroy in meta class ?
	# have except always call super.destroy

	def __init__(self, plugin, obj):
		self.plugin = plugin
		self.obj = obj

	def destroy(self):
		try:
			self.disconnect_all()
		except:
			logger.exception('Exception while disconnecting %s', self)


class WindowExtension(Extension):

	def __init__(self, plugin, window):
		self.plugin = plugin
		self.window = window

		if hasattr(self, 'uimanager_xml'):
			# TODO move uimanager to window
			actiongroup = get_actiongroup(self)
			self.window.ui.uimanager.insert_action_group(actiongroup, 0)
			self._uimanager_id = self.window.ui.uimanager.add_ui_from_string(self.uimanager_xml)

		window.connect_object('destroy', self.__class__.destroy, self)

	def destroy(self):
		try:
			# TODO move uimanager to window
			if hasattr(self, '_uimanager_id') \
			and self._uimanager_id is not None:
				self.window.ui.uimanager.remove_ui(self._uimanager_id)
				self._uimanager_id = None

			if hasattr(self, 'actiongroup'):
				self.window.ui.uimanager.remove_action_group(self.actiongroup)
		except:
			logger.exception('Exception while removing UI %s', self)

		Extension.destroy(self)


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

	def destroy(self):
		try:
			for b in self._dialog_buttons:
				self.window.action_area.remove(b)
		except:
			logger.exception('Could not remove buttons')

		WindowExtension.destroy(self)
