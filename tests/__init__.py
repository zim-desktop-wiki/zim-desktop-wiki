# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Zim test suite'''

import os
import shutil
import unittest
import codecs

__all__ = [
	'parsing', 'fs', 'config',
	'formats', 'templates',
	'stores', 'index', 'notebook',
	'history', 'plugins',
	'pageview',
]

__unittest = 1 # needed to get stack trace OK for class TestCase


def set_environ():
	os.environ.update({
		'XDG_DATA_HOME': './tests/tmp/share',
		'XDG_DATA_DIRS': './tests/tmp/share',
		'XDG_CONFIG_HOME': './tests/tmp/config',
		'XDG_CONFIG_DIRS': './tests/tmp/config',
		'XDG_CACHE_HOME': './tests/tmp/cache'
	})


def create_tmp_dir(name):
	'''Returns a path to a tmp dir for tests to store dump data.
	The dir is removed and recreated empty every time this function
	is called.
	'''
	dir = os.path.join('tests', 'tmp', name)
	if os.path.exists(dir):
		shutil.rmtree(dir)
	assert not os.path.exists(dir) # make real sure
	os.makedirs(dir)
	assert os.path.exists(dir) # make real sure
	return dir

_test_data_cache = {}

def get_test_data(path):
	if not path in _test_data_cache:
		buffer = codecs.open('tests/data/'+path, encoding='utf8').read()
		_test_data_cache[path] = buffer

	buffer = _test_data_cache[path]
	assert len(buffer) and not buffer.isspace()
	return buffer

def get_notebook_data(format):
	'''Generator function for test data'''
	assert format == 'wiki' # No other formats available for now
	manifest = get_test_data('notebook-wiki/MANIFEST')
	files = [f.rstrip() for f in manifest.splitlines()]
	for file in files:
		pagename = file[:-4] # remove .txt
		pagename = pagename.replace('/',':').replace('_', ' ')
		yield (pagename, get_test_data('notebook-wiki/'+file))

def get_test_notebook(format='wiki'):
	'''Returns a notebook with a memory store and some test data'''
	from zim.notebook import Notebook, Path
	from zim.index import Index
	notebook = Notebook(index=Index(dbfile=':memory:'))
	store = notebook.add_store(Path(':'), 'memory')
	manifest = []
	for name, text in get_notebook_data(format):
			manifest.append(name)
			store._set_node(Path(name), text)
	notebook.testdata_manifest = expand_manifest(manifest)
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


class TestCase(unittest.TestCase):
	'''FIXME'''

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

		raise self.failureException, msg.encode('utf8')

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
			first = list(first)
			second = list(second)
			diff = Differ().compare(second, first)
			# switching first and second, because usually second
			# is the reference we are testing against
			msg += '\n' + '\n'.join(diff)
		else:
			return

		raise self.failureException, msg.encode('utf8')
