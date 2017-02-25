# -*- coding: utf-8 -*-

# Copyright 2009-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>


from __future__ import with_statement


import sqlite3
import threading
import logging

logger = logging.getLogger('zim.notebook.index')


from zim.newfs import LocalFile, File, Folder, FileNotFoundError
from zim.signals import SignalEmitter


from .files import *
from .base import *
from .pages import *
from .links import *
from .tags import *


DB_VERSION = '0.7'


class Index(SignalEmitter):
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

	@signal: C{new-update-iter (update_iter)}: signal used for plugins wanting
	to extend the indexer
	@signal: C{changed ()}: emitted after changes have been committed
	'''

	__signals__ = {
		'new-update-iter': (None, None, (object,)),
		'changed': (None, None, ()),
	}

	def __init__(self, dbpath, layout):
		'''Constructor
		@param dbpath: a file path for the sqlite db, or C{":memory:"}
		@param layout: a L{NotebookLayout} instance to index
		'''
		self.dbpath = dbpath
		self.layout = layout
		self.lock = threading.RLock()
		self._db = self.new_connection()
		self._db_check()
		self.update_iter = IndexUpdateIter(self._db, self.layout)

	def _db_check(self):
		try:
			if self._get_property('db_version') == DB_VERSION:
				pass
			else:
				logger.debug('Index db_version out of date')
				self._db_init()
		except sqlite3.OperationalError:
			# db is there but table does not exist
			logger.debug('Operational error, init tabels')
			self._db_init()
		except sqlite3.DatabaseError:
			assert not self.dbpath == ':memory:'
			logger.warning('Overwriting possibly corrupt database: %s', self.dbpath)
			self.db.close()
			file = LocalFile(self.dbpath)
			try:
				file.remove()
			except:
				logger.exception('Could not delete: %s', file)
			finally:
				db = self.new_connection()
				self._db_init()

		# TODO checks on locale, others?

	def _db_init(self):
		tables = [r[0] for r in self._db.execute(
			'SELECT name FROM sqlite_master '
			'WHERE type="table" and name NOT LIKE "sqlite%"'
		)]
		for table in tables:
			self._db.execute('DROP TABLE %s' % table)

		logger.debug('(Re-)Initializing database for index')
		self._db.executescript('''
			CREATE TABLE zim_index (
				key TEXT,
				value TEXT,
				CONSTRAINT uc_MetaOnce UNIQUE (key)
			);
			INSERT INTO zim_index VALUES ('db_version', %r)
		''' % DB_VERSION)
		IndexUpdateIter(self._db, self.layout)
		self._db.commit()

	def _get_property(self, key):
		c = self._db.execute('SELECT value FROM zim_index WHERE key=?', (key,))
		row = c.fetchone()
		return row[0] if row else None

	def _set_property(self, key, value):
		with self.lock:
			if value is None:
				self._db.execute('DELETE FROM zim_index WHERE key=?', (key,))
			else:
				self._db.execute('INSERT OR REPLACE INTO zim_index VALUES (?, ?)', (key, value))

	@property
	def is_uptodate(self):
		row = self._db.execute(
			'SELECT * FROM files WHERE index_status=?',
			(STATUS_NEED_UPDATE,)
		).fetchone()
		return row is None

	def check_and_update(self):
		'''Update all data in the index'''
		with self.lock:
			self.update_iter.check_and_update()

	def flush(self):
		'''Delete all data in the index'''
		logger.info('Flushing index')
		with self.lock:
			self._db_init()

	def new_connection(self):
		if self.dbpath == ':memory:' and hasattr(self, '_db'):
			return self._db
		else:
			db = sqlite3.Connection(self.dbpath)
			db.row_factory = sqlite3.Row
			# db.execute('PRAGMA synchronous=OFF;')
			# Don't wait for disk writes, we can recover from crashes
			# anyway. Allows us to use commit more frequently.
			# -- But we do use commit to synchronize between threads
			# -- so disabled for now..
			return db

	def update_file(self, file):
		path = file.relpath(self.layout.root)
		filesindexer = self.update_iter.files
		row = self._db.execute('SELECT id FROM files WHERE path=?', (path,)).fetchone()
		if row is None and not file.exists():
			pass
		else:
			filesindexer.emit('start-update')

			if row:
				node_id = row[0]
				if isinstance(file, File):
					if file.exists():
						filesindexer.update_file(node_id, file)
					else:
						filesindexer.delete_file(node_id)
				elif isinstance(file, Folder):
					if file.exists():
						filesindexer.update_folder(node_id, file)
					else:
						filesindexer.delete_folder(node_id)
				else:
					raise TypeError
			else: # file.exists():
				if isinstance(file, File):
					filesindexer.interactive_add_file(file)
				elif isinstance(file, Folder):
					raise ValueError
				else:
					raise TypeError

			filesindexer.emit('finish-update')
			self._db.commit()
			self.emit('changed')

	def file_moved(self, oldfile, newfile):
		# TODO: make this more efficient, specific for moved folders
		#       by supporting moved pages in indexers

		if isinstance(oldfile, File):
			self.update_file(oldfile)
			self.update_file(newfile)
		elif isinstance(oldfile, Folder):
			self.update_file(oldfile)
			self.update_iter.check_and_update(newfile)
		else:
			raise TypeError


class OldIndex(object):

	def touch_current_page_placeholder(self, path):
		'''Create a placeholder for C{path} if the page does not
		exist. Cleans up old placeholders.
		'''
		# This method uses a hack by linking the page from the ROOT_ID
		# page if it does not exist.

		with self.db_conn.db_change_context() as db:
			# delete
			db.execute(
				'DELETE FROM links WHERE source=?',
				(ROOT_ID,)
			)
			for indexer in self._indexers:
				if isinstance(indexer, LinksIndexer):
					indexer.cleanup_placeholders(self._index, db)

			# touch if needed
			try:
				indexpath = self._pages.lookup_by_pagename(db, path)
			except IndexNotFoundError:
				# insert link
				# insert placeholder
				target = self._index.touch_path(db, path)
				#~ self._index.set_page_exists(db, target, PAGE_EXISTS_HAS_CONTENT) # hack to avoid cleanup before next step :S
				db.execute(
					'INSERT INTO links(source, target, rel, names) '
					'VALUES (?, ?, ?, ?)',
					(ROOT_ID, target.id, HREF_REL_ABSOLUTE, target.name)
				)
				self._index.set_page_exists(db, target, PAGE_EXISTS_AS_LINK)
			else:
				pass # nothing to do

			self._index.before_commit(db)

		self._index.after_commit()

	def on_store_page(self, page):
		with self.db_conn.db_change_context() as db:
			try:
				indexpath = self._pages.lookup_by_pagename(db, page)
			except IndexNotFoundError:
				indexpath = self._index.touch_path(db, page)

			self._index.index_page(db, indexpath)
			self._index.update_parent(db, indexpath.parent)

			self._index.before_commit(db)

		self._index.after_commit()

	def on_move_page(self, oldpath, newpath):
		# TODO - optimize by letting indexers know about move
		if not (newpath == oldpath or newpath.ischild(oldpath)):
			self.on_delete_page(oldpath)
		self.update(newpath)

	def on_delete_page(self, path):
		with self.db_conn.db_change_context() as db:
			try:
				indexpath = self._pages.lookup_by_pagename(db, path)
			except IndexNotFoundError:
				return

			for child in self._pages.walk_bottomup(db, indexpath):
				self._index.delete_page(db, child, cleanup=False)

			last_deleted = self._index.delete_page(db, indexpath, cleanup=True)
			self._index.update_parent(db, last_deleted.parent)

			self._index.before_commit(db)

		self._index.after_commit()

	def add_plugin_indexer(self, indexer):
		'''Add an indexer for a plugin
		Checks the C{PLUGIN_NAME} and C{PLUGIN_DB_FORMAT}
		attributes and calls C{on_init()} when needed.
		Can result in reset of L{probably_uptodate} because the new
		indexer has not seen the pages in the index.
		@param indexer: An instantiation of L{PluginIndexerBase}
		'''
		assert indexer.PLUGIN_NAME and indexer.PLUGIN_DB_FORMAT
		with self.db_conn.db_change_context() as db:
			if self._index._get_property(db, indexer.PLUGIN_NAME) != indexer.PLUGIN_DB_FORMAT:
				indexer.on_init(self._index, db)
				self._index._set_property(db, indexer.PLUGIN_NAME, indexer.PLUGIN_DB_FORMAT)
				self._flag_reindex(db)

		self._indexers.append(indexer)

	def remove_plugin_indexer(self, indexer):
		'''Remove an indexer for a plugin
		Calls the C{on_teardown()} method of the indexer and
		remove it from the list.
		@param indexer: An instantiation of L{PluginIndexerBase}
		'''
		try:
			self._indexers.remove(indexer)
		except ValueError:
			pass

		with self.db_conn.db_change_context() as db:
			indexer.on_teardown(self._index, db)
			self._index._set_property(db, indexer.PLUGIN_NAME, None)

	def flag_reindex(self):
		'''This methods flags all pages with content to be re-indexed.
		Main reason to use this would be when loading a new plugin that
		wants to index all pages.
		'''
		with self.db_conn.db_change_context() as db:
			self._flag_reindex(db)

	def _flag_reindex(self, db):
		self._index._set_property(db, 'probably_uptodate', False)
		db.execute(
			'UPDATE pages SET content_etag=?, needscheck=? WHERE content_etag IS NOT NULL',
			('_reindex_', INDEX_CHECK_PAGE),
		)


class IndexUpdateIter(object):

	def __init__(self, db, layout):
		self.db = db
		self.layout = layout
		self.files = FilesIndexer(db, layout.root)
		self.pages = PagesIndexer(db, layout, self.files)
		self.links = LinksIndexer(db, self.pages, self.files)
		self.tags = TagsIndexer(db, self.pages, self.files)

	def __iter__(self):
		for i in self.files.update_iter():
			yield
		self.db.commit()

	def update(self):
		'''Convenience method to do a full update at once'''
		for i in self.files.update_iter():
			pass
		self.db.commit()

	def check_and_update(self, file=None):
		'''Convenience method to do a full update and check at once'''
		checker = FilesIndexChecker(self.db, self.layout.root)
		checker.queue_check(file=file)
		for out_of_date in checker.check_iter():
			if out_of_date:
				for i in self.files.update_iter():
					pass
		self.db.commit()
