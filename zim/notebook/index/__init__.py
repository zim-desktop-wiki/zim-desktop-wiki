# -*- coding: utf-8 -*-

# Copyright 2009-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>


from __future__ import with_statement


import sqlite3
import threading
import logging

logger = logging.getLogger('zim.notebook.index')

from zim.utils.threading import WorkerThread
from zim.newfs import LocalFile, File, Folder

from zim.newfs import FileNotFoundError

from .files import *
from .base import *
from .pages import *
from .links import *
from .tags import *


DB_VERSION = '0.7'


class MyEMitter(object):

	def __init__(self):
		self._sigal_handlers_normal = []
		self._sigal_handlers_before = []

	def connect_after(self, signal, handler):
		assert signal in self.__signals__, 'No such signal: %s' % signal
		h = (signal, handler)
		self._sigal_handlers_normal.append(h)
		return id(h)

	connect = connect_after

	def connect_before(self, signal, handler):
		assert signal in self.__signals__, 'No such signal: %s' % signal
		h = (signal, handler)
		self._sigal_handlers_before.append(h)
		return id(h)

	def disconnect(self, handlerid):
		self._sigal_handlers_normal = filter(
			lambda h: id(h) != handlerid,
			self._sigal_handlers_normal
		)
		self._sigal_handlers_before = filter(
			lambda h: id(h) != handlerid,
			self._sigal_handlers_before
		)

	def commit_and_emit(self, db, signal_queue):
		for signal, handler in self._sigal_handlers_before:
			for s in signal_queue:
				if s[0] == signal:
					try:
						handler(self, *s[1:])
					except:
						logger.exception('Exception in signal handler for %s', signal)

		db.commit()

		for signal, handler in self._sigal_handlers_normal:
			for s in signal_queue:
				if s[0] == signal:
					try:
						handler(self, *s[1:])
					except:
						logger.exception('Exception in signal handler for %s', signal)


class Index(MyEMitter):
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

	__signals__ = {}
	__signals__.update(PagesIndexer.__signals__)
	__signals__.update(LinksIndexer.__signals__)
	__signals__.update(TagsIndexer.__signals__)

	def __init__(self, dbpath, layout):
		'''Constructor
		@param dbpath: a file path for the sqlite db, or C{":memory:"}
		@param layout: a L{NotebookLayout} instance to index
		'''
		MyEMitter.__init__(self)
		self.dbpath = dbpath
		self.layout = layout
		self.lock = threading.RLock()
		self.db = self.new_connection()
		self._db_check()

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
		tables = [r[0] for r in self.db.execute(
			'SELECT name FROM sqlite_master '
			'WHERE type="table" and name NOT LIKE "sqlite%"'
		)]
		for table in tables:
			self.db.execute('DROP TABLE %s' % table)

		logger.debug('(Re-)Initializing database for index')
		self.db.executescript('''
			CREATE TABLE zim_index (
				key TEXT,
				value TEXT,
				CONSTRAINT uc_MetaOnce UNIQUE (key)
			);
			INSERT INTO zim_index VALUES ('db_version', %r)
		''' % DB_VERSION)
		self.build_indexer(self.db) # initialize all tables
		self.db.commit()

	def _get_property(self, key):
		c = self.db.execute('SELECT value FROM zim_index WHERE key=?', (key,))
		row = c.fetchone()
		return row[0] if row else None

	def _set_property(self, key, value):
		with self.lock:
			if value is None:
				self.db.execute('DELETE FROM zim_index WHERE key=?', (key,))
			else:
				self.db.execute('INSERT OR REPLACE INTO zim_index VALUES (?, ?)', (key, value))

	def update(self):
		'''Update all data in the index'''
		with self.lock:
			indexer = self.build_indexer()
			indexer.check_and_update_all()
			self.commit_and_emit(indexer.db, indexer.page_indexer.signals)

	def flush(self):
		'''Delete all data in the index'''
		logger.info('Flushing index')
		with self.lock:
			self._db_init()

	def new_connection(self):
		if self.dbpath == ':memory:' and hasattr(self, 'db'):
			return self.db
		else:
			db = sqlite3.Connection(self.dbpath)
			db.row_factory = sqlite3.Row
			db.execute('PRAGMA synchronous=OFF;')
			# Don't wait for disk writes, we can recover from crashes
			# anyway. Allows us to use commit more frequently.
			return db

	def build_indexer(self, db=None):
		db = db or self.new_connection()
		signals = []
		content_indexers = [
			LinksIndexer(db, signals),
			TagsIndexer(db, signals)
		]
		for c in content_indexers:
			c.on_db_init()

		page_indexer = PagesIndexer(db, self.layout, content_indexers, signals)
		page_indexer.init_db()

		files_indexer = FilesIndexer(db, self.layout.root, page_indexer)
		files_indexer.init_db()

		return files_indexer

	def update_file(self, file):
		path = file.relpath(self.layout.root)
		indexer = self.build_indexer() # TODO: keep indexer ready
		row = self.db.execute('SELECT id FROM files WHERE path=?', (path,)).fetchone()
		if row:
			node_id = row[0]
			indexer.start_update()
			if isinstance(file, File):
				if file.exists():
					indexer.update_file(node_id, file)
				else:
					indexer.delete_file(node_id)
			elif isinstance(file, Folder):
				if file.exists():
					indexer.update_folder(node_id, file)
				else:
					indexer.delete_folder(node_id)
			else:
				raise TypeError
			indexer.finish_update()
			self.commit_and_emit(indexer.db, indexer.page_indexer.signals)
		elif file.exists():
			indexer.interactive_add_file(file)
			self.commit_and_emit(indexer.db, indexer.page_indexer.signals)
		else:
			pass



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
		attributes and calls C{on_db_init()} when needed.
		Can result in reset of L{probably_uptodate} because the new
		indexer has not seen the pages in the index.
		@param indexer: An instantiation of L{PluginIndexerBase}
		'''
		assert indexer.PLUGIN_NAME and indexer.PLUGIN_DB_FORMAT
		with self.db_conn.db_change_context() as db:
			if self._index._get_property(db, indexer.PLUGIN_NAME) != indexer.PLUGIN_DB_FORMAT:
				indexer.on_db_init(self._index, db)
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
