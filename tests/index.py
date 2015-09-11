# -*- coding: utf-8 -*-

# Copyright 2009-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement


import tests

import copy

from functools import partial

import zim.formats

from zim.fs import Dir
from zim.notebook import Path
from zim.notebook.stores.memory import MemoryStore
from zim.notebook.stores.files import FilesStore

from zim.notebook.index import *


PAGES_TREE = { # Pages stored initially in the notebook
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
		'content': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.\n' \
			'@tag1 @tag2\n',
		'links': [],
		'backlinks': [],
		'tags': ['tag1', 'tag2'],
	},
	Path('Foo:Child2'): {
		'treepath': (1,1),
		'n_children': 0,
		'content': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.\n' \
			'@tag2\n' \
			'[[Child3]]\n',
		'links': ['Foo:Child3'],
		'backlinks': [],
		'tags': ['tag2'],
	},
	Path('Foo:Child1:GrandChild1'): {
		'treepath': (1,0,0),
		'n_children': 0,
		'content': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.\n' \
			'@tag2\n',
		'links': [],
		'backlinks': [],
		'tags': ['tag2'],
	},
	Path('Foo:Child1:GrandChild2'): {
		'treepath': (1,0,1),
		'n_children': 0,
		'content': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.\n',
		'links': [],
		'backlinks': [],
		'tags': [],
	},
	Path('SOME EMPTY FOLDER'): {
		'treepath': None,
		'n_children': 0,
		'content': None,
		'links': [],
		'backlinks': [],
		'tags': [],
	},
}

# Add placeholders for links in content, remove empty folder
PAGES = copy.deepcopy(PAGES_TREE)
PAGES[Path('Foo:Child3')] = {
	'treepath': (1,2),
	'n_children': 0,
	'content': None,
	'links': [],
	'backlinks': ['Foo:Child2'],
	'tags': [],
}
PAGES[Path('Foo')]['n_children'] = 3

PAGES.pop(Path('SOME EMPTY FOLDER'))

# Indexer sequence - per phase children iterate in order of discovery
SEQUENCE = (
	(INDEX_CHECK_TREE, ''),
	(INDEX_CHECK_TREE, 'Foo'),
	(INDEX_CHECK_TREE, 'SOME EMPTY FOLDER'), # non existent, but gets checked
	(INDEX_CHECK_TREE, 'Foo:Child1'),
	(INDEX_CHECK_PAGE, 'Bar'),
	(INDEX_CHECK_PAGE, 'Foo'),
	(INDEX_CHECK_PAGE, 'SOME EMPTY FOLDER'),
	(INDEX_CHECK_PAGE, 'Foo:Child1'),
	(INDEX_CHECK_PAGE, 'Foo:Child2'),
	(INDEX_CHECK_PAGE, 'Foo:Child1:GrandChild1'),
	(INDEX_CHECK_PAGE, 'Foo:Child1:GrandChild2'),
)

# Signals emitted during initial indexing
INIT_SIGNALS = [
	('page-added', 'Bar'),
	('page-added', 'Foo'),
	('page-added', 'Foo:Child1'),
	('page-haschildren-toggled', 'Foo'),
	('page-added', 'Foo:Child2'),
	('page-added', 'Foo:Child1:GrandChild1'),
	('page-haschildren-toggled', 'Foo:Child1'),
	('page-added', 'Foo:Child1:GrandChild2'),
	('page-changed', 'Bar'),
	('page-changed', 'Foo'),
	# No signal here for 'SOME EMPTY FOLDER', no content, so not indexed
	('page-changed', 'Foo:Child1'),
	('page-changed', 'Foo:Child2'),
	('page-added', 'Foo:Child3'), # placeholder discovered
	('page-changed', 'Foo:Child1:GrandChild1'),
	('page-changed', 'Foo:Child1:GrandChild2'),
]

# Pages to be added and deleted to test updates
# Both new namespace (below Bar) and in existing namespace (below Foo)
UPDATE = {
	Path('Bar:AAA'): {
		'treepath': (),
		'n_children': 0,
		'content': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.\n' \
			'@tag1 @tag2\n',
		'links': [],
		'tags': ['tag1', 'tag2'],
	},
	Path('Bar:BBB'): {
		'treepath': (),
		'n_children': 0,
		'content': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.\n' \
			'@tag3\n',
		'links': [],
		'tags': ['tag3'],
	},
	# On purpose skipping "Bar:CCC" and children here - should be touched & cleaned up automatically
	Path('Bar:CCC:xxx:yyy:zzz:aaa'): {
		'treepath': (),
		'n_children': 0,
		'content': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.\n',
		'links': [],
		'tags': [],
	},
	Path('Foo:AAA'): {
		'treepath': (),
		'n_children': 0,
		'content': 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.\n',
		'links': [],
		'tags': [],
	},
}

UPDATED_PAGES = copy.deepcopy(PAGES)
UPDATED_PAGES.update(UPDATE)
UPDATED_PAGES[Path('Bar')]['n_children'] += 3
for path in (
	Path('Bar:CCC'),
	Path('Bar:CCC:xxx'),
	Path('Bar:CCC:xxx:yyy'),
	Path('Bar:CCC:xxx:yyy:zzz'),
):
	UPDATED_PAGES[path] = {
		'treepath': (),
		'n_children': 1,
		'content': None,
		'links': [],
		'tags': [],
	}
UPDATED_PAGES[Path('Foo')]['n_children'] += 1

# Sequence when updating - new pages appended at the end of each phase
UPDATE_SEQUENCE = (
	(INDEX_CHECK_TREE, ''),
	(INDEX_CHECK_TREE, 'Bar'),
	(INDEX_CHECK_TREE, 'Foo'),
	(INDEX_CHECK_TREE, 'SOME EMPTY FOLDER'),
	(INDEX_CHECK_TREE, 'Foo:Child1'),
	(INDEX_CHECK_TREE, 'Bar:CCC'),
	(INDEX_CHECK_TREE, 'Bar:CCC:xxx'),
	(INDEX_CHECK_TREE, 'Bar:CCC:xxx:yyy'),
	(INDEX_CHECK_TREE, 'Bar:CCC:xxx:yyy:zzz'),
	(INDEX_CHECK_PAGE, 'Bar'),
	(INDEX_CHECK_PAGE, 'Foo'),
	(INDEX_CHECK_PAGE, 'SOME EMPTY FOLDER'),
	(INDEX_CHECK_PAGE, 'Foo:Child1'),
	(INDEX_CHECK_PAGE, 'Foo:Child2'),
	(INDEX_CHECK_PAGE, 'Foo:Child1:GrandChild1'),
	(INDEX_CHECK_PAGE, 'Foo:Child1:GrandChild2'),
	(INDEX_CHECK_PAGE, 'Bar:AAA'),
	(INDEX_CHECK_PAGE, 'Bar:BBB'),
	(INDEX_CHECK_PAGE, 'Bar:CCC'),
	(INDEX_CHECK_PAGE, 'Foo:AAA'),
	(INDEX_CHECK_PAGE, 'Bar:CCC:xxx'),
	(INDEX_CHECK_PAGE, 'Bar:CCC:xxx:yyy'),
	(INDEX_CHECK_PAGE, 'Bar:CCC:xxx:yyy:zzz'),
	(INDEX_CHECK_PAGE, 'Bar:CCC:xxx:yyy:zzz:aaa'),
)

# Sequence after deleting update again - same as SEQUENCE but with extra check for Bar children
UPDATE_ROLLBACK_SEQUENCE = (
	(INDEX_CHECK_TREE, ''),
	(INDEX_CHECK_TREE, 'Bar'),
	(INDEX_CHECK_TREE, 'Foo'),
	(INDEX_CHECK_TREE, 'SOME EMPTY FOLDER'),
	(INDEX_CHECK_TREE, 'Foo:Child1'),
	(INDEX_CHECK_PAGE, 'Bar'),
	(INDEX_CHECK_PAGE, 'Foo'),
	(INDEX_CHECK_PAGE, 'SOME EMPTY FOLDER'),
	(INDEX_CHECK_PAGE, 'Foo:Child1'),
	(INDEX_CHECK_PAGE, 'Foo:Child2'),
	(INDEX_CHECK_PAGE, 'Foo:Child1:GrandChild1'),
	(INDEX_CHECK_PAGE, 'Foo:Child1:GrandChild2'),
)

# Sequence for re-indexing the whole notebook
REINDEX_SEQUENCE = [
	t for t in SEQUENCE
		if t[0]==INDEX_CHECK_PAGE and Path(t[1]) in PAGES
]

@tests.slowTest
class TestIndex(tests.TestCase):

	def testInit(self):
		dir = Dir(self.create_tmp_dir())
		dir.touch()
		store = MemoryStore()

		# No file
		file = dir.file('not_yet_existing.db')
		assert not file.exists()
		index = Index.new_from_file(file, store)

		# No zim database
		# TODO

		# Old zim database
		# TODO

		# Corrupt file
		file = dir.file('corrupt.db')
		file.write('foooooooooo\n')
		with tests.LoggingFilter('zim.notebook.index', 'Overwriting possibly corrupt database'):
			index = Index.new_from_file(file, store)


class MemoryIndexerTests(tests.TestCase):

	def setUp(self):
		self.store = MemoryStore()
		self.write_pages(PAGES_TREE)
		self.index = Index.new_from_memory(
			self.store
		)

	def write_pages(self, pages):
		parser = zim.formats.get_parser('wiki')
		for path, attrib in pages.items():
			#~ print "Write", path
			node = self.store.get_node(path)
			if attrib['content']:
				tree = parser.parse(attrib['content'])
				node.store_parsetree(tree)
			else:
				## HACK to make child folder to exist ##
				if isinstance(self.store, MemoryStore):
					print "### TODO: virtual attachments folder"
					node = self.store.get_node(path, vivificate=True)
					node.children_etag = 'EMPTY_FOLDER_ETAG'
					node.haschildren = True
				else:
					dir = node.attachments_dir
					dir.file('foo.png').touch()

	def delete_pages(self, pages):
		for path, attrib in pages.items():
			self.store.delete_page(path)

	def assertIndexMatchesTree(self, index, wanted):
		pages = PagesViewInternal()
		with index.db_conn.db_context() as db:
			seen = set()
			for row in db.execute('SELECT * FROM pages WHERE page_exists>0'):
				if row['id'] == ROOT_ID:
					continue
				indexpath = pages.lookup_by_id(db, row['id'])
				path = Path(indexpath.name)
				self.assertIn(path, wanted)
				self.assertIsNotNone(wanted[path]['treepath'])
				self.assertEqual(indexpath.n_children, wanted[path]['n_children'], 'n_children for %s is %i' % (indexpath.name, indexpath.n_children))
				seen.add(path)

			for path in wanted:
				if wanted[path]['treepath'] is not None:
					self.assertIn(path, seen)

	def assertIndexMatchesPages(self, index, wanted):
		pages = PagesViewInternal()
		linksview = LinksView.new_from_index(index)
		tagsview = TagsView.new_from_index(index)
		with index.db_conn.db_context() as db:
			seen = set()
			for row in db.execute('SELECT id FROM pages WHERE page_exists>0'):
				if row['id'] == ROOT_ID:
					continue
				indexpath = pages.lookup_by_id(db, row['id'])
				path = Path(indexpath.name)
				self.assertIn(path, wanted)
				self.assertEqual(indexpath.n_children, wanted[path]['n_children'])

				attrib = wanted[path]
				self.assertIsNotNone(attrib['treepath'])
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
				if wanted[path]['treepath'] is not None:
					self.assertIn(path, seen)

	def runSequence(self, indexer, sequence, result, tree=None):
		if not tree:
			tree = result
		treecheck = False
		#~ print '---'
		for i, q in enumerate(indexer):
			#~ print '>>', q
			self.assertEqual(q[1].name, sequence[i][1])
			self.assertEqual(q[0], sequence[i][0])
			if not treecheck and q[0] != INDEX_CHECK_TREE:
				self.assertIndexMatchesTree(self.index, tree)
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
		self.runSequence(indexer, SEQUENCE, PAGES, PAGES_TREE)
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
		parser = zim.formats.get_parser('wiki')
		for path, attrib in UPDATE.items():
			#~ print "<<", path
			node = self.store.get_node(path)
			tree = parser.parse(attrib['content'])
			node.store_parsetree(tree)
			self.index.on_store_page(path)
		self.assertIndexMatchesPages(self.index, UPDATED_PAGES)

		#~ print "### Delete pages"
		for path, attrib in UPDATE.items():
			#~ print "<<", path
			self.store.delete_page(path)
			self.index.on_delete_page(path)
		self.assertIndexMatchesPages(self.index, PAGES)

		#~ print "### Force re-index"
		self.index.flag_reindex()
		self.runSequence(indexer, REINDEX_SEQUENCE, PAGES)

	def testThreaded(self):
		# Test to prove that thread will update properly
		self.index.start_update()
		try:
			self.index.wait_for_update()
		except:
			self.index.stop_update()
			raise
		self.assertIndexMatchesPages(self.index, PAGES)

		# Test case to prove that the indexer properly releases the
		# change_lock and the state_lock
		import time

		class MockTreeIndexer(TreeIndexer):
			# Mock indexer that never stops indexing

			def do_update_iter(self, db):
				self.counter = 0
				while True:
					self.counter += 1
					yield

		indexer = MockTreeIndexer.new_from_index(self.index)
		thread = WorkerThread(indexer, indexer.__class__.__name__)
		thread.start()
		try:
			time.sleep(0.1)
			with self.index.db_conn.db_context():
				pass
			time.sleep(0.1)
			with self.index.db_conn.db_change_context():
				pass
		finally:
			thread.stop()

		self.assertGreater(indexer.counter, 100)


@tests.slowTest
class IndexerTests(MemoryIndexerTests):

	def setUp(self):
		dir = Dir(self.create_tmp_dir())
		self.store = FilesStore(dir)
		self.write_pages(PAGES_TREE)
		self.index = Index.new_from_file(
			dir.file('.zim/test_index.db'),
			self.store
		)


class TestIndexPath(tests.TestCase):

	def runTest(self):
		path = IndexPath('Foo:Bar:Baz', [ROOT_ID,2,3,4])
		self.assertEqual(path.id, 4)
		self.assertEqual(path.parent, Path('Foo:Bar'))
		self.assertEqual(path.parent.id, 3)
		self.assertEqual(path.parent.ids, (ROOT_ID,2,3))
		for parent, wanted in zip(path.parents(), [
			IndexPath('Foo:Bar', [ROOT_ID,2,3]),
			IndexPath('Foo', [ROOT_ID,2]),
			IndexPath('', [ROOT_ID])
		]):
			self.assertEqual(parent, wanted)
			self.assertEqual(parent.ids, wanted.ids)

		parent = path.commonparent(Path('Foo:Bar:Dus:Ja'))
		self.assertEqual(parent, Path('Foo:Bar'))
		self.assertEqual(parent.id, 3)
		self.assertEqual(parent.ids, (ROOT_ID,2,3))

		path = IndexPathRow('Foo:Bar', [ROOT_ID,2,3], {
			'n_children': 5,
			'content_etag': '1234',
			'page_exists': PAGE_EXISTS_HAS_CONTENT,
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

		for page in reversed(list(notebook.pages.walk())): # delete bottom up
			notebook.delete_page(page)

		# What else to check ?


### TODO put in test module for Path and Notebook ?
class TestHRefFromWikiLink(tests.TestCase):

	def runtTest(self):
		for link, rel, names, properlink in (
			('Foo:::Bar', HREF_REL_FLOATING, 'Foo:Bar', 'Foo:Bar'),
			(':Foo:', HREF_REL_ABSOLUTE, 'Foo', ':Foo'),
			(':<Foo>:', HREF_REL_ABSOLUTE, 'Foo', ':Foo'),
			('+Foo:Bar', HREF_REL_RELATIVE, 'Foo:Bar', '+Foo:Bar'),
			('Child2:AAA', HREF_REL_FLOATING, 'Child2:AAA', 'Child2:AAA'),
		):
			href = HRef.new_from_wiki_link(link)
			self.assertEqual(href.rel, rel)
			self.assertEqual(href.names, names)
			self.assertEqual(href.to_wiki_link(), properlink)
###

def new_memory_index():
	store = MemoryStore()
	parser = zim.formats.get_parser('wiki')
	for path, attr in PAGES_TREE.items():
		if attr['content'] is not None:
			node = store.get_node(path)
			tree = parser.parse(attr['content'])
			node.store_parsetree(tree)

	index = Index.new_from_memory(store)
	index.update()
	return index


class TestPlaceHolders(tests.TestCase):

	def _get_page_exists(self, index, path):
		pages = PagesView.new_from_index(index)
		path = pages.lookup_by_pagename(path)
		return path.page_exists

	def assertIsPlaceholder(self, index, path):
		assert self._get_page_exists(index, path) == PAGE_EXISTS_AS_LINK, 'Is not a placeholder: %s' % path

	def assertExists(self, index, path):
		assert self._get_page_exists(index, path) == PAGE_EXISTS_HAS_CONTENT, 'Does not exist: %s' % path

	def assertDoesNotExist(self, index, path):
		try:
			e = self._get_page_exists(index, path)
		except IndexNotFoundError:
			pass
		else:
			raise AssertionError, 'Should not exist: %s' % path

	def assertLinks(self, index, source, target):
		links = LinksView.new_from_index(index)
		for link in links.list_links(source):
			if link.target.name == target.name:
				break
		else:
			assert False, '%s does not link to %s' % (source, target)

	def store_page(self, index, path, content):
		parser = zim.formats.get_parser('wiki')
		tree = parser.parse(content)
		node = index.store.get_node(path)
		node.store_parsetree(tree)
		index.on_store_page(path)

	def delete_page(self, index, path):
		index.store.delete_page(path)
		index.on_delete_page(path)

	def runTest(self):
		index = new_memory_index()
		self.assertExists(index, Path('Foo:Child2'))
		self.assertIsPlaceholder(index, Path('Foo:Child3'))
		self.assertLinks(index, Path('Foo:Child2'), Path('Foo:Child3'))

		# delete link origin, placeholder should be gone as well
		self.delete_page(index, Path('Foo:Child2'))
		self.assertDoesNotExist(index, Path('Foo:Child2'))
		self.assertDoesNotExist(index, Path('Foo:Child3'))

		# add again
		self.store_page(index, Path('Foo:Child2'), '\n[[Child3]]\n')
		self.assertExists(index, Path('Foo:Child2'))
		self.assertIsPlaceholder(index, Path('Foo:Child3'))
		self.assertLinks(index, Path('Foo:Child2'), Path('Foo:Child3'))

		# add content to placeholder
		self.store_page(index, Path('Foo:Child3'), 'test 123\n')
		self.assertExists(index, Path('Foo:Child3'))
		self.assertLinks(index, Path('Foo:Child2'), Path('Foo:Child3'))

		# delete content again, turn back to placeholder
		self.delete_page(index, Path('Foo:Child3'))
		self.assertIsPlaceholder(index, Path('Foo:Child3'))
		self.assertLinks(index, Path('Foo:Child2'), Path('Foo:Child3'))

		# update children on parent, placeholder should survive
		parser = zim.formats.get_parser('wiki')
		tree = parser.parse('test 123\n')
		node = index.store.get_node(Path('Foo:AAA'))
		node.store_parsetree(tree)
		index.update()
		self.assertIsPlaceholder(index, Path('Foo:Child3'))
		self.assertLinks(index, Path('Foo:Child2'), Path('Foo:Child3'))

		# add page with same name level above, link now resolves
		self.store_page(index, Path('Child3'), 'test 123\n')
		self.assertDoesNotExist(index, Path('Foo:Child3'))
		self.assertLinks(index, Path('Foo:Child2'), Path('Child3'))

		# delete again, placeholder moves back
		self.delete_page(index, Path('Child3'))
		self.assertIsPlaceholder(index, Path('Foo:Child3'))
		self.assertLinks(index, Path('Foo:Child2'), Path('Foo:Child3'))

		# add placeholder level above, keep both placeholders
		self.store_page(index, Path('Foo'), 'test 123\n[[Child3]]\n')
		self.assertIsPlaceholder(index, Path('Child3'))
		self.assertLinks(index, Path('Foo'), Path('Child3'))
		self.assertIsPlaceholder(index, Path('Foo:Child3'))
		self.assertLinks(index, Path('Foo:Child2'), Path('Foo:Child3'))

		# delete again, placeholder moves back
		self.store_page(index, Path('Foo'), 'test 123\n')
		self.assertDoesNotExist(index, Path('Child3'))
		self.assertIsPlaceholder(index, Path('Foo:Child3'))
		self.assertLinks(index, Path('Foo:Child2'), Path('Foo:Child3'))



class TestPagesView(tests.TestCase):

	def testBasics(self):
		index = new_memory_index()
		pages = PagesView.new_from_index(index)

		root = pages.lookup_by_pagename(Path(':'))
		self.assertTrue(root.isroot)
		toplevel = [p.name for p in pages.list_pages(root)]
		self.assertEqual(toplevel, ['Bar', 'Foo'])
		for name in toplevel:
			path = pages.lookup_by_pagename(Path(name))
			userpath = pages.lookup_from_user_input(name)
			self.assertEqual(path, userpath)
			userpath = pages.lookup_from_user_input(name, ROOT_PATH)
			self.assertEqual(path, userpath)

		self.assertRaises(ValueError, pages.get_previous, ROOT_PATH)
		self.assertRaises(ValueError, pages.get_next, ROOT_PATH)

	def testWalk(self):
		index = new_memory_index()
		pages = PagesView.new_from_index(index)
		pagelist = list( pages.walk() )
		self.assertEqual(
			[p.name for p in pagelist],
			sorted([p.name for p in PAGES.keys()])
		)
		#~ print [p.name for p in pagelist]

		self.assertEqual(len(pagelist), pages.n_all_pages())

		last = len(pagelist)-1
		for i, p in enumerate(pagelist):
			r = pages.get_previous(p)
			if i > 0:
				self.assertEqual(r.name, pagelist[i-1].name)
			else:
				self.assertIsNone(r)

			r = pages.get_next(p)
			if i < last:
				self.assertEqual(r.name, pagelist[i+1].name)
			else:
				self.assertIsNone(r)

		section = Path('Foo')
		for page in pages.walk(section):
			self.assertTrue(page.ischild(section))

	def testRecentChanges(self):
		index = new_memory_index()
		pages = PagesView.new_from_index(index)
		pageset = set( pages.walk() )

		recent = set(pages.list_recent_changes())
		self.assertEqual(recent, pageset)

		recent = set(pages.list_recent_changes(limit=3, offset=0))
		self.assertEqual(len(recent), 3)

	def testResolveLink(self):
		index = new_memory_index()
		pages = PagesView.new_from_index(index)
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

			newhref = pages.create_link(source, path)
			self.assertEqual(newhref.rel, href.rel)
			self.assertEqual(newhref.names, href.names)

	def testResolveUserInput(self):
		index = new_memory_index()
		pages = PagesView.new_from_index(index)

		# cleaning absolute paths
		for name, wanted in (
			('foo:::bar', 'Foo:bar'), # "Foo" exists, so "foo" gets capital
			('::foo:bar:', 'Foo:bar'),
			(':foo', 'Foo'),
			('/foo', 'Foo'),
			(':Bar', 'Bar'),
			(':Foo (Bar)', 'Foo (Bar)'),
			('non-existing-page', 'non-existing-page'),
			# TODO more ambigous test cases
		): self.assertEqual(
			pages.lookup_from_user_input(name), Path(wanted) )

		# resolving relative paths
		for name, ns, wanted in (
			('foo:test', 'Foo:Child1', 'Foo:test'),
			('foo:test', 'Bar', 'Foo:test'),
			('test', 'Foo:Child1', 'Foo:test'),
			('+test', 'Foo:Child1', 'Foo:Child1:test'),
		): self.assertEqual(
			pages.lookup_from_user_input(name, Path(ns)), Path(wanted) )

		self.assertRaises(ValueError, pages.lookup_from_user_input, ':::')

	def testTreePathMethods(self):
		index = new_memory_index()

		def check_treepath(
			get_indexpath_for_treepath,
			get_treepath_for_indexpath,
		):
			# Test all pages
			for p, attr in PAGES.items():
				if attr['treepath']:
					indexpath = get_indexpath_for_treepath(attr['treepath'])
					self.assertEqual(indexpath.name, p.name)
					self.assertEqual(indexpath.treepath, attr['treepath'])
					treepath = get_treepath_for_indexpath(indexpath)
					self.assertEqual(treepath, attr['treepath'])

			# Test non-existing
			p = get_indexpath_for_treepath((1,2,3,4,5))
			self.assertIsNone(p)


		# Separate caches to lets each method start from scratch
		cache1 = {}
		cache2 = {}
		check_treepath(
			get_indexpath_for_treepath_factory(index, cache1),
			get_treepath_for_indexpath_factory(index, cache2)
		)

		self.assertEqual(cache1, cache2)

		# Now try again with a shared cache
		cache = {}
		check_treepath(
			get_indexpath_for_treepath_factory(index, cache),
			get_treepath_for_indexpath_factory(index, cache)
		)

	def testTreePathMethodsFlatlist(self):
		index = new_memory_index()
		pages = PagesView.new_from_index(index)

		def check_treepath(
			get_indexpath_for_treepath,
			get_treepaths_for_indexpath,
		):
			# Test all pages
			for p, attr in PAGES.items():
				if attr['treepath']:
					indexpath = pages.lookup_by_pagename(p)
					assert not indexpath.isroot
					for treepath in get_treepaths_for_indexpath(indexpath):
						myindexpath = get_indexpath_for_treepath(treepath)
						self.assertEqual(myindexpath.name, p.name)
						self.assertEqual(myindexpath.treepath, treepath)

			# Test non-existing
			p = get_indexpath_for_treepath((1,2,3,4,5))
			self.assertIsNone(p)

		# Separate caches to lets each method start from scratch
		cache1 = {}
		cache2 = {}
		check_treepath(
			get_indexpath_for_treepath_flatlist_factory(index, cache1),
			get_treepaths_for_indexpath_flatlist_factory(index, cache2)
		)

		#~ self.assertEqual(cache1, cache2)

		# Now try again with a shared cache
		cache = {}
		check_treepath(
			get_indexpath_for_treepath_flatlist_factory(index, cache),
			get_treepaths_for_indexpath_flatlist_factory(index, cache)
		)



class TestTagsView(tests.TestCase):

	def testIndexTag(self):
		foo = {'name': 'foooooo', 'id':1}
		bar = {'name': 'barrrrr', 'id':2}
		tag = IndexTag(foo)
		self.assertTrue(tag == IndexTag(foo))
		self.assertTrue(tag != IndexTag(bar))
		self.assertTrue(isinstance(hash(tag), int))
		self.assertTrue(isinstance(repr(tag), str))

	def testTagsView(self):
		index = new_memory_index()
		tags = TagsView.new_from_index(index)

		mytags = {}
		for p, attr in PAGES.items():
			for t in attr['tags']:
				if not t in mytags:
					mytags[t] = set()
				mytags[t].add(p.name)

		assert len(mytags) > 1
		#~ import pprint; pprint.pprint(mytags)
		for t in mytags:
			pages = set(p.name for p in tags.list_pages(t))
			self.assertEqual(pages, mytags[t])

		with self.assertRaises(IndexNotFoundError):
			tags.list_pages('foooo')

	def testTreePathMethodsTagged(self):
		index = new_memory_index()
		pages = PagesView.new_from_index(index)
		tags = TagsView.new_from_index(index)

		def check_treepath(
			get_indexpath_for_treepath,
			get_treepaths_for_indexpath,
		):
			# Test all tags
			for tag in tags.list_all_tags():
				treepaths = get_treepaths_for_indexpath(tag)
				self.assertTrue(len(treepaths) == 1 and len(treepaths[0]) == 1)
				indextag = get_indexpath_for_treepath(treepaths[0])
				self.assertEqual(indextag.treepath, treepaths[0])
				self.assertEqual(indextag.name, tag.name)

			# Test all pages
			for p, attr in PAGES.items():
				if attr['treepath']:
					indexpath = pages.lookup_by_pagename(p)
					for treepath in get_treepaths_for_indexpath(indexpath):
						myindexpath = get_indexpath_for_treepath(treepath)
						self.assertEqual(myindexpath.name, p.name)
						self.assertEqual(myindexpath.treepath, treepath)

			# Test non-existing
			p = get_indexpath_for_treepath((20,))
			self.assertIsNone(p)
			p = get_indexpath_for_treepath((1,2,3,4,5))
			self.assertIsNone(p)

		# Separate caches to lets each method start from scratch
		cache1 = {}
		cache2 = {}
		check_treepath(
			get_indexpath_for_treepath_tagged_factory(index, cache1),
			get_treepaths_for_indexpath_tagged_factory(index, cache2)
		)

		#~ self.assertEqual(cache1, cache2)

		# Now try again with a shared cache
		cache = {}
		check_treepath(
			get_indexpath_for_treepath_tagged_factory(index, cache),
			get_treepaths_for_indexpath_tagged_factory(index, cache)
		)





class TestLinksView(tests.TestCase):

	def runTest(self):
		index = new_memory_index()
		linksview = LinksView.new_from_index(index)

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
