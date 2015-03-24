# -*- coding: utf-8 -*-

# Copyright 2009-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement


import tests

import copy

from functools import partial


from zim.fs import Dir
from zim.notebook import Path
from zim.notebook.stores.memory import MemoryStore
from zim.notebook.stores.files import FilesStore

from zim.notebook.index import *


PAGES = {
	Path('Bar'): {
		'treepath': (0,),
		'n_children': 0,
		'content': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.\n' \
			'@tag1 @tag2\n' \
			'[[:Foo]]\n',
		'links': ['Foo'],
		'backlinks': [],
		'tags': ['tag1', 'tag2'],
	},
	Path('Foo'): {
		'treepath': (1,),
		'n_children': 2,
		'content': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.\n',
		'links': [],
		'backlinks': ['Bar'],
		'tags': [],
	},
	Path('Foo:Child1'): {
		'treepath': (1,0),
		'n_children': 2,
		'content': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.\n',
		'links': [],
		'backlinks': [],
		'tags': [],
	},
	Path('Foo:Child2'): {
		'treepath': (1,1),
		'n_children': 0,
		'content': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.\n',
		'links': [],
		'backlinks': [],
		'tags': [],
	},
	Path('Foo:Child1:GrandChild1'): {
		'treepath': (1,0,0),
		'n_children': 0,
		'content': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.\n',
		'links': [],
		'backlinks': [],
		'tags': [],
	},
	Path('Foo:Child1:GrandChild2'): {
		'treepath': (1,0,1),
		'n_children': 0,
		'content': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.\n',
		'links': [],
		'backlinks': [],
		'tags': [],
	},
}

SEQUENCE = ( # Per phase children iterate in order of discovery
	(INDEX_CHECK_TREE, ''),
	(INDEX_CHECK_TREE, 'Foo'),
	(INDEX_CHECK_TREE, 'Foo:Child1'),
	(INDEX_CHECK_PAGE, 'Bar'),
	(INDEX_CHECK_PAGE, 'Foo'),
	(INDEX_CHECK_PAGE, 'Foo:Child1'),
	(INDEX_CHECK_PAGE, 'Foo:Child2'),
	(INDEX_CHECK_PAGE, 'Foo:Child1:GrandChild1'),
	(INDEX_CHECK_PAGE, 'Foo:Child1:GrandChild2'),
)

INIT_SIGNALS = [
	('page-added', 'Bar'),
	('page-haschildren-toggled', ''),
	('page-added', 'Foo'),
	('page-added', 'Foo:Child1'),
	('page-haschildren-toggled', 'Foo'),
	('page-added', 'Foo:Child2'),
	('page-added', 'Foo:Child1:GrandChild1'),
	('page-haschildren-toggled', 'Foo:Child1'),
	('page-added', 'Foo:Child1:GrandChild2'),
]
for check, name in SEQUENCE:
	if name and check == INDEX_CHECK_PAGE:
		INIT_SIGNALS.append(('page-changed', name))


UPDATE = {
	Path('Bar:AAA'): {
		'n_children': 0,
		'content': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.\n',
		'links': [],
		'tags': [],
	},
	Path('Bar:BBB'): {
		'n_children': 0,
		'content': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.\n',
		'links': [],
		'tags': [],
	},
	# On purpose skipping "Bar:CCC" here - should be touched & cleaned up automatically
	Path('Bar:CCC:aaa'): {
		'n_children': 0,
		'content': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.\n',
		'links': [],
		'tags': [],
	},
}

UPDATED_PAGES = dict(copy.deepcopy(PAGES.items()) + UPDATE.items())
UPDATED_PAGES[Path('Bar')]['n_children'] = 3
UPDATED_PAGES[Path('Bar:CCC')] = {
	'n_children': 1,
	'content': None,
	'links': [],
	'tags': [],
}

UPDATE_SEQUENCE = ( # New pages appended at the end of each phase
	(INDEX_CHECK_TREE, ''),
	(INDEX_CHECK_TREE, 'Bar'),
	(INDEX_CHECK_TREE, 'Foo'),
	(INDEX_CHECK_TREE, 'Foo:Child1'),
	(INDEX_CHECK_TREE, 'Bar:CCC'),
	(INDEX_CHECK_PAGE, 'Bar'),
	(INDEX_CHECK_PAGE, 'Foo'),
	(INDEX_CHECK_PAGE, 'Foo:Child1'),
	(INDEX_CHECK_PAGE, 'Foo:Child2'),
	(INDEX_CHECK_PAGE, 'Foo:Child1:GrandChild1'),
	(INDEX_CHECK_PAGE, 'Foo:Child1:GrandChild2'),
	(INDEX_CHECK_PAGE, 'Bar:AAA'),
	(INDEX_CHECK_PAGE, 'Bar:BBB'),
	(INDEX_CHECK_PAGE, 'Bar:CCC'),
	(INDEX_CHECK_PAGE, 'Bar:CCC:aaa'),
)

UPDATE_ROLLBACK_SEQUENCE = (
	# Same as SEQUENCE but with extra check for Bar children
	(INDEX_CHECK_TREE, ''),
	(INDEX_CHECK_TREE, 'Bar'),
	(INDEX_CHECK_TREE, 'Foo'),
	(INDEX_CHECK_TREE, 'Foo:Child1'),
	(INDEX_CHECK_PAGE, 'Bar'),
	(INDEX_CHECK_PAGE, 'Foo'),
	(INDEX_CHECK_PAGE, 'Foo:Child1'),
	(INDEX_CHECK_PAGE, 'Foo:Child2'),
	(INDEX_CHECK_PAGE, 'Foo:Child1:GrandChild1'),
	(INDEX_CHECK_PAGE, 'Foo:Child1:GrandChild2'),
)


class MemoryIndexerTests(tests.TestCase):

	def setUp(self):
		self.store = MemoryStore()
		self.write_pages(PAGES)
		self.index = Index.new_from_memory(
			self.store
		)

	def write_pages(self, pages):
		for path, attrib in pages.items():
			page = self.store.get_page(path)
			page.parse('wiki', attrib['content'])
			self.store.store_page(page)

	def delete_pages(self, pages):
		for path, attrib in pages.items():
			self.store.delete_page(path)

	def assertIndexMatchesTree(self, index, wanted):
		pages = PagesViewInternal()
		with index.db_conn.db_context() as db:
			seen = set()
			for row in db.execute('SELECT * FROM pages'):
				if row['id'] == ROOT_ID:
					continue
				indexpath = pages.lookup_by_id(db, row['id'])
				path = Path(indexpath.name)
				self.assertIn(path, wanted)
				self.assertEqual(indexpath.n_children, wanted[path]['n_children'])
				seen.add(path)

			for path in wanted:
				self.assertIn(path, seen)

	def assertIndexMatchesPages(self, index, wanted):
		pages = PagesViewInternal()
		linksview = LinksView.new_from_index(index)
		tagsview = TagsView.new_from_index(index)
		with index.db_conn.db_context() as db:
			seen = set()
			for row in db.execute('SELECT id FROM pages'):
				if row['id'] == ROOT_ID:
					continue
				indexpath = pages.lookup_by_id(db, row['id'])
				path = Path(indexpath.name)
				self.assertIn(path, wanted)
				self.assertEqual(indexpath.n_children, wanted[path]['n_children'])

				attrib = wanted[path]
				if attrib['content']:
					self.assertTrue(indexpath.hascontent)
				else:
					self.assertFalse(indexpath.hascontent)

				links = list( linksview.list_links(path) )
				self.assertEqual(len(links), len(attrib['links']))
				for l, link in zip(attrib['links'], links):
					self.assertEqual(l, link.target.name)

				tags = list( tagsview.list_tags(path) )
				self.assertEqual(len(tags), len(attrib['tags']))
				for t, tag in zip(attrib['tags'], tags):
					self.assertEqual(t, tag.name)

				seen.add(path)

			for path in wanted:
				self.assertIn(path, seen)

	def runSequence(self, indexer, sequence, result):
		treecheck = False
		for i, q in enumerate(indexer):
			#~ print '>>', q
			self.assertEqual(q[1].name, sequence[i][1])
			self.assertEqual(q[0], sequence[i][0])
			if not treecheck and q[0] != INDEX_CHECK_TREE:
				self.assertIndexMatchesTree(self.index, result)
				treecheck = True

		assert i == len(sequence)-1
		assert treecheck
		self.assertIndexMatchesPages(self.index, result)

	def testStepByStep(self):
		# This test combines a number of sub-tests because cost of
		# setUp is too much to run them all separate
		signals = []
		def signal_logger(o, path, signal):
			signals.append((signal, path.name))

		sids = []
		for signal in (
			'page-added',
			'page-haschildren-toggled',
			'page-changed',
			'page-to-be-removed',
		):
			sids.append(
				self.index.connect(signal, partial(signal_logger, signal=signal)) )

		indexer = TreeIndexer.new_from_index(self.index)

		#~ print "### Init"
		self.assertFalse(self.index.probably_uptodate)
		indexer.queue_check(ROOT_PATH)
		self.runSequence(indexer, SEQUENCE, PAGES)
		self.assertTrue(self.index.probably_uptodate)
		#~ import pprint; pprint.pprint(signals);
		self.assertEqual(signals, INIT_SIGNALS)

		#~ print "### Init re-run" # update should be stable
		signals[:] = []
		indexer.queue_check(ROOT_PATH)
		self.runSequence(indexer, SEQUENCE, PAGES)
		self.assertEqual(signals, [])

		for sid in sids:
			self.index.disconnect(sid)

		#~ print "### Update new page"
		self.write_pages(UPDATE)
		indexer.queue_check(ROOT_PATH)
		self.runSequence(indexer, UPDATE_SEQUENCE, UPDATED_PAGES)

		#~ print "### Update missing page"
		self.delete_pages(UPDATE)
		indexer.queue_check(ROOT_PATH)
		self.runSequence(indexer, UPDATE_ROLLBACK_SEQUENCE, PAGES)

		#~ print "### Store pages"
		for path, attrib in UPDATE.items():
			#~ print ">>", path
			page = self.store.get_page(path)
			page.parse('wiki', attrib['content'])
			self.store.store_page(page)
			self.index.on_store_page(page)
		self.assertIndexMatchesPages(self.index, UPDATED_PAGES)

		#~ print "### Delete pages"
		for path, attrib in UPDATE.items():
			#~ print ">>", path
			self.store.delete_page(path)
			self.index.on_delete_page(path)
		self.assertIndexMatchesPages(self.index, PAGES)

		#~ print "### Force re-index"
		self.index.flag_reindex()
		self.runSequence(indexer, [t for t in SEQUENCE if t[0]==INDEX_CHECK_PAGE], PAGES)

	def testThreaded(self):
		self.index.start_update()
		self.index.wait_for_update()
		self.assertIndexMatchesPages(self.index, PAGES)


@tests.slowTest
class IndexerTests(MemoryIndexerTests):

	def setUp(self):
		dir = Dir(self.create_tmp_dir())
		self.store = FilesStore(dir)
		self.write_pages(PAGES)
		self.index = Index.new_from_file(
			dir.file('.zim/test_index.db'),
			self.store
		)


class TestIndexPath(tests.TestCase):

	def runTest(self):
		path = IndexPath('Foo:Bar:Baz', [ROOT_ID,2,3,4])
		self.assertEqual(path.id, 4)
		self.assertEqual(path.parent.id, 3)
		self.assertEqual(path.parent.ids, (ROOT_ID,2,3))
		self.assertEqual(list(path.parents()), [
			IndexPath('Foo:Bar', [ROOT_ID,2,3]),
			IndexPath('Foo', [ROOT_ID,2]),
			IndexPath('', [ROOT_ID])
		])

		path = IndexPathRow('Foo:Bar', [ROOT_ID,2,3], {
			'n_children': 5,
			'content_etag': '1234',
		})
		self.assertEqual(path.n_children, 5)
		self.assertTrue(path.hascontent)
		self.assertTrue(path.exists())
		self.assertRaises(AttributeError, lambda: path.foo)


class TestTestNotebook(tests.TestCase):
	# Above we use a small set so we can specify each and every step
	# Here we test the larger notebook with test data used in other
	# tests to ensure this works as well.

	def runTest(self):
		notebook = tests.new_notebook()
		self.assertTrue(notebook.index.probably_uptodate)
		pages = PagesView.new_from_index(notebook.index)
		for name in notebook.testdata_manifest:
			path = Path(name)
			indexpath = pages.lookup_by_pagename(path)
			self.assertIsInstance(indexpath, IndexPathRow)
		# What else to check ?

### TODO put in test module for Path and Notebook ?
class TestHRefFromWikiLink(tests.TestCase):

	def runtTest(self):
		for link, rel, names in (
			('Foo:::Bar', HREF_REL_FLOATING, 'Foo:Bar'),
			(':Foo:', HREF_REL_ABSOLUTE, 'Foo'),
			(':<Foo>:', HREF_REL_ABSOLUTE, 'Foo'),
			('+Foo:Bar', HREF_REL_RELATIVE, 'Foo:Bar'),
			('Child2:AAA', HREF_REL_FLOATING, 'Child2:AAA'),
		):
			href = HRef.new_from_wiki_link(link)
			self.assertEqual(href.rel, rel)
			self.assertEqual(href.names, names)
###

class TestPagesView(tests.TestCase):

	def setUp(self):
		store = MemoryStore()
		for path, attr in PAGES.items():
			store.store_node(path, attr['content'])

		self.index = Index.new_from_memory(store)
		self.index.update()

	def testWalk(self):
		pages = PagesView.new_from_index(self.index)
		pagelist = list( pages.walk() )
		self.assertEqual(
			[p.name for p in pagelist],
			sorted([p.name for p in PAGES.keys()])
		)
		#~ print [p.name for p in pagelist]

		last = len(pagelist)-1
		for i, p in enumerate(pagelist):
			if i > 0:
				r = pages.get_previous(p)
				self.assertEqual(r.name, pagelist[i-1].name)

			if i < last:
				r = pages.get_next(p)
				self.assertEqual(r.name, pagelist[i+1].name)

	def testRecentChanges(self):
		pages = PagesView.new_from_index(self.index)
		pageset = set( pages.walk() )

		recent = set(pages.list_recent_changes())
		self.assertEqual(recent, pageset)

		recent = set(pages.list_recent_changes(limit=3, offset=0))
		self.assertEqual(len(recent), 3)


	def testResolveLink(self):
		pages = PagesView.new_from_index(self.index)
		for sourcename, link, target in (
			('Foo:Child1:GrandChild1', 'Child1', 'Foo:Child1'),
			('Foo:Child1:GrandChild1', 'Child2:AAA', 'Foo:Child2:AAA'),
			('Foo:Child1:GrandChild1', 'AAA', 'Foo:Child1:AAA'),
			('Foo:Child1:GrandChild1', '+AAA', 'Foo:Child1:GrandChild1:AAA'),
			('Foo:Child1:GrandChild1', ':AAA', 'AAA'),
			# TODO more examples
		):
			source = pages.lookup_by_pagename(Path(sourcename))
			self.assertIsNotNone(source)
			self.assertEqual(source.name, sourcename)
			href = HRef.new_from_wiki_link(link)
			path = pages.resolve_link(source, href)
			self.assertEqual(path.name, target)

	def testTreePathMethods(self):
		def check_treepath(get_indexpath_for_treepath, get_treepath_for_indexpath):
			for p, attr in PAGES.items():
				indexpath = get_indexpath_for_treepath(attr['treepath'])
				self.assertEqual(indexpath.name, p.name)
				self.assertEqual(indexpath.treepath, attr['treepath'])
				treepath = get_treepath_for_indexpath(indexpath)
				self.assertEqual(treepath, attr['treepath'])

		# Separate caches to lets each method start from scratch
		cache1 = {}
		cache2 = {}
		check_treepath(
			get_indexpath_for_treepath_factory(self.index, cache1),
			get_treepath_for_indexpath_factory(self.index, cache2)
		)

		self.assertEqual(cache1, cache2)

		# Now try again with a shared cache
		cache = {}
		check_treepath(
			get_indexpath_for_treepath_factory(self.index, cache),
			get_treepath_for_indexpath_factory(self.index, cache)
		)


class TestTagsView(tests.TestCase):

	def setUp(self):
		store = MemoryStore()
		for path, attr in PAGES.items():
			store.store_node(path, attr['content'])

		self.index = Index.new_from_memory(store)
		self.index.update()

	def runTest(self):
		tags = TagsView.new_from_index(self.index)

		mytags = {}
		for p, attr in PAGES.items():
			for t in attr['tags']:
				if not t in mytags:
					mytags[t] = set()
				mytags[t].add(p.name)

		assert len(mytags) > 1
		for t in mytags:
			pages = set(p.name for p in tags.list_pages(t))
			self.assertEqual(pages, mytags[t])


class TestLinksView(tests.TestCase):

	def setUp(self):
		store = MemoryStore()
		for path, attr in PAGES.items():
			store.store_node(path, attr['content'])

		self.index = Index.new_from_memory(store)
		self.index.update()

	def runTest(self):
		linksview = LinksView.new_from_index(self.index)

		for p, attr in PAGES.items():
			links = [l.target.name for l in linksview.list_links(p)]
			n_links = linksview.n_list_links(p)
			self.assertEqual(links, attr['links'])
			self.assertEqual(n_links, len(links))

			back_links = [l.source.name for l in linksview.list_links(p, LINK_DIR_BACKWARD)]
			n_back_links = linksview.n_list_links(p, LINK_DIR_BACKWARD)
			self.assertEqual(back_links, attr['backlinks'])
			self.assertEqual(n_back_links, len(back_links))

			all_links = [(l.source.name, l.target.name) for l in linksview.list_links(p, LINK_DIR_BOTH)]
			n_all_links = linksview.n_list_links(p, LINK_DIR_BOTH)
			self.assertEqual(all_links,
				[(p.name, l) for l in links] + [(l, p.name) for l in back_links])
			self.assertEqual(n_all_links, len(all_links))

			if p.parent.isroot:
				links = list(linksview.list_links_section(p))
				self.assertTrue(len(links) >= len(attr['links']))
				n_links = linksview.n_list_links_section(p)
				self.assertEqual(n_links, len(links))


class TestDBConnection(tests.TestCase):

		@staticmethod
		def select(conn, statement):
			rows = []
			with conn.db_context() as db:
				for row in db.execute(statement):
					rows.append(tuple(row))
			return rows

		def testRollback(self):
			conn = MemoryDBConnection()
			cont = conn.db_change_context()

			# setup table
			with cont as db:
				db.executescript(
					'CREATE TABLE test (string TEXT); '
					'INSERT INTO test VALUES("bar"); '
					'INSERT INTO test VALUES("foo"); '
				)

			self.assertEqual(self.select(conn, 'SELECT * FROM test ORDER BY string'),
				[('bar',), ('foo',)]
			)

			# test rollback after error
			def insert_with_error():
				with cont as db:
					db.execute('INSERT INTO test VALUES("dus")')
					db.execute('INSERT INTO test VALUES("ja")')
					raise AssertionError

			self.assertRaises(AssertionError, insert_with_error)
			self.assertEqual(self.select(conn, 'SELECT * FROM test ORDER BY string'),
				[('bar',), ('foo',)]
			)
