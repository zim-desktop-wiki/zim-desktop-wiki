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
import gobject
import logging

from zim.notebook import Path, Link

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
	href INTEGER,
	type INTEGER
);
create table if not exists linktypes (
	id INTEGER PRIMARY KEY,
	label TEXT
);
'''

# TODO first index all namespaces before indexing pages
# else we can not resolve links properly - probably need two queues...

# TODO need better support for TreePaths, e.g. as signal arguments for Treemodel

class IndexPath(Path):
	'''Like Path but adds more attributes, functions as an iterator for
	rows in the table with pages.'''

	__slots__ = ('_indexpath', '_row', '_pagelist_ref', '_pagelist_index')

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
		self._pagelist_ref = None
		self._pagelist_index = None
		# The pagelist attributes are not used in this module, but the
		# slot is reserved for usage in the PageTreeStore class to cache
		# a pagelist instead of doing the same query over and over again.

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


class Index(gobject.GObject):
	'''FIXME'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'page-inserted': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'page-updated': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'page-haschildren-toggled': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'page-deleted': (gobject.SIGNAL_RUN_LAST, None, (object,))
	}

	def __init__(self, notebook=None, dbfile=None):
		'''If no dbfile is given, the default file for this notebook will be
		used will be used. Main use of providing a dbfile here is to make the
		index operate in memory by setting dbfile to ":memory:".
		'''
		gobject.GObject.__init__(self)
		self.dbfile = dbfile
		self.db = None
		self.notebook = None
		self._updating= False
		self._update_queue = []
		if self.dbfile:
			self._connect()
		if notebook:
			self.set_notebook(notebook)

	def set_notebook(self, notebook):
		self.notebook = notebook

		if not self.dbfile:
			# TODO index for RO notebooks
			#~ if notebook.isreadonly \
			#~ and not notebook.dir is None \
			#~ and notebook.dir.file('index.db').exists():
				#~ self.dbfile = notebook.dir.file('index.db')
			#~ else:
			if notebook.cache_dir is None:
				logger.debug('No cache dir found - loading index in memory')
				self.dbfile = ':memory:'
			else:
				notebook.cache_dir.touch()
				self.dbfile = notebook.cache_dir.file('index.db')
				logger.debug('Index database file: %s', self.dbfile)
			self._connect()

		# TODO connect to notebook signals for pages being moved / deleted /
		# modified

	def do_save_page(self, page):
		self.index_page(page)

	def do_move_page(self, page):
		pass # TODO index logic for moving page(s)

	def _connect(self):
		self.db = sqlite3.connect(
			str(self.dbfile), detect_types=sqlite3.PARSE_DECLTYPES)
		self.db.row_factory = sqlite3.Row

		# TODO verify database integrity and zim version number
		self.db.executescript(SQL_TABLES)

	def update(self, path=None,
		recursive=True, background=False, fullcheck=False,
		callback=None
	):
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

		A callback method can be supplied that will be called after each
		updated path. This can be used e.g. to display a progress bar. the
		callback gets two arguments, the first is the path just processed,
		the second the queue of paths to be updated.

		Indexes are checked width first. This is important to make the visual
		behavior of treeviews displaying the index look more solid.
		'''
		if path is None or path.isroot:
			indexpath = IndexPath(':', (0,))
		else:
			indexpath = self.lookup_path(path)
			if indexpath is None:
				indexpath = self._touch(path)

		self._update_queue.append((indexpath, recursive, fullcheck))

		if background:
			if not self._updating:
				logger.debug('Starting background index update')
				self._updating = False
				gobject.idle_add(self._do_update, callback)
		else:
			logger.debug('Updating index')
			while self._do_update(callback):
				continue

	def _do_update(self, callback):
		# This method needs to return boolean because it is
		# called as an idle event handler
		if self._update_queue:
			path = self._update_queue[0][0]
			self._update()
			if not callback is None:
				callback(path, self._update_queue)
			return True
		else:
			logger.debug('Background index update done')
			self._updating = False
			return False

	def _touch(self, path):
		'''This creates a path along with all it's parents'''
		try:
			cursor = self.db.cursor()
			names = path.split()
			parentid = 0
			indexpath = []
			inserted = []
			for i in range(len(names)):
				p = self.lookup_path()
				if p is None:
					haschildren = i < (len(names) - 1)
					cursor.execute(
						'insert into pages(basename, parent, hascontent, haschildren) values (?, ?, ?, ?)',
						(names[i], parentid, False, haschildren))
					parentid = cursor.lastrowid
					indexpath.append(parentid)
					inserted.append(IndexPath(':'.join(names[:i+1]), indexpath))
				else:
					# TODO check if haschildren is correct, update and emit has-children-toggled if not
					parentid = p.id
					indexpath.append(parentid)

			self.db.commit()
		except:
			self.db.rollback()
			logger.warn('Got exception while touching %s', path)
		else:
			for path in inserted:
				self.emit('page-inserted', path)


	def _update(self):
		'''This method unshifts one instruction for the queue and processes
		it.
		'''
		path, recursive, fullcheck = self._update_queue.pop(0)

		# TODO implement fullcheck for page contents
		if fullcheck:
			uptodate = False
			#~ try:
				#~ current = self.notebook.get_page_indexkey(path)
				#~ if current and path.indexkey == current:
					#~ uptodate = True
			#~ except NotImplementedError:
				#~ pass # we don't know
			if not uptodate:
				page = self.notebook.get_page(path)
				self.index_page(page)

		# TODO check index keys to optimize updating
		#~ current = None
		#~ try:
			#~ current = self.notebook.get_pagelist_indexkey(path)
			#~ if path.indexkey == current:
				#~ return True
		#~ except NotImplementedError:
			#~ pass # we don't know, so re-index

		# if we get here the cache was out of date or the pagelist does not
		# exist anymore - empty list must result in deleting all sub-pages
		try:
			cursor = self.db.cursor()
			cursor.execute('select id, basename from pages where parent==?', (path.id,))
			rows = cursor.fetchall()
			cleanup = set([r['basename'] for r in rows])

			# check for new pages
			seenchildren = False
			inserted = []
			for page in self.notebook.get_pagelist(path):
				seenchildren = True
				if page.basename in cleanup:
					cleanup.remove(page.basename)
				else:
					# We set haschildren to False untill we have actualy seen those
					# children. Failing to do so will cause trouble with the
					# gtk.TreeModel interface to the database, which can not handle
					# nodes that say they have children but fail to deliver when
					# asked.
					cursor = self.db.cursor()
					cursor.execute(
						'insert into pages(basename, parent, hascontent, haschildren) values (?, ?, ?, ?)',
						(page.basename, path.id, page.hascontent, False))
					indexpath = path._indexpath + (cursor.lastrowid,)
					inserted.append(IndexPath(page.name, indexpath))
					fullcheck = True # tree below does not yet exist - check fully

				if fullcheck or (recursive and page.haschildren):
					# FIXME get rid of this lookup_path()
					child = self.lookup_path(page, parent=path)
					assert not child is None
					self._update_queue.append((child, recursive, fullcheck))

			# cleanup remaining pages - TODO
			#~ for basename in cleanup:
				#~ self.do_delete_page(records[basename])

			# Update index key to reflect we did our updates - TODO
			#~ if not current is None:
				#~ self.db.execute(
					#~ 'update pages set childrenkey = ? where id == ?',
					#~ (path.id, current) )

			if path.isroot:
				self.db.commit()
			else:
				self.db.execute(
					'update pages set haschildren=? where id==?',
					(seenchildren, path.id) )
				self.db.commit()
		except:
			self.db.rollback()
			logger.warn('Get exception while indexing pagelist for %s', path)
		else:
			if not path.isroot:
				self.emit('page-haschildren-toggled', path)

			for path in inserted:
				self.emit('page-inserted', path)

	def index_page(self, page):
		'''Indexes page contents for page. Does not look at sub-pages etc.
		use 'update()' for that.
		'''
		print 'INDEX', page
		try:
			path = self.lookup_path(page)
			if path is None:
				path = self._touch(page)
			self.db.execute('delete from links where source == ?', (path.id,))
			for link in page.get_links():
				print 'LINK', link
				# TODO ignore links that are not internal
				href = self.notebook.resolve_path(link.href)
				print '>>', href
				if not href is None:
					href = self.lookup_path(href)
				if not href is None:
					print 'INSERT', href
					# TODO lookup href type
					self.db.execute('insert into links (source, href) values (?, ?)', (path.id, href.id))
			self.db.commit()
		except:
			self.db.rollback()
			logger.warn('Got exception while indexing page %s', path)
		else:
			self.emit('page-updated', path)

	def do_delete_page(self, path):
		'''Delete page plus sub-pages plus forward links from the index'''
		# TODO actually delete a page + children + links
		# TODO emit signal for deleted pages
		path = self.lookup_path(path)
		if path.haschildren:
			self._delete_pagelist(path)
		self.db.commit()
		self.emit('page-deleted', path)

	def walk(self, path=None):
		if path is None or path.isroot:
			return self._walk(IndexPath(':', (0,)), ())
		else:
			path = self.lookup_path(path)
			if path is None:
				raise ValueError
			return self._walk(path, path._indexpath)

	def _walk(self, path, indexpath):
		# Here path always is an IndexPath
		cursor = self.db.cursor()
		cursor.execute('select * from pages where parent == ?', (path.id,))
		for row in cursor:
			name = path.name+':'+row['basename']
			childpath = indexpath+(row['id'],)
			child = IndexPath(name, childpath, row)
			yield child
			if child.haschildren:
				for grandchild in self._walk(child, childpath):
					yield grandchild

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

	def list_links(self, path, direction=LINK_DIR_FORWARD):
		path = self.lookup_path(path)
		if path:
			cursor = self.db.cursor()
			if direction == LINK_DIR_FORWARD:
				cursor.execute('select * from links where source == ?', (path.id,))
			elif direction == LINK_DIR_BOTH:
				cursor.execute('select * from links where source == ? or href == ?', (path.id, path.id))
			else:
				cursor.execute('select * from links where href == ?', (path.id,))

			for link in cursor:
				if link['source'] == path.id:
					source = path
					href = self.lookup_id(link['href'])
				else:
					source = self.lookup_id(link['source'])
					href = path
				# TODO lookup type by id

				yield Link(source, href)

	def get_previous(self, path):
		'''Returns the next page in the index, crossing namespaces'''
		# TODO get_previous

	def get_next(self, path):
		'''Returns the next page in the index, crossing namespaces'''
		# TODO get_next


# Need to register classes defining gobject signals
gobject.type_register(Index)
