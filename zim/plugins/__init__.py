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
	'''Sets __path__ for the zim.plugins pacakge. This determines what
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


def get_plugin_module(pluginname):
	'''Returns the plugin module object for a given name'''
	# __import__ has some quirks, see the reference manual
	pluginname = pluginname.lower()
	mod = __import__('zim.plugins.'+pluginname)
	mod = getattr(mod, 'plugins')
	mod = getattr(mod, pluginname)
	return mod


def get_plugin(pluginname):
	'''Returns the plugin class object for a given name'''
	mod = get_plugin_module(pluginname)
	for name in dir(mod):
		obj = getattr(mod, name)
		if ( isinstance(obj, (type, types.ClassType)) # is a class
		and issubclass(obj, PluginClass) # is derived from PluginClass
		and not obj == PluginClass ): # but is not PluginClass itself
			obj.plugin_key = pluginname
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
		'''Like check_dependencies, but just returns boolean'''
		return all(dep[1] for dep in klass.check_dependencies())

	@classmethod
	def check_dependencies(klass):
		'''This method checks which dependencies are met. It should return a list of tuples,
		one for each dependency, with a string giving the name of the dependency and a boolean
		indicating if it is fulfilled or not. When a plugin has no dependencies an empty list
		should be returned (which is done in the base class).
		'''
		return []

	def __init__(self, ui):
		gobject.GObject.__init__(self)
		self.ui = ui
		assert 'name' in self.plugin_info, 'Plugins should provide a name in the info dict'
		assert 'description' in self.plugin_info, 'Plugins should provide a description in the info dict'
		assert 'author' in self.plugin_info, 'Plugins should provide a author in the info dict'
		if self.plugin_preferences:
			assert isinstance(self.plugin_preferences[0], tuple), 'BUG: preferences should be defined as tupels'
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
		# config file is only available after the notebook is openend.
		# Therefore we need to link the actual file and merge back
		# any defaults that were set during plugin intialization etc.
		if self.ui.uistate:
			section = self.__class__.__name__
			defaults = self.uistate
			self.uistate = self.ui.uistate[section]
			for key, value in defaults.items():
				self.uistate.setdefault(key, value)

	def initialize_ui(self, ui):
		'''Callback called during contruction of the ui.
		Can be overloaded by subclasses.
		'''
		# FIXME more documentation how / when to use this
		pass

	def initialize_notebook(self, notebookuri):
		'''Callback called before contruction of the notebook.
		Not called when plugin is contructed while notebook already
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
		or toolbar item asociated with the action in sync with your internal
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
