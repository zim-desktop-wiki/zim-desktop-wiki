# -*- coding: utf8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import tests

from zim.index import Index, IndexPath, LINK_DIR_BACKWARD, LINK_DIR_BOTH
from zim.notebook import Path, Link
from zim.gui.pageindex import PageTreeStore

class TestIndex(tests.TestCase):

	def testDB(self):
		# Note that in this test our index is not the default index
		# for the notebook. So any assumption from the notebook about
		# the index will be wrong.
		index = Index(dbfile=':memory:')
		notebook = tests.get_test_notebook()
		manifest = notebook.testdata_manifest
		index.set_notebook(notebook)
		index.update()

		#~ cursor = index.db.cursor()
		#~ cursor.execute('select * from pages')
		#~ cursor.execute('select * from links')
		#~ print '\n==== DB ===='
		#~ for row in cursor:
			#~ print row

		path = index.lookup_path(Path('Test:foo:bar'))
		self.assertTrue(isinstance(path, IndexPath))
		path = index.lookup_id(path.id)
		self.assertTrue(isinstance(path, IndexPath))
		self.assertEqual(path.name, 'Test:foo:bar')

		pagelist = index.list_pages(None)
		self.assertTrue(len(pagelist) > 0)

		forwlist = list(index.list_links(Path('Test:foo:bar')))
		backlist = list(index.list_links(Path('Test:foo:bar'), LINK_DIR_BACKWARD))
		bothlist = list(index.list_links(Path('Test:foo:bar'), LINK_DIR_BOTH))
		for l in forwlist, backlist, bothlist:
			self.assertTrue(len(l) > 0)
			for link in l:
				self.assertTrue(isinstance(link, Link))
				self.assertTrue(isinstance(link.source, IndexPath))
				self.assertTrue(isinstance(link.href, IndexPath))
		self.assertTrue(len(forwlist) + len(backlist) == len(bothlist))


class TestPageTreeStore(tests.TestCase):

	def testPageTreeStore(self):
		index = Index(dbfile=':memory:')
		notebook = tests.get_test_notebook()
		manifest = notebook.testdata_manifest
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
