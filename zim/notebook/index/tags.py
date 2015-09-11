# -*- coding: utf-8 -*-

# Copyright 2009-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement


from zim.utils import natural_sort_key, init_generator
from zim.signals import SIGNAL_BEFORE


from .base import IndexerBase, IndexViewBase, IndexNotFoundError
from .pages import PagesViewInternal, \
	ROOT_PATH, IndexPath, get_treepath_for_indexpath_factory


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

	__signals__ = {
		'tag-created': (None, None, (object,)),
		'tag-delete': (SIGNAL_BEFORE, None, (object,)),
		'tag-deleted': (None, None, (object,)),

		'tag-add-to-page': (SIGNAL_BEFORE, None, (object, object)),
		'tag-added-to-page': (None, None, (object, object)),
		'tag-remove-from-page': (SIGNAL_BEFORE, None, (object, object)),
		'tag-removed-from-page': (None, None, (object, object)),
	}

	INIT_SCRIPT = '''
		CREATE TABLE tags (
			id INTEGER PRIMARY KEY,
			name TEXT,
			sortkey TEXT,

			CONSTRAINT uc_TagOnce UNIQUE (name)
		);
		CREATE TABLE tagsources (
			source INTEGER REFERENCES pages(id),
			tag INTEGER REFERENCES tags(id),

			CONSTRAINT uc_TagSourceOnce UNIQUE (source, tag)
		);
	'''

	def on_index_page(self, index, db, indexpath, parsetree):
		db.execute(
			'DELETE FROM tagsources WHERE source=?',
			(indexpath.id,)
		)

		if parsetree:
			for name in parsetree.iter_tag_names():
				row = db.execute(
					'SELECT id FROM tags WHERE name=?', (name,)
				).fetchone()
				if row:
					tagid = row['id']
				else:
					sortkey = natural_sort_key(name)
					c = db.execute(
						'INSERT INTO tags(name, sortkey) VALUES (?, ?)', (name, sortkey)
					)
					tagid = c.lastrowid

				db.execute(
					'INSERT INTO tagsources(source, tag) VALUES (?, ?)',
					(indexpath.id, tagid)
				)

		db.execute(
			'DELETE FROM tags WHERE id not in (SELECT DISTINCT tag FROM tagsources)'
		)

	def on_delete_page(self, index, db, indexpath):
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

	def lookup_by_tagname(self, tag):
		with self._db as db:
			return self._lookup_by_tagname(db, tag)

	def _lookup_by_tagname(self, db, tag):
		if isinstance(tag, IndexTag):
			tag = tag.name
		row = db.execute(
			'SELECT * FROM tags WHERE name=?', (tag.lstrip('@'),)
		).fetchone()
		if not row:
			raise IndexNotFoundError
		return IndexTag(row)

	def list_all_tags(self):
		'''Returns all tags in the index as L{IndexTag} objects'''
		with self._db as db:
			for row in db.execute(
				'SELECT tags.name, tags.id '
				'FROM tags '
				'ORDER BY tags.sortkey, tags.name'
			):
				yield IndexTag(row)

	def list_all_tags_by_n_pages(self):
		'''Returns all tags in the index as L{IndexTag} objects'''
		with self._db as db:
			for row in db.execute(
				'SELECT tags.name, tags.id '
				'FROM tags '
				'INNER JOIN tagsources ON tags.id=tagsources.tag '
				'GROUP BY tags.id '
				'ORDER BY count(*) DESC'
			):
				yield IndexTag(row)

	def n_list_all_tags(self):
		with self._db as db:
			r = db.execute(
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
		with self._db as db:
			for row in db.execute(
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
				yield IndexTag(row)

	@init_generator
	def list_tags(self, path):
		'''Returns all tags for a given page
		@param path: a L{Path} object for the page
		@returns: yields L{IndexTag} objects
		@raises IndexNotFoundError: if C{path} is not found in the index
		'''
		with self._db as db:
			indexpath = self._pages.lookup_by_pagename(db, path)
			yield # init done

			for row in db.execute(
				'SELECT tags.name, tags.id '
				'FROM tagsources '
				'LEFT JOIN tags ON tagsources.tag=tags.id '
				'WHERE tagsources.source = ?'
				'ORDER BY tags.sortkey, tags.name',
				(indexpath.id,)
			):
				yield IndexTag(row)

	@init_generator
	def list_pages(self, tag):
		'''List all pages tagged with a given tag.
		@param tag: a tag name as string or an C{IndexTag} object
		@returns: yields L{IndexPathRow} objects
		'''
		with self._db as db:
			tag = self._lookup_by_tagname(db, tag)
			yield # init done

			for row in db.execute(
				'SELECT tagsources.source '
				'FROM tagsources JOIN pages ON tagsources.source=pages.id '
				'WHERE tagsources.tag = ? '
				'ORDER BY pages.sortkey, pages.basename, pages.id',
				(tag.id,)
				# order by id as well because basenames are not unique
			):
				yield self._pages.lookup_by_id(db, row['source'])

	def n_list_pages(self, tag):
		with self._db as db:
			tag = self._lookup_by_tagname(db, tag)
			r = db.execute(
				'SELECT COUNT(*) '
				'FROM tagsources JOIN pages ON tagsources.source=pages.id '
				'WHERE tagsources.tag = ?',
				(tag.id,)
			).fetchone()
			return r[0]




def get_indexpath_for_treepath_tagged_factory(index, cache):
	'''Factory for the "get_indexpath_for_treepath()" method
	used by the page index Gtk widget.
	This method stores the corresponding treepaths in the C{treepath}
	attribute of the indexpath.
	The "tagged" version uses L{IndexTag}s for the toplevel with pages
	underneath that match the specific tag, followed by their children.
	@param index: an L{Index} object
	@param cache: a dict used to store (intermediate) results
	@returns: a function
	'''
	# This method is constructed by a factory to speed up all lookups
	# it is defined here to keep all SQL code in the same module
	assert not cache, 'Better start with an empty cache!'

	db_context = index.db_conn.db_context()
	pages = PagesViewInternal()

	def get_indextag(db, position):
		if (position,) in cache:
			return cache[(position,)]

		row = db.execute(
			'SELECT * '
			'FROM tags '
			'ORDER BY sortkey, name '
			'LIMIT 1 OFFSET ? ',
			(position,)
		).fetchone()
		if row:
			itag = IndexTag(row)
			itag.treepath = (position,)
			cache[itag.treepath] = itag
			return itag
		else:
			return None

	def get_indexpath_for_treepath_tagged(treepath):
		assert isinstance(treepath, tuple)
		if treepath in cache:
			return cache[treepath]

		with db_context as db:
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
					'ORDER BY pages.sortkey, pages.basename, pages.id '
					'LIMIT 1 OFFSET ? ',
					(tag.id, treepath[1],)
				).fetchone()
				if row:
					parent = pages.lookup_by_row(db, row)
					parent.treepath = mytreepath
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
						'WHERE parent=? and page_exists>0 '
						'ORDER BY sortkey, basename '
						'LIMIT 1 OFFSET ? ',
						(parent.id, mytreepath[-1])
					).fetchone()
					if row:
						parent = parent.child_by_row(row)
						parent.treepath = mytreepath
						cache[mytreepath] = parent
					else:
						return None

			# Now cache a slice at the target level
			parentpath = treepath[:-1]
			offset = treepath[-1]
			for i, row in enumerate(db.execute(
				'SELECT * FROM pages '
				'WHERE parent=? and page_exists>0 '
				'ORDER BY sortkey, basename '
				'LIMIT 20 OFFSET ? ',
				(parent.id, offset)
			)):
				mytreepath = parentpath + (offset + i,)
				if not mytreepath in cache:
					indexpath = parent.child_by_row(row)
					indexpath.treepath = mytreepath
					cache[mytreepath] = indexpath

		try:
			return cache[treepath]
		except KeyError:
			return None

	return get_indexpath_for_treepath_tagged


def get_treepaths_for_indexpath_tagged_factory(index, cache):
	'''Factory for the "get_treepath_for_indexpath()" method
	used by the page index Gtk widget.
	The "tagged" version uses L{IndexTag}s for the toplevel with pages
	underneath that match the specific tag, followed by their children.
	@param index: an L{Index} object
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

	db_context = index.db_conn.db_context()
	get_treepath_for_indexpath = get_treepath_for_indexpath_factory(index, {})

	def get_tag_position(db, tagname, tagid):
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
		if row:
			return row[0]
		else:
			raise IndexConsistencyError, 'huh!?'


	def get_treepaths_for_indexpath_tagged(indexpath):
		with db_context as db:
			if isinstance(indexpath, IndexTag):
				tagposition = get_tag_position(db, indexpath.name, indexpath.id)
				return [(tagposition,)]

			parent = ROOT_PATH
			treepaths = []
			normalpath = get_treepath_for_indexpath(indexpath)

			for basename, id, j in zip(
				indexpath.name.split(':'),
				indexpath.ids[1:], # remove ROOT_ID in front
				range(1, len(indexpath.ids))
			):
				part = IndexPath(parent.name+':'+basename, parent.ids+(id,))
				sortkey = natural_sort_key(basename)
				tags = db.execute(
					'SELECT tags.name, tags.id '
					'FROM tagsources '
					'LEFT JOIN tags ON tagsources.tag=tags.id '
					'WHERE tagsources.source = ?',
					(part.id,)
				).fetchall()

				for tagname, tagid in tags:
					tagposition = get_tag_position(db, tagname, tagid)
					row = db.execute(
						'SELECT COUNT(*) '
						'FROM tagsources JOIN pages ON tagsources.source=pages.id '
						'WHERE tagsources.tag = ? and ('
						'	pages.sortkey<? '
						'	or (pages.sortkey=? and pages.basename<?)'
						'	or (pages.sortkey=? and pages.basename=? and pages.id<?)'
						')',
						(tagid,
							sortkey,
							sortkey, basename,
							sortkey, basename, id
						)
					).fetchone()
					if row:
						mytreepath = (tagposition, row[0],) + normalpath[j:]
							# tag + toplevel + remainder of real treepath
						treepaths.append(mytreepath)
						#~ if not mytreepath in cache:
							#~ row = db.execute(
								#~ 'SELECT * FROM pages WHERE id=?', (id,)
							#~ ).fetchone()
							#~ if row:
								#~ parent = parent.child_by_row(row)
								#~ parent.treepath = mytreepath
								#~ cache[mytreepath] = parent
							#~ else:
								#~ raise IndexConsistencyError, 'Invalid IndexPath: %r' % part
					else:
						raise IndexConsistencyError, 'huh!?'

				parent = part

		return treepaths

	return get_treepaths_for_indexpath_tagged

