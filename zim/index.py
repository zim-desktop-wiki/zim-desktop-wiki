# -*- coding: utf-8 -*-

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

The database also stores the version number of the zim version that
created it. After upgrading to a new version the database will
automatically be flushed. Thus modifications to this module will be
transparent as long as the zim version number is updated.
'''

# Note that it is important that this module fires signals and list pages
# in a consistent order, if the order is not consistent or changes without
# the apropriate signals the pageindex widget will get confused and mess up.

from __future__ import with_statement

import sqlite3
import gobject
import logging

import zim
from zim.notebook import Path, Link, PageNameError

logger = logging.getLogger('zim.index')

LINK_DIR_FORWARD = 1
LINK_DIR_BACKWARD = 2
LINK_DIR_BOTH = 3

ROOT_ID = 1 # Primary key starts count at 1 and first entry will be root

SQL_CREATE_TABLES = '''
create table if not exists meta (
	key TEXT,
	value TEXT
);
create table if not exists pages (
	id INTEGER PRIMARY KEY,
	basename TEXT,
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
	type INTEGER
);
create table if not exists linktypes (
	id INTEGER PRIMARY KEY,
	label TEXT
);
'''

# TODO need better support for TreePaths, e.g. as signal arguments for Treemodel

# TODO need a verify_path that works like lookup_path but adds checks when path
# already has a indexpath attribute, e.g. check basename and parent id
# Otherwise we might be re-using stale data. Also check copying of
# _indexpath in notebook.Path

# FIXME, the idea to have some index paths with and some without data
# was a really bad idea. Need to clean up the code as this is / will be
# a source of obscure bugs. Remove or replace lookup_data().

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
	def parentid(self):
		if self._indexpath and len(self._indexpath) > 1:
			return self._indexpath[-2]
		else:
			assert self.isroot, 'BUG: only root entry can have top level indexpath'
			return None

	@property
	def hasdata(self): return not self._row is None

	def __getattr__(self, attr):
		if self._row is None:
			raise AttributeError, 'This IndexPath does not contain row data'
		else:
			try:
				return self._row[attr]
			except IndexError:
				raise AttributeError, '%s has no attribute %s' % (self.__repr__(), attr)

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


class DBCommitContext(object):
	'''Class used for the Index.db_commit attribute.
	This allows syntax like:

		with index.db_commit:
			cursor = index.db.get_cursor()
			cursor.execute(...)

	instead off:

		try:
			cursor = index.db.get_cursor()
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
	'''This class wraps the database with meta data on zim pages'''
	# TODO document signals

	# Resolving links depends on the contents of the database and
	# links to non-existing pages can create new page nodes. This has
	# consequences for updating the database and makes things a bit
	# more complicated than expected at first sight. Page nodes for
	# non-exisiting page are refered to as 'placeholders' below.
	#
	# 1) When updating we first traverse the whole page tree creating
	#    nodes for all existing pages before indexing contents and links
	# 2) When we do index the contents we need to go top down through
	#    the tree, indexing parent nodes before we index children. This is
	#    because resolving links goes bottom up and may see non-exisitng
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
		'page-indexed': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'page-haschildren-toggled': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'page-deleted': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'delete': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'start-update': (gobject.SIGNAL_RUN_LAST, None, ()),
		'end-update': (gobject.SIGNAL_RUN_LAST, None, ()),
	}

	def __init__(self, notebook=None, dbfile=None):
		'''If no dbfile is given, the default file for this notebook will be
		used will be used. Main use of providing a dbfile here is to make the
		index operate in memory by setting dbfile to ":memory:".
		'''
		gobject.GObject.__init__(self)
		self.dbfile = dbfile
		self.db = None
		self.db_commit = None
		self.notebook = None
		self.properties = None
		self.updating = False
		self._checkcontents = False
		self._update_pagelist_queue = []
		self._index_page_queue = []
		if self.dbfile:
			self._connect()
		if notebook:
			self.set_notebook(notebook)

	def set_notebook(self, notebook):
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
			self.delete(oldpath)
			self.update(newpath, background=True)

		def on_page_updated(o, page):
			indexpath = self.lookup_path(page)
			if not indexpath:
				indexpath = self.touch(page)
			links = self._get_placeholders(indexpath, recurs=False)
			self._index_page(indexpath, page)
			for link in links:
				self.cleanup(link)

		self.notebook.connect_after('store-page', on_page_updated)
		self.notebook.connect_after('move-page', on_page_moved)
		self.notebook.connect_after('delete-page', lambda o, p: self.delete(p))

	def _connect(self):
		self.db = sqlite3.connect(
			str(self.dbfile), detect_types=sqlite3.PARSE_DECLTYPES)
		self.db.row_factory = sqlite3.Row

		self.properties = PropertiesDict(self.db)
		if self.properties['zim_version'] != zim.__version__:
			# init database layout
			self.db.executescript(SQL_CREATE_TABLES)
			self.flush()
			self.properties['zim_version'] = zim.__version__

		self.db_commit = DBCommitContext(self.db)

	def flush(self):
		'''Flushes all database content. Can be used before calling
		update() to have a clean re-build. However, this method does not
		generate signals, so it is not safe to use while a PageTreeStore
		is connected to the index.
		'''
		logger.info('Flushing index')

		# Drop queues
		self._update_pagelist_queue = []
		self._index_page_queue = []

		# Drop data
		for table in ('pages', 'pagetypes', 'links', 'linktypes'):
			self.db.execute('drop table "%s"' % table)
		self.db.executescript(SQL_CREATE_TABLES)

		# Create root node
		cursor = self.db.cursor()
		cursor.execute('insert into pages(basename, parent, hascontent, haschildren) values (?, ?, ?, ?)', ('', 0, False, False))
		assert cursor.lastrowid == 1, 'BUG: Primary key should start counting at 1'

		self.db.commit()

	def _flush_queue(self, path):
		# Removes any pending updates for path and it's children
		name = path.name
		namespace = name + ':'
		keep = lambda p: not (p.name == name or p.name.startswith(namespace))
		self._update_pagelist_queue = filter(keep, self._update_pagelist_queue)
		self._index_page_queue = filter(keep, self._index_page_queue)

	def update(self, path=None, background=False, checkcontents=True, callback=None):
		'''This method initiates a database update for a namespace, or,
		if no path is given for the root namespace of the notebook. For
		each path the indexkey as provided by the notebook store will be checked
		to decide if an update is needed. Note that if we have a new index which
		is still empty, updating will build the contents.

		If "background" is True the update will be scheduled on idle events
		in the glib / gtk main loop. Starting a second background job while
		one is already running just adds the new path in the queue.

		If "checkcontents" is True the indexkey for each page is checked to
		determine if the contents also need to be indexed. If this option
		is False only pagelists will be updated. Any new pages that are
		encoutered are always indexed fully regardless of this option.

		A callback method can be supplied that will be called after each
		updated path. This can be used e.g. to display a progress bar. the
		callback gets the path just processed as an argument. If the callback
		returns False the update will not continue.

		Indexes are checked width first. This is important to make the visual
		behavior of treeviews displaying the index look more solid.
		'''

		# Updating uses two queues, one for indexing the tree structure and a
		# second for pages where we need to index the content. Reason is that we
		# first need to have the full tree before we can reliably resolve links
		# and thus index content.

		if path is None:
			path = Path(':')

		indexpath = self.lookup_path(path)
		if indexpath is None:
			indexpath = self.touch(path)
			indexpath._row['haschildren'] = True
			indexpath._row['childrenkey'] = None
			checkcontent = True

		self._flush_queue(path)
		self._update_pagelist_queue.append(indexpath)
		if checkcontents and not indexpath.isroot:
			self._index_page_queue.append(indexpath)

		if not self.updating:
			self.emit('start-update')

		if background:
			if not self.updating:
				# Start new queue
				logger.info('Starting background index update')
				self.updating = True
				self._checkcontents = checkcontents
				gobject.idle_add(self._do_update, (checkcontents, callback))
			# Else let running queue pick it up
		else:
			logger.info('Updating index')
			if self.updating:
				checkcontents = checkcontents or self._checkcontents
			while self._do_update((checkcontents, callback)):
				continue

	def ensure_update(self, callback=None):
		'''Wait till any background update is finished'''
		if self.updating:
			logger.info('Ensure index updated')
			while self._do_update((self._checkcontents, callback)):
				continue
		else:
			return

	def _do_update(self, data):
		# This returns boolean to continue or not because it can be called as an
		# idle event handler, if a callback is used, the callback should give
		# this boolean value.
		# TODO can we add a percentage to the callback ?
		# set it to None while building page listings, but set
		# percentage once max of pageindex list is known
		checkcontents, callback = data
		if self._update_pagelist_queue or self._index_page_queue:
			try:
				if self._update_pagelist_queue:
					path = self._update_pagelist_queue.pop(0)
					self._update_pagelist(path, checkcontents)
				elif self._index_page_queue:
					path = self._index_page_queue.pop(0)
					page = self.notebook.get_page(path)
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
					logger.info('Index update is cancelled')
					self._update_pagelist_queue = [] # flush
					self._index_page_queue = [] # flush
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
			self.updating = False
			self.emit('end-update')
			return False

	def touch(self, path):
		'''This method creates a path along with all it's parents.
		Returns the final IndexPath. Path is created as a palceholder which
		has neither content or children.
		'''
		with self.db_commit:
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
						'insert into pages(basename, parent, hascontent, haschildren) values (?, ?, ?, ?)',
						(names[i], parentid, False, haschildren))
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
				self.db.execute('update pages set haschildren = ? where id == ?', (True, lastparent.id))
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
		seen = set()
		hadcontent = path.hascontent
		with self.db_commit:
			self.db.execute('delete from links where source==?', (path.id,))

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

					if link != page and not link.name in seen:
						# Filter out self refering links and remove doubles
						seen.add(link.name)
						indexpath = self.lookup_path(link)
						if indexpath is None:
							indexpath = self.touch(link)

						self.db.execute(
							'insert into links (source, href) values (?, ?)',
							(path.id, indexpath.id) )

			key = self.notebook.get_page_indexkey(page)
			self.db.execute(
				'update pages set hascontent=?, contentkey=? where id==?',
				(page.hascontent, key, path.id) )

		#~ print '!! PAGE-INDEX', path
		# We don't use page-updated here to avoid triggering the
		#~ self.emit('page-indexed', page, path)

		path = self.lookup_data(path) # refresh
		if hadcontent != path.hascontent:
			self.emit('page-updated', path)

	def _update_pagelist(self, path, checkcontent):
		'''Checks and updates the pagelist for a path if needed and queues any
		child pages for updating based on "checkcontents" and whether
		the child has children itself. Called indirectly by update().
		'''
		#~ print '!! UPDATE LIST', path, path._indexpath
		assert isinstance(path, IndexPath)
		if not path.hasdata:
			path = path.lookup_data(path)
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

		def check_and_queue(child, rawchild):
			# Helper function to queue individual children
			if child.haschildren:
				self._update_pagelist_queue.append(child)
			elif checkcontent:
				pagekey = self.notebook.get_page_indexkey(rawchild or child)
				if not (pagekey and child.contentkey == pagekey):
					self._index_page_queue.append(child)

		listkey = self.notebook.get_pagelist_indexkey(rawpath)
		uptodate = listkey and path.childrenkey == listkey

		cursor = self.db.cursor()
		cursor.execute('select * from pages where parent==?', (path.id,))

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
			with self.db_commit:
				for page in self.notebook.get_pagelist(rawpath):
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
								'update pages set hascontent=?, contentkey=NULL where id==?',
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
						# We set haschildren to False untill we have actualy seen those
						# children. Failing to do so will cause trouble with the
						# gtk.TreeModel interface to the database, which can not handle
						# nodes that say they have children but fail to deliver when
						# asked.
						cursor = self.db.cursor()
						cursor.execute(
							'insert into pages(basename, parent, hascontent, haschildren) values (?, ?, ?, ?)',
							(page.basename, path.id, page.hascontent, False))
						child = IndexPath(page.name, indexpath + (cursor.lastrowid,),
							{	'hascontent': page.hascontent,
								'haschildren': page.haschildren,
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
							'update pages set hascontent=0, contentkey=NULL where id==?', (child.id,))
							# If you're not in the pagelist, you don't have content
						changes.append((child, 2))
						if child.haschildren:
							self._update_pagelist_queue.append(child)
					else:
						delete.append(child)

				# Update index key to reflect we did our updates
				haschildren = len(seen) + len(keep) > 0
				self.db.execute(
					'update pages set childrenkey=?, haschildren=?, hascontent=? where id==?',
					(listkey, haschildren, hascontent, path.id) )

				# ... commit

			path = self.lookup_data(path) # refresh
			if not path.isroot and (hadchildren != path.haschildren):
				self.emit('page-haschildren-toggled', path)

			if not path.isroot and (hadcontent != path.hascontent):
				self.emit('page-updated', path)

			# All these signals should come in proper order...
			changes.sort(key=lambda c: c[0].basename)
			for child, action in changes:
				if action == 1:
					self.emit('page-inserted', child)
				else: # action == 2:
					self.emit('page-updated', child)

			# Clean up pages that disappeared
			for child in delete:
				self.emit('delete', child)

			# ... we are followed by an cleanup_all() when indexing is done

	def delete(self, path):
		'''Delete page plus sub-pages plus forward links from the index'''
		indexpath = self.lookup_path(path)
		if indexpath:
			links = self._get_placeholders(indexpath, recurs=True)
			self.emit('delete', indexpath)
			self.cleanup(indexpath.parent)
			for link in links:
				self.cleanup(link)

	def do_delete(self, path):
		# Tries to delete path and all of it's children, but keeps
		# pages that are placeholders and their parents
		self._flush_queue(path)

		root = path
		paths = [root]
		paths.extend(list(self.walk(root)))

		# Clean up links and content
		with self.db_commit:
			for path in paths:
				self.db.execute('delete from links where source=?', (path.id,))
				self.db.execute('update pages set hascontent=0, contentkey=NULL where id==?', (path.id,))

		# Clean up any nodes that are not a link
		paths.reverse() # process children first
		delete = []
		keep = []
		toggled = []
		for path in paths:
			with self.db_commit:
				hadchildren = path.haschildren
				haschildren = self.n_list_pages(path) > 0
				if haschildren or self.n_list_links(path, direction=LINK_DIR_BACKWARD):
					# Keep but check haschildren
					keep.append(path)
					self.db.execute(
						'update pages set haschildren=?, childrenkey=NULL where id==?',
						(haschildren, path.id) )
					if hadchildren != haschildren:
						toggled.append(path)
				else:
					# Delete
					delete.append(path)
					self.db.execute('delete from pages where id=?', (path.id,))
			self.lookup_data(path) # refresh

		if keep:
			# signal per child
			for path in delete:
				self.emit('page-deleted', path)
			for path in toggled:
				self.emit('page-haschildren-toggled', path)
			for path in keep:
				self.emit('page-updated', path)
		else:
			# signal once
			root = self.lookup_data(root) # refresh
			self.emit('page-deleted', root)

		parent = root.parent
		if not parent.isroot and self.n_list_pages(parent) == 0:
			with self.db_commit:
				self.db.execute(
					'update pages set haschildren=0, childrenkey=NULL where id==?',
					(parent.id,) )
				parent = self.lookup_data(parent)
			self.emit('page-haschildren-toggled', parent)

	def cleanup(self, path):
		'''Delete path if it has no content, no children and is
		not linked by any other page.
		'''
		if path.isroot:
			return

		parent = path.parent
		if isinstance(path, IndexPath):
			path = self.lookup_data(path)
		else:
			path = self.lookup_path(path)
			if not path:
				self.cleanup(parent) # recurs

		if not (path.hascontent or path.haschildren) \
		and self.n_list_links(path, direction=LINK_DIR_BACKWARD) == 0:
			self.emit('delete', path)
			self.cleanup(parent) # recurs

	def cleanup_all(self):
		'''Find and cleanup any pages without content, children and
		backlinks.
		'''
		cursor = self.db.cursor()
		cursor.execute(
			'select id from pages where hascontent=0 and haschildren=0')
		for row in cursor:
			path = self.lookup_id(row['id'])
			self.cleanup(path)

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
		cursor.execute('select * from pages where parent == ? order by lower(basename)', (path.id,))
			# FIXME, this lower is not utf8 proof
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
		If path is not indexed this method returns None.
		'''
		# Constructs the indexpath downward
		if isinstance(path, IndexPath):
			if not path.hasdata:
				return self.lookup_data(path)
			else:
				return path
		elif path.isroot:
			cursor = self.db.cursor()
			cursor.execute('select * from pages where id==?', (ROOT_ID,))
			row = cursor.fetchone()
			return IndexPath(':', (ROOT_ID,), row)

		if parent:
			indexpath = list(parent._indexpath)
		elif hasattr(path, '_indexpath'):
			# Page objects copy the _indexpath attribute
			# FIXME can this cause issues when the index is modified in between ?
			indexpath = list(path._indexpath)
		else:
			indexpath = [ROOT_ID]

		names = path.name.split(':')
		names = names[len(indexpath)-1:] # shift X items
		parentid = indexpath[-1]

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

	def lookup_data(self, path):
		'''Returns a full IndexPath for a IndexPath that has 'hasdata'
		set to False.
		'''
		cursor = self.db.cursor()
		cursor.execute('select * from pages where id==?', (path.id,))
		path._row = cursor.fetchone()
		#~ assert path._row, 'Path does not exist: %s' % path
		return path

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
			myrow = cursor.fetchone()
			names.insert(0, myrow['basename'])
			parent = myrow['parent']

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
			parentid = ROOT_ID
			indexpath = [ROOT_ID]

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
			parentid = ROOT_ID
			name = ''
			indexpath = (ROOT_ID,)
		else:
			path = self.lookup_path(path)
			if path is None:
				return []
			parentid = path.id
			name = path.name
			indexpath = path._indexpath

		cursor = self.db.cursor()
		cursor.execute('select * from pages where parent==? order by lower(basename)', (parentid,))
			# FIXME, this lower is not utf8 proof
		return [
			IndexPath(name+':'+r['basename'], indexpath+(r['id'],), r)
				for r in cursor ]

	def n_list_pages(self, path):
		'''Returns the number of pages below path'''
		# TODO optimize this one
		return len(self.list_pages(path))

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

	def n_list_links(self, path, direction=LINK_DIR_FORWARD):
		'''Like list_lins() but returns only the number of links instead
		of the links themselves.
		'''
		# TODO optimize this one
		return len(list(self.list_links(path, direction)))

	def get_previous(self, path, recurs=True):
		'''Returns the previous page in the index. If 'recurs' is False it stays
		in the same namespace as path, but by default it crossing namespaces and
		walks the whole tree.
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
					prev = self.list_pages(prev)[-1]
			return prev

	def _get_prev(self, path):
		'''Atomic function for get_previous()'''
		pagelist = self.list_pages(path.parent)
		i = pagelist.index(path)
		if i > 0:
			return pagelist[i-1]
		else:
			return None

	def get_next(self, path, recurs=True):
		'''Returns the next page in the index. If 'recurs' is False it stays
		in the same namespace as path, but by default it crossing namespaces and
		walks the whole tree.
		'''
		path = self.lookup_path(path)
		if path is None or path.isroot:
			return None

		if not recurs:
			return self._get_next(path)
		elif path.haschildren:
			# descent to first child
			return self.list_pages(path)[0]
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
		'''Atomic function for get_next()'''
		pagelist = self.list_pages(path.parent)
		i = pagelist.index(path)
		if i+1 < len(pagelist):
			return pagelist[i+1]
		else:
			return None

	def get_unique_path(self, suggestedpath):
		'''Find a non existing path based on 'path' - basically just adds
		an integer until we hit a path that does not exist.
		'''
		path = self.lookup_path(suggestedpath)
		if path is None: return suggestedpath
		elif path.isroot:
			raise LookupError, 'Can not create new top level path'
		else:
			cursor = self.db.cursor()
			cursor.execute('select basename from pages where basename like ? and parent==?',
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
	'''Wrapper for access to the meta table with properties'''

	def __init__(self, db):
		self.db = db

	def __setitem__(self, k, v):
		cursor = self.db.cursor()
		cursor.execute('delete from meta where key=?', (k,))
		cursor.execute('insert into meta(key, value) values (?, ?)', (k, v))
		self.db.commit()

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
