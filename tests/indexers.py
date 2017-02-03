# -*- coding: utf-8 -*-

# Copyright 2009-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement


import tests


import os
import sys
import sqlite3
import time

from zim.notebook.layout import FilesLayout
from zim.newfs import LocalFolder, File

from zim.notebook import Path
from zim.notebook.index.files import FilesIndexer, TestFilesDBTable
from zim.notebook.index.pages import PagesIndexer, TestPagesDBTable
from zim.notebook.index.links import LinksIndexer
from zim.notebook.index.tags import TagsIndexer


class TestFilesIndexer(tests.TestCase, TestFilesDBTable):

	FILES = (
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
	)
	FILES_UPDATE = (
		'tmp.txt', # page with child
		'tmp/',
		'tmp/foo.txt',

		'new/', # nested page
		'new/page.txt',
	)
	FILES_CHANGE = (
		'foo.txt',
	)
	PAGE_TEXT = 'test 123\n'

	def runTest(self):
		# Test in 3 parts:
		#   1. Index existing files structure
		#   2. Check and update after new files appear
		#   3. Check and update after files disappear

		self.root = self.setUpFolder()
		db = sqlite3.connect(':memory:')
		db.row_factory = sqlite3.Row

		def cb_filter_func(name, a, kw):
			#~ print '>>', name
			if name in ('on_db_start_update', 'on_db_finish_update'):
				o, = a
				return ()
			else:
				o, file_id, file = a
				self.assertIsInstance(file_id, int)
				self.assertIsInstance(file, File)
				return file.relpath(self.root)

		cb_logger = tests.CallBackLogger(cb_filter_func)

		indexer = FilesIndexer(db, self.root, cb_logger)
		indexer.init_db()

		# 1. Index existing files structure
		self.create_files(self.FILES)
		indexer.check_and_update_all()

		files = set(f for f in self.FILES if not f.endswith('/'))

		self.assertEqual(set(cb_logger['on_db_file_inserted']), files)
		self.assertEqual(set(cb_logger['on_db_file_updated']), files)
		self.assertNotIn('on_db_file_deleted', cb_logger)

		self.assertFilesDBConsistent(db)
		self.assertFilesDBEquals(db, self.FILES)

		# 2. Check and update after new files appear
		cb_logger.clear()
		self.create_files(
			self.FILES_UPDATE + self.FILES_CHANGE
		)
		indexer.check_and_update_all()

		files = set(f for f in self.FILES_UPDATE if not f.endswith('/'))
		update = files | set(self.FILES_CHANGE)

		self.assertEqual(set(cb_logger['on_db_file_inserted']), files)
		self.assertEqual(set(cb_logger['on_db_file_updated']), update)
		self.assertNotIn('on_db_file_deleted', cb_logger)

		self.assertFilesDBConsistent(db)
		self.assertFilesDBEquals(db,
			self.FILES + self.FILES_UPDATE
		)

		# 3. Check and update after files disappear
		cb_logger.clear()
		self.remove_files(self.FILES_UPDATE)
		indexer.check_and_update_all()

		files = set(f for f in self.FILES_UPDATE if not f.endswith('/'))

		self.assertNotIn('on_db_file_inserted', cb_logger)
		self.assertNotIn('on_db_file_updated', cb_logger)
		self.assertEqual(set(cb_logger['on_db_file_deleted']), files)

		self.assertFilesDBConsistent(db)
		self.assertFilesDBEquals(db, self.FILES)


	def create_files(self, files):
		for name in files:
			if name.endswith('/'):
				self.root.folder(name).touch()
			else:
				self.root.file(name).write(self.PAGE_TEXT)

	def remove_files(self, files):
		for name in reversed(files):
			if name.endswith('/'):
				self.root.folder(name).remove()
			else:
				self.root.child(name).remove()


class MockSignalQueue(dict):

	def __init__(self, filter_func):
		self.filter_func = filter_func

	def append(self, s):
		signal = s[0]
		a = s[1:]
		self.setdefault(signal, [])
		self[signal].append(self.filter_func(signal, a))




class TestPagesIndexer(TestPagesDBTable, tests.TestCase):

	FILES = (
		'foo.txt', # page with children
		'foo/test.png',
		'foo/sub1.txt',
		'foo/sub2.txt',
		'bar.txt', # page without children
		'foo-bar.txt', # page without children
		'baz/dus/ja.txt', # page nested 2 folders deep
		'argh/somefile.pdf', # not a page
	)
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

		self.root = self.setUpFolder(mock=tests.MOCK_NEVER)
		layout = FilesLayout(self.root)
		db = sqlite3.connect(':memory:')
		db.row_factory = sqlite3.Row

		def cb_filter_func(name, a, kw):
			if name in ('on_db_start_update', 'on_db_finish_update'):
				o, = a
				return ()
			else:
				if name == 'on_db_index_page':
					o, page_id, page, content = a
				else:
					o, page_id, page = a

				self.assertIsInstance(page_id, int)
				self.assertIsInstance(page, Path)
				return page.name

		def sig_filter_func(signal, a):
			assert signal in PagesIndexer.__signals__, 'Unexpected signal: %s' % signal
			path, = a
			self.assertIsInstance(path, Path)
			return path.name

		cb_logger = tests.CallBackLogger(cb_filter_func)
		signals = MockSignalQueue(sig_filter_func)

		indexer = PagesIndexer(db, layout, [cb_logger], signals)
		indexer.init_db()

		file_indexer = tests.MockObject()

		# 1. insert files
		for i, path in enumerate(self.FILES):
			file = self.root.file(path)
			file.touch()
			indexer.on_db_file_inserted(
				file_indexer, i, file
			)
			self.assertPagesDBConsistent(db)

		pages = self.PAGES
		namespaces = self.NAMESPACES

		self.assertPagesDBEquals(db, pages)

		self.assertEquals(set(signals['page-added']), set(pages))
		self.assertEquals(set(signals['page-haschildren-toggled']), set(namespaces))
		self.assertEquals(set(signals['page-node-changed']), set(namespaces))
		self.assertNotIn('page-changed', signals)
		self.assertNotIn('page-removed', signals)

		# 2. update files
		signals.clear()
		for i, path in enumerate(self.FILES):
			file = self.root.file(path)
			indexer.on_db_file_updated(
				file_indexer, i, file
			)
			self.assertPagesDBConsistent(db)

		self.assertPagesDBEquals(db, pages)

		pages = self.CONTENT

		self.assertNotIn('page-added', signals)
		self.assertNotIn('page-haschildren-toggled', signals)
		self.assertNotIn('page-node-changed', signals)
		self.assertEquals(set(signals['page-changed']), set(pages))
		self.assertNotIn('page-removed', signals)

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
			indexer.on_db_file_deleted(
				file_indexer, i, file
			)
			self.assertPagesDBConsistent(db)

		self.assertPagesDBEquals(db, [])

		pages = self.PAGES
		source_changed = ['foo'] # has source that is deleted before children

		self.assertNotIn('page-added', signals)
		self.assertNotIn('page-haschildren-toggled', signals)
		self.assertEquals(set(signals['page-node-changed']), set(source_changed))
		self.assertEquals(set(signals['page-removed']), set(pages))


from zim.utils import natural_sort_key
from zim.notebook.index.pages import PagesViewInternal, ParseTreeMask
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
		db = sqlite3.connect(':memory:')
		db.row_factory = sqlite3.Row
		pi = PagesIndexer(db, None, [], [])
		pi.init_db()
		for i, name, cont in self.PAGES:
			db.execute(
				'INSERT INTO pages(id, name, sortkey, parent) VALUES (?, ?, ?, 1)',
				(i, name, natural_sort_key(name))
			)

		## Test PagesViewInternal methods
		iview = PagesViewInternal(db)
		i, pn = iview.resolve_pagename(Path(''), ['foo'])
		self.assertEqual((i, pn), (3, Path('Foo')))

		i, pn = iview.resolve_link(Path('Foo'), HRef.new_from_wiki_link('Bar'))
		self.assertEqual((i, pn), (2, Path('Bar')))

		## Test the actual indexer
		indexer = LinksIndexer(db, [])
		indexer.on_db_init()

		page_indexer = tests.MaskedObject(pi, 'insert_link_placeholder')

		for i, name, cont in self.PAGES:
			indexer.on_db_added_page(page_indexer, i, Path(name))

		for i, name, text in self.PAGES:
			tree = WikiParser().parse(text)
			doc = ParseTreeMask(tree)
			indexer.on_db_index_page(page_indexer, i, Path(name), doc)

		indexer.on_db_finish_update(db)

		links = sorted(
			(r['source'], r['target'])
				for r in db.execute('SELECT * FROM links')
		)
		self.assertEqual(links, [(3,2), (3,4)])

		page_indexer = tests.MaskedObject(pi, 'remove_page')

		for i, name, cont in self.PAGES:
			indexer.on_db_delete_page(page_indexer, i, Path(name))

		indexer.on_db_finish_update(page_indexer)

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

		indexer = TagsIndexer(db, [])
		indexer.on_db_init()
		for i, name, text in self.PAGES:
			tree = WikiParser().parse(text)
			doc = ParseTreeMask(tree)
			indexer.on_db_index_page(None, i, Path(name), doc)
		indexer.on_db_finish_update(db)

		self.assertTags(db,
			[('tag1', 1), ('tag2', 2), ('tag3', 3)],
 			[(1, 2), (2, 2), (2, 3), (3, 3)]
		)

		for i, name, content in self.PAGES:
			indexer.on_db_delete_page(None, i, Path(name))
		indexer.on_db_finish_update(db)

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


def buildFullIndexer(folder):
	layout = FilesLayout(folder)

	db = sqlite3.connect(':memory:')
	db.row_factory = sqlite3.Row

	signals = []
	content_indexers = [
		LinksIndexer(db, signals),
		TagsIndexer(db, signals)
	]
	for c in content_indexers:
		c.on_db_init()

	pages_indexer = PagesIndexer(db, layout, content_indexers, signals)
	pages_indexer.init_db()

	files_indexer = FilesIndexer(db, folder, pages_indexer)
	files_indexer.init_db()

	return files_indexer


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
		files_indexer = buildFullIndexer(self.root)

		# 1. Index existing files structure
		self.create_files(self.FILES)
		files_indexer.check_and_update_all()

		# 2. Check and update after new files appear
		self.create_files(self.FILES_UPDATE)
		files_indexer.check_and_update_all()

		# 3. Check and update after files disappear
		self.remove_files(self.FILES_UPDATE)
		files_indexer.check_and_update_all()
