# -*- coding: utf-8 -*-

# Copyright 2009-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import sqlite3
import threading
import logging

from datetime import datetime

from zim.notebook import Path, HRef
from zim.utils import natural_sort_key
from zim.notebook import \
	HREF_REL_ABSOLUTE, HREF_REL_FLOATING, HREF_REL_RELATIVE

from .base import IndexViewBase, IndexerBase, \
	IndexConsistencyError, IndexNotFoundError, \
	SIGNAL_BEFORE, SIGNAL_AFTER


ROOT_ID = 1 #: Constant for the ID of the root namespace in "pages"
			# (Primary key starts count at 1 and first entry will be root)


class IndexPath(Path):

	__slots__ = ('ids', 'id')

	def __init__(self, name, ids):
		Path.__init__(self, name) # FUTURE - optimize this away ??
		self.id = ids[-1]
		self.ids = tuple(ids)

	@property
	def parent(self):
		'''Get the path for the parent page'''
		namespace = self.namespace
		if namespace:
			return IndexPath(namespace, self.ids[:-1])
		elif self.isroot:
			return None
		else:
			return ROOT_PATH

	def parents(self):
		'''Generator function for parent Paths including root'''
		if ':' in self.name:
			path = self.name.split(':')[:-1]
			ids = list(self.ids[:-1])
			while len(path) > 0:
				yield IndexPath(':'.join(path), tuple(ids))
				path.pop()
				ids.pop()
		yield ROOT_PATH

	def child_by_row(self, row):
		name = self.name + ':' + row['basename']
		ids = self.ids + (row['id'],)
		return IndexPathRow(name, ids, row)


ROOT_PATH = IndexPath(':', [ROOT_ID])


class IndexPathRow(IndexPath):
	'''Subclass of L{Path} but optimized for index lookups. Objects of
	this class can be used anywhere where a L{Path} is required in the
	API. However in the L{Index} API they are special because the
	IndexPath also contains information which is cached in the
	index.

	@ivar name: the full name of the path
	@ivar parts: all the parts of the name (split on ":")
	@ivar basename: the basename of the path (last part of the name)
	@ivar namespace: the name for the parent page or empty string
	@ivar isroot: C{True} when this Path represents the top level namespace
	@ivar parent: the L{Path} object for the parent page
	@ivar hascontent: page has text content
	@ivar haschildren: page has child pages
	@ivar ctime: creation time of the page (currently unused)
	@ivar mtime: modification time of the page (currently unused)
	'''
	## TODO update docs

	# treepath is reserved for use by e.g. a treestore implementation

	__slots__ = ('_row', 'treepath')

	_attrib = (
		'basename',
		'sortkey',
		'parent',
		'n_children',
		'ctime',
		'mtime',
		'content_etag',
		'children_etag',
	)

	def __init__(self, name, ids, row):
		'''Constructor

		@param name: the full page name
		@param indexpath: a tuple of page ids for all the parents of
		this page and it's own page id (so linking all rows in the
		page hierarchy for this page)
		@param row: optional sqlite3.Row for row for this page in the
		"pages" table, specifies most other attributes for this object
		The property C{hasdata} is C{True} when the row is set.
		'''
		assert row
		IndexPath.__init__(self, name, ids)
		self._row = row

	@property
	def hascontent(self): return self._row['content_etag'] is not None

	@property
	def haschildren(self): return self._row['n_children'] > 0

	def __getattr__(self, attr):
		if attr in self._attrib:
			return self._row[attr]
		else:
			raise AttributeError, '%s has no attribute %s' % (self.__repr__(), attr)

	def exists(self):
		return self.haschildren or self.hascontent


class PagesIndexer(IndexerBase):
	'''Indexer for the "pages" table.
	This object doesn't do much, since most logic for updating the
	"pages" table is already handled by the L{TreeIndexer} class.
	Main function of the indexer is to emit the proper signals.

	@signal: C{page-inserted (L{IndexPathRow})}: emitted when a page is newly
	added to the index (so a new row is inserted in the pages table)
	@signal: C{page-updated (L{IndexPathRow})}: page content has changed
	@signal: C{page-haschildren-toggled (L{IndexPathRow})}: the value of the
	C{haschildren} attribute changed for this page
	@signal: C{page-to-be-deleted (L{IndexPathRow})}: emitted before a
	page is deleted from the index
	'''

	__signals__ = {
		'page-added': (SIGNAL_AFTER, None, (object,)),
		'page-haschildren-toggled': (SIGNAL_AFTER, None, (object,)),
		'page-changed': (SIGNAL_AFTER, None, (object,)),
		'page-to-be-removed': (SIGNAL_BEFORE, None, (object,)),
	}

	INIT_SCRIPT = '''
		CREATE TABLE pages (
			-- these keys are set when inserting a new page and never modified
			id INTEGER PRIMARY KEY,
			parent INTEGER REFERENCES pages(id),
			basename TEXT,
			sortkey TEXT,

			-- these keys are managed by the TreeIndexer - no need to signal
			needscheck INTEGER DEFAULT 0,
			childseen BOOLEAN DEFAULT 1,
			content_etag TEXT,
			children_etag TEXT,

			-- these keys are managed by PageIndex
			n_children BOOLEAN DEFAULT 0,
			ctime TIMESTAMP,
			mtime TIMESTAMP,

			CONSTRAINT uc_PagesOnce UNIQUE (parent, basename)
		);
		INSERT INTO pages(parent, basename, sortkey) VALUES (0, '', '');
	'''

	def on_new_page(self, db, indexpath):
		# emit inserted
		# emit haschildren-toggled on parent when first
		parent = indexpath.parent
		id = parent.id
		n_children_pre = db.execute(
			'SELECT n_children FROM pages WHERE id=?',
			(id,)
		).fetchone()['n_children']
		db.execute(
			'UPDATE pages '
			'SET n_children=(SELECT count(*) FROM pages WHERE parent=?) '
			'WHERE id=?',
			(id, id)
		)
		self.emit('page-added', indexpath)
		if n_children_pre == 0:
			self.emit('page-haschildren-toggled', parent)

	def on_index_page(self, db, indexpath, page):
		# emit changed if mtime is new - or just always ?
		ctime = datetime.fromtimestamp(page.ctime)
		mtime = datetime.fromtimestamp(page.mtime)
		db.execute(
			'UPDATE pages '
			'SET ctime=?, mtime=? '
			'WHERE id=?',
			(ctime, mtime, indexpath.id)
		)
		self.emit('page-changed', indexpath)

	def on_delete_page(self, db, indexpath):
		# emit to-be-deleted
		# emit haschildren-toggled on parent when last
		# Same as on_new_page, but subtract 1 because this page is to be deleted
		parent = indexpath.parent
		id = parent.id
		db.execute(
			'UPDATE pages '
			'SET n_children=(SELECT count(*) FROM pages WHERE parent=?) - 1 '
			'WHERE id=?',
			(id, id)
		)
		self.emit('page-to-be-removed', indexpath)
		n_children_post = db.execute(
			'SELECT n_children FROM pages WHERE id=?',
			(id,)
		).fetchone()['n_children']
		if n_children_post == 0:
			self.emit('page-haschildren-toggled', parent)


class PagesViewInternal(object):
	'''This class defines private methods used by L{PagesView},
	L{LinksView}, L{TagsView} and others. Because it is used internal
	it assumes proper locks are in place, and arguments are always valid
	L{IndexPath}s where specified. It takes a C{sqlite3.Connection}
	object as the first argument for all methods.

	This class is B{not} intended for use out side of index related
	classes. Instead the L{PagesView} class should be used, which has
	a more robust API and checks locks and validity of paths.
	'''

	def lookup_by_id(self, db, id):
		'''Get the L{IndexPathRow} for a given page id
		@param db: a C{sqlite3.Connection} object
		@param id: the page id (primary key for this page)
		@returns: the L{IndexPathRow} for this id
		@raises IndexConsistencyError: if C{id} does not exist in the index
		or parents are missing or inconsistent
		'''
		c = db.execute('SELECT * FROM pages WHERE id=?', (id,))
		row = c.fetchone()
		if row:
			return self.lookup_by_row(db, row)
		else:
			raise IndexConsistencyError, 'No such page id: %r' % id

	def lookup_by_row(self, db, row):
		'''Get the L{IndexPathRow} for a given table row
		@param db: a C{sqlite3.Connection} object
		@param row: the table row for the page
		@returns: the L{IndexPathRow} for this row
		@raises IndexConsistencyError: if parents of C{row} are missing
		or claim to not have children
		'''
		# Constructs the indexpath upwards
		indexpath = [row['id']]
		names = [row['basename']]
		parent = row['parent']
		cursor = db.cursor()
		while parent != 0:
			indexpath.insert(0, parent)
			cursor.execute('SELECT basename, parent, n_children FROM pages WHERE id=?', (parent,))
			myrow = cursor.fetchone()
			if not myrow or myrow['n_children'] < 1:
				if myrow:
					raise IndexConsistencyError, 'Parent has no children'
				else:
					raise IndexConsistencyError, 'Parent missing'
			names.insert(0, myrow['basename'])
			parent = myrow['parent']

		return IndexPathRow(':'.join(names), indexpath, row)

	def lookup_by_pagename(self, db, path):
		#~ @param db: a C{sqlite3.Connection} object

		# Constructs the indexpath downwards - do not optimize for
		# IndexPath objects - assume they are invalid and check top down
		if path.isroot:
			c = db.execute('SELECT * FROM pages WHERE id=?', (ROOT_ID,))
			row = c.fetchone()
			return IndexPathRow(path.name, [ROOT_ID], row)
		else:
			cursor = db.cursor()
			ids = [ROOT_ID]
			for basename in path.parts:
				cursor.execute(
					'SELECT * FROM pages WHERE basename=? and parent=?',
					(basename, ids[-1])
				)
				row = cursor.fetchone()
				if row is None:
					# TODO some wrapper that uses this error to trigger indexer checks
					raise IndexNotFoundError, 'No such path in index: %s' % path.name
				ids.append(row['id'])

			return IndexPathRow(path.name, ids, row)

	def lookup_by_parent(self, db, parent, basename):
		'''Internal implementation of L{PageView.lookup_by_parent()}'''
		c = db.execute(
			'SELECT * FROM pages WHERE parent=? and basename=?',
			(parent.id, basename)
		)
		row = c.fetchone()
		if row:
			return parent.child_by_row(row)
		else:
			raise IndexNotFoundError, 'No such path in index: %s' % parent.child(basename).name

	def resolve_link(self, db, source, href):
		'''Internal implementation of L{PageView.resolve_link()}'''
		# First determine where the link is anchored, search upward
		if href.rel == HREF_REL_ABSOLUTE or source.isroot:
			path = ROOT_PATH
		elif href.rel == HREF_REL_RELATIVE:
			path = source
		else: # HREF_REL_FLOATING
			anchor_key = href.anchor_key()
			path_keys = [natural_sort_key(p) for p in source.parts]
			if anchor_key in path_keys:
				# explicit anchor in page name - use last match
				i = [i for i, k in enumerate(path_keys) if k == anchor_key][-1]
				if i == 0:
					path = ROOT_PATH
				else:
					path = IndexPath(':'.join(source.parts[:i]), source.ids[:i])
			else:
				# search upward namespaces
				for parent in source.parents():
					r = db.execute(
						'SELECT id, basename FROM pages WHERE parent=? and sortkey=? LIMIT 1',
						(parent.id, anchor_key)
					).fetchone()
					if r:
						path = parent
						break
				else:
					path = source.parent # default to parent namespace
					assert path is not None

		# Now resolve downward the right case
		parts = href.parts()
		while parts:
			basename, sortkey = parts.pop(0)
			rows = db.execute(
				'SELECT * FROM pages WHERE parent=? and sortkey=? ORDER BY basename',
				(path.id, sortkey)
			).fetchall()
			for row in rows:
				if row['basename'] == basename: # exact match
					path = path.child_by_row(row)
					break
			else:
				if rows: # case insensitive match
					path = path.child_by_row(rows[0])
				else:
					remainder = ':'.join([basename] + [t[0] for t in parts])
					return path.child(remainder)
		else:
			return path

	def walk(self, db, indexpath):
		for row in db.execute(
			'SELECT * FROM pages WHERE parent=? ORDER BY sortkey, basename',
			(indexpath.id,)
		):
			child = indexpath.child_by_row(row)
			yield child
			if child.haschildren:
				for grandchild in self.walk(db, child): # recurs
					yield grandchild


class PagesView(IndexViewBase):
	'''Index view that exposes the "pages" table in the index'''

	def __init__(self, db_context):
		IndexViewBase.__init__(self, db_context)
		self._pages = PagesViewInternal()

	def lookup_by_pagename(self, path):
		'''Lookup a pagename in the index
		@param path: a L{Path} object
		@returns: a L{IndexPathRow} object
		@raises IndexNotFoundError: if C{path} does not exist in the index
		'''
		with self._db as db:
			return self._pages.lookup_by_pagename(db, path)

	def lookup_from_user_input(self, name, reference=None):
		'''Lookup a pagename based on user input
		@param name: the user input as string
		@reference: a L{Path} in case reletive links are supported as
		customer input
		@returns: a L{IndexPath} or L{Path} for C{name}
		@raises ValueError: when C{name} would reduce to empty string
		after removing all invalid characters, or if C{name} is a
		relative link while no C{reference} page is given.
		@raises IndexNotFoundError: when C{reference} is not indexed
		'''
		# This method re-uses most of resolve_link() but is defined
		# separate because it has a distinct different purpose.
		# Only accidental that we treat user input as links ... ;)
		href = HRef.new_from_wiki_link(name)
		if reference and not reference.isroot:
			return self.resolve_link(reference, href)
		elif href.rel == HREF_REL_RELATIVE:
			raise ValueError, 'Invalid page name: %s' % name
		else:
			return self.resolve_link(ROOT_PATH, href)

	def resolve_link(self, source, href):
		'''Find the end point of a link
		Depending on the link type (absolute, relative, or floating),
		this method first determines the starting point of the link
		path. Then it goes downward doing a case insensitive match
		against the index.
		@param source: a L{Path} for the starting point of the link
		@param href: a L{HRef} object for the link
		@returns: a L{Path} or L{IndexPath} object for the target of the
		link. The object type of the return value depends on whether the
		target exists in the index or not.
		'''
		assert isinstance(source, Path)
		assert isinstance(href, HRef)
		with self._db as db:
			source = self._pages.lookup_by_pagename(db, source)
			return self._pages.resolve_link(db, source, href)

	def list_pages(self, path):
		'''Generator for child pages of C{path}
		@param path: a L{Path} object
		@returns: yields L{IndexPathRow} objects for children of C{path}
		@raises IndexNotFoundError: if C{path} is not found in the index
		'''
		with self._db as db:
			path = self._pages.lookup_by_pagename(db, path)
			for row in db.execute(
				'SELECT * FROM pages WHERE parent=? ORDER BY sortkey, basename',
				(path.id,)
			):
				child = path.child_by_row(row)
				yield child

	def walk(self, path=None):
		'''Generator function to yield all pages in the index, depth
		first

		@param path: a L{Path} object for the starting point, can be
		used to only iterate a sub-tree. When this is C{None} the
		whole notebook is iterated over
		@returns: an iterator that yields L{IndexPathRow} objects
		@raises IndexNotFoundError: if C{path} does not exist in the index
		'''
		with self._db as db:
			if path is None or path.isroot:
				return self._pages.walk(db, ROOT_PATH)
			else:
				return self._pages.walk(db, self.lookup_by_pagename(path))

	def get_previous(self, path):
		'''Get the previous path in the index, in the same order that
		L{walk()} will yield them

		@param path: a L{Path} object
		@returns: an L{IndexPath} or C{None} if there was no previous
		page
		'''
		if path.isroot:
			raise ValueError, 'Got: %s' % path

		with self._db as db:
			path = self._pages.lookup_by_pagename(db, path)

			c = db.execute(
				'SELECT * FROM pages WHERE parent=? and sortkey<? and basename<? '
				'ORDER BY sortkey, basename DESC LIMIT 1',
				(path.parent.id, natural_sort_key(path.basename), path.basename)
			) # DESC means revers order
			row = c.fetchone()
			if not row:
				# First on this level - climb one up to parent
				if path.parent.isroot:
					return None
				else:
					return path.parent
			else:
				# Decent to deepest child of previous path
				prev = path.parent.child_by_row(row)
				while prev.haschildren:
					c = db.execute(
						'SELECT * FROM pages WHERE parent=? '
						'ORDER BY sortkey, basename DESC LIMIT 1',
						(prev.id,)
					) # DESC means revers order
					row = c.fetchone()
					if row:
						prev = prev.child_by_row(row)
					else:
						raise IndexConsistencyError, 'Missing children'
				return prev

	def get_next(self, path):
		'''Get the next path in the index, in the same order that
		L{walk()} will yield them

		@param path: a L{Path} object
		@returns: an L{IndexPath} or C{None} if there was no next
		page
		'''
		if path.isroot:
			raise ValueError, 'Got: %s' % path

		with self._db as db:
			path = self._pages.lookup_by_pagename(db, path)

			if path.haschildren:
				# Descent to first child
				c = db.execute(
					'SELECT * FROM pages WHERE parent=? '
					'ORDER BY sortkey, basename LIMIT 1',
					(path.id,)
				)
				row = c.fetchone()
				if row:
					return path.child_by_row(row)
				else:
					raise IndexConsistencyError, 'Missing children'
			else:
				while not path.isroot:
					# Next on this level
					c = db.execute(
						'SELECT * FROM pages WHERE parent=? and sortkey>? and basename>? '
						'ORDER BY sortkey, basename LIMIT 1',
						(path.parent.id, natural_sort_key(path.basename), path.basename)
					)
					row = c.fetchone()
					if row:
						return path.parent.child_by_row(row)
					else:
						# Go up one level and find next there
						path = path.parent
				else:
					return None

	def list_recent_changes(self, limit=None, offset=None):
		assert not (offset and not limit), "Can't use offset without limit"
		if limit:
			selection = ' LIMIT %i OFFSET %i' % (limit, offset or 0)
		else:
			selection = ''

		with self._db as db:
			for row in db.execute(
				'SELECT * FROM pages ORDER BY mtime' + selection
			):
				yield self._pages.lookup_by_row(db, row)


def get_indexpath_for_treepath_factory(index, cache):
	'''Factory for the "get_indexpath_for_treepath()" method
	used by the page index Gtk widget.
	This method stores the corresponding treepaths in the C{treepath}
	attribute of the indexpath.
	@param index: an L{Index} object
	@param cache: a dict used to store (intermediate) results
	@returns: a function
	'''
	# This method is constructed by a factory to speed up all lookups
	# it is defined here to keep all SQL code in the same module
	db_context = index.db_conn.db_context()

	def get_indexpath_for_treepath(treepath):
		assert isinstance(treepath, tuple)
		if treepath in cache:
			return cache[treepath]

		with db_context as db:
			# Iterate parent paths
			parent = ROOT_PATH
			for i in range(1, len(treepath)):
				mytreepath = tuple(treepath[:i])
				if mytreepath in cache:
					parent = cache[mytreepath]
				else:
					row = db.execute(
						'SELECT * FROM pages WHERE parent=? '
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
				'SELECT * FROM pages WHERE parent=? '
				'ORDER BY sortkey, basename '
				'LIMIT 20 OFFSET ? ',
				(parent.id, offset)
			)):
				mytreepath = parentpath + (offset + i,)
				indexpath = parent.child_by_row(row)
				indexpath.treepath = mytreepath
				cache[mytreepath] = indexpath

		try:
			return cache[treepath]
		except KeyError:
			return None

	return get_indexpath_for_treepath

def get_treepath_for_indexpath_factory(index, cache):
	'''Factory for the "get_treepath_for_indexpath()" method
	used by the page index Gtk widget.
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

	db_context = index.db_conn.db_context()

	def get_treepath_for_indexpath(indexpath):
		with db_context as db:
			treepath = []
			parent = ROOT_PATH
			for part in reversed([indexpath] + list(indexpath.parents())[:-1]):
				basename = part.basename
				sortkey = natural_sort_key(basename)
				row = db.execute(
					'SELECT COUNT(*) FROM pages '
					'WHERE parent=? and ('
					'	sortkey<? '
					'	or (sortkey=? and basename<?)'
					')',
					(parent.id, sortkey, sortkey, basename)
				).fetchone()
				if row:
					treepath.append(row[0])
					mytreepath = tuple(treepath)
					if mytreepath in cache:
						if cache[mytreepath].ids != part.ids:
							raise IndexConsistencyError, 'Cache out of date'
					elif not isinstance(part, IndexPathRow):
						row = db.execute(
							'SELECT * FROM pages WHERE id=?', (part.id,)
						).fetchone()
						if row:
							part = parent.child_by_row(row)
							part.treepath = mytreepath
							cache[mytreepath] = part
						else:
							raise IndexConsistencyError, 'Invalid IndexPath: %r' % part
					else:
						part.treepath = mytreepath
						cache[mytreepath] = part

					parent = part
				else:
					raise IndexConsistencyError, 'huh!?'

		return tuple(treepath)

	return get_treepath_for_indexpath
