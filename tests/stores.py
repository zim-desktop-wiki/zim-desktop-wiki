# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Test cases for basic stores modules.'''

import tests

from zim.fs import *
from zim.notebook import Notebook, Path, LookupError, PageExistsError
import zim.stores


def walk(store, namespace=None):
	if namespace == None:
		namespace = Path(':')
	for page in store.get_pagelist(namespace):
		yield namespace, page
		if page.haschildren:
			for parent, child in walk(store, page): # recurs
				yield parent, child


def ascii_page_tree(store, namespace=None, level=0):
	'''Returns an ascii page tree. Used for debugging the test'''
	if namespace is None:
		namespace = store.namespace

	if namespace.isroot: basename = '<root>'
	else: basename = namespace.basename

	text = '  '*level + basename + '\n'
	level += 1
	for page in store.get_pagelist(namespace):
		if page.haschildren:
			text += ascii_page_tree(store, page, level) # recurs
		else:
			text += '  '*level + page.basename + '\n'

	return text


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
		self.assertEqualDiffData(names, self.index)

	def testManipulate(self):
		'''Test moving and deleting pages in the store'''

		# check test setup OK
		for path in (Path('Test:BAR'), Path('NewPage')):
			page = self.store.get_page(path)
			self.assertFalse(page.haschildren)
			self.assertFalse(page.hascontent)

		# check errors
		self.assertRaises(LookupError,
			self.store.move_page, Path('NewPage'), Path('Test:BAR'))
		self.assertRaises(PageExistsError,
			self.store.move_page, Path('Test:foo'), Path('TODOList'))

		for oldpath, newpath in (
			(Path('Test:foo'), Path('Test:BAR')),
			(Path('TODOList'), Path('NewPage:Foo:Bar:Baz')),
		):
			page = self.store.get_page(oldpath)
			text = page.dump('wiki')
			self.assertTrue(page.haschildren)

			#~ print ascii_page_tree(self.store)
			self.store.move_page(oldpath, newpath)
			#~ print ascii_page_tree(self.store)

			# newpath should exist and look like the old one
			page = self.store.get_page(newpath)
			self.assertTrue(page.haschildren)
			self.assertEqual(page.dump('wiki'), text)

			# oldpath should be deleted
			page = self.store.get_page(oldpath)
			self.assertFalse(page.haschildren)
			self.assertFalse(page.hascontent)

			# let's delete the newpath again
			self.assertTrue(self.store.delete_page(newpath))
			page = self.store.get_page(newpath)
			self.assertFalse(page.haschildren)
			self.assertFalse(page.hascontent)

			# delete again should silently fail
			self.assertFalse(self.store.delete_page(newpath))

		# check cleaning up works OK
		page = self.store.get_page(Path('NewPage'))
		self.assertFalse(page.haschildren)
		self.assertFalse(page.hascontent)

		# check case-sensitive move
		self.store.move_page(Path('utf8'), Path('UTF8'))
		page = self.store.get_page(Path('utf8'))
		self.assertFalse(page.haschildren)
		newpage = self.store.get_page(Path('UTF8'))
		self.assertTrue(newpage.haschildren)
		self.assertFalse(newpage == page)


	# TODO test getting a non-existing page
	# TODO test if children uses namespace objects
	# TODO test move, delete, read, write



class TestFiles(TestStoresMemory):
	'''Test the store.files module'''

	slowTest = True

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
