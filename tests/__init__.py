# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Zim test suite'''

import os
import sys
import shutil
import unittest
import logging
import gettext
import xml.etree.cElementTree as etree


__all__ = [
	'coding', 'translations',
	'errors', 'parsing', 'fs', 'config', 'applications', 'async',
	'formats', 'templates',
	'stores', 'index', 'notebook',
	'history', 'plugins',
	'export', 'www', 'search',
	'widgets', 'gui', 'pageview',
	'calendar', 'printtobrowser', 'versioncontrol', 'inlinecalculator',
	'tasklist', 'tags',
	'equationeditor', 'diagrameditor',
]

__unittest = 1 # needed to get stack trace OK for class TestCase


gettext.install('zim', unicode=True, names=('_', 'gettext', 'ngettext'))


def set_environ():
	tmpdir = './tests/tmp/'
	os.environ.update({
		'ZIM_TEST_RUNNING': 'True',
		'TMP': tmpdir,
		'XDG_DATA_HOME': './tests/tmp/data_home',
		'XDG_DATA_DIRS': './tests/tmp/data_dir',
		'XDG_CONFIG_HOME': './tests/tmp/config_home',
		'XDG_CONFIG_DIRS': './tests/tmp/config_dir',
		'XDG_CACHE_HOME': './tests/tmp/cache_home'
	})
	if os.name == 'nt':
		tmpdir = unicode(tmpdir)
	else:
		tmpdir = tmpdir.encode(sys.getfilesystemencoding())
	if os.path.isdir(tmpdir):
		shutil.rmtree(tmpdir)
	os.mkdir(tmpdir)

	hicolor = os.environ['XDG_DATA_DIRS'] + '/icons/hicolor'
	os.makedirs(hicolor)


def create_tmp_dir(name):
	'''Returns a path to a tmp dir for tests to store dump data.
	The dir is removed and recreated empty every time this function
	is called.
	'''
	dir = os.path.join('tests', 'tmp', name)
	if os.name == 'nt':
		dir = unicode(dir)
	else:
		dir = dir.encode(sys.getfilesystemencoding())
	if os.path.exists(dir):
		shutil.rmtree(dir)
	assert not os.path.exists(dir) # make real sure
	os.makedirs(dir)
	assert os.path.exists(dir) # make real sure
	return dir


_test_data_wiki = None

def get_test_data(format):
	global _test_data_wiki
	assert format == 'wiki' # No other formats available for now
	if _test_data_wiki is None:
		_test_data_wiki = _get_test_data_wiki()

	for name, text in _test_data_wiki:
		#~ print '>', name
		yield name, text


def get_test_data_page(format, name):
	global _test_data_wiki
	assert format == 'wiki' # No other formats available for now
	if not _test_data_wiki:
		_test_data_wiki = _get_test_data_wiki()

	for n, text in _test_data_wiki:
		if n == name:
			return text
	assert False, 'Could not find data for page: %s' % name


def _get_test_data_wiki():
	test_data = []
	tree = etree.ElementTree(file='tests/data/notebook-wiki.xml')
	for node in tree.getiterator(tag='page'):
		name = node.attrib['name']
		text = unicode(node.text.lstrip('\n'))
		test_data.append((name, text))
	return tuple(test_data)


def get_test_notebook(format='wiki'):
	'''Returns a notebook with a memory store and some test data'''
	from zim.notebook import Notebook, Path
	from zim.index import Index
	notebook = Notebook(index=Index(dbfile=':memory:'))
	store = notebook.add_store(Path(':'), 'memory')
	manifest = []
	for name, text in get_test_data(format):
		manifest.append(name)
		store.set_node(Path(name), text)
	notebook.testdata_manifest = expand_manifest(manifest)
	notebook.index.update()
	return notebook


def expand_manifest(names):
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


def get_test_page(name='Foo'):
	'''FIXME'''
	from zim.notebook import Notebook, Path
	notebook = Notebook()
	notebook.add_store(Path(':'), 'memory')
	return notebook, notebook.get_page(Path(name))


def print_index(index):
	print '==== INDEX ===='
	for page in index.walk():
		print page.name, page.hascontent, page.haschildren
		for link in index.list_links(page):
			print '\t->', link.href.name
	print '==============='



class TestCase(unittest.TestCase):
	'''Base class for test cases'''

	def run(self, *args):
		unittest.TestCase.run(self, *args)

	def assertEqualDiff(self, first, second, msg=None):
		'''Fail if the two strings are unequal as determined by
		the '==' operator. On failure shows a diff of both strings.
		Alternatively the arguments can be lists of lines.
		'''
		if msg is None:
			msg = u'Strings differ:'
		else:
			msg = unicode(msg)

		if not type(first) == type(second):
			types = type(first), type(second)
			msg += ' types differ, %s and %s' % types
		elif not first:
			msg += ' first text is empty'
		elif not second:
			msg += ' second text is empty'
		elif not first == second:
			from difflib import Differ
			if isinstance(first, basestring):
				first = first.splitlines(True)
			if isinstance(second, basestring):
				second = second.splitlines(True)
			diff = Differ().compare(second, first)
			# switching first and second, because usually second
			# is the reference we are testing against
			msg += '\n' + ''.join(diff)
		else:
			return

		raise self.failureException, msg.encode('utf-8')

	def assertEqualDiffData(self, first, second, msg=None):
		'''Like assertEqualDiff(), but handles sets and other
		data types that can be cast to lists.
		'''
		if msg is None:
			msg = u'Values differ:'
		else:
			msg = unicode(msg)

		if not type(first) == type(second):
			types = type(first), type(second)
			msg += ' types differ, %s and %s' % types
		elif first is None:
			msg += ' first item is "None"'
		elif second is None:
			msg += ' second item is "None"'
		elif not first == second:
			from difflib import Differ
			if isinstance(first, set):
				first = list(first)
				second = list(second)
				first.sort()
				second.sort()
			else:
				first = list(first)
				second = list(second)
			diff = Differ().compare(second, first)
			# switching first and second, because usually second
			# is the reference we are testing against
			msg += '\n' + '\n'.join(diff)
		else:
			return

		raise self.failureException, msg.encode('utf-8')


class MockObject(object):
	'''Base class for mock objects. Any attribute is automatically
	vivicated as a method which results None. Alternatively mock
	methods can be installed with mock_method(). Attributes that are
	not methods need to be initialized explicitly.

	All method call are logged, so they can be inspected. The attribute
	'mock_calls' has a list of tuples with mock methods and arguments in
	order they have been called.
	'''

	def __init__(self):
		self.mock_calls = []

	def __getattr__(self, name):
		'''Automatically mock methods'''
		return self.mock_method(name, None)

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


class LoggingFilter(object):
	'''Base class for logging filters that can be used as a context
	using the "with" keyword. To subclass it you only need to set the
	logger to be used and (the begin of) the message to filter.
	'''

	logger = None
	message = None

	def __init__(self, logger=None, message=None):
		if logger: self.logger = logger
		if message: self.message = message

		self.loggerobj = logging.getLogger(self.logger)

	def __enter__(self):
		self.loggerobj.addFilter(self)

	def __exit__(self, *a):
		self.loggerobj.removeFilter(self)

	def filter(self, record):
		return not record.getMessage().startswith(self.message)
