# -*- coding: utf-8 -*-

# Copyright 2009-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement

from .base import IndexerBase, IndexViewBase, IndexNotFoundError
from .pages import PagesViewInternal


class IndexTag(object):
	'''Object to represent a page tag in the L{Index} API

	These are tags that appear in pages with an "@", like "@foo". They
	are indexed by the L{Index} and represented with this class.

	@ivar name: the name of the tag, e.g. "foo" for an "@foo" in the page
	@ivar id: the id of this tag in the table (primary key)
	'''

	__slots__ = ('name', 'id')

	def __init__(self, row):
		self.name = row['name'].lstrip('@')
		self.id = row['id']

	def __repr__(self):
		return '<%s: %s>' % (self.__class__.__name__, self.name)

	def __hash__(self):
		return self.name.__hash__()

	def __eq__(self, other):
		if isinstance(other, IndexTag):
			return self.name == other.name
		else:
			return False

	def __ne__(self, other):
		return not self.__eq__(other)


class TagsIndexer(IndexerBase):

	__signals__ = {}

	INIT_SCRIPT = '''
		CREATE TABLE if not exists tags (
			id INTEGER PRIMARY KEY,
			name TEXT,
			sortkey TEXT,

			CONSTRAINT uc_TagOnce UNIQUE (name)
		);
		CREATE TABLE if not exists tagsources (
			source INTEGER REFERENCES pages(id),
			tag INTEGER REFERENCES tags(id),

			CONSTRAINT uc_TagSourceOnce UNIQUE (source, tag)
		);
	'''

	def on_index_page(self, db, indexpath, page):
		db.execute(
			'DELETE FROM tagsources WHERE source=?',
			(indexpath.id,)
		)

		for name, attrib in page.get_tags():
			row = db.execute(
				'SELECT id FROM tags WHERE name=?', (name,)
			).fetchone()
			if row:
				tagid = row['id']
			else:
				c = db.execute(
					'INSERT INTO tags(name) VALUES (?)', (name,)
				)
				tagid = c.lastrowid

			db.execute(
				'INSERT INTO tagsources(source, tag) VALUES (?, ?)',
				(indexpath.id, tagid)
			)

		db.execute(
			'DELETE FROM tags WHERE id not in (SELECT DISTINCT tag FROM tagsources)'
		)

	def on_delete_page(self, db, indexpath):
		db.execute(
			'DELETE FROM tagsources WHERE source=?',
			(indexpath.id,)
		)
		db.execute(
			'DELETE FROM tags WHERE id not in (SELECT DISTINCT tag FROM tagsources)'
		)


class TagsView(IndexViewBase):

	def __init__(self, db_context):
		IndexViewBase.__init__(self, db_context)
		self._pages = PagesViewInternal()

	def _lookup_by_name(self, db, tag):
		if isinstance(tag, IndexTag):
			tag = tag.name
		row = self.db.execute(
			'SELECT * FROM tags WHERE name=?', (tag.lstrip('@'),)
		).fetchone()
		if not row:
			raise IndexNotFoundError
		return IndexTag(row)

	def list_tags(self, path):
		'''Returns all tags for a given page
		@param path: a L{Path} object for the page
		@returns: yields L{IndexTag} objects
		@raises IndexNotFoundError: if C{path} is not found in the index
		'''
		with self._db as db:
			indexpath = self._pages.lookup_by_pagename(db, path)

			for row in db.execute(
				'SELECT tags.name, tags.id '
				'FROM tagsources '
				'LEFT JOIN tags ON tagsources.tag=tags.id '
				'WHERE tagsources.source = ?',
				(indexpath.id,)
			):
				yield IndexTag(row)


	def list_pages(self, tag):
		'''List all pages tagged with a given tag.
		@param tag: a tag name as string or an C{IndexTag} object
		@returns: yields L{IndexPathRow} objects
		'''
		with self._db as db:
			tag = self._lookup_by_name(db, tag)
			for row in db.execute(
				'SELECT tagsources.source '
				'FROM tagsources JOIN pages ON tagsources.source=pages.id '
				'WHERE tagsources.tag = ? '
				'ORDER BY pages.sortkey, pages.basename, pages.id',
				(tag.id,)
				# order by id as well because basenames are not unique
			):
				yield self._pages.lookup_by_id(row['source'])


