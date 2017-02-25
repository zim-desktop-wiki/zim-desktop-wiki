# -*- coding: utf-8 -*-

# Copyright 2009-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement


from zim.utils import natural_sort_key
from zim.signals import SIGNAL_NORMAL


from .base import IndexerBase, IndexView, IndexNotFoundError
from .pages import PagesViewInternal, ROOT_PATH, \
	PageIndexRecord  #, get_treepath_for_indexpath_factory


class IndexTag(object):
	'''Object to represent a page tag in the L{Index} API

	These are tags that appear in pages with an "@", like "@foo". They
	are indexed by the L{Index} and represented with this class.

	@ivar name: the name of the tag, e.g. "foo" for an "@foo" in the page
	@ivar id: the id of this tag in the table (primary key)
	@ivar treepath: tuple of index numbers, reserved for use by
	C{TreeStore} widgets
	'''

	__slots__ = ('name', 'id', 'treepath')

	def __init__(self, name, id, treepath=None):
		self.name = name.lstrip('@')
		self.id = id
		self.treepath = treepath

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

	__signals__ = {
		'tag-row-inserted': (SIGNAL_NORMAL, None, (object,)),
		'tag-row-deleted': (SIGNAL_NORMAL, None, (object,)),
		'tag-added-to-page': (SIGNAL_NORMAL, None, (object, object)),
		'tag-removed-from-page': (SIGNAL_NORMAL, None, (object, object)),
	}

	def __init__(self, db, pagesindexer, filesindexer):
		IndexerBase.__init__(self, db)
		self.connectto_all(pagesindexer, (
			'page-changed', 'page-row-deleted'
		))
		self.connectto(filesindexer,
			'finish-update'
		)

		self.db.executescript('''
			CREATE TABLE IF NOT EXISTS tags (
				id INTEGER PRIMARY KEY,
				name TEXT,
				sortkey TEXT,

				CONSTRAINT uc_TagOnce UNIQUE (name)
			);
			CREATE TABLE IF NOT EXISTS tagsources (
				source INTEGER REFERENCES pages(id),
				tag INTEGER REFERENCES tags(id),

				CONSTRAINT uc_TagSourceOnce UNIQUE (source, tag)
			);
		''')

	def on_page_changed(self, pagesindexer, pagerow, doc):
		oldtags = dict(
			(r[0], (r[1], r[2])) for r in self.db.execute(
				'SELECT tags.sortkey, tags.name, tags.id FROM tagsources '
				'LEFT JOIN tags ON tagsources.tag = tags.id '
				'WHERE tagsources.source=?',
				(pagerow['id'],)
			)
		)

		for name in set(doc.iter_tag_names()):
			sortkey = natural_sort_key(name)
			if sortkey in oldtags:
				oldtags.pop(sortkey)
			else:
				row = self.db.execute(
					'SELECT name, id FROM tags WHERE sortkey=?', (sortkey,)
				).fetchone()
				if not row:
					# Create new tag
					self.db.execute(
						'INSERT INTO tags(name, sortkey) VALUES (?, ?)',
						(name, sortkey)
					)
					row = self.db.execute(
						'SELECT name, id FROM tags WHERE sortkey=?', (sortkey,)
					).fetchone()
					assert row
					self.emit('tag-row-inserted', row)

				self.db.execute(
					'INSERT INTO tagsources(source, tag) VALUES (?, ?)',
					(pagerow['id'], row['id'])
				)
				self.emit('tag-added-to-page', row, pagerow)

		for row in oldtags.values():
			self.db.execute(
				'DELETE FROM tagsources WHERE source=? and tag=?',
				(pagerow['id'], row['id'])
			)
			self.emit('tag-removed-from-page', row, pagerow)

	def on_page_row_deleted(self, pageindexer, row):
		self.db.execute(
			'DELETE FROM tagsources WHERE source=?',
			(row['id'],)
		)

	def on_finish_update(self, filesindexer):
		for r in self.db.execute(
			'SELECT tags.name, tags.id FROM tags '
			'WHERE id not in (SELECT DISTINCT tag FROM tagsources)'
		):
			self.emit('tag-row-deleted', r)

		self.db.execute(
			'DELETE FROM tags '
			'WHERE id not in (SELECT DISTINCT tag FROM tagsources)'
		)


class TagsView(IndexView):

	def __init__(self, db):
		IndexView.__init__(self, db)
		self._pages = PagesViewInternal(db)

	def lookup_by_tagname(self, tag):
		if isinstance(tag, IndexTag):
			tag = tag.name
		row = self.db.execute(
			'SELECT name, id FROM tags WHERE name=?', (tag.lstrip('@'),)
		).fetchone()
		if not row:
			raise IndexNotFoundError
		return IndexTag(*row)

	def list_all_tags(self):
		'''Returns all tags in the index as L{IndexTag} objects'''
		for row in self.db.execute(
			'SELECT tags.name, tags.id '
			'FROM tags '
			'ORDER BY tags.sortkey, tags.name'
		):
			yield IndexTag(*row)

	def list_all_tags_by_n_pages(self):
		'''Returns all tags in the index as L{IndexTag} objects'''
		for row in self.db.execute(
			'SELECT tags.name, tags.id '
			'FROM tags '
			'INNER JOIN tagsources ON tags.id=tagsources.tag '
			'GROUP BY tags.id '
			'ORDER BY count(*) DESC'
		):
			yield IndexTag(*row)

	def n_list_all_tags(self):
		r = self.db.execute(
			'SELECT COUNT(*) '
			'FROM tags '
		).fetchone()
		return r[0]

	def list_intersecting_tags(self, tags):
		'''List tags that have pages in common with a given set of tags

		Generator function that lists all tags that occur on pages
		that match the given tag set. This is used to narrow down
		possible tag sets that are not empty. (This method is used e.g.
		in the L{zim.plugins.tags.TagCloudWidget} widget to decide which
		tags to show once some tags are selected.)

		@param tags: an iterable of L{IndexTag} objects
		@returns: yields L{IndexTag} objects
		'''
		tag_ids = '(' + ','.join(str(t.id) for t in tags) + ')'
		for row in self.db.execute(
			# The sub-query filters on pages that match all of the given tags
			# The main query selects all tags occuring on those pages and sorts
			# them by number of matching pages
			'SELECT tags.name, tags.id '
			'FROM tags '
			'INNER JOIN tagsources ON tags.id = tagsources.tag '
			'WHERE tagsources.source IN ('
			'   SELECT source FROM tagsources '
			'   WHERE tag IN %s '
			'   GROUP BY source '
			'   HAVING count(tag) = ? '
			' ) '
			'GROUP BY tags.id '
			'ORDER BY count(*) DESC' % tag_ids, (len(tags),)
		):
			yield IndexTag(*row)

	def list_tags(self, path):
		'''Returns all tags for a given page
		@param path: a L{Path} object for the page
		@returns: yields L{IndexTag} objects
		@raises IndexNotFoundError: if C{path} is not found in the index
		'''
		page_id = self._pages.get_page_id(path) # can raise
		return self._list_tags(page_id)

	def _list_tags(self, page_id):
		for row in self.db.execute(
			'SELECT tags.name, tags.id '
			'FROM tagsources '
			'LEFT JOIN tags ON tagsources.tag=tags.id '
			'WHERE tagsources.source = ?'
			'ORDER BY tags.sortkey, tags.name',
			(page_id,)
		):
			yield IndexTag(*row)

	def n_list_tags(self, path):
		page_id = self._pages.get_page_id(path) # can raise
		r = self.db.execute(
			'SELECT COUNT(*) '
			'FROM tagsources '
			'LEFT JOIN tags ON tagsources.tag=tags.id '
			'WHERE tagsources.source = ?',
			(page_id,)
		).fetchone()
		return r[0]

	def list_pages(self, tag):
		'''List all pages tagged with a given tag.
		@param tag: a tag name as string or an C{IndexTag} object
		@returns: yields L{PageIndexRecord} objects
		'''
		tag = self.lookup_by_tagname(tag)
		return self._list_pages(tag)

	def _list_pages(self, tag):
		for row in self.db.execute(
			'SELECT tagsources.source '
			'FROM tagsources JOIN pages ON tagsources.source=pages.id '
			'WHERE tagsources.tag = ? '
			'ORDER BY pages.sortkey, pages.name',
			(tag.id,)
			# order by id as well because basenames are not unique
		):
			yield self._pages.get_pagename(row['source'])

	def n_list_pages(self, tag):
		tag = self.lookup_by_tagname(tag)
		r = self.db.execute(
			'SELECT COUNT(*) '
			'FROM tagsources JOIN pages ON tagsources.source=pages.id '
			'WHERE tagsources.tag = ?',
			(tag.id,)
		).fetchone()
		return r[0]




def get_indexpath_for_treepath_tagged_factory(db, cache):
	'''Factory for the "get_indexpath_for_treepath()" method
	used by the page index Gtk widget.
	This method stores the corresponding treepaths in the C{treepath}
	attribute of the indexpath.
	The "tagged" version uses L{IndexTag}s for the toplevel with pages
	underneath that match the specific tag, followed by their children.
	@param db: a {sqlite3.Connection} object
	@param cache: a dict used to store (intermediate) results
	@returns: a function
	'''
	# This method is constructed by a factory to speed up all lookups
	# it is defined here to keep all SQL code in the same module
	assert not cache, 'Better start with an empty cache!'

	def get_indextag(db, position):
		if (position,) in cache:
			return cache[(position,)]

		row = db.execute(
			'SELECT name, id FROM tags ORDER BY sortkey, name LIMIT 1 OFFSET ? ',
			(position,)
		).fetchone()
		if row:
			itag = IndexTag(*row, treepath=(position,))
			cache[itag.treepath] = itag
			return itag
		else:
			return None

	def get_indexpath_for_treepath_tagged(treepath):
		assert isinstance(treepath, tuple)
		if treepath in cache:
			return cache[treepath]

		# Get toplevel tag
		tag = get_indextag(db, treepath[0])
		if len(treepath) == 1 or tag is None:
			return tag

		# Get toplevel page
		mytreepath = tag.treepath + (treepath[1],)
		if mytreepath in cache:
			parent = cache[mytreepath]
		else:
			row = db.execute(
				'SELECT pages.* '
				'FROM tagsources JOIN pages ON tagsources.source=pages.id '
				'WHERE tagsources.tag = ? '
				'ORDER BY pages.sortkey, pages.name '
				'LIMIT 1 OFFSET ? ',
				(tag.id, treepath[1],)
			).fetchone()
			if row:
				parent = PageIndexRecord(row, mytreepath)
				cache[mytreepath] = parent
			else:
				return None

		# Iterate parent paths
		for i in range(2, len(treepath)):
			mytreepath = tuple(treepath[:i])
			if mytreepath in cache:
				parent = cache[mytreepath]
			else:
				row = db.execute(
					'SELECT * FROM pages '
					'WHERE parent=? '
					'ORDER BY sortkey, name '
					'LIMIT 1 OFFSET ? ',
					(parent.id, mytreepath[-1])
				).fetchone()
				if row:
					parent = PageIndexRecord(row, mytreepath)
					cache[mytreepath] = parent
				else:
					return None

		# Now cache a slice at the target level
		parentpath = treepath[:-1]
		offset = treepath[-1]
		for i, row in enumerate(db.execute(
			'SELECT * FROM pages '
			'WHERE parent=? '
			'ORDER BY sortkey, name '
			'LIMIT 20 OFFSET ? ',
			(parent.id, offset)
		)):
			mytreepath = parentpath + (offset + i,)
			if not mytreepath in cache:
				indexpath = PageIndexRecord(row, mytreepath)
				cache[mytreepath] = indexpath

		try:
			return cache[treepath]
		except KeyError:
			return None

	return get_indexpath_for_treepath_tagged


def get_treepaths_for_indexpath_tagged_factory(db, cache):
	'''Factory for the "get_treepath_for_indexpath()" method
	used by the page index Gtk widget.
	The "tagged" version uses L{IndexTag}s for the toplevel with pages
	underneath that match the specific tag, followed by their children.
	@param db: a C{sqlite3.Connection} object
	@param cache: a dict used to store (intermediate) results
	@returns: a function
	'''
	# This method is constructed by a factory to speed up all lookups
	# it is defined here to keep all SQL code in the same module
	#
	# We don't do a reverse cache lookup - faster to just go forwards.
	# Only cache to ensure subsequent get_indexpath_for_treepath calls
	# are faster. Don't overwrite existing items in the cache to ensure
	# ref count on paths.
	#
	# For the tagged version, all tags are toplevel, so walk parents and
	# add a result for each tag of each parent followed by sub-tree
	assert not cache, 'Better start with an empty cache!'

	get_treepath_for_indexpath = get_treepath_for_indexpath_factory(db, {})

	def get_tag_position(tagname, tagid):
		tagsortkey = natural_sort_key(tagname)
		row = db.execute(
			'SELECT COUNT(*) '
			'FROM tags '
			'WHERE ('
			'   sortkey<? '
			'   or (sortkey=? and name<?) '
			')',
			(tagsortkey, tagsortkey, tagname)
		).fetchone()
		return row[0]

	def get_treepaths_for_indexpath_tagged(indexpath):
		if isinstance(indexpath, IndexTag):
			tagposition = get_tag_position(indexpath.name, indexpath.id)
			return [(tagposition,)]

		# for each parent find each tag as starting point
		treepaths = []
		normalpath = get_treepath_for_indexpath(indexpath)
		names = indexpath.parts
		for i, basename in enumerate(names):
			name = ':'.join(names[:i+1])

			r = db.execute(
				'SELECT id FROM pages WHERE name=?',
				(name,)
			).fetchone()
			if r:
				page_id, = r
			else:
				raise IndexConsistencyError, 'No such page: %s' % name

			tags = db.execute(
				'SELECT tags.name, tags.id '
				'FROM tagsources '
				'LEFT JOIN tags ON tagsources.tag=tags.id '
				'WHERE tagsources.source = ?',
				(page_id,)
			).fetchall()

			sortkey = natural_sort_key(basename)
			for tagname, tagid in tags:
				tagposition = get_tag_position(tagname, tagid)
				n, = db.execute(
					'SELECT COUNT(*) FROM tagsources '
					'LEFT JOIN pages ON tagsources.source=pages.id '
					'WHERE tagsources.tag = ? and ('
					'	pages.sortkey<? '
					'	or (pages.sortkey=? and pages.name<?)'
					')',
					(tagid, sortkey, sortkey, name)
				).fetchone()
				mytreepath = (tagposition, n,) + normalpath[i+1:]
					# tag + toplevel + remainder of real treepath
				treepaths.append(mytreepath)

		return treepaths

	return get_treepaths_for_indexpath_tagged
