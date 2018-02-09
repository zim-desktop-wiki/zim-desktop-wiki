
# Copyright 2009-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>



import tests

from gi.repository import Gtk

import sqlite3

from zim.notebook import Path, HRef
from zim.formats.wiki import Parser as WikiParser
from zim.newfs.mock import MockFolder

from tests.indexers import buildUpdateIter

TEXT = 'Lorem ipsum dolor sit amet, consectetur adipiscing elit.\n'
FILES = (
	('Bar.txt', TEXT + '@tag1 @tag2\n[[Foo]]\n'),
		# --> Foo
	('Foo.txt', TEXT),
		# <-- Bar
	('Foo/Child1.txt', TEXT + '@tag1 @tag2\n'),
	('Foo/Child2.txt', TEXT + '@tag2\n[[Child3]]\n'),
		# --> PLaceholder Foo:Child3
	('Foo/Child1/GrandChild1.txt', TEXT + '@tag2\n'),
	('Foo/Child1/GrandChild2.txt', TEXT),
)
TREEPATHS = (
	('Bar', (0,)),
	('Foo', (1,)),
	('Foo:Child1', (1, 0)),
	('Foo:Child1:GrandChild1', (1, 0, 0)),
	('Foo:Child1:GrandChild2', (1, 0, 1)),
	('Foo:Child2', (1, 1)),
	('Foo:Child3', (1, 2)),
)
LINKS = (
	('Bar', ['Foo'], []),
	('Foo', [], ['Bar']),
	('Foo:Child1', [], []),
	('Foo:Child2', ['Foo:Child3'], []),
	('Foo:Child3', [], ['Foo:Child2']),
)
TAGS = {
	'tag1': ['Bar', 'Foo:Child1'],
	'tag2': ['Bar', 'Foo:Child1', 'Foo:Child2', 'Foo:Child1:GrandChild1'],
}
TREEPATHS_TAGGED_12 = (
	# include only pages that have both tags
	# top level sorts by basename
	('Bar', (0,)),
	('Foo:Child1', (1,)),
		('Foo:Child1:GrandChild1', (1, 0)),
		('Foo:Child1:GrandChild2', (1, 1)),
)
TREEPATHS_TAGS_12 = (
	# include all pages with any of the tags
	# top level sorts by basename: Bar, Child, GranChild
	('tag1', (0,)),
		('Bar', (0, 0)),
		('Foo:Child1', (0, 1)),
			('Foo:Child1:GrandChild1', (0, 1, 0)),
			('Foo:Child1:GrandChild2', (0, 1, 1)),
	('tag2', (1,)),
		('Bar', (1, 0,)),
		('Foo:Child1', (1, 1,)),
			('Foo:Child1:GrandChild1', (1, 1, 0)),
			('Foo:Child1:GrandChild2', (1, 1, 1)),
		('Foo:Child2', (1, 2,)),
		('Foo:Child1:GrandChild1', (1, 3,)),
)

_SQL = None
def new_test_database(files=FILES):
	if files == FILES:
		global _SQL
		if _SQL is None:
			_SQL = _get_sql(FILES)
		sql = _SQL
	else:
		sql = _get_sql(files)

	db = sqlite3.Connection(':memory:')
	db.row_factory = sqlite3.Row
	db.executescript(sql)
	return db


def _get_sql(files):
	folder = MockFolder('/mock/notebook/')
	indexer = buildUpdateIter(folder)
	for path, text in files:
		folder.file(path).write(text)
	indexer.check_and_update()
	lines = list(indexer.db.iterdump())
	indexer.db.close()
	return '\n'.join(lines)


#class TestMemoryIndex(tests.TestCase):
#
#	def runTest(self):
#		db = new_test_database()
#		for line in db.iterdump():
#			print line

from zim.notebook.index.pages import PagesIndexer, PagesView, \
	PagesTreeModelMixin, \
	IndexNotFoundError
	#get_treepath_for_indexpath_factory, get_indexpath_for_treepath_factory, \
	#get_treepaths_for_indexpath_flatlist_factory, get_indexpath_for_treepath_flatlist_factory, \

class TestPagesView(tests.TestCase):

	def testBasics(self):
		db = new_test_database()
		pages = PagesView(db)

		toplevel = [p.name for p in pages.list_pages(Path(':'))]
		self.assertIn('Bar', toplevel)
		self.assertIn('Foo', toplevel)

		for name in toplevel:
			path = Path(name)
			userpath = pages.lookup_from_user_input(name)
			self.assertEqual(path, userpath)

	def testWalk(self):
		db = new_test_database()
		pages = PagesView(db)

		names = [p.name for p in pages.walk()]
		self.assertIn('Bar', names)
		self.assertIn('Foo', names)
		self.assertIn('Foo:Child1:GrandChild1', names)
		self.assertNotIn('', names)

		self.assertEqual(len(names), pages.n_all_pages())

		last = len(names) - 1
		for i, name in enumerate(names):
			p = pages.get_previous(Path(name))
			if i > 0:
				self.assertIsNotNone(p, 'Missing prev for %s' % name)
				self.assertEqual(p.name, names[i - 1])
			else:
				self.assertIsNone(p)

			n = pages.get_next(Path(name))
			if i < last:
				self.assertIsNotNone(n, 'Missing next for %s' % name)
				self.assertEqual(n.name, names[i + 1])
			else:
				self.assertIsNone(n)

		section = Path('Foo')
		for page in pages.walk(section):
			self.assertTrue(page.ischild(section))

	def testPreviousAndNext(self):
		# Mix of caps and small letters to trigger issues with sorting
		names = ('AAA', 'BBB', 'ccc', 'ddd', 'EEE', 'FFF', 'ggg', 'hhh')
		db = new_test_database((name + '.txt', 'Test 123\n') for name in names)
		pages = PagesView(db)

		last = len(names) - 1
		for i, name in enumerate(names):
			p = pages.get_previous(Path(name))
			if i > 0:
				self.assertIsNotNone(p, 'Missing prev for %s' % name)
				self.assertEqual(p.name, names[i - 1])
			else:
				self.assertIsNone(p)

			n = pages.get_next(Path(name))
			if i < last:
				self.assertIsNotNone(n, 'Missing next for %s' % name)
				self.assertEqual(n.name, names[i + 1])
			else:
				self.assertIsNone(n)

	def testRecentChanges(self):
		db = new_test_database()
		pages = PagesView(db)

		pageset = set(pages.walk())
		recent = set(pages.list_recent_changes())
		self.assertEqual(recent, pageset)

		recent = set(pages.list_recent_changes(limit=3, offset=0))
		self.assertEqual(len(recent), 3)

	def testResolveLink(self):
		db = new_test_database()
		pages = PagesView(db)

		for sourcename, link, target in (
			('Foo:Child1:GrandChild1', 'Child1', 'Foo:Child1'),
			('Foo:Child1:GrandChild1', 'Child2:AAA', 'Foo:Child2:AAA'),
			('Foo:Child1:GrandChild1', 'AAA', 'Foo:Child1:AAA'),
			('Foo:Child1:GrandChild1', '+AAA', 'Foo:Child1:GrandChild1:AAA'),
			('Foo:Child1:GrandChild1', ':AAA', 'AAA'),

			# TODO more examples
			#~ ('Foo:Bar', 'Bar', 'Foo:Bar'),
			#~ ('Foo:Bar', '+Baz', 'Foo:Bar:Baz'),
			#~ ('Foo:Bar:Baz', 'Foo:Dus', 'Foo:Dus'),
			#~ ('Foo:Bar:Baz', 'Dus', 'Foo:Bar:Dus'),
			#~ ('Foo:Bar', 'Dus:Ja', 'Dus:Ja'),
			#~ ('Foo:Bar', 'Ja', 'Foo:Ja'),
			#~ ('Foo:Bar:Baz', 'Bar', 'Foo:Bar'),
			#~ ('Foo:Bar:Baz', 'Foo', 'Foo'),
			#~ ('Foo:Bar:Baz', ':Bar', 'Bar'), # conflict with anchor

		):
			source = Path(sourcename)
			href = HRef.new_from_wiki_link(link)
			path = pages.resolve_link(source, href)
			self.assertEqual(path.name, target)

			newhref = pages.create_link(source, path)
			self.assertEqual(newhref.rel, href.rel)
			self.assertEqual(newhref.names, href.names)

	def testResolveUserInput(self):
		db = new_test_database()
		pages = PagesView(db)

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
		):
			self.assertEqual(
			pages.lookup_from_user_input(name), Path(wanted))

		# resolving relative paths
		for name, ns, wanted in (
			('foo:test', 'Foo:Child1', 'Foo:test'),
			('foo:test', 'Bar', 'Foo:test'),
			('test', 'Foo:Child1', 'Foo:test'),
			('+test', 'Foo:Child1', 'Foo:Child1:test'),
		):
			self.assertEqual(
				pages.lookup_from_user_input(name, Path(ns)), Path(wanted))

		self.assertRaises(ValueError, pages.lookup_from_user_input, ':::')

	def testTreePathMethods(self):
		db = new_test_database()
		mockindex = tests.MockObject()
		mockindex._db = db
		mockindex.update_iter = tests.MockObject()
		mockindex.update_iter.pages = tests.MockObject()

		model = PagesTreeModelMixin(mockindex)

		# Test all pages
		for name, treepath in TREEPATHS:
			myiter = model.get_mytreeiter(treepath)
			self.assertEqual(myiter.row['name'], name)
			self.assertEqual(myiter.treepath, Gtk.TreePath(treepath))
			my_treepath = model.find(Path(name))
			self.assertEqual(my_treepath, Gtk.TreePath(treepath))

		# Test non-existing
		p = model.get_mytreeiter((1, 2, 3, 4, 5))
		self.assertIsNone(p)
		self.assertRaises(IndexNotFoundError, model.find, Path('non-existing-page'))


from zim.notebook.index.tags import TagsIndexer, TagsView, IndexTag, \
		TaggedPagesTreeModelMixin, TagsTreeModelMixin


class TestTagsView(tests.TestCase):

	def testIndexTag(self):
		foo = ('foooooo', 1)
		bar = ('barrrrr', 2)
		tag = IndexTag(*foo)
		self.assertTrue(tag == IndexTag(*foo))
		self.assertTrue(tag != IndexTag(*bar))
		self.assertTrue(isinstance(hash(tag), int))
		self.assertTrue(isinstance(repr(tag), str))

	def testTagsView(self):
		db = new_test_database()
		tags = TagsView(db)

		alltags = tags.list_all_tags()
		self.assertEqual(set(t.name for t in alltags), set(TAGS.keys()))

		alltags = tags.list_all_tags_by_n_pages()
		self.assertEqual(set(t.name for t in alltags), set(TAGS.keys()))

		self.assertEqual(tags.n_list_all_tags(), len(TAGS))

		for name in TAGS:
			indextag = tags.lookup_by_tagname(name)
			self.assertEqual(indextag.name, name)
			pages = tags.list_pages(name)
			self.assertEqual([p.name for p in pages], TAGS[name])
			self.assertEqual(tags.n_list_pages(name), len(TAGS[name]))

		mytags = tags.list_tags(Path('Bar'))
		self.assertEqual([t.name for t in mytags], ['tag1', 'tag2'])
		self.assertEqual(tags.n_list_tags(Path('Bar')), 2)

		mytag = tags.lookup_by_tagname('tag1')
		mytags = tags.list_intersecting_tags([mytag])
		self.assertEqual([t.name for t in mytags], ['tag1', 'tag2'])

		with self.assertRaises(IndexNotFoundError):
			tags.list_pages('foooo')

	def walk_treepaths(self, model, start=()):
		maxrange = 100
		for i in range(0, maxrange):
			assert i < maxrange
			mypath = start + (i,)
			myiter = model.get_mytreeiter(mypath)
			if myiter:
				yield (str(myiter.row['name']), mypath)
				for p in self.walk_treepaths(model, mypath):
					yield p
			else:
				break

	def testTaggedPagesTreePathMethods(self):
		db = new_test_database()
		mockindex = tests.MockObject()
		mockindex._db = db
		mockindex.update_iter = tests.MockObject()
		mockindex.update_iter.pages = tests.MockObject()
		mockindex.update_iter.tags = tests.MockObject()
		model = TaggedPagesTreeModelMixin(mockindex, tags=('tag1', 'tag2'))

		# Test all pages
		for name, treepath in TREEPATHS_TAGGED_12:
			myiter = model.get_mytreeiter(treepath)
			self.assertEqual(myiter.row['name'], name)
			self.assertEqual(myiter.treepath, Gtk.TreePath(treepath))

			my_treepaths = model.find_all(Path(name))
			self.assertIn(Gtk.TreePath(treepath), my_treepaths)
			for treepath in my_treepaths:
				myiter = model.get_mytreeiter(treepath)
				self.assertEqual(myiter.row['name'], name)

		# Test no more data than above
		treepaths = list(self.walk_treepaths(model))
		self.assertEqual(treepaths, list(TREEPATHS_TAGGED_12))

		# Test non-existing
		p = model.get_mytreeiter((1, 2, 3, 4, 5))
		self.assertIsNone(p)
		self.assertRaises(IndexNotFoundError, model.find_all, Path('non-existing-page'))

	def testTagsTreePathMethods(self):
		db = new_test_database()
		mockindex = tests.MockObject()
		mockindex._db = db
		mockindex.update_iter = tests.MockObject()
		mockindex.update_iter.pages = tests.MockObject()
		mockindex.update_iter.tags = tests.MockObject()

		model = TagsTreeModelMixin(mockindex, tags=('tag1', 'tag2'))
		tags = TagsView(db)

		# Test all pages
		for name, treepath in TREEPATHS_TAGS_12:
			myiter = model.get_mytreeiter(treepath)
			self.assertEqual(myiter.row['name'], name)
			self.assertEqual(myiter.treepath, Gtk.TreePath(treepath))
			if len(treepath) == 1:
				tag = tags.lookup_by_tagname(name)
				my_treepaths = model.find_all(tag)
			else:
				my_treepaths = model.find_all(Path(name))

			self.assertIn(Gtk.TreePath(treepath), my_treepaths)
			for treepath in my_treepaths:
				myiter = model.get_mytreeiter(treepath)
				self.assertEqual(myiter.row['name'], name)

		# Test no more data than above
		treepaths = list(self.walk_treepaths(model))
		self.assertEqual(treepaths, list(TREEPATHS_TAGS_12))

		# Test non-existing
		p = model.get_mytreeiter((1, 2, 3, 4, 5))
		self.assertIsNone(p)
		self.assertRaises(IndexNotFoundError, model.find_all, Path('non-existing-page'))


from zim.notebook.index.links import LinksIndexer, LinksView, \
	LINK_DIR_FORWARD, LINK_DIR_BACKWARD, LINK_DIR_BOTH

class TestLinksView(tests.TestCase):

	def runTest(self):
		db = new_test_database()
		linksview = LinksView(db)

		for name, links, backlinks in LINKS:
			path = Path(name)
			mylinks = [l.target.name for l in linksview.list_links(path)]
			n_links = linksview.n_list_links(path)
			self.assertEqual(mylinks, links)
			self.assertEqual(n_links, len(links))

			mybacklinks = [l.source.name for l in linksview.list_links(path, LINK_DIR_BACKWARD)]
			n_backlinks = linksview.n_list_links(path, LINK_DIR_BACKWARD)
			self.assertEqual(mybacklinks, backlinks)
			self.assertEqual(n_backlinks, len(backlinks))

			all_links = [(l.source.name, l.target.name)
							for l in linksview.list_links(path, LINK_DIR_BOTH)]
			n_all_links = linksview.n_list_links(path, LINK_DIR_BOTH)
			self.assertEqual(all_links,
				[(name, l) for l in links] + [(l, name) for l in backlinks])
			self.assertEqual(n_all_links, len(all_links))

			if path.parent.isroot:
				mylinks = list(linksview.list_links_section(path))
				self.assertTrue(len(mylinks) >= len(links))
				n_links = linksview.n_list_links_section(path)
				self.assertEqual(n_links, len(mylinks))

		lclinks = [(l.source, l.target) for l in linksview.list_floating_links('foo')]
		uclinks = [(l.source, l.target) for l in linksview.list_floating_links('FOO')]
		self.assertGreater(len(lclinks), 0)
		self.assertEqual(lclinks, uclinks)
