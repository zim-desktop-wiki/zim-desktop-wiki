# -*- coding: utf8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

'''This module contains an class that keeps an index of
all pages, links and backlinks in a notebook.
This index is stored as a sqlite database and allows efficient
lookups of the notebook structure.

To support the index acting as a cache the Store backends should support
a method "get_index_key(pagename)". This method should return a key that
changes when either the page or it's list of children changes (so changes to
the content of a child or the children of a child do not affect this key).
If this method is not implemented pages are re-indexed every time the index
is checked. If this method returns None the page and it's children do no
longer exist.

Note: there are some particular problems with storing hierarchical lists in
a asociative database. Especially lookups of page names are a bit inefficient,
as we need to do a seperate lookup for each parent. Open for future improvement.
'''

import sqlite3
import logging

from zim.notebook import Path

logger = logging.getLogger('zim.index')

LINK_DIR_FORWARD = 1
LINK_DIR_BACKWARD = 2
LINK_DIR_BOTH = 3

# Primary keys start counting with "1", so we can use parent=0
# for pages in the root namespace...

SQL_TABLES = '''
create table if not exists pages (
	id INTEGER PRIMARY KEY,
	basename TEXT,
	parent INTEGER DEFAULT '0',
	hascontent BOOLEAN,
	haschildren BOOLEAN,
	type INTEGER,
	ctime TIMESTAMP,
	mtime TIMESTAMP,
	contentkey TEXT,
	childrenkey TEXT
);
create table if not exists pagetypes (
	id INTEGER PRIMARY KEY,
	label TEXT
);
create table if not exists links (
	source INTEGER,
	drain INTEGER,
	type INTEGER
);
create table if not exists linktypes (
	id INTEGER PRIMARY KEY,
	label TEXT
);
'''


def find_database_file(notebook):
	# Check notebook writable and not an a remote fs
	# Else fall back to XDG_CACHE dir
	# this logic should be in notebook.cache_dir
	# if not cache dir return None
	return None


class IndexPath(Path):
	'''Like Path but adds more attributes, functions as an iterator for
	rows in the table with pages.'''

	__slots__ = ('_indexpath', '_row')

	def __init__(self, name, indexpath, row=None):
		'''Constructore, needs at least a full path name and a tuple of index
		ids pointing to this path in the index. Row is an optional sqlite3.Row
		object and contains the actual data for this path. If row is given
		all properties can be queried as attributes of the IndexPath object.
		The property 'hasdata' is True when the IndexPath has row data.
		'''
		Path.__init__(self, name)
		self._indexpath = tuple(indexpath)
		self._row = row

	@property
	def id(self): return self._indexpath[-1]

	@property
	def hasdata(self): return not self._row is None

	def __getattr__(self, attr):
		if self._row is None:
			raise AttributeError, 'This IndexPath does not contain row data'
		else:
			try:
				return self._row[attr]
			except IndexError:
				raise AttributeError, '%s has no attribute %s' % (self.__repr__, attr)

	def get_parent(self):
		'''Returns IndexPath for parent path'''
		if self.namespace:
			return IndexPath(self.namespace, self._indexpath[:-1])
		elif self.isroot:
			return None
		else:
			return IndexPath(':', (0,))

	def parents(self):
		'''Generator function for parent namespace IndexPaths including root'''
		# version optimized to include indexpaths
		if ':' in self.name:
			path = self.name.split(':')
			path.pop()
			while len(path) > 0:
				namespace = ':'.join(path)
				indexpath = self._indexpath[:len(path)]
				yield IndexPath(namespace, indexpath)
				path.pop()
		yield IndexPath(':', (0,))


class Index(object):
	'''FIXME'''

	def __init__(self, notebook=None, dbfile=None):
		'''If no dbfile is given, the result of 'find_database_file(notebook)'
		will be used. Main use of providing a dbfile here is to make the index
		operate in memory by setting dbfile to ":memory:".
		'''
		self.dbfile = dbfile
		self.db = None
		self.notebook = None
		self._update_queue = []
		if self.dbfile:
			self._connect()
		if notebook:
			self.set_notebook(notebook)

	def set_notebook(self, notebook):
		self.notebook = notebook

		if not self.dbfile:
			self.dbfile = find_database_file(notebook)
			if self.dbfile is None:
				logger.debug('No cache dir found - loading index in memory')
				self.dbfile = ':memory:'
			self._connect()

		# TODO connect to notebook signals for pages being moved / deleted /
		# modified

	def _connect(self):
		self.db = sqlite3.connect(
			self.dbfile, detect_types=sqlite3.PARSE_DECLTYPES)
		self.db.row_factory = sqlite3.Row

		# TODO verify database integrity
		self.db.executescript(SQL_TABLES)

	def update(self, path=None, recursive=True, background=False, fullcheck=False):
		'''This method initiates a database update for a namespace, or, if no
		path is given for the root namespace of the notebook.

		* If "recursive" is True, all namespaces below the given path will
		  be checked.
		* If "background" is True the update will be scheduled on idle events
		  in the glib / gtk main loop. Starting a second background job while
		  one is already running just adds the new path in the queue.
		* In normal operation only page listings are checked. To also check
		  and, when needed, re-index the page contents for all pages set
		  "fullcheck" to True.

		Indexes are checked width first. This is important to make the visual
		behavior of treeviews displaying the index look more solid.
		'''
		if path is None or path.isroot:
			path = IndexPath(':', (0,))
		else:
			path = self.lookup_path(path)

		if path is None:
			assert False, 'TODO: create parent paths first'

		self._update_queue.append((path, recursive, fullcheck))
		if background:
			assert False, 'TODO: start time trigger'
		else:
			while self._update_queue:
				self._do_update_one()

	def _do_update_one(self):
		'''This method unshifts one instruction for the queue and processes
		it. Returns False if the queue is empty, True other wise, so it can
		be called as an event handle.
		'''
		if not self._update_queue:
			return False
		else:
			path, recursive, fullcheck = self._update_queue.pop(0)

		#~ if fullcheck:
			#~ self._check_page(self, path)

		#~ current = None
		#~ try:
			#~ current = self.notebook.get_pagelist_indexkey(path)
			#~ if path.indexkey == current:
				#~ return True
		#~ except NotImplementedError:
			#~ pass # we don't know, so re-index

		# if we get here the cache was out of date or the pagelist does not
		# exist anymore - empty list must result in dropping all sub-pages
		cursor = self.db.cursor()
		cursor.execute('select id, basename from pages where parent==?', (path.id,))
		rows = cursor.fetchall()
		cleanup = set([r.basename for r in rows])

		# check for new pages
		seenchildren = False
		for page in self.notebook.get_pagelist(path):
			seenchildren = True
			if page.basename in cleanup:
				cleanup.remove(page.basename)
			else:
				self.db.execute(
					'insert into pages(basename, parent, hascontent, haschildren) values (?, ?, ?, ?)',
					(page.basename, path.id, page.hascontent, False))
				# We set haschildren to False untill we have actualy seen those
				# children. Failing to do so will cause trouble with the
				# gtk.TreeModel interface to the database, which can not handle
				# nodes that say they have children but fail to deliver when
				# asked.

				# TODO queue content check even if no fullcheck is done

			if fullcheck or (recursive and page.haschildren):
				child = self.lookup_path(page, parent=path)
				assert not child is None
				self._update_queue.append((child, recursive, fullcheck))

		# cleanup remaining pages
		#~ for basename in cleanup:
			#~ self._drop_page(records[basename])

		# Update index key to reflect we did our updates
		#~ if not current is None:
			#~ self.db.execute(
				#~ 'update pages set childrenkey = ? where id == ?',
				#~ (path.id, current) )
		self.db.execute(
			'update pages set haschildren=? where id==?',
			(seenchildren, path.id) )

		return True

	def _check_page(self, page, record):
		try:
			current = self.notebook.get_page_indexkey(path)
			if current and path.indexkey == current:
				return # indexkey is not None and cache up to date
		except NotImplementedError:
			pass # we don't know

		self._update_page(page)

	def indexpage(self, page):
		# check if path exists, if not call insert, else call update
		pass


	def _update_page(self, page, record):
		'''Like insert, but re-use existing record'''

	def _update_links(self, page):
		# do not care about double checking all links
		# drop all links and insert new set
		pass

	def _drop_page(self, path):
		'''Drop page plus sub-pages plus forward links'''
		# TODO ...
		if path.haschildren:
			self._drop_pagelist(path)


	def lookup_path(self, path, parent=None):
		'''Returns an IndexPath for path. This method is mostly intended
		for internal use only, but can be used by other modules in
		some cases to optimize repeated index lookups. If a parent IndexPath
		is known this can be given to speed up the lookup.
		'''
		# Constructs the indexpath downward
		if isinstance(path, IndexPath):
			return path

		indexpath = []
		if parent and not parent.isroot:
			indexpath.extend(parent._indexpath)
		elif hasattr(path, '_indexpath'):
			# Page objects copy the _indexpath attribute
			indexpath.extend(path._indexpath)

		names = path.name.split(':')
		if indexpath:
			names = names[len(indexpath):] # shift X items
			parentid = indexpath[-1]
		else:
			parentid = 0

		cursor = self.db.cursor()
		if not names: # len(indexpath) was len(names)
			cursor.execute('select * from pages where id==?', (indexpath[-1],))
			row = cursor.fetchone()
		else:
			for name in names:
				cursor.execute(
					'select * from pages where basename==? and parent==?',
					(name, parentid) )
				row = cursor.fetchone()
				if row is None:
					return None # path is not indexed
				indexpath.append(row['id'])
				parentid = row['id']

		return IndexPath(path.name, indexpath, row)

	def lookup_id(self, id):
		'''Returns an IndexPath for an index id'''
		# Constructs the indexpath upwards
		cursor = self.db.cursor()
		cursor.execute('select * from pages where id==?', (id,))
		row = cursor.fetchone()
		if row is None:
			return None # no such id !?

		indexpath = [row['id']]
		names = [row['basename']]
		parent = row['parent']
		while parent != 0:
			indexpath.insert(0, parent)
			cursor.execute('select basename, parent from pages where id==?', (parent,))
			row = cursor.fetchone()
			names.insert(0, row['basename'])
			parent = row['parent']

		return IndexPath(':'.join(names), indexpath, row)

	def resolve_case(self, name, namespace=None):
		'''Construct an IndexPath or Path by doing a case insensitive lookups
		for pages matching these name. If the full sub-page is found an
		IndexPath is returned. If at least the first part of the name is found
		an a Path is returned with the part that was found in the correct case
		and the remaining parts in the original case. If no match is found at
		all None is returned. If a parent namespace is given, the page name is
		resolved as a (indirect) sub-page of that path while assuming the case
		of the parent path is correct.
		'''
		if namespace and not namespace.isroot:
			parent = self.lookup_path(namespace)
			if parent is None:
				return None # parent does not even exist
			else:
				parentid = parent.id
				indexpath = list(parent._indexpath)
		else:
			parent = Path(':')
			parentid = 0
			indexpath = []

		names = name.split(':')
		found = []
		cursor = self.db.cursor()
		for name in names:
			cursor.execute(
				'select * from pages where lower(basename)==lower(?) and parent==?',
				(name, parentid) )
			rows = {}
			for row in cursor.fetchall():
				rows[row['basename']] = row

			if not rows:
				# path is not indexed
				if found: # but at least we found some match
					found.extend(names[len(found):]) # pad remaining names
					if not parent.isroot: found.insert(0, parent.name)
					return Path(':'.join(found))
					# FIXME should we include an indexpath here ?
				else:
					return None
			elif name in rows: # exact match
				row = rows[name]
			else: # take first insensitive match based on sorting
				n = rows.keys()
				n.sort()
				row = rows[n[0]]

			indexpath.append(row['id'])
			parentid = row['id']
			found.append(row['basename'])

		if not parent.isroot: found.insert(0, parent.name)
		return IndexPath(':'.join(found), indexpath, row)

	def list_pages(self, path):
		'''Returns a list of IndexPath objects for the sub-pages of 'path', or,
		if no path is given for the root namespace of the notebook.
		'''
		if path is None or path.isroot:
			parentid = 0
			name = ''
			indexpath = ()
		else:
			path = self.lookup_path(path)
			if path is None:
				return []
			parentid = path.id
			name = path.name
			indexpath = path._indexpath

		cursor = self.db.cursor()
		cursor.execute('select * from pages where parent==?', (parentid,))
		return [
			IndexPath(name+':'+r['basename'], indexpath+(r['id'],), r)
				for r in cursor ]

	def list_links(self, page, direction=LINK_DIR_FORWARD):
		return []
		# select name from join pages and links where drain = ?

	def get_previous(self, page):
		'''FIXME Like Namespace.get_previous(page), but crosses namespace bounds'''

	def get_next(self, page):
		'''FIXME Like Namespace.get_next(page), but crosses namespace bounds'''

	def on_save_page(self, page):
		pass

	def on_move_page(self, page):
		pass

	def on_delete_page(self, page):
		self._drop_page(page)
