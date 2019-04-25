
# Copyright 2009-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import tests


import os
import sys
import sqlite3
import time

from zim.notebook.layout import FilesLayout
from zim.newfs import LocalFolder, File
from zim.newfs.mock import os_native_path

from zim.notebook import Path
from zim.notebook.index import Index, DB_VERSION
from zim.notebook.index.files import FilesIndexer, TestFilesDBTable, FilesIndexChecker
from zim.notebook.index.pages import PagesIndexer, TestPagesDBTable
from zim.notebook.index.links import LinksIndexer
from zim.notebook.index.tags import TagsIndexer


def is_dir(path):
	return path.endswith('/') or path.endswith('\\')


@tests.slowTest
class TestIndexInitialization(tests.TestCase):

	def setUp(self):
		self.folder = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		self.folder.touch() # Must exist for sane notebook
		self.layout = FilesLayout(self.folder)

	def testWithoutFileAndWithValidFile(self):
		# Two tests combined because first needed as init for the second
		file = self.folder.file('index.db')
		self.assertFalse(file.exists())
		index = Index(file.path, self.layout)
		self.assertTrue(file.exists())
		self.assertEqual(index.get_property('db_version'), DB_VERSION)

		index._db.close()
		del(index)

		index = Index(file.path, self.layout)
		self.assertTrue(file.exists())
		self.assertEqual(index.get_property('db_version'), DB_VERSION)

	def testWithValidDBFile(self):
		# E.g. old index, not conforming our table layout
		file = self.folder.file('index.db')
		self.assertFalse(file.exists())

		db = sqlite3.Connection(file.path)
		db.execute('CREATE TABLE zim_index (key TEXT);')
		db.close()

		self.assertTrue(file.exists())
		index = Index(file.path, self.layout)
		self.assertTrue(file.exists())
		self.assertEqual(index.get_property('db_version'), DB_VERSION)

	def testWithBrokenFile(self):
		file = self.folder.file('index.db')
		file.write('this is not a database file...\n')

		self.assertTrue(file.exists())
		with tests.LoggingFilter('zim.notebook.index', 'Overwriting'):
			with tests.LoggingFilter('zim.notebook.index', 'Could not access'):
				index = Index(file.path, self.layout)
		self.assertTrue(file.exists())
		self.assertEqual(index.get_property('db_version'), DB_VERSION)

	def testWithLockedFile(self):
		file = self.folder.file('index.db')
		file.write('this is not a database file...\n')
		os.chmod(file.path, 0o000) # make read-only
		self.addCleanup(lambda: os.chmod(file.path, 0o700))

		self.assertTrue(file.exists())
		with tests.LoggingFilter('zim.notebook.index', 'Overwriting'):
			with tests.LoggingFilter('zim.notebook.index', 'Could not access'):
				index = Index(file.path, self.layout)
		self.assertTrue(file.exists())
		self.assertEqual(index.get_property('db_version'), DB_VERSION)


class TestFilesIndexer(tests.TestCase, TestFilesDBTable):

	FILES = tuple(map(os_native_path, (
		'foo.txt', # page with children
		'foo/',
		'foo/test.png',
		'foo/sub1.txt',
		'foo/sub2.txt',

		'bar.txt', # page without children
		'bar/', # empty folder

		'foo-bar.txt', # page without children

		'baz/', # page nested 2 folders deep
		'baz/dus/',
		'baz/dus/ja.txt',

		'argh/', # not a page
		'argh/somefile.pdf',
	)))
	FILES_UPDATE = tuple(map(os_native_path, (
		'tmp.txt', # page with child
		'tmp/',
		'tmp/foo.txt',

		'new/', # nested page
		'new/page.txt',
	)))
	FILES_CHANGE = (
		'foo.txt',
	)
	PAGE_TEXT = 'test 123\n'

	def runTest(self):
		# Test in 3 parts:
		#   1. Index existing files structure
		#   2. Check and update after new files appear
		#   3. Check and update after files disappear

		self.root = self.setUpFolder(mock=tests.MOCK_DEFAULT_REAL)
		db = sqlite3.connect(':memory:')
		db.row_factory = sqlite3.Row

		indexer = FilesIndexer(db, self.root)

		def cb_filter_func(name, o, a):
			#~ print('>>', name)
			if name in ('start-update', 'finish-update'):
				self.assertFalse(a)
				return ()
			else:
				row, = a
				self.assertIsInstance(row, sqlite3.Row)
				return row['path']

		signals = tests.SignalLogger(indexer, cb_filter_func)

		def check_and_update_all():
			checker = FilesIndexChecker(indexer.db, indexer.folder)
			checker.queue_check()
			for out_of_date in checker.check_iter():
				if out_of_date:
					for i in indexer.update_iter():
						pass
			indexer.db.commit()


		# 1. Index existing files structure
		self.create_files(self.FILES)
		check_and_update_all()

		files = set(f for f in self.FILES if not is_dir(f))

		self.assertEqual(set(signals['file-row-inserted']), files)
		self.assertEqual(set(signals['file-row-changed']), files)
		self.assertEqual(signals['file-row-deleted'], [])

		self.assertFilesDBConsistent(db)
		self.assertFilesDBEquals(db, self.FILES)

		# 2. Check and update after new files appear
		signals.clear()
		self.create_files(
			self.FILES_UPDATE + self.FILES_CHANGE
		)
		check_and_update_all()

		files = set(f for f in self.FILES_UPDATE if not is_dir(f))
		update = files | set(self.FILES_CHANGE)

		self.assertEqual(set(signals['file-row-inserted']), files)
		self.assertEqual(set(signals['file-row-changed']), update)
		self.assertEqual(signals['file-row-deleted'], [])

		self.assertFilesDBConsistent(db)
		self.assertFilesDBEquals(db,
			self.FILES + self.FILES_UPDATE
		)

		# 3. Check and update after files disappear
		signals.clear()
		self.remove_files(self.FILES_UPDATE)
		check_and_update_all()

		files = set(f for f in self.FILES_UPDATE if not is_dir(f))

		self.assertEqual(signals['file-row-inserted'], [])
		self.assertEqual(signals['file-row-changed'], [])
		self.assertEqual(set(signals['file-row-deleted']), files)

		self.assertFilesDBConsistent(db)
		self.assertFilesDBEquals(db, self.FILES)

	def create_files(self, files):
		for name in files:
			if is_dir(name):
				self.root.folder(name).touch()
			else:
				self.root.file(name).write(self.PAGE_TEXT)

	def remove_files(self, files):
		for name in reversed(files):
			if is_dir(name):
				self.root.folder(name).remove()
			else:
				self.root.child(name).remove()


class TestFilesIndexerWithCaseInsensitiveFilesytem(tests.TestCase, TestFilesDBTable):

	def runTest(self):
		folder = self.setUpFolder(mock=tests.MOCK_ALWAYS_MOCK)
		folder._fs.set_case_sensitive(False)

		db = sqlite3.connect(':memory:')
		db.row_factory = sqlite3.Row
		indexer = FilesIndexer(db, folder)

		def check_and_update_all():
			checker = FilesIndexChecker(indexer.db, indexer.folder)
			checker.queue_check()
			for out_of_date in checker.check_iter():
				if out_of_date:
					for i in indexer.update_iter():
						pass
			indexer.db.commit()

		for name in ('aaa.txt', 'bbb.txt', 'ccc.txt'):
			folder.file(name).write('Test 123\n')

		check_and_update_all()
		self.assertFilesDBConsistent(db)
		self.assertFilesDBEquals(db, ('aaa.txt', 'bbb.txt', 'ccc.txt'))

		mtime = folder.mtime()
		folder.file('aaa.txt').moveto(folder.file('AAA.txt'))
		self.assertEqual(list(folder.list_names()), ['AAA.txt', 'bbb.txt', 'ccc.txt'])
		self.assertNotEqual(folder.mtime(), mtime)

		check_and_update_all()
		self.assertFilesDBConsistent(db)
		self.assertFilesDBEquals(db, ('AAA.txt', 'bbb.txt', 'ccc.txt'))


class TestPagesIndexer(TestPagesDBTable, tests.TestCase):

	FILES = tuple(map(os_native_path, (
		'foo.txt', # page with children
		'foo/test.png',
		'foo/sub1.txt',
		'foo/sub2.txt',
		'bar.txt', # page without children
		'foo-bar.txt', # page without children
		'baz/dus/ja.txt', # page nested 2 folders deep
		'argh/somefile.pdf', # not a page
	)))
	PAGES = (
		'foo',
		'foo:sub1',
		'foo:sub2',
		'bar',
		'foo-bar',
		'baz',
		'baz:dus',
		'baz:dus:ja',
	)
	CONTENT = ( # These have a file
		'foo',
		'foo:sub1',
		'foo:sub2',
		'bar',
		'foo-bar',
		'baz:dus:ja',
	)
	NAMESPACES = ( # These have also a folder
		'foo',
		'baz',
		'baz:dus',
	)
	PLACEHOLDERS = (
		'some:none_existing:page',
		'foo:sub1:subsub',
		'toplevel'
	)
	PLACEHOLDERS_ALL = (
		'some:none_existing:page',
		'some:none_existing',
		'some',
		'foo:sub1:subsub',
		'toplevel'
	)

	def runTest(self):
		# Test in 4 parts:
		#   1. insert files
		#   2. update files
		#   3. add some placeholders
		#   4. delete files

		self.root = self.setUpFolder()
		layout = FilesLayout(self.root)
		db = sqlite3.connect(':memory:')
		db.row_factory = sqlite3.Row

		file_indexer = tests.MockObject()

		indexer = PagesIndexer(db, layout, file_indexer)

		def cb_filter_func(name, o, a):
			if name == 'page-changed':
				row, content = a
			elif name == 'page-row-changed':
				row, oldrow = a
			else:
				row, = a

			self.assertIsInstance(row, sqlite3.Row)
			return row['name']

		signals = tests.SignalLogger(indexer, cb_filter_func)

		# 1. insert files
		for i, path in enumerate(self.FILES):
			file = self.root.file(path)
			file.write('test 123')
			row = {'id': i, 'path': path}
			indexer.on_file_row_inserted(file_indexer, row)
			self.assertPagesDBConsistent(db)

		self.assertPagesDBEquals(db, self.PAGES)
		self.assertEqual(set(signals['page-row-inserted']), set(self.PAGES))
		self.assertEqual(set(signals['page-row-changed']), set(self.NAMESPACES))
		self.assertEqual(signals['page-row-deleted'], [])
		self.assertEqual(signals['page-changed'], [])

		# 2. update files
		signals.clear()
		for i, path in enumerate(self.FILES):
			row = {'id': i, 'path': path}
			indexer.on_file_row_changed(file_indexer, row)
			self.assertPagesDBConsistent(db)

		self.assertPagesDBEquals(db, self.PAGES)
		self.assertEqual(signals['page-row-inserted'], [])
		self.assertEqual(set(signals['page-row-changed']), set(self.CONTENT))
		self.assertEqual(signals['page-row-deleted'], [])
		self.assertEqual(set(signals['page-changed']), set(self.CONTENT))

		# 3. add some placeholders
		for pagename in self.PLACEHOLDERS:
			indexer.insert_link_placeholder(Path(pagename))
			self.assertPagesDBConsistent(db)

		self.assertPagesDBEquals(db, self.PAGES
			+ self.PLACEHOLDERS_ALL)

		for pagename in self.PLACEHOLDERS:
			indexer.delete_link_placeholder(Path(pagename))
			self.assertPagesDBConsistent(db)

		self.assertPagesDBEquals(db, self.PAGES)

		# 4. delete files
		signals.clear()
		for i, path in enumerate(self.FILES):
			file = self.root.file(path)
			file.remove()
			row = {'id': i, 'path': path}
			indexer.on_file_row_deleted(file_indexer, row)
			self.assertPagesDBConsistent(db)

		self.assertPagesDBEquals(db, [])
		self.assertEqual(signals['page-row-inserted'], [])
		self.assertEqual(set(signals['page-row-changed']), {'foo'})
						 # "foo" has source that is deleted before children
		self.assertEqual(set(signals['page-row-deleted']), set(self.PAGES))
		self.assertEqual(signals['page-changed'], ['foo'])
						 # "foo" has source that is deleted before children


class TestPageNameConflict(tests.TestCase):

	def runTest(self):
		folder = self.setUpFolder()
		layout = FilesLayout(folder)
		db = sqlite3.connect(':memory:')
		db.row_factory = sqlite3.Row

		file_indexer = tests.MockObject()

		indexer = PagesIndexer(db, layout, file_indexer)

		id1 = indexer.insert_page(Path('Test'), None)
		with tests.LoggingFilter('zim.notebook.index', 'Error while inserting page'):
			id2 = indexer.insert_page(Path('Test'), None)

		self.assertEqual(id1, id2)


from zim.utils import natural_sort_key
from zim.notebook.index.pages import PagesViewInternal
from zim.notebook.page import HRef
from zim.formats.wiki import Parser as WikiParser
from zim.newfs.mock import MockFile

class TestLinksIndexer(tests.TestCase):

	## Intended layout ##
	#
	# page Foo --> page Bar
	# page Foo --> placeholder Dus

	PAGES = [
		(2, 'Bar', 'test123\n'),
		(3, 'Foo', '[[Bar]]\n[[Dus]]\n'),
	]

	def runTest(self):
		def basename(name):
			if ":" in name:
				return name.split(":")[-1]
			else:
				return name

		db = sqlite3.connect(':memory:')
		db.row_factory = sqlite3.Row
		pi = PagesIndexer(db, None, tests.MockObject())
		for i, name, cont in self.PAGES:
			db.execute(
				'INSERT INTO pages(id, name, lowerbasename, sortkey, parent, source_file) VALUES (?, ?, ?, ?, 1, 1)',
				(i, name, basename(name).lower(), natural_sort_key(name))
			)

		## Test PagesViewInternal methods
		iview = PagesViewInternal(db)
		i, pn = iview.resolve_pagename(Path(''), ['foo'])
		self.assertEqual((i, pn), (3, Path('Foo')))

		i, pn = iview.resolve_link(Path('Foo'), HRef.new_from_wiki_link('Bar'))
		self.assertEqual((i, pn), (2, Path('Bar')))

		## Test the actual indexer
		pageindexer = tests.MaskedObject(pi, 'connect')
		indexer = LinksIndexer(db, pageindexer)

		for i, name, cont in self.PAGES:
			row = {'id': i, 'name': name, 'sortkey': natural_sort_key(name), 'is_link_placeholder': False}
			indexer.on_page_row_inserted(pageindexer, row)

		###
		pageindexer.setObjectAccess('insert_link_placeholder')
		for i, name, text in self.PAGES:
			tree = WikiParser().parse(text)
			row = {'id': i, 'name': name}
			indexer.on_page_changed(pageindexer, row, tree)

		indexer.update()

		links = sorted(
			(r['source'], r['target'])
				for r in db.execute('SELECT * FROM links')
		)
		self.assertEqual(links, [(3, 2), (3, 4)])

		###
		pageindexer.setObjectAccess('remove_page')
		for i, name, cont in self.PAGES:
			row = {'id': i, 'name': name, 'is_link_placeholder': False}
			indexer.on_page_row_deleted(pageindexer, row)

		indexer.update()

		rows = db.execute('SELECT * FROM links').fetchall()
		self.assertEqual(rows, [])


class TestTagsIndexer(tests.TestCase):

	PAGES = (
		(2, 'foo', '@tag1 @tag2'),
		(3, 'bar', '@tag2 @tag3')
	)

	def runTest(self):
		db = sqlite3.connect(':memory:')
		db.row_factory = sqlite3.Row

		indexer = TagsIndexer(db, tests.MockObject())
		for i, name, text in self.PAGES:
			tree = WikiParser().parse(text)
			row = {'id': i, 'name': name}
			indexer.on_page_changed(None, row, tree)
		indexer.update()

		self.assertTags(db,
			[('tag1', 1), ('tag2', 2), ('tag3', 3)],
 			[(1, 2), (2, 2), (2, 3), (3, 3)]
		)

		for i, name, content in self.PAGES:
			row = {'id': i, 'name': name}
			indexer.on_page_row_delete(None, row)
		indexer.update()

		self.assertTags(db, [], [])

	def assertTags(self, db, wantedtags, wantedsources):
		tags = [tuple(r) for r in db.execute(
			'SELECT name, id FROM tags'
		)]
		self.assertEqual(tags, wantedtags)

		tagsources = [tuple(r) for r in db.execute(
			'SELECT tag, source FROM tagsources'
		)]
		self.assertEqual(tagsources, wantedsources)


from zim.notebook.index import IndexUpdateIter


def buildUpdateIter(folder):
	db = sqlite3.connect(':memory:')
	db.row_factory = sqlite3.Row
	layout = FilesLayout(folder)
	return IndexUpdateIter(db, layout)


class TestFullIndexer(TestFilesIndexer):

	# Just test that all indexers play nice together,
	# no detailed assertions

	PAGE_TEXT = 'test 123\n[[foo:sub1]]\n[[sub1]]\n@tagfoo\n'
		# link content choosen to have one link
		# that resolves always and one link that
		# resolves for some pages, but causes
		# placeholder for other namespaces

	def runTest(self):
		# Test in 3 parts:
		#   1. Index existing files structure
		#   2. Check and update after new files appear
		#   3. Check and update after files disappear

		self.root = self.setUpFolder()
		update_iter = buildUpdateIter(self.root)

		# 1. Index existing files structure
		self.create_files(self.FILES)
		update_iter.check_and_update()

		# 2. Check and update after new files appear
		self.create_files(self.FILES_UPDATE)
		update_iter.check_and_update()

		# 3. Check and update after files disappear
		self.remove_files(self.FILES_UPDATE)
		update_iter.check_and_update()
