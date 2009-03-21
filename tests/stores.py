# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Test cases for basic stores modules.'''

import tests

from zim.fs import *
from zim.notebook import Notebook, Path
import zim.stores


def walk(store, namespace=None):
	if namespace == None:
		namespace = Path(':')
	for page in store.get_pagelist(namespace):
		yield namespace, page
		if page.haschildren:
			for parent, child in walk(store, page): # recurs
				yield parent, child


class TestStoresMemory(tests.TestCase):
	'''Test the store.memory module'''

	def setUp(self):
		'''Initialise a fresh notebook'''
		store = zim.stores.get_store('memory')
		self.store = store.Store(path=Path(':'), notebook=Notebook())
		self.index = set()
		for name, text in tests.get_notebook_data('wiki'):
			self.store._set_node(Path(name), text)
			self.index.add(name)
		self.normalize_index()

	def normalize_index(self):
		'''Make sure the index conains namespaces for all page names'''
		pages = self.index.copy()
		for name in pages:
			parts = name.split(':')
			parts.pop()
			while parts:
				self.index.add(':'.join(parts))
				parts.pop()

	def testIndex(self):
		'''Test we get a proper index'''
		names = set()
		for parent, page in walk(self.store):
			self.assertTrue(len(page.name) > 0)
			self.assertTrue(len(page.basename) > 0)
			self.assertTrue(page.namespace == parent.name)
			names.add( page.name )
		#import pprint
		#pprint.pprint(self.index)
		#pprint.pprint(names)
		self.assertTrue(u'utf8:\u03b1\u03b2\u03b3' in names) # Check usage of unicode
		self.assertEqual(names, self.index)

	#~ def testResolveFile(self):
		#~ '''Test store.resolve_file()'''

	# TODO test getting a non-existing page
	# TODO test if children uses namespace objects
	# TODO test move, delete, read, write


class TestFiles(TestStoresMemory):
	'''Test the store.files module'''

	def setUp(self):
		TestStoresMemory.setUp(self)
		tmpdir = tests.create_tmp_dir('stores_TestFiles')
		self.dir = Dir([tmpdir, 'store-files'])
		self.mem = self.store
		store = zim.stores.get_store('files')
		self.store = store.Store(
			path=Path(':'), notebook=Notebook(), dir=self.dir )
		for parent, page in walk(self.mem):
			if page.hascontent:
				mypage = self.store.get_page(page)
				mypage.set_parsetree(page.get_parsetree())

	# TODO test move, delete, read, write
