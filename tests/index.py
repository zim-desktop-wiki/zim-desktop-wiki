# -*- coding: utf8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import tests

from zim.fs import Dir
from zim.index import Index, IndexPath, LINK_DIR_BACKWARD, LINK_DIR_BOTH
from zim.notebook import Notebook, Path, Link
from zim.gui.pageindex import PageTreeStore

class TestIndex(tests.TestCase):

	def setUp(self):
		# Note that in this test our index is not the default index
		# for the notebook. So any assumption from the notebook about
		# the index will be wrong.
		self.index = Index(dbfile=':memory:')
		self.notebook = tests.get_test_notebook()
		self.index.set_notebook(self.notebook)
		self.manifest = self.notebook.testdata_manifest

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

		# repeat update() to check if update is stable
		manifest = len(self.manifest)
		self.assertEqual(count_pages(self.index.db), manifest)
		self.index.update(checkcontents=False)
		self.assertEqual(count_pages(self.index.db), manifest)

		# now go through the flush loop
		self.index.flush()
		self.assertEqual(count_pages(self.index.db), 0)
		self.index.update()
		self.assertEqual(count_pages(self.index.db), manifest)

		# now index only part of the tree - and repeat
		self.index.flush()
		self.assertEqual(count_pages(self.index.db), 0)
		self.index.update(Path('Test'))
		firstcount = count_pages(self.index.db)
		self.assertTrue(firstcount > 2)
		self.index.update(Path('Test'))
		self.assertEqual(count_pages(self.index.db), firstcount)


class TestIndexFiles(TestIndex):
	# Like the test above, but now using a files backend

	slowTest = True

	def setUp(self):
		dir = Dir(tests.create_tmp_dir('index_TestIndexFiles'))
		self.notebook = Notebook(path=dir)
		self.index = self.notebook.index
		store = self.notebook.get_store(':')
		manifest = []
		for name, text in tests.get_notebook_data('wiki'):
			manifest.append(name)
			page = store.get_page(Path(name))
			page.set_text('wiki', text)
		self.manifest = tests.expand_manifest(manifest)


class TestPageTreeStore(tests.TestCase):

	def runTest(self):
		'''Test PageTreeStore index interface'''
		index = Index(dbfile=':memory:')
		notebook = tests.get_test_notebook()
		index.set_notebook(notebook)
		index.update()

		treestore = PageTreeStore(index)
		self.assertEqual(treestore.get_flags(), 0)
		self.assertEqual(treestore.get_n_columns(), 1)

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
		for page in notebook.walk():
			names = page.name.split(':')
			if len(names) > len(path):
				path.append(0)
			elif len(names) < len(path):
				path.pop()
				path[-1] += 1
			else:
				path[-1] += 1
			iter = treestore.get_iter(tuple(path))
			indexpath = treestore.get_indexpath(iter)
			self.assertEqual(indexpath, page)
			#~ print '>>', path, page
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
