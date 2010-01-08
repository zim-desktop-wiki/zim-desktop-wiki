# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import tests

from zim.fs import Dir
from zim.index import Index, IndexPath, LINK_DIR_BACKWARD, LINK_DIR_BOTH
from zim.notebook import Notebook, Path, Link
from zim.gui.pageindex import PageTreeStore, PageTreeView
from zim.formats import ParseTree


def get_files_notebook(key):
	# We fill the notebook using the store interface, as this test comes before
	# the notebook test, but after the store test.
	dir = Dir(tests.create_tmp_dir('index_'+key))
	notebook = Notebook(dir=dir)
	store = notebook.get_store(':')
	manifest = []
	for name, text in tests.get_test_data('wiki'):
		manifest.append(name)
		page = store.get_page(Path(name))
		page.parse('wiki', text)
		store.store_page(page)
	notebook.testdata_manifest = tests.expand_manifest(manifest)
	return notebook


class TestIndex(tests.TestCase):

	def setUp(self):
		# Note that in this test our index is not the default index
		# for the notebook. So any assumption from the notebook about
		# the index will be wrong.
		self.index = Index(dbfile=':memory:')
		self.notebook = tests.get_test_notebook()
		self.index.set_notebook(self.notebook)

	def runTest(self):
		'''Test indexing'''
		# This is one big test instead of seperate sub tests because in the
		# subclass we generate a file based notebook in setUp, and we do not
		# want to do that many times

		#~ print self.__class__.__name__
		self.index.update()

		#~ print '\n==== DB ===='
		#~ cursor = self.index.db.cursor()
		#~ cursor.execute('select * from pages')
		#~ for row in cursor:
			#~ print row
		#~ cursor.execute('select * from links')
		#~ for row in cursor:
			#~ print row

		# paths / ids
		path = self.index.lookup_path(Path('Test:foo:bar'))
		self.assertTrue(isinstance(path, IndexPath))
		path = self.index.lookup_id(path.id)
		self.assertTrue(isinstance(path, IndexPath))
		self.assertEqual(path.name, 'Test:foo:bar')

		# pages
		pagelist = self.index.list_pages(None)
		self.assertTrue(len(pagelist) > 0)
		pagelist = self.index.list_pages(Path('Test'))
		self.assertTrue(len(pagelist) > 0)
		for page in pagelist:
			self.assertTrue(page.name.startswith('Test:'))
			self.assertTrue(page.name.count(':') == 1)
		pagelist = self.index.list_pages(Path('Linking'))
		self.assertTrue(Path('Linking:Dus') in pagelist)
		pagelist = self.index.list_pages(Path('Some:Non:Existing:Path'))
		self.assertTrue(len(pagelist) == 0)

		# links
		forwlist = list(self.index.list_links(Path('Test:foo:bar')))
		backlist = list(self.index.list_links(Path('Test:foo:bar'), LINK_DIR_BACKWARD))
		bothlist = list(self.index.list_links(Path('Test:foo:bar'), LINK_DIR_BOTH))
		for l in forwlist, backlist, bothlist:
			self.assertTrue(len(l) > 0)
			for link in l:
				self.assertTrue(isinstance(link, Link))
				self.assertTrue(isinstance(link.source, IndexPath))
				self.assertTrue(isinstance(link.href, IndexPath))
		self.assertTrue(len(forwlist) + len(backlist) == len(bothlist))

		n = self.index.n_list_links(Path('Test:foo:bar'), LINK_DIR_BACKWARD)
		self.assertEqual(n, len(backlist))


		# cursor.row_count is not reliable - see docs
		def count_pages(db):
			c = db.cursor()
			c.execute('select id from pages')
			r = c.fetchall()
			return len(r)

		def dump_db(db):
			c = db.cursor()
			c.execute('select * from pages')
			text = ''
			for row in c:
				# HACK iterating of sqlite3.Row objects only supported for python 2.6
				myrow = []
				for i in range(len(row)):
					myrow.append(row[i])
				text += ', '.join(map(str, myrow)) + '\n'
			return text

		# repeat update() to check if update is stable
		manifest = len(self.notebook.testdata_manifest)
		self.assertTrue(count_pages(self.index.db) >= manifest)
		origdb = dump_db(self.index.db)
		self.index.update(checkcontents=False)
		self.assertEqualDiff(dump_db(self.index.db), origdb)

		# indexkey
		for path in (Path('Test'), Path('Test:foo')):
			indexpath = self.index.lookup_path(path)
			self.assertEqual(indexpath.contentkey, self.notebook.get_page_indexkey(path))
			self.assertEqual(indexpath.childrenkey, self.notebook.get_pagelist_indexkey(path))

		# other functions
		path = self.index.get_unique_path(Path('non-existing-path'))
		self.assertEqual(path, Path('non-existing-path'))
		path = self.index.get_unique_path(Path('Test:foo'))
		self.assertEqual(path, Path('Test:foo_1'))

		# get_previous / get_next
		page = self.index.list_pages(None)[0]
		seen = 0
		while page:
			seen = max(seen, page.name.count(':'))
			page = self.index.get_next(page)
		self.assertTrue(seen >= 2)

		page = self.index.list_pages(None)[-1]
		seen = 0
		while page:
			seen = max(seen, page.name.count(':'))
			page = self.index.get_previous(page)
		self.assertTrue(seen >= 2)

		# now go through the flush loop
		self.index.flush()
		self.assertEqual(count_pages(self.index.db), 1)
		self.index.update()
		self.assertEqualDiff(dump_db(self.index.db), origdb)

		# now index only part of the tree - and repeat
		self.index.flush()
		self.assertEqual(count_pages(self.index.db), 1)
		self.index.update(Path('Test'))
		self.assertTrue(count_pages(self.index.db) > 2)
		partdb = dump_db(self.index.db)
		self.index.update(Path('Test'))
		self.assertEqualDiff(dump_db(self.index.db), partdb)

		# Index whole tree again
		self.index.update()

		# Check cleanup
		path = Path('New:Nested:Path')
		self.index.touch(path)
		parent = self.index.lookup_path(path.parent)
		self.assertTrue(parent and parent.haschildren)
		self.index.delete(path)
		parent = self.index.lookup_path(path.parent)
		self.assertTrue(parent is None)

		#~ # Check cleanup for links
		links = [link.href for link in self.index.list_links(Path('roundtrip'))]
		for p in ('foo:bar', 'Bar'):
			self.assertTrue(Path(p) in links)
			path = self.index.lookup_path(Path('foo:bar'))
			self.assertTrue(path)

		tree = ParseTree().fromstring('<zim-tree><link href=":foo:bar">:foo:bar</link></zim-tree>')
		page = self.notebook.get_page(Path('roundtrip'))
		page.set_parsetree(tree)
		self.notebook.store_page(page)
		path = self.index.lookup_path(Path('Bar'))
		self.assertTrue(path is None)
		path = self.index.lookup_path(Path('foo:bar'))
		self.assertTrue(path)

		self.notebook.delete_page(Path('roundtrip'))
		path = self.index.lookup_path(Path('foo:bar'))
		self.assertTrue(path is None)


class TestIndexFiles(TestIndex):
	# Like the test above, but now using a files backend

	slowTest = True

	def setUp(self):
		self.notebook = get_files_notebook('TestIndexFiles')
		self.index = self.notebook.index

	def runTest(self):
		'''Test indexing files'''
		TestIndex.runTest(self)


class TestPageTreeStore(tests.TestCase):

	slowTest = True

	def setUp(self):
		self.index = Index(dbfile=':memory:')
		self.notebook = tests.get_test_notebook()
		self.index.set_notebook(self.notebook)

	def runTest(self):
		'''Test PageTreeStore index interface'''
		# This is one big test instead of seperate sub tests because in the
		# subclass we generate a file based notebook in setUp, and we do not
		# want to do that many times

		self.index.update()
		treestore = PageTreeStore(self.index)
		self.assertEqual(treestore.get_flags(), 0)
		self.assertEqual(treestore.get_n_columns(), 5)

		treeview = PageTreeView(None) # just run hidden to check errors
		treeview.set_model(treestore)

		n = treestore.on_iter_n_children()
		self.assertTrue(n > 0)
		n = treestore.iter_n_children(None)
		self.assertTrue(n > 0)

		# Quick check for basic methods
		path = treestore.on_get_iter((0,))
		self.assertTrue(isinstance(path, IndexPath) and not path.isroot)
		basename = treestore.on_get_value(path, 0)
		self.assertTrue(len(basename) > 0)
		self.assertEqual(treestore.get_treepath(path), (0,))

		path2 = treestore.on_iter_children()
		self.assertEqual(path2, path)

		self.assertTrue(treestore.on_get_iter((20,20,20,20,20)) is None)
		self.assertRaises(
			ValueError, treestore.get_treepath, Path('nonexisting'))

		# Now walk through the whole notebook testing the API
		# with nested pages and stuff
		path = []
		for page in self.notebook.walk():
			names = page.name.split(':')
			if len(names) > len(path):
				path.append(0) # always increment by one
			elif len(names) < len(path):
				while len(names) < len(path):
					path.pop()
				path[-1] += 1
			else:
				path[-1] += 1
			#~ print '>>', page, path
			iter = treestore.get_iter(tuple(path))
			indexpath = treestore.get_indexpath(iter)
			#~ print '>>>', indexpath
			self.assertEqual(indexpath, page)
			self.assertEqual(
				treestore.get_value(iter, 0), page.basename)
			self.assertEqual(
				treestore.get_path(iter), tuple(path))
			if indexpath.haschildren:
				self.assertTrue(treestore.iter_has_child(iter))
				child = treestore.iter_children(iter)
				self.assertTrue(not child is None)
				child = treestore.iter_nth_child(iter, 0)
				self.assertTrue(not child is None)
				parent = treestore.iter_parent(child)
				self.assertEqual(
					treestore.get_indexpath(parent), page)
				childpath = treestore.get_path(child)
				self.assertEqual(
					childpath, tuple(path) + (0,))
				n = treestore.iter_n_children(iter)
				for i in range(1, n):
					child = treestore.iter_next(child)
					childpath = treestore.get_path(child)
					self.assertEqual(
						childpath, tuple(path) + (i,))
				child = treestore.iter_next(child)
				self.assertTrue(child is None)

			else:
				self.assertTrue(not treestore.iter_has_child(iter))
				child = treestore.iter_children(iter)
				self.assertTrue(child is None)
				child = treestore.iter_nth_child(iter, 0)
				self.assertTrue(child is None)

		# Check if all the signals go OK
		del treestore
		self.index.flush()
		treestore = PageTreeStore(self.index)
		self.index.update()


class TestPageTreeStoreFiles(TestPageTreeStore):

	slowTest = True

	def setUp(self):
		self.notebook = get_files_notebook('TestPageTreeStoreFiles')
		self.index = self.notebook.index

	def runTest(self):
		'''Test PageTreeStore index interface with files index'''
		TestPageTreeStore.runTest(self)
