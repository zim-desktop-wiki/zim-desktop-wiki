# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Test cases for basic stores modules.'''

import unittest
import os
import codecs
import shutil

from zim.fs import *
import zim.stores

def get_data(format):
	'''Generator function for test data'''
	assert format == 'wiki' # No other formats available for now
	file = codecs.open('tests/notebook-wiki.txt', encoding='utf8')
	pagename = None
	buffer = u''
	for line in file:
		if line.startswith('%%%%'):
			# new page start, yield previous page
			if not pagename is None:
				yield (pagename, buffer)
			pagename = line.strip('% \n')
			buffer = u''
		else:
			buffer += line
	yield (pagename, buffer)

def norm_index(index):
	'''Make sure the index conains namespaces for all page names'''
	pages = index.copy()
	for name in pages:
		parts = name.split(':')
		parts.pop()
		while len(parts) > 1:
			index.add(':'.join(parts))
			parts.pop()

class TestNotebook(object):
	'''Empty stub class'''


class TestStoresMemory(unittest.TestCase):
	'''Test the store.memory module'''

	def __init__(self, *args, **opts):
		'''Initialise a fresh notebook'''
		unittest.TestCase.__init__(self, *args, **opts)
		store = zim.stores.get_store('memory')
		self.store = store.Store(namespace='', notebook=TestNotebook())
		self.index = set()
		for name, text in get_data('wiki'):
			self.store._set_node(name, text)
			self.index.add(name)
		norm_index(self.index)

	def testIndex(self):
		'''Test we get a proper index'''
		names = set()
		for page in self.store.get_root().walk():
			names.add( page.name )
		#import pprint
		#pprint.pprint(self.index)
		#pprint.pprint(names)
		self.assertEqual(names, self.index)

	# TODO test move, delete, read, write

class TestFiles(TestStoresMemory):
	'''Test the store.files module'''

	def __init__(self, *args, **opts):
		TestStoresMemory.__init__(self, *args, **opts)
		self.dir = Dir(['tmp', 'store-files'])
		assert not self.dir.exists(), 'Data not cleaned up after previous run'
		self.mem = self.store
		store = zim.stores.get_store('files')
		self.store = store.Store(
			namespace='', notebook=TestNotebook(),
			dir=self.dir )
		for page in self.mem.get_root().walk():
			if page.isempty():
				continue
			self.store.set_page( page )

	def __del__(self):
		shutil.rmtree(self.dir.path)

	# TODO test move, delete, read, write

if __name__ == '__main__':
	unittest.main()
