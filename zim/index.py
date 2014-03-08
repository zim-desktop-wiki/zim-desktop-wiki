# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains the L{Index} class which keeps an index of all
pages, links and backlinks in a notebook. This index is stored as a
SQLite database and allows efficient lookups of the notebook structure.
The L{IndexPath} class is used to refer to page L{Path}s in this index.


SQL Tables
==========

I{Explanation of the database layout - skip this section if you just
want to use the API of the L{Index} object}

The main SQL table is "B{pages}", which has an entry for each page in the
notebook. Rows in this table are linked hierarchicaly; each row only
has the basename of the page and a link to it's parent, do to construct
the whole page name multiple look ups are needed. Each entry in this
table is referred to by it's primary key. There is a special
L{IndexPath} class, which implements the L{Path} interface but also
keeps the primary keys for the page and it's parents. Re-using these
L{IndexPath} objects to lookup pages speeds up the look up of the
exact entries in the table. Main properties indexed int the "pages"
table are "hascontent" and "haschildren" which are boolean flags to
signal if the page has actual text content and whether it has child
pages or not.

The table "B{links}" keeps track of links between pages. Each row in this
table refers two ids in the "pages" table. This means that even when
the linked page does not exist, it does need to exist in the "pages"
table. Such link targets that do not exist will show up in the "pages"
table with both "hascontent" and "haschildren" set to C{False}. Such
entries in the index are also referred to as 'placeholders' (in the
L{PageIndex} widget they will show up grey and italic). Since
the "pages" table is hierarchical, any parent of a placeholder also
needs to be created in the table.

The tables "B{tags}" and "B{tagsources}" maintain a list of tags in each
page. Here "tags" has a list of tags that are used in this notebook
and "tagsources" links between tag ids and page ids for pages containing
the tag. In the API tags are represented by L{IndexTag} objects.

The database also stores the version number of the zim version that
created it. After upgrading to a new version the database will
automatically be flushed. Thus modifications to this module will be
transparent as long as the zim version number is updated. This and
other properties are stored in the "B{meta}" table, which is mapped by
the C{index.properties} attribute.

( The remaining tables "B{pagetypes}" and "B{linktypes}" are reserved for
future use to assign a "type" property to pages and links. )

For documentation of the database API, see the C{sqlite3} module in the
standard Python library.

Plugins
=======

Plugins can add additional tables to the database. For example the
"tasklist" plugin indexes the tasks found in each page and puts them
in a separate table. It uses the the 'intialize-db', 'index-page' and
'page-deleted' signals to create and maintain it's own table.

See the "tasklist" plugin for an example.


@todo: Add page types and link types
@todo: start caching ctime and mtime for all pages
'''

# Note that it is important that this module fires signals and list
# pages in a consistent order, if the order is not consistent or changes
# without the appropriate signals the pageindex widget will get confused
# and mess up.

# This module has a number of methods that appear as a private version
# doing all the work and a public one of the same name just wrapping
# the private one with a db commit. This is done to minimize the number
# of commits per action. SQLite is optimized for low number of commits
# and doing many of them will hurt performance, especially on systems
# with a slow harddisk (e.g. the flash drive in a maemo system).


from __future__ import with_statement

import sqlite3
import gobject
import unicodedata
import logging

import zim
from zim.utils import natural_sort_key, natural_sort
from zim.notebook import Path, Link, PageNameError

logger = logging.getLogger('zim.index')

LINK_DIR_FORWARD = 1 #: Constant for forward links
LINK_DIR_BACKWARD = 2 #: Constant for backward links
LINK_DIR_BOTH = 3 #: Constant for links in any direction

ROOT_ID = 1 #: Constant for the ID of the root namespace in "pages"
			# (Primary key starts count at 1 and first entry will be root)

#: Definition of all the SQL tables used by the L{Index} object
SQL_CREATE_TABLES = '''
create table if not exists meta (
	key TEXT,
	value TEXT
);
create table if not exists pages (
	id INTEGER PRIMARY KEY,
	basename TEXT,
	sortkey TEXT,
	parent INTEGER DEFAULT '0',
	hascontent BOOLEAN,
	haschildren BOOLEAN,
	type INTEGER,
	ctime TIMESTAMP,
	mtime TIMESTAMP,
	contentkey FLOAT,
	childrenkey FLOAT
);
create table if not exists pagetypes (
	id INTEGER PRIMARY KEY,
	label TEXT
);
create table if not exists links (
	source INTEGER,
	href INTEGER,
	type INTEGER,
	CONSTRAINT uc_LinkOnce UNIQUE (source, href, type)
);
create table if not exists linktypes (
	id INTEGER PRIMARY KEY,
	label TEXT
);
create table if not exists tags (
	id INTEGER PRIMARY KEY,
	name TEXT,
	sortkey TEXT
);
create table if not exists tagsources (
	source INTEGER,
	tag INTEGER,
	CONSTRAINT uc_TagOnce UNIQUE (source, tag)
);
create table if not exists propertynames (
	id INTEGER PRIMARY KEY,
	name TEXT,
	CONSTRAINT uc_PropertyNameOnce UNIQUE (name)
);
create table if not exists properties (
	page INTEGER,
	property INTEGER,
	value TEXT,
	CONSTRAINT uc_PropertyOnce UNIQUE (page, property, value)
);
'''

# TODO need a verify_path that works like lookup_path but adds checks when path
# already has a indexpath attribute, e.g. check basename and parent id
# Otherwise we might be re-using stale data. Also check copying of
# _indexpath in notebook.Path

# FIXME, the idea to have some index paths with and some without data
# was a really bad idea. Need to clean up the code as this is / will be
# a source of obscure bugs. Remove or replace lookup_data().

# Note on "ORDER BY": we use the sortkey property (which is set using
# natural_sort_key()), but we also sort on the real name as 2nd column.
# The reason is that the sort keys produced by natural_sort_key() are
# not case sensitive, and we want stable behavior if two sort keys
# are the same, while the actual names are not.


class IndexPath(Path):
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
	@ivar type: page type (currently unused)
	@ivar ctime: creation time of the page (currently unused)
	@ivar mtime: modification time of the page (currently unused)
	@ivar contentkey: caching key as provided by the store on last index
	@ivar childrenkey: caching key as provided by the store on last index
	@ivar id: page id in the SQL table (primary key for this page)
	@ivar parentid: page id for the parent page
	@ivar hasdata: C{True} when this object has all data from the table
	(when C{False} only a limitted number of attributes is set)

	@todo: Remove need for "hasdata: attribute for IndexPath - either
	by adding an additional class with light version or by removing
	places where an IndexPath is constructed without a row
	'''

	__slots__ = ('_indexpath', '_row')

	_attrib = (
		'basename',
		'parent',
		'hascontent',
		'haschildren',
		'type',
		'ctime',
		'mtime',
		'contentkey',
		'childrenkey',
	)

	def __init__(self, name, indexpath, row=None):
		'''Constructor

		@param name: the full page name
		@param indexpath: a tuple of page ids for all the parents of
		this page and it's own page id (so linking all rows in the
		page hierarchy for this page)
		@param row: optional sqlite3.Row for row for this page in the
		"pages" table, specifies most other attributes for this object
		The property C{hasdata} is C{True} when the row is set.
		'''
		Path.__init__(self, name)
		self._indexpath = tuple(indexpath)
		self._row = row

	@property
	def id(self): return self._indexpath[-1]

	@property
	def parentid(self):
		if self._indexpath and len(self._indexpath) > 1:
			return self._indexpath[-2]
		else:
			assert self.isroot, 'BUG: only root entry can have top level indexpath'
			return None

	@property
	def hasdata(self): return not self._row is None

	def __getattr__(self, attr):
		if not attr in self._attrib:
			raise AttributeError, '%s has no attribute %s' % (self.__repr__(), attr)
		elif self._row is None:
			raise AttributeError, 'This IndexPath does not contain row data'
		else:
			return self._row[attr]

	def exists(self):
		return self.haschildren or self.hascontent

	@property
	def parent(self):
		'''Returns IndexPath for parent path'''
		namespace = self.namespace
		if namespace:
			return IndexPath(namespace, self._indexpath[:-1])
		elif self.isroot:
			return None
		else:
			return IndexPath(':', (ROOT_ID,))

	def parents(self):
		'''Generator function for parent namespace IndexPaths including root'''
		# version optimized to include indexpaths
		if ':' in self.name:
			path = self.name.split(':')
			path.pop()
			while len(path) > 0:
				namespace = ':'.join(path)
				indexpath = self._indexpath[:len(path)+1]
				yield IndexPath(namespace, indexpath)
				path.pop()
		yield IndexPath(':', (ROOT_ID,))


class IndexTag(object):
	'''Object to represent a page tag in the L{Index} API

	These are tags that appear in pages with an "@", like "@foo". They
	are indexed by the L{Index} and represented with this class.

	@ivar name: the name of the tag, e.g. "foo" for an "@foo" in the page
	@ivar id: the id of this tag in the table (primary key)
	'''

	__slots__ = ('name', 'id')

	def __init__(self, name, id):
		self.name = name.lstrip('@')
		self.id = id

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



class DBCommitContext(object):
	'''Context manager to manage database commits.
	Used for the L{index.db_commit<Index.db_commit>} attribute. Using
	this attribute allows syntax like::

		with index.db_commit:
			cursor = index.db.cursor()
			cursor.execute(...)

	instead off::

		try:
			cursor = index.db.cursor()
			cursor.execute(...)
		except:
			index.db.rollback()
		else:
			index.db.commit()
	'''

	def __init__(self, db):
		self.db = db

	def __enter__(self):
		pass

	def __exit__(self, exc_type, exc_value, traceback):
		if exc_value:
			self.db.rollback()
		else:
			self.db.commit()

		return False # re-raise error


class Index(gobject.GObject):
	'''This class defines an index of all pages, links, backlinks, tags
	etc. in a notebook. This index is stored as a SQLite database and
	allows efficient lookups of the notebook structure. See te module
	documentation for some notes on the SQL layout.

	@ivar dbfile: the L{File} object for the database file, or the
	string "C{:memory:}" when we run the database in memory
	@ivar db: the C{sqlite3.Connection} object for the database
	@ivar db_commit: a L{DBCommitContext} object
	@ivar notebook: the L{Notebook} which is indexed by this Index
	@ivar properties: a L{PropertiesDict} with properties for this
	index
	@ivar updating: C{True} when an update of the index is in
	progress

	@signal: C{start-update ()}: emitted when an index update starts
	@signal: C{end-update ()}: emitted when an index update ends
	@signal: C{initialize-db ()}: emitted when we (re-)initialize the
	database tables. When this signal is emitted either the database is
	new or all tables have been dropped. E.g. a plugin could add a
	handler to create it's custom tables on this signal.

	@signal: C{page-inserted (L{IndexPath})}: emitted when a page is newly
	added to the index (so a new row is inserted in the pages table)
	@signal: C{page-updated (L{IndexPath})}: page content has changed
	@signal: C{page-indexed (L{IndexPath}, L{Page})}: emitted after a
	page has been indexed by the index. This signal is intended for
	example for plugins that want to do some additional indexing.
	@signal: C{page-haschildren-toggled (L{IndexPath})}: the value of the
	C{haschildren} attribute changed for this page
	@signal: C{page-deleted (L{IndexPath})}: emitted after a page has been
	droppen from the index (note that it does no longer exist, so any
	lookups will fail -- use page-to-be-deleted) when you want to get
	a signal before the row is actually dropped
	@signal: C{page-to-be-deleted (L{IndexPath})}: like page-deleted but
	emitted before the data is actually dropped

	@signal: C{tag-created (L{IndexTag})}: emitted when a new tag has been
	created (so first time a cerain tag is encountered in the notebook)
	@signal: C{tag-inserted (L{IndexTag}, L{IndexPath}, firsttag)}:
	emitted when a reference between a tag and a page is inserted in the
	index. The 3rd argument is C{True} when this is the first tag
	for this page.
	@signal: C{tag-to-be-inserted (L{IndexTag}, L{IndexPath}, firsttag)}:
	like tag-inserted but emitted before adding the data in the database
	@signal: C{tag-removed (L{IndexTag}, L{IndexPath}, lasttag)}:
	emitted when a reference between a page and a tag is removed. The
	3rd argument is C{True} when this was the last tag for this page
	@signal: C{tag-to-be-removed (L{IndexTag}, L{IndexPath}, lasttag)}:
	like tag-removed but emitted before dropping the data
	@signal: C{tag-deleted (L{IndexTag})}: emitted when a tag is no longer
	used in a notebook
	@signal: C{tag-to-be-deleted (L{IndexTag})}: like tag-deleted, but
	emitted before the data is dropped from the table

	@todo: rename page-deleted to page-dropped to have more consistent
	signal names
	@todo: check need for tag-to-be-inserted and tag-to-be-removed
	signals in the API (and check tag signal names in general)
	@todo: group API documentation in meaningfull groups, e.g.
	methods related to pages, links and tags
	'''

	# Resolving links depends on the contents of the database and
	# links to non-existing pages can create new page nodes. This has
	# consequences for updating the database and makes things a bit
	# more complicated than expected at first sight. Page nodes for
	# non-existing page are referred to as 'placeholders' below.
	#
	# 1) When updating we first traverse the whole page tree creating
	#    nodes for all existing pages before indexing contents and links
	# 2) When we do index the contents we need to go top down through
	#    the tree, indexing parent nodes before we index children. This is
	#    because resolving links goes bottom up and may see non-existing
	#    pages created based on a link in a parent.
	# 3) We need to clean up trees of placeholders by checking if they
	#    have pages linking to them or not. This needs to go bottom up as
	#    there may be non-existing parent pages that also need to be
	#    cleaned up.
	#
	# TODO TODO TODO - finish this thought and check correctness of this blob

	# Note that queues tend to become very large, so make sure to only
	# put Paths in the queue, not Pages

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'page-inserted': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'page-updated': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'page-indexed': (gobject.SIGNAL_RUN_LAST, None, (object, object)),
		'page-haschildren-toggled': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'page-deleted': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'page-to-be-deleted': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'start-update': (gobject.SIGNAL_RUN_LAST, None, ()),
		'end-update': (gobject.SIGNAL_RUN_LAST, None, ()),
		'initialize-db': (gobject.SIGNAL_RUN_LAST, None, ()),
		'tag-created': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'tag-inserted': (gobject.SIGNAL_RUN_LAST, None, (object, object, object)),
		'tag-to-be-inserted': (gobject.SIGNAL_RUN_LAST, None, (object, object, object)),
		'tag-removed': (gobject.SIGNAL_RUN_LAST, None, (object, object, object)),
		'tag-to-be-removed': (gobject.SIGNAL_RUN_LAST, None, (object, object, object)),
		'tag-deleted': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'tag-to-be-deleted': (gobject.SIGNAL_RUN_LAST, None, (object,)),
	}

	def __init__(self, notebook=None, dbfile=None):
		'''Constructor

		@param notebook: a L{Notebook} object
		@param dbfile: a L{File} object for the database file or
		the special string "C{:memory:}". When set to C{None} the index
		will fall back to the default database file for the notebook.
		'''
		gobject.GObject.__init__(self)
		self.dbfile = dbfile
		self.db = None
		self.db_commit = None
		self.notebook = None
		self.properties = None
		self.updating = False
		self._idle_signal_id = None
		self._update_pagelist_queue = []
		self._index_page_queue = []
		if self.dbfile:
			self._connect()
		if notebook:
			self.set_notebook(notebook)

	def set_notebook(self, notebook):
		'''Set the notebook to index. Connects to various signals of
		the notebook to trigger indexing when pages change etc.

		@param notebook: a L{Notebook} object
		'''
		self.notebook = notebook

		if not self.dbfile:
			if notebook.cache_dir is None:
				logger.debug('No cache dir found - loading index in memory')
				self.dbfile = ':memory:'
			else:
				notebook.cache_dir.touch()
				self.dbfile = notebook.cache_dir.file('index.db')
				logger.debug('Index database file: %s', self.dbfile)
			self._connect()

		def on_page_moved(o, oldpath, newpath, update_links):
			# When we are the primary index and the notebook is also
			# updating links, these calls are already done by the
			# notebook directly.
			#~ print '!! on_page_moved', oldpath, newpath, update_links
			self.delete(oldpath)
			self.update_async(newpath)

		def on_page_updated(o, page):
			indexpath = self.lookup_path(page)
			with self.db_commit:
				if not indexpath:
					indexpath = self._touch(page)
				links = self._get_placeholders(indexpath, recurs=False)
				self._index_page(indexpath, page)
				for link in links:
					self._cleanup(link)

		self.notebook.connect('stored-page', on_page_updated)
		self.notebook.connect('moved-page', on_page_moved)
		self.notebook.connect_object('deleted-page', self.__class__.delete, self)

	def _connect(self):
		self.db = sqlite3.connect(
			str(self.dbfile), detect_types=sqlite3.PARSE_DECLTYPES)
		self.db.row_factory = sqlite3.Row
		self.db_commit = DBCommitContext(self.db)

		self.properties = PropertiesDict(self.db)
		with self.db_commit:
			if self.properties['zim_version'] != zim.__version__:
				# flush content and init database layout
				self._flush()
				self.properties._set('zim_version', zim.__version__)

	def do_initialize_db(self):
		with self.db_commit:
			self.db.executescript(SQL_CREATE_TABLES)

	def flush(self):
		'''Flush all indexed data and clear the database

		This method drops all tables in the databse and then re-creates
		the tables used by the index.

		@note: This method does not emit proper signals for deleting
		content, so it is not safe to use while a L{PageTreeStore}
		is connected to the index unless the store is discarded after
		the flush.

		@emits: initialize-db
		'''
		with self.db_commit:
			self._flush()

	def _flush(self):
		logger.info('Flushing index')

		# Drop queues
		self._update_pagelist_queue = []
		self._index_page_queue = []

		# Drop data
		cursor = self.db.cursor()
		cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
		for table in [row[0] for row in cursor.fetchall()]:
			cursor.execute('DROP TABLE "%s"' % table)
		self.emit('initialize-db')

		# Create root node
		cursor.execute('insert into pages(basename, sortkey, parent, hascontent, haschildren) values (?, ?, ?, ?, ?)', ('', '', 0, False, False))
		assert cursor.lastrowid == 1, 'BUG: Primary key should start counting at 1'

		# Set meta properties
		self.properties._set('zim_version', zim.__version__)

	def _flush_queue(self, path):
		# Removes any pending updates for path and it's children
		name = path.name
		namespace = name + ':'
		keep = lambda p: not (p.name == name or p.name.startswith(namespace))
		self._update_pagelist_queue = filter(keep, self._update_pagelist_queue)
		self._index_page_queue = filter(keep, self._index_page_queue)

	def update(self, path=None, callback=None):
		'''Update the index by scanning the notebook

		Typically an (async) update is run at least once after opening
		a notebook to detect any manual changes etc. to the notebook.

		Indexes are checked width first. This is important to make the
		visual behavior of treeviews displaying the index look more
		solid. The update is done by checking the X{indexkey} each path
		as provided by the notebook store to decide if an update is
		needed.

		If you want to ignore the X{indexkey} and just re-index every
		page you need to call L{flush()} before calling C{update()}.
		This will have the same result as initialzing a brand new index.

		@keyword path: optional L{Path} to start update for a subtree
		only, if C{None} the whole notebook is indexed
		@keyword callback: optional callback function to be called for
		each path that is updated. 	The callback gets the path just
		processed as an argument. If the callback returns False the
		update will not continue. (This allows updating a progress bar
		and have a way to cancel the update from the dialog.)
		'''
		self._update(path, callback, False)

	def update_async(self, path=None, callback=None):
		'''Update the index by scanning the notebook asynchronous

		Like L{update()} but runs asynchronous

		@note: unlike most "C{*_async()}" methods we do not use
		threading here at the moment, instead the update is done on idle
		signals from the main loop.

		@keyword path: optional L{Path} to start update for a subtree only
		@keyword callback: optional callback function to be called for
		each path that is updated.
		'''
		self._update(path, callback, True)

	def _update(self, path, callback, async):
		# Updating uses two queues, one for indexing the tree structure and a
		# second for pages where we need to index the content. Reason is that we
		# first need to have the full tree before we can reliably resolve links
		# and thus index content.

		# TODO replace queues by invalidating indexkeys in the table

		if path is None:
			path = Path(':')

		indexpath = self.lookup_path(path)
		if indexpath is None:
			indexpath = self.touch(path)
			indexpath._row['haschildren'] = True
			indexpath._row['childrenkey'] = None

		self._flush_queue(path)
		self._update_pagelist_queue.append(indexpath)
		if not indexpath.isroot:
			self._index_page_queue.append(indexpath)
				# FIXME check indexkey here

		if not self.updating:
			self.emit('start-update')

		if async:
			if not self.updating:
				# Start new queue
				logger.info('Starting async index update')
				self.updating = True
				self._idle_signal_id = \
					gobject.idle_add(self._do_update, callback)
			# Else let running queue pick it up
		else:
			logger.info('Updating index')
			self._stop_background_signal() # just to be sure
			while self._do_update(callback):
				continue

	def ensure_update(self, callback=None):
		'''Wait for an ongoing asynchronous update.

		If an asynchronous update is running, this method will block
		untill it is finished and then return. If no update was ongoing
		it returns immediatly.

		@param callback: a callback function to call while updating,
		see L{update()} for details
		'''
		if self.updating:
			logger.info('Ensure index updated')
			self._stop_background_signal()
			while self._do_update(callback):
				continue
		else:
			return

	def stop_updating(self):
		'''Force asynchronous indexing to stop'''
		if self._update_pagelist_queue or self._index_page_queue:
			logger.info('Index update is canceled')
		# else natural end of index update, or just checking

		self._stop_background_signal()
		self._update_pagelist_queue = [] # flush
		self._index_page_queue = [] # flush

		if self.updating:
			self.emit('end-update')
			self.updating = False

	def _stop_background_signal(self):
		if self._idle_signal_id:
			gobject.source_remove(self._idle_signal_id)
			self._idle_signal_id = None


	def _do_update(self, callback):
		# This returns boolean to continue or not because it can be called as an
		# idle event handler, if a callback is used, the callback should give
		# this boolean value.
		# TODO can we add a percentage to the callback ?
		# set it to None while building page listings, but set
		# percentage once max of pageindex list is known
		if self._update_pagelist_queue or self._index_page_queue:
			try:
				if self._update_pagelist_queue:
					path = self._update_pagelist_queue.pop(0)
					with self.db_commit:
						self._update_pagelist(path)
				elif self._index_page_queue:
					path = self._index_page_queue.pop(0)
					page = self.notebook.get_page(path)
					with self.db_commit:
						self._index_page(path, page)
			except KeyboardInterrupt:
				raise
			except:
				# Catch any errors while listing & parsing all pages
				logger.exception('Got an exception while indexing "%s":', path)

			#~ print "\"%s\" %i %i" % (path.name, len(self._update_pagelist_queue), len(self._index_page_queue))
			if not callback is None:
				cont = callback(path)
				if not cont is True:
					self.stop_updating()
					return False
			return True
		else:
			try:
				self.cleanup_all()
			except KeyboardInterrupt:
				raise
			except:
				logger.exception('Got an exception while removing placeholders')
			logger.info('Index update done')
			self.stop_updating()
			return False

	def touch(self, path):
		'''Create an entry for a L{Path} in the index

		This method creates a path in the index along with all it's
		parents. The path is initally created as a palceholder which has
		neither content or children.

		@param path: a L{Path} object
		@returns: the L{IndexPath} object for C{path}
		'''
		with self.db_commit:
			return self._touch(path)

	def _touch(self, path):
		cursor = self.db.cursor()
		names = path.parts
		parentid = ROOT_ID
		indexpath = [ROOT_ID]
		inserted = [] # newly inserted paths
		lastparent = None # last parent that already existed
		for i in range(len(names)):
			p = self.lookup_path(Path(names[:i+1]))
			if p is None:
				haschildren = i < (len(names) - 1)
				cursor.execute(
					'insert into pages(basename, sortkey, parent, hascontent, haschildren) values (?, ?, ?, ?, ?)',
					(names[i], natural_sort_key(names[i]), parentid, False, haschildren))

				parentid = cursor.lastrowid
				indexpath.append(parentid)
				inserted.append(
					IndexPath(':'.join(names[:i+1]), indexpath,
						{'hascontent': False, 'haschildren': haschildren}))
			else:
				lastparent = p
				parentid = p.id
				indexpath.append(parentid)

		if lastparent and not lastparent.haschildren:
			self.db.execute('update pages set haschildren = ? where id = ?', (True, lastparent.id))
		else:
			lastparent = None

		if lastparent:
			self.emit('page-haschildren-toggled', lastparent)

		for path in inserted:
			self.emit('page-inserted', path)

		if inserted:
			return inserted[-1]
		else:
			return self.lookup_path(path)

	def _index_page(self, path, page):
		'''Indexes page contents for page.

		TODO: emit a signal for this for plugins to use
		'''
		# Avoid emitting page-updated here when not needed because it
		# triggers re-draws of the pageindex

		#~ print '!! INDEX PAGE', path, path._indexpath
		assert isinstance(path, IndexPath) and not path.isroot
		seen_links = set()

		hadcontent = path.hascontent

		had_tags = set()
		has_tags = set()

		created_tags = []

		# Initialize seen tags
		for tag in self.list_tags(path):
			had_tags.add(tag.id)

		self.db.execute('delete from links where source = ?', (path.id,))

		if page.hascontent:
			for type, href, _ in page.get_links():
				if type != 'page':
					continue

				try:
					link = self.notebook.resolve_path(
						href, source=page, index=self)
						# need to specify index=self here because we are
						# not necessary the default index for the notebook
				except PageNameError:
					continue

				if link != page and not link.name in seen_links:
					# Filter out self referring links and remove doubles
					seen_links.add(link.name)
					indexpath = self.lookup_path(link)
					if indexpath is None:
						indexpath = self._touch(link)

					self.db.execute(
						'insert into links (source, href) values (?, ?)',
						(path.id, indexpath.id) )

			for _, attrib in page.get_tags():
				tag = attrib['name'].strip()
				indextag = self.lookup_tag(tag)
				if indextag is None:
					# Create tag
					cursor = self.db.cursor()
					cursor.execute(
						'insert into tags(name, sortkey) values (?, ?)',
						(tag, natural_sort_key(tag))
					)
					indextag = IndexTag(tag, cursor.lastrowid)
					created_tags.append(indextag)
				has_tags.add(indextag.id)

		key = self.notebook.get_page_indexkey(page)
		self.db.execute(
			'update pages set hascontent = ?, contentkey = ? where id = ?',
			(page.hascontent, key, path.id) )

		# Insert tags
		for i, tag in enumerate(has_tags.difference(had_tags)):
			self.emit('tag-to-be-inserted', self.lookup_tagid(tag), path, (len(had_tags) == 0) and (i == 0))
			try:
				self.db.execute(
					'insert into tagsources (source, tag) values (?, ?)',
					(path.id, tag,))
			except sqlite3.IntegrityError:
				# Catch already existing entries
				pass

		# Remove tags
		removed_tags = had_tags.difference(has_tags)
		for i, tag in enumerate(removed_tags):
			self.emit('tag-to-be-removed', self.lookup_tagid(tag), path, (len(has_tags) == 0) and (i == len(removed_tags)-1))
			self.db.execute('delete from tagsources where source = ? and tag = ?', (path.id, tag))

		path = self.lookup_data(path) # refresh

		if hadcontent != path.hascontent:
			self.emit('page-updated', path)

		for tag in created_tags:
			self.emit('tag-created', tag)

		for i, tag in enumerate(has_tags.difference(had_tags)):
			self.emit('tag-inserted', self.lookup_tagid(tag), path, (len(had_tags) == 0) and (i == 0))

		for i, tag in enumerate(removed_tags):
			self.emit('tag-removed', tag, path, (len(has_tags) == 0) and (i == len(removed_tags)-1))

		self._purge_tag_table()

		#~ print '!! PAGE-INDEXED', path
		self.emit('page-indexed', path, page)

	def _purge_tag_table(self):
		deleted_tags = []
		cursor = self.db.cursor()
		cursor.execute('select id, name from tags where id not in (select tag from tagsources)')
		for row in cursor:
			deleted_tags.append(IndexTag(row['name'], row['id']))
			self.emit('tag-to-be-deleted', deleted_tags[-1])
		self.db.execute('delete from tags where id not in (select tag from tagsources)')

		for tag in deleted_tags:
			self.emit('tag-deleted', tag)

	def _update_pagelist(self, path):
		'''Checks and updates the pagelist for a path if needed and
		queue any child pages for updating.
		'''
		#~ print '!! UPDATE LIST', path, path._indexpath
		assert isinstance(path, IndexPath)
		if not path.hasdata:
			path = self.lookup_data(path)
		hadchildren = path.haschildren
		hadcontent = path.hascontent

		if path.isroot:
			rawpath = Path(':')
			hascontent = False
			indexpath = (ROOT_ID,)
		else:
			rawpath = self.notebook.get_page(path)
			hascontent = rawpath.hascontent
			indexpath = path._indexpath

		# Check if listing is uptodate

		def check_and_queue(child, page):
			# Helper function to queue individual children

			if (page and page.haschildren) or child.haschildren:
				self._update_pagelist_queue.append(child)
			else:
				pagekey = self.notebook.get_page_indexkey(page or child)
				if not (pagekey and child.contentkey == pagekey):
					self._index_page_queue.append(child)

		listkey = self.notebook.get_pagelist_indexkey(rawpath)
		uptodate = listkey and path.childrenkey == listkey

		cursor = self.db.cursor()
		cursor.execute('select * from pages where parent = ?', (path.id,))

		if uptodate:
			#~ print '!! ... is up to date'
			for row in cursor:
				p = IndexPath(path.name+':'+row['basename'], indexpath+(row['id'],), row)
				check_and_queue(p, None)
		else:
			#~ print '!! ... updating'
			children = {}
			for row in cursor:
				children[row['basename']] = row
			seen = set()
			changes = []

			for page in self.notebook.get_pagelist(rawpath):
				#~ print '!! ... ... page:', page, page.haschildren
				seen.add(page.basename)
				if page.basename in children:
					row = children[page.basename]
					if page.hascontent == row['hascontent']:
						child = IndexPath(path.name+':'+row['basename'], indexpath+(row['id'],), row)
						check_and_queue(child, page)
					else:
						# Child aquired content - let's index it
						cursor = self.db.cursor()
						cursor.execute(
							'update pages set hascontent = ?, contentkey = NULL where id = ?',
							(page.hascontent, row['id'],) )
						child = IndexPath(path.name+':'+row['basename'], indexpath+(row['id'],),
							{	'hascontent': page.hascontent,
								'haschildren': page.haschildren,
								'childrenkey': row['childrenkey'],
								'contentkey': None,
							} )
						changes.append((child, 2))
						if page.haschildren:
							self._update_pagelist_queue.append(child)
						if page.hascontent:
							self._index_page_queue.append(child)
				else:
					# We set haschildren to False until we have actually seen those
					# children. Failing to do so will cause trouble with the
					# gtk.TreeModel interface to the database, which can not handle
					# nodes that say they have children but fail to deliver when
					# asked.
					cursor = self.db.cursor()
					cursor.execute(
						'insert into pages(basename, sortkey, parent, hascontent, haschildren) values (?, ?, ?, ?, ?)',
						(page.basename, natural_sort_key(page.basename), path.id, page.hascontent, False))
					child = IndexPath(page.name, indexpath + (cursor.lastrowid,),
						{	'hascontent': page.hascontent,
							'haschildren': False,
							'childrenkey': None,
							'contentkey': None,
						} )
					changes.append((child, 1))
					if page.haschildren:
						self._update_pagelist_queue.append(child)
					if page.hascontent:
						self._index_page_queue.append(child)

			# Figure out which pages to delete - but keep placeholders
			keep = set()
			delete = []
			for basename in set(children.keys()).difference(seen):
				row = children[basename]
				child = IndexPath(
					path.name+':'+basename, indexpath+(row['id'],), row)
				if child.haschildren or self.n_list_links(child, direction=LINK_DIR_BACKWARD) > 0:
					keep.add(child)
					self.db.execute(
						'update pages set hascontent = 0, contentkey = NULL where id = ?', (child.id,))
						# If you're not in the pagelist, you don't have content
					changes.append((child, 2))
					if child.haschildren:
						self._update_pagelist_queue.append(child)
				else:
					delete.append(child)

			# Update index key to reflect we did our updates
			haschildren = len(seen) + len(keep) > 0
			self.db.execute(
				'update pages set childrenkey = ?, haschildren = ?, hascontent = ? where id = ?',
				(listkey, haschildren, hascontent, path.id) )

			path = self.lookup_data(path) # refresh
			if not path.isroot and (hadchildren != path.haschildren):
				self.emit('page-haschildren-toggled', path)

			if not path.isroot and (hadcontent != path.hascontent):
				self.emit('page-updated', path)

			# All these signals should come in proper order...
			natural_sort(changes, key=lambda c: c[0].basename)
			for child, action in changes:
				if action == 1:
					self.emit('page-inserted', child)
				else: # action == 2:
					self.emit('page-updated', child)

			# Clean up pages that disappeared
			for child in delete:
				self._delete(child)

			# ... we are followed by an cleanup_all() when indexing is done

	def delete(self, path):
		'''Delete a L{Path} from the index

		This will delete all data indexed from this page from the index.
		This means C{path} and all it's children will be flagged as
		having no content. However they may stay appear as placeholders
		in the index if they are linked by other pages.

		Removing a page can also trigger other page to be removed from
		the index. For example parents that have no children anymore
		will be cleaned up automatically, and placeholders that were
		kept alive because of links from this page as well.

		@param path: a L{Path} object
		'''
		indexpath = self.lookup_path(path)
		if indexpath:
			links = self._get_placeholders(indexpath, recurs=True)
			with self.db_commit:
				self._delete(indexpath)
				self._cleanup(indexpath.parent)
				for link in links:
					self._cleanup(link)

	def _delete(self, path):
		# Tries to delete path and all of it's children, but keeps
		# pages that are placeholders and their parents
		self._flush_queue(path)

		root = self.lookup_path(path)
		paths = [root]
		paths.extend(list(self.walk(root)))

		# Clean up links and content
		for path in paths:
			self.db.execute('delete from links where source = ?', (path.id,))
			self.db.execute('update pages set hascontent = 0, contentkey = NULL where id = ?', (path.id,))

		# Clean up tags
		for path in paths:
			tags = list(self.list_tags(path))
			for i, tag in enumerate(tags):
				self.emit('tag-to-be-removed', tag, path, i == len(tags) - 1)
				self.db.execute('delete from tagsources where source = ? and tag = ?', (path.id, tag.id))
			for i, tag in enumerate(tags):
				self.emit('tag-removed', tag, path, i == len(tags) - 1)

		# Clean up any nodes that are not a link
		paths.reverse() # process children first
		delete = []
		keep = []
		for path in paths:
			if path.isroot or not path.hasdata:
				continue
			hadchildren = path.haschildren
			haschildren = self.n_list_pages(path) > 0
			placeholder = haschildren or self.n_list_links(path, direction=LINK_DIR_BACKWARD)
			if placeholder:
				# Keep but check haschildren
				keep.append(path)
				self.db.execute(
					'update pages set haschildren = ?, childrenkey = NULL where id = ?',
					(haschildren, path.id) )
			else:
				# Delete
				self.emit('page-to-be-deleted', path) # HACK needed to signal the page index
				delete.append(path)
				self.db.execute('delete from pages where id=?', (path.id,))

			self.lookup_data(path) # refresh
			if placeholder:
				self.emit('page-updated', path)
				if hadchildren != haschildren:
					self.emit('page-haschildren-toggled', path)
			else:
				self.emit('page-deleted', path)

		parent = root.parent
		if not parent.isroot and self.n_list_pages(parent) == 0:
			self.db.execute(
				'update pages set haschildren = 0, childrenkey = NULL where id = ?',
				(parent.id,) )
			parent = self.lookup_data(parent)
			self.emit('page-haschildren-toggled', parent)

	def add_link(self, source, href, type=None):
		'''Add a link to the index. Intended to be used by plugins that
		can e.g. extract links from custom objects. Keep in mind that
		all links will be flushed the next time when the C{source} page
		is indexed.
		@param source: source L{Path}
		@param href: target L{Path}
		@param type: optional link type as string
		'''
		source = self.lookup_path(source)
		href = self.lookup_path(href) # TODO or placeholder !!
		if not (source and href):
			raise ValueError, 'No such path' # FIXME

		if type:
			typeid = self.lookup_linktype_id(type, create=True)
			self.db.execute(
				'insert into links (source, href, type) values (?, ?, ?)',
				(source.id, href.id, typeid) )
		else:
			self.db.execute(
				'insert into links (source, href) values (?, ?)',
				(source.id, href.id) )

	def add_property(self, page, property, value):
		'''Add a page property to the index. Intended to be used by
		plugins that can e.g. extract properties from custom objects.
		Keep in mind that all properties will be flushed the next time
		when the page is indexed.
		@param page: page L{Path}
		@param property: property name as string
		@param value: the property value
		'''
		path = self.lookup_path(page)
		if not path:
			raise ValueError, 'No such path: %s' % page

		propid = self.lookup_property_id(property, create=True)
		self.db.execute(
			'insert into properties (page, property, value) values (?, ?, ?)',
			(page.id, propid, value) )

		## TODO delete these again !

	def lookup_property_id(self, property, create=False):
		cursor = self.db.cursor()
		cursor.execute('select * from property where name = ?', (property.lower(),))
		row = cursor.fetchone()

	def cleanup(self, path):
		'''Check if a L{Path} can be removed from the index, and
		clean it up if so

		This method cleans up pages that have no content, no longer
		cruhave any children and are no longer linked by other pages.
		This is intended to cleanup (old) placeholders.

		@param path: a L{Path} object
		'''
		with self.db_commit:
			self._cleanup(path)

	def _cleanup(self, path):
		if path.isroot:
			return

		origpath = path
		path = self.lookup_path(path)
		if not path or not path.hasdata:
			# path does not exist in table - maybe it disappeared already
			self._cleanup(origpath.parent) # recurs
			return

		if not (path.hascontent or path.haschildren) \
		and self.n_list_links(path, direction=LINK_DIR_BACKWARD) == 0:
			self._delete(path)
			self._cleanup(path.parent) # recurs

	def cleanup_all(self):
		'''	Check for any L{Path}s that can be removed from the index,
		and clean them up

		Like L{cleanup()} but checks the whole index
		'''
		with self.db_commit:
			self._cleanup_all

	def _cleanup_all(self):
		cursor = self.db.cursor()
		cursor.execute(
			'select id from pages where hascontent=0 and haschildren=0')
		for row in cursor:
			path = self.lookup_id(row['id'])
			self._cleanup(path)

	def _get_placeholders(self, path, recurs):
		'''Return candidates for cleanup when path is updated or deleted'''
		ids = [path.id]
		if recurs:
			ids.extend(p.id for p in self.walk(path))
		placeholders = []
		cursor = self.db.cursor()
		for id in ids:
			cursor.execute(
				'select pages.id from pages inner join links on links.href=pages.id '
				'where links.source=? and pages.hascontent=0 and pages.haschildren=0',
				(id,))
			placeholders.extend(self.lookup_id(row['id']) for row in cursor)
		return placeholders

	def walk(self, path=None):
		'''Generator function to yield all pages in the index, depth
		first

		@param path: a L{Path} object for the starting point, can be
		used to only iterate a sub-tree. When this is C{None} the
		whole notebook is iterated over
		@returns: yields L{IndexPath} objects
		'''
		if path is None or path.isroot:
			return self._walk(IndexPath(':', (ROOT_ID,)), ())
		else:
			indexpath = self.lookup_path(path)
			if indexpath is None:
				raise ValueError, 'no such path in the index %s' % path
			return self._walk(indexpath, indexpath._indexpath)

	def _walk(self, path, indexpath):
		# Here path always is an IndexPath
		cursor = self.db.cursor()
		cursor.execute('select * from pages where parent = ? order by sortkey, basename', (path.id,))
		for row in cursor:
			name = path.name+':'+row['basename']
			childpath = indexpath+(row['id'],)
			child = IndexPath(name, childpath, row)
			yield child
			if child.haschildren:
				for grandchild in self._walk(child, childpath):
					yield grandchild

	def lookup_path(self, path, parent=None):
		'''Lookup the L{IndexPath} for a L{Path}, adding all the
		information from the database about the path.

		If the C{path} is an L{IndexPath} already, it will passed to
		L{lookup_data()} and then returned. So as long as it is passed
		a sub-class of L{Path} this method will always result in a
		proper L{IndexPath} object.

		This method is mostly intended for internal use in the index
		module, but in some cases it is useful to convert explicitly
		to L{IndexPath} to optimize repeated index lookups.

		@param path: the L{Path} object
		@param parent: any known parent L{IndexPath}, this will speed
		up the lookup by reducing the number of queries needed to
		reconstruct the hierarchical nesting of the path.
		@returns: the L{IndexPath} for C{path} or C{None} when this
		path does not exist in the index.
		'''
		# Constructs the indexpath downward
		if isinstance(path, IndexPath):
			if not path.hasdata:
				return self.lookup_data(path)
			else:
				return path
		elif path.isroot:
			cursor = self.db.cursor()
			cursor.execute('select * from pages where id = ?', (ROOT_ID,))
			row = cursor.fetchone()
			return IndexPath(':', (ROOT_ID,), row)

		if parent: indexpath = list(parent._indexpath)
		else:      indexpath = [ROOT_ID]

		names = path.name.split(':')
		names = names[len(indexpath)-1:] # shift X items
		parentid = indexpath[-1]

		cursor = self.db.cursor()
		if not names: # len(indexpath) was len(names)
			cursor.execute('select * from pages where id = ?', (indexpath[-1],))
			row = cursor.fetchone()
		else:
			for name in names:
				cursor.execute(
					'select * from pages where basename = ? and parent = ?',
					(name, parentid) )
				row = cursor.fetchone()
				if row is None:
					return None # path is not indexed
				indexpath.append(row['id'])
				parentid = row['id']

		return IndexPath(path.name, indexpath, row)

	def lookup_data(self, path):
		'''Returns a full IndexPath for a IndexPath that has 'hasdata'
		set to False.

		@todo: get rid of this method
		'''
		cursor = self.db.cursor()
		cursor.execute('select * from pages where id = ?', (path.id,))
		path._row = cursor.fetchone()
		#~ assert path._row, 'Path does not exist: %s' % path
		return path

	def lookup_id(self, id):
		'''Get the L{IndexPath} for a given page id

		Mainly intended for internal use, but can be used e.g by
		plugins that add their own tables refering to pages by id.

		@param id: the page id (primary key for this page)
		@returns: the L{IndexPath} for this row
		'''
		# Constructs the indexpath upwards
		cursor = self.db.cursor()
		cursor.execute('select * from pages where id = ?', (id,))
		row = cursor.fetchone()
		if row is None:
			return None # no such id !?

		indexpath = [row['id']]
		names = [row['basename']]
		parent = row['parent']
		while parent != 0:
			indexpath.insert(0, parent)
			cursor.execute('select basename, parent from pages where id = ?', (parent,))
			myrow = cursor.fetchone()
			names.insert(0, myrow['basename'])
			parent = myrow['parent']

		return IndexPath(':'.join(names), indexpath, row)

	def lookup_tag(self, tag):
		'''Get the L{IndexTag} for a tag name

		@param tag: the tag name as string or an L{IndexTag}
		@returns: the L{IndexTag} for C{tag} or C{None} if the tag does
		not exist in the notebook
		'''
		# Support 'None' as untagged
		assert not tag is None

		if isinstance(tag, IndexTag):
			return tag
		else:
			assert isinstance(tag, basestring)
			cursor = self.db.cursor()
			cursor.execute('select * from tags where name = ?', (tag,))
			row = cursor.fetchone()
			if row is None:
				return None # no such name
			return IndexTag(row['name'], row['id'])

	def lookup_tagid(self, id):
		'''Get the L{IndexTag} for a tag id

		@param id: the tag id (primary key in the "tags" table)
		@returns: the L{IndexTag} object for this id
		'''
		cursor = self.db.cursor()
		cursor.execute('select * from tags where id = ?', (id,))
		row = cursor.fetchone()
		if row is None:
			return None # no such id !?
		return IndexTag(row['name'], row['id'])

	def resolve_case(self, name, namespace=None):
		'''Resolves path names case insensitive for existing pages

		This method checks the parts of C{name} (separated by ":")
		in the index. If for any part an entry exists with the same
		case, this will be used, otherwise it will check for entries
		with the same name both different case and use the first one
		found. If no entry is found with the same name at all, the
		lookup will stop.

		If at least the first part of C{name} could be matched there
		is a partial match, and parts that can not be resolved will be
		kept in the same case as the given input.

		The purpose of this method is to help converting e.g. user input
		to proper L{Path} objects. By matching the case to the index
		the chance of duplicate pages with different case is reduced.

		@param name: the full page name, or a page name relative to
		{namespace}
		@param namespace: optional parent namespace for which the case
		is already known
		@returns: a L{Path} if a partial match was found, an
		L{IndexPath} if a full match was found, or C{None} when no
		match was found at all
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
			parentid = ROOT_ID
			indexpath = [ROOT_ID]

		names = name.split(':')
		found = []
		cursor = self.db.cursor()
		for name in names:
			cursor.execute(
				'select * from pages where sortkey = ? and parent = ?',
				(natural_sort_key(name), parentid) )
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
			elif unicodedata.normalize('NFC', name) in rows:
				name = unicodedata.normalize('NFC', name)
				row = rows[name]
			elif unicodedata.normalize('NFD', name) in rows:
				name = unicodedata.normalize('NFD', name)
				row = rows[name]
			else:
				# take first match based on sorting
				# case insensitive or unicode compatibility (NFKD / NFKC)
				n = rows.keys()
				n.sort()
				row = rows[n[0]]

			indexpath.append(row['id'])
			parentid = row['id']
			found.append(row['basename'])

		if not parent.isroot: found.insert(0, parent.name)
		return IndexPath(':'.join(found), indexpath, row)

	def get_page_index(self, path):
		'''Get the index where this path would appear in the result
		of L{list_pages()} for C{path.parent}. Used by the
		L{PageTreeStore} interface to get the gtk TreePath for a path.

		@param path: a L{Path} object
		@returns: the relative index for C{path} in the parent namespace
		(integer)
		'''
		if path.isroot:
			raise ValueError, 'Root path does not have an index number'

		path = self.lookup_path(path)
		if not path:
			raise ValueError, 'Could not find path in index'

		sortkey = natural_sort_key(path.basename)
		cursor = self.db.cursor()
		cursor.execute(
			'select count(*) from pages where parent = ? '
			'and (sortkey < ? or (sortkey = ? and basename < ?))',
			(path.parent.id, sortkey, sortkey, path.basename)
		)
		row = cursor.fetchone()
		return int(row[0])

	def list_pages(self, path, offset=None, limit=None):
		'''Generator function listing all pages in a specific namespace

		The optional arguments C{offset} and C{limit} can be used to
		iterate only a slice of the list. Note that both C{offset} and
		C{limit} must always be defined together.

		When C{path} does not exist in the index an empty list is yielded.

		@param path: a L{Path} object giving the namespace or C{None}
		for the top level pages
		@keyword offset: offset in list to start (integer)
		@keyword limit: max pages to return (integer)

		@returns: yields L{IndexPath} objects
		'''
		if path is None or path.isroot:
			parentid = ROOT_ID
			name = ''
			indexpath = (ROOT_ID,)
		else:
			path = self.lookup_path(path)
			if path:
				parentid = path.id
				name = path.name
				indexpath = path._indexpath
			else:
				parentid = None

		if parentid:
			cursor = self.db.cursor()
			query = 'select * from pages where parent = ? order by sortkey, basename'
			if offset is None and limit is None:
				cursor.execute(query, (parentid,))
			else:
				cursor.execute(query + ' limit ? offset ?', (parentid, limit, offset))

			for row in cursor:
				yield IndexPath(
						name+':'+row['basename'],
						indexpath+(row['id'],),
						row)

	def get_all_pages_index(self, path):
		'''Get the index where this path would appear in the result
		of L{list_all_pages()}. Used e.g. by the "tags" plugin to get
		the gtk TreePath for a path in the flat list.

		@param path: a L{Path} object
		@returns: the relative index for C{path} (integer)
		'''
		if path.isroot:
			raise ValueError, 'Root path does not have an index number'

		path = self.lookup_path(path)
		if not path:
			raise ValueError, 'Could not find path in index'

		# Can't use count() here, like in get_page_index(), because
		# basenames are not unique in this lookup
		# FIXME do this anyway - use sorting on id instead
		cursor = self.db.cursor()
		cursor.execute('select id from pages where id != ? order by sortkey, basename, id', (ROOT_ID,))
			# Added id to "order by" columns because basenames are not unique
		i = 0
		for row in cursor:
			if row['id'] == path.id: return i
			i += 1

		assert False, 'BUG: could not find path in index'

	def list_all_pages(self, offset=None, limit=None):
		'''Generator function listing all pages as a flat page list
		depth first

		The optional arguments C{offset} and C{limit} can be used to
		iterate only a slice of the list. Note that both C{offset} and
		C{limit} must always be defined together.

		@keyword offset: offset in list to start (integer)
		@keyword limit: max pages to return (integer)

		@returns: yields L{IndexPath} objects
		'''
		cursor = self.db.cursor()

		query = 'select id from pages where id != ? order by sortkey, basename, id'
			# Added id to "order by" columns because basenames are not unique
		if offset is None and limit is None:
			cursor.execute(query, (ROOT_ID,))
		else:
			cursor.execute(query + ' limit ? offset ?', (ROOT_ID, limit, offset))

		for row in cursor:
			yield self.lookup_id(row['id'])

	def n_list_pages(self, path):
		'''Get the number of pages that will be returned by
		L{list_pages()} for C{path}. Used by the C{PageTreeStore}
		interface.

		@param path: a L{Path} object giving the namespace or C{None}
		for the top level pages
		@returns: the number of child pages below C{path}
		'''
		if path is None or path.isroot:
			parentid = ROOT_ID
		else:
			path = self.lookup_path(path)
			if path is None:
				return 0
			parentid = path.id
		cursor = self.db.cursor()
		cursor.execute('select count(*) from pages where parent = ?', (parentid,))
		row = cursor.fetchone()
		return int(row[0])

	def n_list_all_pages(self):
		'''Get the number of pages that will be returned by
		L{list_all_pages()}

		@returns: the number of pages in the notebook
		'''
		cursor = self.db.cursor()
		cursor.execute('select count(*) from pages')
		row = cursor.fetchone()
		return int(row[0]) - 1 # subtract 1 for the ROOT_ID row

	def list_recent_pages(self, offset=None, limit=None):
		'''List pages in order of modification time, newest first'''
		# HACK using contentkey rather than actual mtime field !
		query = 'select * from pages where hascontent = 1 order by contentkey desc'
		cursor = self.db.cursor()
		if offset is None and limit is None:
			cursor.execute(query)
		else:
			assert limit is not None and offset is not None
			cursor.execute(query + ' limit ? offset ?', (limit, offset))

		for row in cursor:
			yield self.lookup_id(row['id'])

	def list_links(self, path, direction=LINK_DIR_FORWARD):
		'''Generator listing links between pages

		@param path: the L{Path} for which to list links
		@param direction: the link direction to be listed. This can be
		one of:
			- C{LINK_DIR_FORWARD}: for links from path
			- C{LINK_DIR_BACKWARD}: for links to path
			- C{LINK_DIR_FORWARD}: for links from and to path
		@returns: yields L{Link} objects or empty list if path does not
		exist or no links are found
		'''
		path = self.lookup_path(path)
		if path:
			cursor = self.db.cursor()
			if direction == LINK_DIR_FORWARD:
				cursor.execute('select * from links where source = ?', (path.id,))
			elif direction == LINK_DIR_BOTH:
				cursor.execute('select * from links where source = ? or href = ?', (path.id, path.id))
			else:
				cursor.execute('select * from links where href = ?', (path.id,))

			for link in cursor:
				if link['source'] == path.id:
					source = path
					href = self.lookup_id(link['href'])
				else:
					source = self.lookup_id(link['source'])
					href = path
				# TODO lookup type by id

				yield Link(source, href)

	def list_links_to_tree(self, path, direction=LINK_DIR_FORWARD):
		'''Generator listing links for all child pages

		Like list_links() but recursive for sub pages below path

		@param path: the L{Path} for which to list links
		@param direction: the link direction to be listed
		@returns: yields L{Link} objects or empty list if path does not
		exist or no links are found
		'''
		path = self.lookup_path(path)
		if path:

			for link in self.list_links(path, direction):
				yield link

			for child in self.walk(path):
				for link in self.list_links(child, direction):
					yield link

	def n_list_links(self, path, direction=LINK_DIR_FORWARD):
		'''Get the number of links to be listed with L{list_links()}

		@param path: the L{Path} for which to list links
		@param direction: the link direction to be listed
		@returns: the number of links
		'''
		path = self.lookup_path(path)
		if not path:
			return 0

		cursor = self.db.cursor()
		if direction == LINK_DIR_FORWARD:
			cursor.execute('select count(*) from links where source = ?', (path.id,))
		elif direction == LINK_DIR_BOTH:
			cursor.execute('select count(*) from links where source = ? or href = ?', (path.id, path.id))
		else:
			cursor.execute('select count(*) from links where href = ?', (path.id,))
		row = cursor.fetchone()
		return int(row[0])

	def n_list_links_to_tree(self, path, direction=LINK_DIR_FORWARD):
		'''Get the number of links to be listed with L{list_links_to_tree()}

		@param path: the L{Path} for which to list links
		@param direction: the link direction to be listed
		@returns: the number of links
		'''
		# TODO optimize this one
		n = self.n_list_links(path, direction)
		for child in self.walk(path):
			n += self.n_list_links(child, direction)
		return n

	def get_tag_index(self, tag):
		'''Get the index where this tag will appear in the result
		of L{list_all_tags()}

		@param tag: a tag name or an L{IndexTag} object
		@returns: the index of this tag in the list (integer)
		'''
		tag = self.lookup_tag(tag)
		if not tag:
			raise ValueError, 'Could not find tag in index'

		sortkey = natural_sort_key(tag.name)
		cursor = self.db.cursor()
		cursor.execute(
			'select count(*) from tags where '
			'(sortkey < ? or (sortkey = ? and name < ?))',
			(sortkey, sortkey, tag.name)
		)
		row = cursor.fetchone()
		return int(row[0])

	def list_all_tags(self, offset=None, limit=None):
		'''Generator listing all tags that are used in this notebook

		The optional arguments C{offset} and C{limit} can be used to
		iterate only a slice of the list. Note that both C{offset} and
		C{limit} must always be defined together.

		@keyword offset: offset in list to start, an integer or None
		@keyword limit: max pages to return, an integer or None

		@returns: yields L{IndexTag} objects
		'''
		cursor = self.db.cursor()
		query = 'select * from tags order by sortkey, name'
		if offset is None:
			cursor.execute(query)
		else:
			cursor.execute(query + ' limit ? offset ?', (limit, offset))
		for row in cursor:
			yield IndexTag(row['name'], row['id'])

	def n_list_all_tags(self):
		'''Get the total number of tags used in this notebook

		@returns: the number of tags
		'''
		cursor = self.db.cursor()
		cursor.execute('select count(*) from tags')
		row = cursor.fetchone()
		return int(row[0])

	def list_all_tags_by_score(self):
		'''Generator listing all tags that are used in this notebook
		in order of occurence

		Like C{list_all_tags()} but sorted by the number of times they
		are used.

		@returns: yields L{IndexTag} objects
		'''
		cursor = self.db.cursor()
		cursor.execute(
			'SELECT id, name, count(*) hits'
			' FROM tags t INNER JOIN tagsources s ON t.id = s.tag'
			' GROUP BY s.tag'
			' ORDER BY count(*) DESC'
		)
		for row in cursor:
			yield IndexTag(row['name'], row['id'])

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
		cursor = self.db.cursor()
		cursor.execute(
			# The sub-query filters on pages that match all of the given tags
			# The main query selects all tags occuring on those pages and sorts
			# them by number of matching pages
			'SELECT id, name, count(*) hits'
			' FROM tags t INNER JOIN tagsources s ON t.id = s.tag'
			' WHERE s.source IN ('
			'   SELECT source FROM tagsources'
			'   WHERE tag IN %s'
			'   GROUP BY source'
			'   HAVING count(tag) = ?'
			' )'
			' GROUP BY s.tag'
			' ORDER BY count(*) DESC' % tag_ids, (len(tags),)
		)
		for row in cursor:
			yield IndexTag(row['name'], row['id'])

	def list_tags(self, path):
		'''Returns all tags for a given page

		@param path: a L{Path} object for the page
		@returns: yields L{IndexTag} objects
		'''
		path = self.lookup_path(path)
		if path:
			cursor = self.db.cursor()
			cursor.execute('select * from tagsources where source = ?', (path.id,))
			for row in cursor:
				yield self.lookup_tagid(row['tag'])

	def get_tagged_page_index(self, tag, path):
		'''Get the index where a path will appear in the result
		of L{list_tagged_pages()} for a given tag.

		@param tag: a tag name or L{IndexTag} object
		@param path: an {IndexPath} object
		@returns: the position of the path in the list (integer)
		'''
		if path.isroot:
			raise ValueError, 'Root path does not have an index number'

		path = self.lookup_path(path)
		if not path:
			raise ValueError, 'Could not find path in index'

		tag = self.lookup_tag(tag)
		if not tag:
			raise ValueError, 'Could not find tag in index'

		# Can't use count() here, like in get_page_index(), because
		# basenames are not unique in this lookup
		# FIXME do this anyway - sort by id
		cursor = self.db.cursor()
		cursor.execute(
			'select tagsources.source '
			'from tagsources join pages on tagsources.source=pages.id '
			'where tagsources.tag = ? '
			'order by pages.sortkey, pages.basename, pages.id',
			(tag.id,)
		)
			# Added id to "order by" columns because basenames are not unique
		i = 0
		for row in cursor:
			if row['source'] == path.id: return i
			i += 1

		raise ValueError, 'Path does not have given tag'

	def list_tagged_pages(self, tag, offset=None, limit=None):
		'''List all pages tagged with a given tag.

		The optional arguments C{offset} and C{limit} can be used to
		iterate only a slice of the list. Note that both C{offset} and
		C{limit} must always be defined together.

		@param tag: an L{IndexTag} object
		@keyword offset: offset in list to start, an integer or None
		@keyword limit: max pages to return, an integer or None

		@returns: yields L{IndexPath} objects
		'''
		tag = self.lookup_tag(tag)
		if not tag is None:
			cursor = self.db.cursor()
			query = 'select tagsources.source ' \
			'from tagsources join pages on tagsources.source=pages.id ' \
			'where tagsources.tag = ? ' \
			'order by pages.sortkey, pages.basename, pages.id'
			# Added id to "order by" columns because basenames are not unique
			if offset is None and limit is None:
				cursor.execute(query, (tag.id,))
			else:
				cursor.execute(query + ' limit ? offset ?', (tag.id, limit, offset))
			for row in cursor:
				yield self.lookup_id(row['source'])

	def get_untagged_root_page_index(self, path):
		'''Get the index where a path will appear in the result
		of L{list_untagged_root_pages()}.

		@param path: a L{Path} object
		@returns: the position of the path in the list
		'''
		if path.isroot:
			raise ValueError, 'Root path does not have an index number'

		path = self.lookup_path(path)
		if not path:
			raise ValueError, 'Could not find path in index'

		cursor = self.db.cursor()
		cursor.execute('select count(*) from tagsources where source = ?', (path.id,))
		row = cursor.fetchone()
		if int(row[0]) > 0:
			raise ValueError, 'Page has tags'

		sortkey = natural_sort_key(path.basename)
		cursor = self.db.cursor()
		cursor.execute(
			'select count(*) from pages where parent = ? '
			'and id not in (select source from tagsources) '
			'and (sortkey < ? or (sortkey = ? and basename < ?))',
			(ROOT_ID, sortkey, sortkey, path.basename)
		)
		row = cursor.fetchone()
		return int(row[0])

	def list_untagged_root_pages(self, offset=None, limit=None):
		'''List pages without tags in the top level namespace

		The optional arguments C{offset} and C{limit} can be used to
		iterate only a slice of the list. Note that both C{offset} and
		C{limit} must always be defined together.

		@keyword offset: offset in list to start, an integer or None
		@keyword limit: max pages to return, an integer or None

		@returns: yields L{IndexPath} objects
		'''
		cursor = self.db.cursor()
		query = 'select * from pages where parent = ? and id not in (select source from tagsources) order by sortkey, basename'
		if offset is None and limit is None:
			cursor.execute(query, (ROOT_ID,))
		else:
			cursor.execute(query + ' limit ? offset ?', (ROOT_ID, limit, offset))
		for row in cursor:
			yield IndexPath(row['basename'], (ROOT_ID, row['id'],), row)

	def n_list_tagged_pages(self, tag):
		'''Returns the number of pages tagged with a given tag
		@param tag: an L{IndexTag} object
		'''
		tag = self.lookup_tag(tag)
		if tag:
			cursor = self.db.cursor()
			cursor.execute('select count(*) from tagsources where tag = ?', (tag.id,))
			row = cursor.fetchone()
			return int(row[0])
		else:
			return 0

	def n_list_untagged_root_pages(self):
		'''Returns the number of untagged pages in the top level namespace'''
		cursor = self.db.cursor()
		cursor.execute('select count(*) from pages where parent = ? and id not in (select source from tagsources)', (ROOT_ID,))
		row = cursor.fetchone()
		return int(row[0])

	def get_previous(self, path, recurs=True):
		'''Get the previous path in the index

		This method allows moving through the index as if it were a
		flat list.

		@param path: a L{Path} object
		@param recurs: if C{False} only a previous page in the same
		namespace is returned, if C{True} previous page can be in a
		different namespace (walking depth first).
		@returns: an L{IndexPath} or C{None} if there was no previous
		page
		'''
		path = self.lookup_path(path)
		if path is None or path.isroot:
			return None

		if not recurs:
			return self._get_prev(path)
		else:
			prev = self._get_prev(path)
			if prev is None:
				# climb one up to parent
				parent = path.parent
				if not parent.isroot:
					prev = parent
			else:
				# decent to deepest child of previous path
				while prev.haschildren:
					pages = list(self.list_pages(prev))
					prev = pages[-1]
			return prev

	def _get_prev(self, path):
		# TODO: this one can be optimized using get_page_index() and
		# using offset and limit for list_pages()
		pagelist = list(self.list_pages(path.parent))
		i = pagelist.index(path)
		if i > 0:
			return pagelist[i-1]
		else:
			return None

	def get_next(self, path, recurs=True):
		'''Get the next path in the index

		This method allows moving through the index as if it were a
		flat list.

		@param path: a L{Path} object
		@param recurs: if C{False} only a next page in the same
		namespace is returned, if C{True} next page can be in a
		different namespace (walking depth first).
		@returns: an L{IndexPath} or C{None} if there was no next
		page
		'''
		path = self.lookup_path(path)
		if path is None or path.isroot:
			return None

		if not recurs:
			return self._get_next(path)
		elif path.haschildren:
			# descent to first child
			pages = list(self.list_pages(path))
			return pages[0]
		else:
			next = self._get_next(path)
			if next is None:
				# climb up to the first parent that has a next path
				for parent in path.parents():
					if parent.isroot:
						break
					next = self._get_next(parent)
					if next:
						break
			return next

	def _get_next(self, path):
		# TODO: this one can be optimized using get_page_index() and
		# using offset and limit for list_pages()
		pagelist = list(self.list_pages(path.parent))
		i = pagelist.index(path)
		if i+1 < len(pagelist):
			return pagelist[i+1]
		else:
			return None

	def get_unique_path(self, suggestedpath):
		'''Find a new non-existing path. Will add a number to the path
		name if it already exists untill a non-existing path is found.

		@param suggestedpath: a L{Path} object
		@returns: a L{Path} object
		'''
		path = self.lookup_path(suggestedpath)
		if path is None: return suggestedpath
		elif path.isroot:
			raise LookupError, 'Can not create new top level path'
		else:
			cursor = self.db.cursor()
			cursor.execute('select basename from pages where basename like ? and parent = ?',
				(path.basename+'%', path.parentid))
			taken = cursor.fetchall()
			i = 1
			name = path.basename + '_'
			while name + str(i) in taken:
				i += 1
			return Path(path.namespace + ':' + name+str(i))

# Need to register classes defining gobject signals
gobject.type_register(Index)


class PropertiesDict(object):
	'''Dict that maps key value pairs in the "meta" table of the
	database. Used to store e.g. the zim version that created the
	index. Used for the L{index.properties<Index.properties>} attribute.
	'''

	def __init__(self, db):
		self.db = db
		self.db_commit = DBCommitContext(self.db)

	def __setitem__(self, k, v):
		with self.db_commit:
			self._set(k, v)

	def _set(self, k, v):
		# This method is directly by Index when we are already in an
		# db commit context.
		cursor = self.db.cursor()
		cursor.execute('delete from meta where key=?', (k,))
		cursor.execute('insert into meta(key, value) values (?, ?)', (k, v))

	def __getitem__(self, k):
		try:
			cursor = self.db.cursor()
			cursor.execute('select value from meta where key=?', (k,))
			row = cursor.fetchone()
			if row:
				return row[0]
			else:
				return None
		except sqlite3.OperationalError: # no such table: meta
			return None
