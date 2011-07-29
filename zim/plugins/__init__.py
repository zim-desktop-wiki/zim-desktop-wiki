# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

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
	'''In Python 2.6 has been introduced feature "Per-user site-packages Directory"
	<http://docs.python.org/whatsnew/2.6.html#pep-370-per-user-site-packages-directory>
	This function backports this feature to Python 2.5.
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
	'''Sets __path__ for the zim.plugins package. This determines what
	directories are searched when importing plugin packages in the
	zim.plugins namespace. This function looks at sys.path and would
	need to be run again if sys.path is modified after loading this
	package.
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
	@raises: ImportError if the given name does not exist

	@note: don't actually use this method to get plugin modules, see
	L{get_plugin_module()} instead.
	'''
	# __import__ has some quirks, see the reference manual
	modname = prefix + '.' + name.lower()
	mod = __import__(modname)
	for part in modname.split('.'):
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
	'''Returns the plugin module object for a given name'''
	return get_module('zim.plugins', name)


def get_plugin(name):
	'''Returns the plugin class object for a given name'''
	mod = get_plugin_module(name)
	obj = lookup_subclass(mod, PluginClass)
	obj.plugin_key = name
	return obj


def list_plugins():
	'''Returns a set of available plugin names'''
	# Only listing folders in __path__ because this parameter determines
	# what folders will considered when importing sub-modules of the
	# this package once this module is loaded.

	# FIXME how should this work for e.g. for python eggs ??
	# for windows exe we now package plugins separately

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
	'''Meta class for objects inheriting from PluginClass. It adds
	wrappers to several methods to call proper call backs.
	'''

	def __init__(klass, name, bases, dictionary):
		originit = klass.__init__

		#~ print 'DECORATE INIT', klass
		def decoratedinit(self, ui, *arg, **kwarg):
			# Calls initialize_ui and finalize_notebooks *after* __init__
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

	Plugins should define two class attributes. The first is a dict
	called 'plugin_info'. It can contain the following keys:

		* name - short name
		* description - one paragraph description
		* author - name of the author
		* help - page name in the manual (optional)

	This info will be used e.g. in the plugin tab of the preferences
	dialog.

	Secondly a tuple can be defined called 'plugin_preferences'.
	Each item in this list should in turn be tuple containing four items:

		* the key in the config file
		* an option type (see InputForm.add_inputs for more details)
		* a label to show in the dialog
		* a default value

	These preferences will be initialized if not set and the actual values
	can be found in the 'preferences' attribute. The type and label will
	be used to render a default configure dialog when triggered from
	the preferences dialog.
	'''

	__metaclass__ = PluginClassMeta

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'preferences-changed': (gobject.SIGNAL_RUN_LAST, None, ()),
	}

	plugin_info = {}

	plugin_preferences = ()

	@classmethod
	def check_dependencies_ok(klass):
		'''Checks minimum dependencies are met

		@returns: True if this plugin can be loaded
		'''
		check, dependencies = klass.check_dependencies()
		return check

	@classmethod
	def check_dependencies(klass):
		'''Checks what dependencies are met and gives details

		To be overloaded in sub-classes that have one or more
		dependencies.

		@returns: a boolean telling overall dependencies are met,
		followed by a list with details. This list consists of 3-tuples
		consisting of a (short) description of the dependency, a boolean
		for dependency being met, and a boolean for this dependency
		being optional or not.
		'''
		return (True, [])

	def __init__(self, ui):
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
		Can be overloaded by subclasses.
		'''
		# FIXME more documentation how / when to use this
		pass

	def initialize_notebook(self, notebookuri):
		'''Callback called before construction of the notebook.
		Not called when plugin is constructed while notebook already
		exists.
		Can be overloaded by subclasses.
		'''
		# FIXME more documentation how / when to use this
		pass

	def finalize_notebook(self, notebook):
		'''Callback called once the notebook object is created and set.
		Can be overloaded by subclasses.
		'''
		# FIXME more documentation how / when to use this
		pass

	def finalize_ui(self, ui):
		'''Callback called just before entering the main loop.
		Can be overloaded by subclasses.
		'''
		# FIXME more documentation how / when to use this
		pass

	def do_decorate_window(self, window):
		'''Callback which is called for each window and dialog that
		opens in zim.
		May be overloaded by sub classes
		'''
		pass

	def do_preferences_changed(self):
		'''Handler called when preferences are changed by the user.
		Can be overloaded by sub classes to apply relevant changes.
		'''
		pass

	def disconnect(self):
		'''Disconnect the plugin object from the ui, should revert
		any changes it made to the application. Default handler removes
		any GUI actions and menu items that were defined.
		'''
		if self.ui.ui_type == 'gtk':
			self.ui.remove_ui(self)
			self.ui.remove_actiongroup(self)
			if self._is_image_generator_plugin:
				self.ui.mainpage.pageview.unregister_image_generator_plugin(self)

	def toggle_action(self, action, active=None):
		'''Trigger a toggle action. If 'active' is None it is toggled, else it
		is forced to state of 'active'. This method helps to keep the menu item
		or toolbar item associated with the action in sync with your internal
		state. A typical usage to define a handler for a toggle action called
		'show_foo' would be:

			def show_foo(self, show=None):
				self.toggle_action('show_foo', active=show)

			def do_show_foo(self, show=None):
				if show is None:
					show = self.actiongroup.get_action('show_foo').get_active()

				# ... the actual logic for toggling on / off 'foo'

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
		self.ui.mainwindow.pageview.register_image_generator_plugin(self, type)
		self._is_image_generator_pluging = True


# Need to register classes defining gobject signals
gobject.type_register(PluginClass)
