
# Copyright 2008-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Zim test suite'''




import os
import sys
import tempfile
import shutil
import logging
import gettext
import xml.etree.cElementTree as etree
import types
import glob

try:
	import gi
	gi.require_version('Gtk', '3.0')
	from gi.repository import Gtk
except ImportError:
	Gtk = None


import unittest
from unittest import skip, skipIf, skipUnless, expectedFailure


gettext.install('zim', names=('_', 'gettext', 'ngettext'))

FAST_TEST = False #: determines whether we skip slow tests or not
FULL_TEST = False #: determine whether we mock filesystem tests or not

# This list also determines the order in which tests will executed
__all__ = [
	# Packaging etc.
	'package', 'translations',
	# Basic libraries
	'datetimetz', 'utils', 'errors', 'signals', 'actions',
	'fs', 'newfs',
	'config', 'applications',
	'parsing', 'tokenparser',
	# Notebook components
	'formats', 'templates',
	'indexers', 'indexviews', 'operations', 'notebook', 'history',
	'export', 'www', 'search',
	# Core application
	'widgets', 'pageview', 'save_page', 'clipboard', 'uiactions',
	'mainwindow', 'notebookdialog',
	'preferencesdialog', 'searchdialog', 'customtools', 'templateeditordialog',
	'main', 'plugins',
	# Plugins
	'pathbar', 'pageindex',
	'journal', 'printtobrowser', 'versioncontrol', 'inlinecalculator',
	'tasklist', 'tags', 'imagegenerators', 'tableofcontents',
	'quicknote', 'attachmentbrowser', 'insertsymbol',
	'sourceview', 'tableeditor', 'bookmarksbar', 'spell',
	'arithmetic', 'linesorter'
]


mydir = os.path.abspath(os.path.dirname(__file__))

# when a test is missing from the list that should be detected
for file in glob.glob(mydir + '/*.py'):
	name = os.path.basename(file)[:-3]
	if name != '__init__' and not name in __all__:
		raise AssertionError('Test missing in __all__: %s' % name)

# get our own data dir
DATADIR = os.path.abspath(os.path.join(mydir, 'data'))

# and project data dir
ZIM_DATADIR = os.path.abspath(os.path.join(mydir, '../data'))

# get our own tmpdir
TMPDIR = os.path.abspath(os.path.join(mydir, 'tmp'))
	# Wanted to use tempfile.get_tempdir here to put everything in
	# e.g. /tmp/zim but since /tmp is often mounted as special file
	# system this conflicts with thrash support. For writing in source
	# dir we have conflict with bazaar controls, this is worked around
	# by a config mode switch in the bazaar backend of the version
	# control plugin

# also get the default tmpdir and put a copy in the env
REAL_TMPDIR = tempfile.gettempdir()


def load_tests(loader, tests, pattern):
	'''Load all test cases and return a unittest.TestSuite object.
	The parameters 'tests' and 'pattern' are ignored.
	'''
	suite = unittest.TestSuite()
	for name in ['tests.' + name for name in __all__]:
		test = loader.loadTestsFromName(name)
		suite.addTest(test)
	return suite


def _setUpEnvironment():
	'''Method to be run once before test suite starts'''
	# In fact to be loaded before loading some of the zim modules
	# like zim.config and any that export constants from it

	# NOTE: do *not* touch XDG_DATA_DIRS here because it is used by Gtk to
	# find resources like pixbuf loaders etc. not finding these will lead to
	# a crash. Especially under msys the defaults are not set but also not
	# map to the default folders. So not touching it is the safest path.
	# For zim internal usage this is overloaded in config.basedirs.set_basedirs()
	os.environ.update({
		'ZIM_TEST_RUNNING': 'True',
		'ZIM_TEST_ROOT': os.getcwd(),
		'TMP': TMPDIR,
		'REAL_TMP': REAL_TMPDIR,
		'XDG_DATA_HOME': os.path.join(TMPDIR, 'data_home'),
		'TEST_XDG_DATA_DIRS': os.path.join(TMPDIR, 'data_dir'),
		'XDG_CONFIG_HOME': os.path.join(TMPDIR, 'config_home'),
		'XDG_CONFIG_DIRS': os.path.join(TMPDIR, 'config_dir'),
		'XDG_CACHE_HOME': os.path.join(TMPDIR, 'cache_home')
	})

	if os.path.isdir(TMPDIR):
		shutil.rmtree(TMPDIR)
	os.makedirs(TMPDIR)


if os.environ.get('ZIM_TEST_RUNNING') != 'True':
	# Do this when loaded, but not re-do in sub processes
	# (doing so will kill e.g. the ipc test...)
	_setUpEnvironment()


## Setup special logging for tests

class UncaughtWarningError(AssertionError):
	pass


class TestLoggingHandler(logging.Handler):
	'''Handler class that raises uncaught errors to ensure test don't fail silently'''

	def __init__(self, level=logging.WARNING):
		logging.Handler.__init__(self, level)
		fmt = logging.Formatter('%(levelname)s %(filename)s %(lineno)s: %(message)s')
		self.setFormatter(fmt)

	def emit(self, record):
		if record.levelno >= logging.WARNING \
		and not record.name.startswith('tests'):
			raise UncaughtWarningError(self.format(record))
		else:
			pass

logging.getLogger().addHandler(TestLoggingHandler())
	# Handle all errors that make it up to the root level

try:
	logging.getLogger('zim.test').warning('foo')
except UncaughtWarningError:
	pass
else:
	raise AssertionError('Raising errors on warning fails')

###


from zim.newfs import LocalFolder

import zim.config.manager
import zim.plugins

_zim_pyfiles = []

def zim_pyfiles():
	'''Returns a list with file paths for all the zim python files'''
	if not _zim_pyfiles:
		for d, dirs, files in os.walk('zim'):
			_zim_pyfiles.extend([d + '/' + f for f in files if f.endswith('.py')])
		_zim_pyfiles.sort()
	for file in _zim_pyfiles:
		yield file # shallow copy


def slowTest(obj):
	'''Decorator for slow tests

	Tests wrapped with this decorator are ignored when you run
	C{test.py --fast}. You can either wrap whole test classes::

		@tests.slowTest
		class MyTest(tests.TestCase):
			...

	or individual test functions::

		class MyTest(tests.TestCase):

			@tests.slowTest
			def testFoo(self):
				...

			def testBar(self):
				...
	'''
	if FAST_TEST:
		wrapper = skip('Slow test')
		return wrapper(obj)
	else:
		return obj


MOCK_ALWAYS_MOCK = 'mock' #: Always choose mock folder, alwasy fast
MOCK_DEFAULT_MOCK = 'default_mock' #: By default use mock, but sometimes at random use real fs or at --full
MOCK_DEFAULT_REAL = 'default_real' #: By default use real fs, mock oly for --fast
MOCK_ALWAYS_REAL = 'real' #: always use real fs -- not recommended unless test fails for mock

import random
import time

TIMINGS = []

class TestCase(unittest.TestCase):
	'''Base class for test cases'''

	maxDiff = None

	mockConfigManager = True

	def run(self, *a, **kwa):
		start = time.time()
		unittest.TestCase.run(self, *a, **kwa)
		end = time.time()
		TIMINGS.append((self.__class__.__name__ + '.' + self._testMethodName, end - start))

	@classmethod
	def setUpClass(cls):
		if cls.mockConfigManager:
			zim.config.manager.makeConfigManagerVirtual()
			zim.plugins.resetPluginManager()

	@classmethod
	def tearDownClass(cls):
		if Gtk is not None:
			gtk_process_events() # flush any pending events / warnings

		zim.config.manager.resetConfigManager()
		zim.plugins.resetPluginManager()

	def setUpFolder(self, name=None, mock=MOCK_DEFAULT_MOCK):
		'''Convenience method to create a temporary folder for testing
		@param name: name postfix for the folder
		@param mock: mock level for this test, one of C{MOCK_ALWAYS_MOCK},
		C{MOCK_DEFAULT_MOCK}, C{MOCK_DEFAULT_REAL} or C{MOCK_ALWAYS_REAL}.
		The C{MOCK_ALWAYS_*} arguments force the use of a real folder or a
		mock object. The C{MOCK_DEFAULT_*} arguments give a preference but
		for these the behavior is overruled by "--fast" and "--full" in the
		test script.
		@returns: a L{Folder} object (either L{LocalFolder} or L{MockFolder})
		that is guarenteed non-existing
		'''
		path = self._get_tmp_name(name)

		if mock == MOCK_ALWAYS_MOCK:
			use_mock = True
		elif mock == MOCK_ALWAYS_REAL:
			use_mock = False
		else:
			if FULL_TEST:
				use_mock = False
			elif FAST_TEST:
				use_mock = True
			else:
				use_mock = (mock == MOCK_DEFAULT_MOCK)

		if use_mock:
			from zim.newfs.mock import MockFolder
			folder = MockFolder(path)
		else:
			from zim.newfs import LocalFolder
			if os.path.exists(path):
				logger.debug('Clear tmp folder: %s', path)
				shutil.rmtree(path)
				assert not os.path.exists(path) # make real sure
			folder = LocalFolder(path)

		assert not folder.exists()
		return folder

	def setUpNotebook(self, name='notebook', mock=MOCK_ALWAYS_MOCK, content={}, folder=None):
		'''
		@param name: name postfix for the folder, see L{setUpFolder}
		@param mock: see L{setUpFolder}, default is C{MOCK_ALWAYS_MOCK}
		@param content: dictionary where the keys are page names and the
		values the page content. If a tuple or list is given, pages are created
		with default text. L{Path} objects are allowed instead of page names
		@param folder: determine the folder to be used, only needed in special
		cases where the folder must be outside of the project folder, like
		when testing version control logic
		'''
		import datetime
		from zim.newfs.mock import MockFolder
		from zim.notebook.notebook import NotebookConfig, Notebook
		from zim.notebook.page import Path
		from zim.notebook.layout import FilesLayout
		from zim.notebook.index import Index
		from zim.formats.wiki import WIKI_FORMAT_VERSION

		if folder is None:
			folder = self.setUpFolder(name, mock)
		folder.touch() # Must exist for sane notebook
		cache_dir = folder.folder('.zim')
		layout = FilesLayout(folder, endofline='unix')

		if isinstance(folder, MockFolder):
			conffile = folder.file('notebook.zim')
			config = NotebookConfig(conffile)
			index = Index(':memory:', layout)
		else:
			conffile = folder.file('notebook.zim')
			config = NotebookConfig(conffile)
			cache_dir.touch()
			index = Index(cache_dir.file('index.db').path, layout)

		if isinstance(content, (list, tuple)):
			content = dict((p, 'test 123') for p in content)

		notebook = Notebook(cache_dir, config, folder, layout, index)
		for name, text in list(content.items()):
			path = Path(name) if isinstance(name, str) else name
			file, folder = layout.map_page(path)
			file.write(
				(
					'Content-Type: text/x-zim-wiki\n'
					'Wiki-Format: %s\n'
					'Creation-Date: %s\n\n'
				) % (WIKI_FORMAT_VERSION, datetime.datetime.now().isoformat())
				+ text
			)

		notebook.index.check_and_update()
		assert notebook.index.is_uptodate
		return notebook

	def create_tmp_dir(self, name=None):
		'''Returns a path to a tmp dir where tests can write data.
		The dir is removed and recreated empty every time this function
		is called with the same name from the same class.
		'''
		print("Deprecated: TestCase.create_tmp_dir()")
		folder = self.setUpFolder(name=name, mock=MOCK_ALWAYS_REAL)
		folder.touch()
		return folder.path

	def _get_tmp_name(self, postfix):
		name = self.__class__.__name__
		if self._testMethodName != 'runTest':
			name += '_' + self._testMethodName

		if postfix:
			assert '/' not in postfix and '\\' not in postfix, 'Don\'t use this method to get sub folders or files'
			name += '_' + postfix

		return os.path.join(TMPDIR, name)


class LoggingFilter(logging.Filter):
	'''Convenience class to surpress zim errors and warnings in the
	test suite. Acts as a context manager and can be used with the
	'with' keyword.

	Alternatively you can call L{wrap_test()} from test C{setUp}.
	This will start the filter and make sure it is cleaned up again.
	'''

	# Due to how the "logging" module works, logging channels do inherit
	# handlers of parents but not filters. Therefore setting a filter
	# on the "zim" channel will not surpress messages from sub-channels.
	# Instead we need to set the filter both on the channel and on
	# top level handlers to get the desired effect.

	def __init__(self, logger, message=None):
		'''Constructor
		@param logger: the logging channel name
		@param message: can be a string, or a sequence of strings.
		Any messages that start with this string or any of these
		strings are surpressed.
		'''
		self.logger = logger
		self.message = message

	def __enter__(self):
		logging.getLogger(self.logger).addFilter(self)
		for handler in logging.getLogger().handlers:
			handler.addFilter(self)

	def __exit__(self, *a):
		logging.getLogger(self.logger).removeFilter(self)
		for handler in logging.getLogger().handlers:
			handler.removeFilter(self)

	def filter(self, record):
		if record.name.startswith(self.logger):
			msg = record.getMessage()
			if self.message is None:
				return False
			elif isinstance(self.message, tuple):
				return not any(msg.startswith(m) for m in self.message)
			else:
				return not msg.startswith(self.message)
		else:
			return True


	def wrap_test(self, test):
		self.__enter__()
		test.addCleanup(self.__exit__)


class DialogContext(object):
	'''Context manager to catch dialogs being opened

	Inteded to be used like this::

		def myCustomTest(dialog):
			self.assertTrue(isinstance(dialog, CustomDialogClass))
			# ...
			dialog.assert_response_ok()

		with DialogContext(
			myCustomTest,
			SomeOtherDialogClass
		):
			gui.show_dialogs()

	In this example the first dialog that is run by C{gui.show_dialogs()}
	is checked by the function C{myCustomTest()} while the second dialog
	just needs to be of class C{SomeOtherDialogClass} and will then
	be closed with C{assert_response_ok()} by the context manager.

	This context only works for dialogs derived from zim's Dialog class
	as it uses a special hook in L{zim.gui.widgets}.
	'''

	def __init__(self, *definitions):
		'''Constructor
		@param definitions: list of either classes or methods
		'''
		self.stack = list(definitions)
		self.old_test_mode = None

	def __enter__(self):
		import zim.gui.widgets
		self.old_test_mode = zim.gui.widgets.TEST_MODE
		self.old_callback = zim.gui.widgets.TEST_MODE_RUN_CB
		zim.gui.widgets.TEST_MODE = True
		zim.gui.widgets.TEST_MODE_RUN_CB = self._callback

	def _callback(self, dialog):
		#~ print('>>>', dialog)
		if not self.stack:
			raise AssertionError('Unexpected dialog run: %s' % dialog)

		handler = self.stack.pop(0)

		if isinstance(handler, type): # is a class
			self._default_handler(handler, dialog)
		else: # assume a function
			handler(dialog)

	def _default_handler(self, cls, dialog):
		if not isinstance(dialog, cls):
			raise AssertionError('Expected dialog of class %s, but got %s instead' % (cls, dialog.__class__))
		dialog.assert_response_ok()

	def __exit__(self, *error):
		import zim.gui.widgets
		zim.gui.widgets.TEST_MODE = self.old_test_mode
		zim.gui.widgets.TEST_MODE_RUN_CB = self.old_callback

		has_error = any(error)
		if self.stack and not has_error:
			raise AssertionError('%i expected dialog(s) not run' % len(self.stack))

		return False # Raise any errors again outside context


class WindowContext(DialogContext):

	def _default_handler(self, cls, window):
		if not isinstance(window, cls):
			raise AssertionError('Expected window of class %s, but got %s instead' % (cls, dialog.__class__))


class ApplicationContext(object):

	def __init__(self, *callbacks):
		self.stack = list(callbacks)

	def __enter__(self):
		import zim.applications
		self.old_test_mode = zim.applications.TEST_MODE
		self.old_callback = zim.applications.TEST_MODE_RUN_CB
		zim.applications.TEST_MODE = True
		zim.applications.TEST_MODE_RUN_CB = self._callback

	def _callback(self, cmd):
		if not self.stack:
			raise AssertionError('Unexpected application run: %s' % cmd)

		handler = self.stack.pop(0)
		return handler(cmd) # need to return for pipe()

	def __exit__(self, *error):
		import zim.gui.widgets
		zim.applications.TEST_MODE = self.old_test_mode
		zim.applications.TEST_MODE_RUN_CB = self.old_callback

		if self.stack and not any(error):
			raise AssertionError('%i expected command(s) not run' % len(self.stack))

		return False # Raise any errors again outside context


class ZimApplicationContext(object):

	def __init__(self, *callbacks):
		self.stack = list(callbacks)

	def __enter__(self):
		from zim.main import ZIM_APPLICATION
		self.apps_obj = ZIM_APPLICATION
		self.old_run = ZIM_APPLICATION._run_cmd
		ZIM_APPLICATION._run_cmd = self._callback

	def _callback(self, cmd, args):
		if not self.stack:
			raise AssertionError('Unexpected command run: %s %r' % (cmd, args))

		handler = self.stack.pop(0)
		handler(cmd, args)

	def __exit__(self, *error):
		self.apps_obj._run_cmd = self.old_run

		if self.stack and not any(error):
			raise AssertionError('%i expected command(s) not run' % len(self.stack))

		return False # Raise any errors again outside context



class TestData(object):
	'''Wrapper for a set of test data in tests/data'''

	def __init__(self, format):
		assert format == 'wiki', 'TODO: add other formats'
		root = os.environ['ZIM_TEST_ROOT']
		tree = etree.ElementTree(file=root + '/tests/data/notebook-wiki.xml')

		test_data = []
		for node in tree.getiterator(tag='page'):
			name = node.attrib['name']
			text = str(node.text.lstrip('\n'))
			test_data.append((name, text))

		self._test_data = tuple(test_data)

	def __iter__(self):
		'''Yield the test data as 2 tuple (pagename, text)'''
		for name, text in self._test_data:
			yield name, text # shallow copy

	def items(self):
		return list(self)

	def __getitem__(self, key):
		return self.get(key)

	def get(self, pagename):
		'''Return text for a specific pagename'''
		for n, text in self._test_data:
			if n == pagename:
				return text
		assert False, 'Could not find data for page: %s' % pagename


WikiTestData = TestData('wiki') #: singleton to be used by various tests

FULL_NOTEBOOK = WikiTestData


def _expand_manifest(names):
	'''Build a set of all pages names and all namespaces that need to
	exist to host those page names.
	'''
	manifest = set()
	for name in names:
		manifest.add(name)
		while name.rfind(':') > 0:
			i = name.rfind(':')
			name = name[:i]
			manifest.add(name)
	return manifest

def new_parsetree():
	'''Returns a new ParseTree object for testing

	Uses data from L{WikiTestData}, page C{roundtrip}
	'''
	import zim.formats.wiki
	parser = zim.formats.wiki.Parser()
	text = WikiTestData.get('roundtrip')
	tree = parser.parse(text)
	return tree

def new_parsetree_from_text(text, format='wiki'):
	import zim.formats
	parser = zim.formats.get_format(format).Parser()
	return parser.parse(text)


def new_parsetree_from_xml(xml):
	# For some reason this does not work with cElementTree.XMLBuilder ...
	from xml.etree.ElementTree import XMLParser
	from zim.formats import ParseTree
	builder = XMLParser()
	builder.feed(xml)
	root = builder.close()
	return ParseTree(root)


def new_page():
	from zim.notebook import Path, Page
	from zim.newfs.mock import MockFile, MockFolder
	file = MockFile('/mock/test/page.txt')
	folder = MockFile('/mock/test/page/')
	page = Page(Path('roundtrip'), False, file, folder)
	page.set_parsetree(new_parsetree())
	return page


def new_page_from_text(text, format='wiki'):
	from zim.notebook import Path, Page
	from zim.notebook import Path, Page
	from zim.newfs.mock import MockFile, MockFolder
	file = MockFile('/mock/test/page.txt')
	folder = MockFile('/mock/test/page/')
	page = Page(Path('Test'), False, file, folder)
	page.set_parsetree(new_parsetree_from_text(text, format))
	return page


class Counter(object):
	'''Object that is callable as a function and keeps count how often
	it was called.
	'''

	def __init__(self, value=None):
		'''Constructor
		@param value: the value to return when called as a function
		'''
		self.value = value
		self.count = 0

	def __call__(self, *arg, **kwarg):
		self.count += 1
		return self.value


class MockObjectBase(object):
	'''Base class for mock objects.

	Mock methods can be installed with L{mock_method()}. All method
	calls to mock methods are logged, so they can be inspected.
	The attribute C{mock_calls} has a list of tuples with mock methods
	and arguments in order they have been called.
	'''

	def __init__(self):
		self.mock_calls = []

	def mock_method(self, name, return_value):
		'''Installs a mock method with a given name that returns
		a given value.
		'''
		def my_mock_method(*arg, **kwarg):
			call = [name] + list(arg)
			if kwarg:
				call.append(kwarg)
			self.mock_calls.append(tuple(call))
			return return_value

		setattr(self, name, my_mock_method)
		return my_mock_method


class MockObject(MockObjectBase):
	'''Simple subclass of L{MockObjectBase} that automatically mocks a
	method which returns C{None} for any non-existing attribute.
	Attributes that are not methods need to be initialized explicitly.
	'''

	def __getattr__(self, name):
		'''Automatically mock methods'''
		if name == '__zim_extension_objects__':
			raise AttributeError
		else:
			return self.mock_method(name, None)


import logging
logger = logging.getLogger('tests')

from functools import partial

class SignalLogger(dict):
	'''Listening object that attaches to all signals of the target and records
	all signals calls in a dictionary of lists.

	Example usage:

		signals = SignalLogger(myobject)
		... # some code causing signals to be emitted
		self.assertEqual(signals['mysignal'], [args])
			# assert "mysignal" is called once with "*args"

	If you don't want to match all arguments, the "filter_func" can be used to
	transform the arguments before logging.

		filter_func(signal_name, object, args) --> args

	'''

	def __init__(self, obj, filter_func=None):
		self._obj = obj
		self._ids = []

		if filter_func is None:
			filter_func = lambda s, o, a: a

		for signal in self._obj.__signals__:
			seen = []
			self[signal] = seen

			def handler(seen, signal, obj, *a):
				seen.append(filter_func(signal, obj, a))
				logger.debug('Signal: %s %r', signal, a)

			id = obj.connect(signal, partial(handler, seen, signal))
			self._ids.append(id)

	def __enter__(self):
		pass

	def __exit__(self, *e):
		self.disconnect()

	def clear(self):
		for signal, seen in list(self.items()):
			seen[:] = []

	def disconnect(self):
		for id in self._ids:
			self._obj.disconnect(id)
		self._ids = []



class CallBackLogger(dict):
	'''Mock object that allows any method to be called as callback and
	records the calls in a dictionary.
	'''

	def __init__(self, filter_func=None):
		if filter_func is None:
			filter_func = lambda n, a, kw: (a, kw)

		self._filter_func = filter_func

	def __getattr__(self, name):

		def cb_method(*arg, **kwarg):
			logger.debug('Callback %s %r %r', name, arg, kwarg)
			self.setdefault(name, [])

			self[name].append(
				self._filter_func(name, arg, kwarg)
			)

		setattr(self, name, cb_method)
		return cb_method


class MaskedObject(object):

	def __init__(self, obj, *names):
		self.__obj = obj
		self.__names = names

	def setObjectAccess(self, *names):
		self.__names = names

	def __getattr__(self, name):
		if name in self.__names:
			return getattr(self.__obj, name)
		else:
			raise AttributeError('Acces to \'%s\' not allowed' % name)


def gtk_process_events(*a):
	'''Method to simulate a few iterations of the gtk main loop'''
	assert Gtk is not None
	while Gtk.events_pending():
		Gtk.main_iteration()
	return True # continue


def gtk_get_menu_item(menu, id):
	'''Get a menu item from a C{Gtk.Menu}
	@param menu: a C{Gtk.Menu}
	@param id: either the menu item label or the stock id
	@returns: a C{Gtk.MenuItem} or C{None}
	'''
	items = menu.get_children()
	ids = [i.get_property('label') for i in items]
		# Gtk.ImageMenuItems that have a stock id happen to use the
		# 'label' property to store it...

	assert id in ids, \
		'Menu item "%s" not found, we got:\n' % id \
		+ ''.join('- %s \n' % i for i in ids)

	i = ids.index(id)
	return items[i]


def gtk_activate_menu_item(menu, id):
	'''Trigger the 'click' action an a menu item
	@param menu: a C{Gtk.Menu}
	@param id: either the menu item label or the stock id
	'''
	item = gtk_get_menu_item(menu, id)
	item.activate()


def find_widgets(type):
	'''Iterate through all top level windows and recursively walk through their
	children, returning all childs which are of given type.
	@param type: any class inherited from C{Gtk.Widget}
	@returns: list of widgets of given type
	'''
	widgets = []
	def walk_containers(root_container):
		if not hasattr(root_container, 'get_children'):
			return
		for child in root_container.get_children():
			if isinstance(child, type):
				widgets.append(child)
			walk_containers(child)
	for window in Gtk.Window.list_toplevels():
		walk_containers(window)
	return widgets
