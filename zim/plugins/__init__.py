# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

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

import zim.fs
from zim.fs import Dir
from zim.config import ListDict


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
		if 'APPDATA' in os.environ:
			dir = Dir([os.environ['APPDATA'],
						'Python/Python25/site-packages'])
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


def get_module(prefix, name):
	'''Import a module for C{prefix + '.' + name}

	@param prefix: the module path to search (e.g. "zim.plugins")
	@param name: the module name (e.g. "calendar") - case insensitive

	@returns: module object
	@raises ImportError: if the given name does not exist

	@note: don't actually use this method to get plugin modules, see
	L{get_plugin_module()} instead.
	'''
	# __import__ has some quirks, see the reference manual
	modname = prefix + '.' + name.lower()
	mod = __import__(modname)
	for part in modname.split('.')[1:]:
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
	for name in dir(module):
		obj = getattr(module, name)
		if ( isinstance(obj, (type, types.ClassType)) # is a class
		and issubclass(obj, klass) # is derived from e.g. PluginClass
		and not obj == klass ): # but is not e.g. PluginClass itself (which is imported)
			return obj


def get_plugin_module(name):
	'''Get the plugin module for a given name

	@param name: the plugin module name (e.g. "calendar")
	@returns: the plugin module object
	'''
	return get_module('zim.plugins', name)


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
				self.ui.connect_after('open-notebook', self._merge_uistate)
					# FIXME with new plugin API should not need this merging
				self.ui.connect_object_after('open-notebook',
					self.__class__.finalize_notebook, self)

		klass.__init__ = decoratedinit


		origfinalize = klass.finalize_ui

		def decoratedfinalize(self, ui, *arg, **kwarg):
			origfinalize(self, ui, *arg, **kwarg)
			if not self.__class__ is klass:
				return # Avoid wrapping both base class and sub classes
			#~ print 'FINALIZE UI', self
			ui.connect_object('new-window', self.__class__.do_decorate_window, self)
			for window in ui.windows:
				self.do_decorate_window(window)

		klass.finalize_ui = decoratedfinalize




class PluginClass(gobject.GObject):
	'''Base class for plugins. Every module containing a plugin should
	have exactly one class derived from this base class. That class
	will be initialized when the plugin is loaded.

	Plugin classes should define two class attributes: L{plugin_info} and
	L{plugin_preferences}. Optionally, they can also define the class
	attribute L{is_profile_independent}.

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

	@signal: preferences-changed (): emitted after the preferences
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

	def _merge_uistate(self, *a):
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
		# NOTE: this method is decorated by the meta class
		pass

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
		pass

	def do_decorate_window(self, window):
		'''Callback which is called for each window and dialog that
		opens in zim.
		May be overloaded by sub classes
		'''
		pass

	def do_preferences_changed(self):
		'''Handler called when preferences are changed by the user

		@implementation: optional, may be implemented by subclasses.
		to apply relevant changes.
		'''
		pass

	def disconnect(self):
		'''Disconnect the plugin object from the ui.

		This should revert any changes the plugin made to the
		application (although preferences etc. can be left in place).
		It is only called when a user actually disables the plugin,
		not when the application exits. See the relevant sigals on
		L{zim.gui.GtkInterface} for that.

		@implementation: must be implemented by sub-classes that do
		more than just adding a menu item. The default implementation
		just removes any menu items that were defined by this plugin.
		'''
		if self.ui.ui_type == 'gtk':
			self.ui.remove_ui(self)
			self.ui.remove_actiongroup(self)
			if self._is_image_generator_plugin:
				self.ui.mainpage.pageview.unregister_image_generator_plugin(self)

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
