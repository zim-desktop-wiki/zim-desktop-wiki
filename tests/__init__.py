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
	'stores', 'notebook',
	'history', 'plugins'
]

__unittest = 1 # needed to get stack trace OK for class TestCase


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

def get_notebook_data(format):
	'''Generator function for test data'''
	assert format == 'wiki' # No other formats available for now
	file = codecs.open('tests/data/notebook-wiki.txt', encoding='utf8')

	# Read manifest
	manifest = []
	for line in file:
		if line.isspace(): break
		manifest.append(line.strip())

	pagename = None
	buffer = u''
	i = -1
	for line in file:
		if line.startswith('%%%%'):
			# new page start, yield previous page
			if not pagename is None:
				yield (pagename, buffer)
			pagename = line.strip('% \n')
			i += 1
			assert manifest[i] == pagename, \
				'got page %s, expected %s' % (pagename, manifest[i])
			buffer = u''
		else:
			buffer += line
	yield (pagename, buffer)


def get_test_notebook(format='wiki'):
	'''Returns a notebook with a memory store and some test data'''
	from zim.notebook import Notebook
	notebook = Notebook()
	store = notebook.add_store('', 'memory')
	manifest = []
	for name, text in get_notebook_data(format):
			manifest.append(name)
			store._set_node(name, text)
	notebook.testdata_manifest = _expand_manifest(manifest)
	return notebook

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

def get_test_page(name=':Foo'):
	'''FIXME'''
	from zim.notebook import Notebook
	notebook = Notebook()
	notebook.add_store('', 'memory')
	return notebook.get_page(name)


class TestCase(unittest.TestCase):
	'''FIXME'''

	def run(self, *args):
		unittest.TestCase.run(self, *args)

	def assertEqualDiff(self, first, second, msg=None):
		'''Fail if the two strings are unequal as determined by
		the '==' operator. On failure shows a diff of both strings.
		'''
		if msg is None:
			msg = u'Strings differ:'
		else:
			msg = unicode(msg)
		if not first == second:
			#~ print '>>>>\n'+first+'=====\n'+second+'<<<<\n'
			if not first:
				msg += ' first string is empty'
			elif not second:
				msg += ' second string is empty'
			elif not type(first) == type(second):
				types = type(first), type(second)
				msg += ' types differ, %s and %s' % types
			else:
				from difflib import Differ
				diff = Differ().compare(
					second.splitlines(), first.splitlines() )
				# switching first and second, because usually second
				# is the reference we are testing against
				msg += '\n' + '\n'.join(diff)
			raise self.failureException, msg.encode('utf8')


