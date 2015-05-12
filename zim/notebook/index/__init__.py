# -*- coding: utf-8 -*-

# Copyright 2009-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>


from __future__ import with_statement


### ISSUES ###
#
# Some way for main thread to inspect progress -- for progress dialog
#	report stage (scanning tree, indexing pages)
#	x out of n (done since start of update versus total flagged to do)
#  - use the probably-up-to-date here as well ?
#
# Try to use multiprocessing instead of threading for the indexer ?
#
# Issue with page exists flag: since PAGE_EXISTS_AS_LINK overrules
# PAGE_EXISTS_UNCERTAIN, methods like check_pagelist and update_children
# can miss pages that are flagged as placeholder, while existing as
# well as folder in the store
# Solve be "page_exists_in_store" flag, or separate table of files &
# folders from table of notebook nodes ...
#
##############

# Flow for indexer when checking a page:
#
#  queue
#    |
#    |--> CHECK_TREE
#    |       |    check etag_children
#    |       |     add / remove children
#    |       |      recursive for all children
#    |       V
#    |--> CHECK_PAGE
#    |       | |  check etag_content
#    |       | |   index content
#    |       | |    check etag_children
#    |       | V
#    `--> CHECK_CHILDREN
#            | |  check etag_children
#            | |    add / remove children
#            | |     recursive for new / changed children only
#            V V
#          UPTODATE
#
# The indexer prioritizes CHECK_CHILDREN and CHECK_TREE over CHECK_PAGE.
# As a result we first walk the whole tree structure before starting
# to idex content.
#
# The "on_store_page" and "on_delete_page" calls are typically called
# in another thread. Will aquire lock and interrupt the indexer. This
# way interactive changes from the GUI always are handled immediatly.


import sqlite3
import threading
import logging

logger = logging.getLogger('zim.notebook.index')

from zim.utils.threading import WorkerThread
from zim.fs import File

from .base import *
from .pages import *
from .links import *
from .tags import *


DB_VERSION = '0.6'

# Constants for the "needsheck" column in the "pages" table
# Lower numbers take precedence while processing
INDEX_UPTODATE = 0		 # No update needed
INDEX_NEED_UPDATE_CHILDREN = 1  # TODO - base probaby uptodate on this
INDEX_NEED_UPDATE_PAGE = 2  # TODO - base probaby uptodate on this
INDEX_CHECK_TREE = 3     # Check if children need to be updated, followed by a check page, recursive
INDEX_CHECK_CHILDREN = 4 # Check if children need to be updated, do nothing if children etag OK
INDEX_CHECK_PAGE = 5     # Check if page needs to be updated, do nothing if both etag OK


INDEX_INIT_SCRIPT = '''
CREATE TABLE zim_index (
	key TEXT,
	value TEXT,
	CONSTRAINT uc_MetaOnce UNIQUE (key)
);
INSERT INTO zim_index VALUES ('db_version', %r);
INSERT INTO zim_index VALUES ('probably_uptodate', 0);
''' % DB_VERSION


class Index(object):
	'''The Index keeps a cache of all pages in a notebook store, all
	links between pages and all tags. This data is used to speed up
	many operatons in the user interface, like showing the notebook
	index in the side pane, showing "what links here" and faster search
	for page attributes.

	The C{Index} object is an opaque object that only exposes an API
	to trigger index updates and notifications when changes are found.
	It does not expose the data it keeps directly. To query the index,
	you need to construct an "index view" first, see e.g. the
	L{PagesIndexView}, L{LinksIndexView} and L{TagsIndexView} classes.
	For convenience the L{Notebook} class also exposes these three
	views with the respective attributes C{pages}, C{links} and C{tags}.
	'''
	# We could also expose the above mentioned 3 views in this object,
	# but we don't do so to encourage the Notebook interface to be
	# used instead.

	@classmethod
	def new_from_file(klass, file, store):
		'''Constructor for a file based index
		@param file: a L{File} object for the sqlite database
		@param store: a L{StoreClass} instance to index
		'''
		file.dir.touch()
		db_conn = ThreadingDBConnection(file.encodedpath)
		return klass(db_conn, store)

	@classmethod
	def new_from_memory(klass, store):
		'''Constructor for an in-memory index
		@param store: a L{StoreClass} instance to index
		'''
		db_conn = MemoryDBConnection()
		return klass(db_conn, store)

	def __init__(self, db_conn, store):
		'''Constructor
		@param db_conn: a L{DBConnection} object
		@param store: a L{StoreClass} instance to index
		'''
		self.db_conn = db_conn
		self._db = db_conn.db_change_context()
		self.store = store
		self.indexers = [PagesIndexer(), LinksIndexer(), TagsIndexer()]
		self._pages = PagesViewInternal()
		self._index = IndexInternal(self.store, self.indexers)
		self._thread = None

		try:
			with self._db as db:
				if self._index.get_property(db, 'db_version') != DB_VERSION:
					logger.debug('Index db_version out of date')
					self._db_init()
		except sqlite3.OperationalError:
			# db is there but table does not exist
			logger.debug('Operational error, init tabels')
			self._db_init()
		except sqlite3.DatabaseError:
			if hasattr(db_conn, 'dbfilepath'):
				logger.warning('Overwriting possibly corrupt database: %s', db_conn.dbfilepath)
				db_conn.close_connections()
				file = File(self.db_conn.dbfilepath)
				if file.exists():
					file.remove()
				self._db = db_conn.db_change_context()
				self._db_init()
			else:
				raise

		# TODO checks on locale, others?

	@property
	def probably_uptodate(self):
		with self._db as db:
			value = self._index.get_property(db, 'probably_uptodate')
			return False if value == '0' else True

	def _db_init(self):
		with self._db as db:
			c = db.execute(
				'SELECT name FROM sqlite_master '
				'WHERE type="table" and name NOT LIKE "sqlite%"'
			)
			tables = [row[0] for row in c.fetchall()]
			for table in tables:
				db.execute('DROP TABLE %s' % table)

			logger.debug('(Re-)Initializing database for index')
			db.executescript(INDEX_INIT_SCRIPT)
			for indexer in self.indexers:
				indexer.on_db_init(self, db)

	def connect(self, signal, handler):
		for indexer in self.indexers:
			if signal in indexer.__signals__:
				return indexer.connect(signal, handler)
		else:
			raise ValueError, 'No such signal: %s' % signal

	def disconnect(self, handlerid):
		for indexer in self.indexers:
			indexer.disconnect(handlerid)
		# else pass

	def update(self, path=None):
		'''Update the index and return when done
		This method is faster than the background updates because
		it only commits the database at the end when all is done.
		@param path: a C{Path} object, if given only the index
		below this path is updated, else the entire index is updated.
		'''
		for i in self.update_iter(path):
			continue

	def update_iter(self, path=None):
		self.stop_update()

		indexer = TreeIndexer.new_from_index(self)
		indexer.queue_check(path)

		# Run with a single commit at the end
		with self._db as db:
			for i in indexer.do_update_iter(db):
				yield i

	def start_update(self, path=None):
		'''Start update in a separate thread.
		This is a relatively slow update because a separate commit is
		done for each page. The advantage is that changes become
		visible incrementally.
		If an update is
		'''
		indexer = TreeIndexer.new_from_index(self)
		indexer.queue_check(path)

		if not (self._thread and self._thread.is_alive()):
			self._thread = WorkerThread(indexer, indexer.__class__.__name__)
			self._thread.start()

	def stop_update(self):
		'''Stop update thread if any'''
		if self._thread:
			self._thread.stop()
			self._thread = None

	def wait_for_update(self, timeout=None):
		'''Wait for update thread if any
		@param timeout: timeout in second
		@returns: C{True} is thread was still running at timeout, else
		C{False}
		'''
		if self._thread:
			self._thread.join(timeout)
			if self._thread.is_alive():
				return True # keep waiting
			else:
				self._thread = None
		return False

	def flush(self):
		'''Delete all data in the index'''
		logger.info('Flushing index')
		self._db_init()

	def touch_path_interactive(self, path):
		'''Check to be called when a page is opened in the GUI
		Temporarily touches the path as a placeholder and starts checks.
		'''
		raise NotImplemented

	def cleanup_path_interactive(self, path):
		'''Cleanup to be called when leaving a (non-existing) page.
		Removes placeholders left by C{touch_path_interactive()}
		'''
		raise NotImplemented

	def on_store_page(self, page):
		with self._db as db:
			try:
				indexpath = self._pages.lookup_by_pagename(db, page)
			except IndexNotFoundError:
				indexpath = self._index.touch_path(db, page)

			self._index.index_page(db, indexpath)
			self._index.update_parent(db, indexpath.parent)

	def on_delete_page(self, path):
		with self._db as db:
			try:
				indexpath = self._pages.lookup_by_pagename(db, path)
			except IndexNotFoundError:
				return

			last_deleted = self._index.delete_page(db, indexpath, cleanup=True)
			self._index.update_parent(db, last_deleted.parent)

	def flag_reindex(self):
		'''This methods flags all pages with content to be re-indexed.
		Main reason to use this would be when loading a new plugin that
		wants to index all pages.
		'''
		with self._db as db:
			self._index.set_property(db, 'probably_uptodate', False)
			db.execute(
				'UPDATE pages SET content_etag=?, needscheck=? WHERE content_etag IS NOT NULL',
				('_reindex_', INDEX_CHECK_PAGE),
			)


class IndexInternal(object):
	'''Common methods between L{TreeIndexer} and L{Index}'''

	def __init__(self, store, indexers):
		self.store = store
		self.indexers = indexers
		self._pages = PagesViewInternal()

	def get_property(self, db, key):
		c = db.execute('SELECT value FROM zim_index WHERE key=?', (key,))
		row = c.fetchone()
		if row:
			return row[0]
		else:
			return None

	def set_property(self, db, key, value):
		db.execute('DELETE FROM zim_index WHERE key=?', (key,))
		db.execute('INSERT INTO zim_index(key, value) VALUES (?, ?)', (key, value))

	def insert_page(self, db, parent, path, needscheck=INDEX_CHECK_PAGE):
		'''Insert a record for the page, but page does not really exists
		untill L{set_page_exists()} has been called.
		'''
		db.execute(
			'INSERT INTO pages(parent, basename, sortkey, needscheck) '
			'VALUES (?, ?, ?, ?)',
			(parent.id, path.basename, natural_sort_key(path.basename), needscheck)
		)
		indexpath = self._pages.lookup_by_parent(db, parent, path.basename)
		return indexpath

	def set_page_exists(self, db, indexpath, page_exists=PAGE_EXISTS_HAS_CONTENT):
		assert page_exists in (PAGE_EXISTS_AS_LINK, PAGE_EXISTS_HAS_CONTENT)

		for parent in reversed(list(indexpath.parents())): # top down
			parentrow = self._pages.lookup_by_indexpath(db, parent)
			if parentrow.page_exists < page_exists:
				self._set_page_exists(db, parentrow, page_exists)

		self._set_page_exists(db, indexpath, page_exists)

	def _set_page_exists(self, db, indexpath, page_exists):
		new = indexpath.page_exists == PAGE_EXISTS_UNCERTAIN
		db.execute(
			'UPDATE pages SET page_exists=? WHERE id=?',
			(page_exists, indexpath.id),
		)
		if new and not indexpath.isroot:
			for indexer in self.indexers:
				indexer.on_new_page(self, db, indexpath)

	def touch_path(self, db, path):
		parent = ROOT_PATH
		names = path.parts
		while names: # find existing parents
			try:
				indexpath = self._pages.lookup_by_parent(db, parent, names[0])
			except IndexNotFoundError:
				break
			else:
				names.pop(0)
				parent = indexpath

		while names: # create missing parts
			basename = names.pop(0)
			path = parent.child(basename)
			indexpath = self.insert_page(db, parent, path, needscheck=INDEX_UPTODATE)
			parent = indexpath

		return indexpath

	def index_page(self, db, indexpath):
		# Get etag first - when data changes these should
		# always be older to ensure changes are detected in next run
		assert isinstance(indexpath, IndexPathRow)
		etag = self.store.get_content_etag(indexpath)

		if etag and indexpath.page_exists != PAGE_EXISTS_HAS_CONTENT:
			self.set_page_exists(db, indexpath)

		page = self.store.get_page(indexpath)
		for indexer in self.indexers:
			indexer.on_index_page(self, db, indexpath, page)
		db.execute(
			'UPDATE pages SET content_etag=? WHERE id=?',
			(etag, indexpath.id)
		)

	def delete_page(self, db, indexpath, cleanup):
		assert not indexpath.isroot
		for indexer in self.indexers:
			indexer.on_delete_page(self, db, indexpath)

		db.execute('DELETE FROM pages WHERE id=?', (indexpath.id,))

		parent = indexpath.parent
		basename = indexpath.basename
		for indexer in self.indexers:
			indexer.on_deleted_page(self, db, parent, basename)

		if cleanup:
			parent = indexpath.parent
			if not parent.isroot:
				parent = self._pages.lookup_by_id(db, parent.id)
				if not self.check_existance(db, parent):
					return self.delete_page(db, parent, cleanup=True) # recurs

		# else
		return indexpath

	def check_existance(self, db, indexpath):
		if indexpath.hascontent:
			return True
		else:
			c = db.execute(
				'SELECT count(*) FROM pages '
				'WHERE parent=? and page_exists>0',
				(indexpath.id,)
			)
			return c.fetchone()[0] > 0

	def update_parent(self, db, parent):
		# To be called after inserting or deleting a page driven by
		# the notebook API (not driven by the indexer)

		# Get etag first - when data changes these should
		# always be older to ensure changes are detected in next run
		etag = self.store.get_children_etag(parent)
		if self.check_pagelist(db, parent):
			db.execute(
				'UPDATE pages SET children_etag=? WHERE id=?',
				(etag, parent.id)
			)
			# do not set 'needscheck', allow for recursive update in action
		else:
			raise AssertionError, 'Namespace changed: %s' % parent
			#~ pass # TODO - actively start indexer

	def check_pagelist(self, db, indexpath):
		pages = set()
		for page in self.store.get_pagelist(indexpath):
			pages.add(page.basename)
			# TODO - speedup with name list API iso. object list

		try:
			for row in db.execute(
				'SELECT basename FROM pages WHERE parent=? and page_exists<>?',
				(indexpath.id, PAGE_EXISTS_AS_LINK)
			):
				pages.remove(row['basename'])
		except KeyError:
			return False

		return not pages # OK if empty


class TreeIndexer(IndexInternal):
	'''This indexer looks at the database for pages that are flagged
	as needing a check. It checks and where necessary updates the
	database cache.

	The C{__iter__()} function serves as the main loop for indexing
	all pages that are flagged. Thus a C{TreeIndexer} object can be
	used as iterable, e.g. in combination with the L{WorkerThread}
	class.
	'''

	@classmethod
	def new_from_index(klass, index):
		return klass(
			index.db_conn,
			index.store,
			index.indexers
		)

	def __init__(self, db_conn, store, indexers):
		self.db_conn = db_conn
		self.store = store
		self.indexers = indexers
		self._pages = PagesViewInternal()

	def queue_check(self, path, check=INDEX_CHECK_TREE):
		with self.db_conn.db_change_context() as db:
			if path and not path.isroot:
				path = self._pages.lookup_by_pagename(db, pagename)
			else:
				path = ROOT_PATH

			db.execute(
				'UPDATE pages SET needscheck=? WHERE id=?',
				(INDEX_CHECK_TREE, path.id)
			)

	def __iter__(self):
		# Run with commit after each cycle
		change_context = self.db_conn.db_change_context()
		update_iter = self.do_update_iter(change_context._db)
		while True:
			with change_context:
				try:
					i = update_iter.next()
				except StopIteration:
					break
				else:
					yield i

	def do_update_iter(self, db):
		logger.info('Starting index update')
		while True:
			# Get next page to be checked from db
			row = db.execute(
				'SELECT * FROM pages WHERE needscheck > 0 '
				'ORDER BY needscheck, id LIMIT 1'
			).fetchone()
				# ORDER BY: parents always have lower "id" than children

			if row:
				check = row['needscheck']
				indexpath = self._pages.lookup_by_row(db, row)
			else:
				break # Stop thread, index up to date

			# Dispatch to the proper method
			try:
				if check == INDEX_CHECK_CHILDREN:
					self.check_children(db, indexpath)
				elif check == INDEX_CHECK_TREE:
					self.check_children(db, indexpath, checktree=True)
				elif check == INDEX_CHECK_PAGE:
					self.check_page(db, indexpath)
				else:
					raise AssertionError('BUG: Unknown update flag: %i' % check)
			except:
				# Avoid looping for same page
				logger.exception('Error while handling update for page: %s', indexpath)
				db.execute(
					'UPDATE pages SET needscheck=? WHERE id=?',
					(INDEX_UPTODATE, indexpath.id)
				)

			for indexer in self.indexers:
				indexer.emit_queued_signals()

			# Let outside world know what we are doing
			# and allow wrapper to commit changes
			yield check, indexpath

		self.set_property(db, 'probably_uptodate', True)

		logger.info('Index update finished')

	def check_children(self, db, indexpath, checktree=False):
		### TODO check page_exists tag is correct here
		###      if not, propagate changes upward

		# Get etag first - when data changes these should
		# always be older to ensure changes are detected in next run
		etag = self.store.get_children_etag(indexpath)

		if etag != indexpath.children_etag:
			self.set_property(db, 'probably_uptodate', False)
			if etag and not indexpath.children_etag:
				self.new_children(db, indexpath, etag)
			elif etag:
				self.update_children(db, indexpath, etag, checktree=checktree)
			else:
				self.delete_children(db, indexpath)
		elif checktree:
			# Check whether any grand-children changed
			# For a file store this may affect the children_etag
			# because creating the folder changes the parent folder
			# for emory store and other file layouts this behavior
			# differs.
			for page in self.store.get_pagelist(indexpath):
				row = db.execute(
					'SELECT * FROM pages WHERE parent=? and basename=?',
					(indexpath.id, page.basename)
				).fetchone()
				if row:
					if page.haschildren or row['n_children'] > 0: # has and/or had children
						check = INDEX_CHECK_TREE
					else:
						check = INDEX_CHECK_PAGE

					db.execute(
						'UPDATE pages SET needscheck=? WHERE id=?',
						(check, row['id'],)
					)
				else:
					raise IndexConsistencyError, 'Missing index for: %s' % page
		else:
			pass

		if checktree and not indexpath.isroot:
			needscheck = INDEX_CHECK_PAGE
		else:
			needscheck = INDEX_UPTODATE

		db.execute(
			'UPDATE pages SET children_etag=?, needscheck=? WHERE id=?',
			(etag, needscheck, indexpath.id)
		)

	def new_children(self, db, indexpath, etag):
		for page in self.store.get_pagelist(indexpath):
			check = INDEX_CHECK_TREE if page.haschildren else INDEX_CHECK_PAGE
			child = self.insert_page(db, indexpath, page, needscheck=check)
			if page.hascontent:
				self.set_page_exists(db, child)

	def update_children(self, db, indexpath, etag, checktree=False):
		c = db.cursor()

		# First flag all children in index
		c.execute('UPDATE pages SET childseen=0 WHERE parent=? and page_exists<>?',
			(indexpath.id, PAGE_EXISTS_AS_LINK)
		)

		# Then go over the list
		for page in self.store.get_pagelist(indexpath):
			c.execute(
				'SELECT * FROM pages WHERE parent=? and basename=?',
				(indexpath.id, page.basename)
			)
			row = c.fetchone()
			if not row: # New child
				check = INDEX_CHECK_TREE if page.haschildren else INDEX_CHECK_PAGE
				child = self.insert_page(db, indexpath, page, needscheck=check)
				if page.hascontent:
					self.set_page_exists(db, child)
			else: # Existing child
				if page.hascontent and row['page_exists'] != PAGE_EXISTS_HAS_CONTENT:
					child = self._pages.lookup_by_row(db, row)
					self.set_page_exists(db, child)

				if checktree:
					if page.haschildren or row['n_children'] > 0: # has and/or had children
						check = INDEX_CHECK_TREE
					else:
						check = INDEX_CHECK_PAGE
				else:
					if page.hascontent != bool(row['content_etag']):
						check = INDEX_CHECK_PAGE
					elif page.haschildren != (row['n_children'] > 0):
						check = INDEX_CHECK_CHILDREN
					else:
						check = None

				if check is None:
					c.execute(
						'UPDATE pages SET childseen=1 WHERE id=?',
						(row['id'],)
					)
				else:
					c.execute(
						'UPDATE pages SET childseen=1, needscheck=? WHERE id=?',
						(check, row['id'],)
					)

		# Finish by deleting pages that went missing
		for row in c.execute(
			'SELECT * FROM pages WHERE parent=? and childseen=0',
			(indexpath.id,)
		):
			child = self._pages.lookup_by_row(db, row)
			self.delete_children(db, child)
			self.delete_page(db, child, cleanup=False)

	def delete_children(self, db, indexpath):
		for row in db.execute(
			'SELECT * FROM pages WHERE parent=?',
			(indexpath.id,)
		):
			child = indexpath.child_by_row(row)
			self.delete_children(db, child) # recurs depth first - no check here on haschildren!
			self.delete_page(db, child, cleanup=False)

	def check_page(self, db, indexpath):
		etag = self.store.get_content_etag(indexpath)
		if etag != indexpath.content_etag:
			self.index_page(db, indexpath)

		# Queue a children check if needed (not recursive)
		children_etag = self.store.get_children_etag(indexpath)
		if children_etag == indexpath.children_etag:
			needscheck = INDEX_UPTODATE
		else:
			self.set_property(db, 'probably_uptodate', False)
			needscheck = INDEX_CHECK_CHILDREN
		db.execute(
			'UPDATE pages SET needscheck=? WHERE id=?',
			(needscheck, indexpath.id)
		)


class DBConnection(object):
	'''A DBConnection object manages one or more connections to the
	same database.

	Database access is protected by two locks: a "state lock" and
	a "change lock". The state lock is used by all objects that want
	to retrieve info from the index. As long as you hold the lock,
	nobody is going to change the index in between. However, changes can
	be pending to be committed when you release the lock. Aquire the
	change lock to ensure nobody is planning changes in paralel.

	This logic is enforced by wrapping the database connections in
	L{DBContext} and L{DBChangeContext} objects. The first is used by
	objects that only want a view of the database, the second by the
	index when changing the database.

	Do not instantiate this class directly, use implementations
	L{ThreadingDBConnection} or L{MemoryDBConnection} instead.
	'''

	def __init__(self):
		raise NotImplementedError

	@staticmethod
	def _db_connect(string, check_same_thread=False):
		# We use the undocumented "check_same_thread=False" argument to
		# allow calling database from multiple threads. This allows
		# views to be used from different threads as well. The state lock
		# protects the access to the connection in that case.
		# For threads that make changes, a new connection is made anyway
		db = sqlite3.connect(
			string,
			detect_types=sqlite3.PARSE_DECLTYPES,
			check_same_thread=check_same_thread,
		)
		db.row_factory = sqlite3.Row
		return db

	def db_context(self):
		'''Returns a L{DBContext} object'''
		return DBContext(self._get_db(), self._state_lock)

	def db_change_context(self):
		'''Returns a L{DBChangeContext} object'''
		return DBChangeContext(
			self._get_db(check_same_thread=True),
			self._state_lock, self._change_lock
		)

	def close_connections(self):
		raise NotImplementedError


class MemoryDBConnection(DBConnection):

	def __init__(self):
		self._db = self._db_connect(':memory:')
		self._state_lock = threading.RLock()
		self._change_lock = self._state_lock # all changes visile immediatly

	def _get_db(self, check_same_thread=False):
		return self._db


class ThreadingDBConnection(DBConnection):
	'''Implementation of L{DBConnection} that re-connects for each
	thread. The advantage is that changes made in a thread do not
	become visible to other threads untill they are committed.
	'''

	def __init__(self, dbfilepath):
		if dbfilepath == ':memory:':
			raise ValueError, 'This class can not work with in-memory databases, use MemoryDBConnection instead'
		self.dbfilepath = dbfilepath
		self._connections = {}
		self._state_lock = threading.RLock()
		self._change_lock = threading.RLock()

	def _get_db(self, check_same_thread=False):
		thread = threading.current_thread().ident
		if thread not in self._connections:
			self._connections[thread] = \
				self._db_connect(
					self.dbfilepath, check_same_thread=check_same_thread)
		return self._connections[thread]

	def close_connections(self):
		for key in self._connections.keys():
			db = self._connections.pop(key)
			db.close()


class DBContext(object):
	'''Used for using a db connection with an asociated lock.
	Intended syntax::

		self._db = DBContext(db_conn, state_lock)
		...

		with self._db as db:
			db.execute(...)
	'''

	def __init__(self, db, state_lock):
		self._db = db
		self.state_lock = state_lock

	def __enter__(self):
		self.state_lock.acquire()
		self._total_changes = self._db.total_changes
		return self._db

	def __exit__(self, exc_type, exc_value, traceback):
		self.state_lock.release()
		assert self._total_changes == self._db.total_changes, 'Unexpected changes to db'
		return False # re-raise error


class DBChangeContext(object):
	'''Context manager to manage database changes.
	Intended syntax::

		self._db = DBChangeContext(db_conn, state_lock, change_lock)
		...

		with self._db as db:
			db.execute(...)
	'''

	def __init__(self, db, state_lock, change_lock):
		self._db = db
		self.state_lock = state_lock
		self.change_lock = change_lock
		self._counter = 0 # counter makes commit re-entrant

	def __enter__(self):
		self.change_lock.acquire()
		self._counter += 1
		return self._db

	def __exit__(self, exc_type, exc_value, traceback):
		try:
			self._counter -= 1
			if self._counter == 0:
				if exc_value:
					self._db.rollback()
				else:
					with self.state_lock:
						self._db.commit()
		finally:
			self.change_lock.release()

		return False # re-raise error
