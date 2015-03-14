# -*- coding: utf-8 -*-

# Copyright 2009-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from zim.notebook import HRef, \
	HREF_REL_ABSOLUTE, HREF_REL_FLOATING, HREF_REL_RELATIVE


from .base import IndexerBase, IndexViewBase
from .pages import PagesViewInternal, IndexPath


LINK_DIR_FORWARD = 1 #: Constant for forward links
LINK_DIR_BACKWARD = 2 #: Constant for backward links
LINK_DIR_BOTH = 3 #: Constant for links in any direction


class IndexLink(object):
	'''Class used to represent links between two pages

	@ivar source: L{IndexPath} object for the source of the link
	@ivar target: L{IndexPath} object for the target of the link
	'''

	__slots__ = ('source', 'target')

	def __init__(self, source, target):
		self.source = source
		self.target = target

	def __repr__(self):
		return '<%s: %s to %s>' % (self.__class__.__name__, self.source, self.target)


class LinksIndexer(IndexerBase):

	__signals__ = {}

	INIT_SCRIPT = '''
		CREATE TABLE if not exists links (
			source INTEGER REFERENCES pages(id),
			target INTEGER REFERENCES pages(id),

			-- attributes of a HRef object
			rel INTEGER,
			names TEXT,
			sortkeys TEXT,

			-- flag for the updater
			needscheck BOOLEAN DEFAULT 0,

			CONSTRAINT uc_LinkOnce UNIQUE (source, rel, sortkeys)
		);
	'''

	def __init__(self):
		IndexerBase.__init__(self)
		self._pages = PagesViewInternal()

	def on_new_page(self, db, indexpath):
		# TODO - refine this -- idem below in on_delete
		# - can we join tables and only flag links that have a plaeceholder as target?
		# - what about absolute links that may match a different case now ?
		db.execute(
			'UPDATE links SET needscheck=1 WHERE rel=? and sortkeys LIKE ?',
			(HREF_REL_FLOATING, '%:' + indexpath.sortkey + ':%',)
		)
		self._update_links(db)

	def on_index_page(self, db, indexpath, page):
		db.execute(
			'DELETE FROM links WHERE source=?',
			(indexpath.id,)
		)
		for href in page.iter_page_href():
			self.insert_for_page(db, indexpath, href)

	def on_delete_page(self, db, indexpath):
		db.execute(
			'UPDATE links SET needscheck=1 WHERE target=?',
			(indexpath.id,)
		)
		# TODO refine - see comment above in on_new
		db.execute(
			'UPDATE links SET needscheck=1 WHERE rel=? and sortkeys LIKE ?',
			(HREF_REL_FLOATING, '%:' + indexpath.sortkey + ':%',)
		)
		db.execute(
			'DELETE FROM links WHERE source=?',
			(indexpath.id,)
		)
		self._update_links(db)

	def _update_links(self, db):
		# TODO: should thid be in the queue ? Seems potential heavy operation, even though all on index

		# Order of processig is important here for stability of the index
		# e.g. two placeholders with different case
		for row in db.execute(
			'SELECT * FROM links WHERE needscheck=1 ORDER BY sortkeys, names'
		):
			source = self._pages.lookup_by_id(db, row['source'])
			href = HRef(row['rel'], row['names'], row['sortkeys'])
			target = self._pages.resolve_link(db, source, href)
			if not isinstance(target, IndexPath):
				print 'TODO touch placeholder', target
				continue

			db.execute(
				'UPDATE links SET target=?, needscheck=? WHERE source=? and names=?',
				(target.id, False, row['source'], row['names'])
			)

	def insert_for_page(self, db, source, href):
		target = self._pages.resolve_link(db, source, href)
		if not isinstance(target, IndexPath):
			print 'TODO touch placeholder', target
			return

		db.execute(
			'INSERT INTO links(source, target, rel, names, sortkeys) ' \
			'VALUES (?, ?, ?, ?, ?)',
			(source.id, target.id, href.rel, href.names, href.sortkeys)
		)


class LinksView(IndexViewBase):

	def __init__(self, db_context):
		IndexViewBase.__init__(self, db_context)
		self._pages = PagesViewInternal()

	def list_links(self, path, direction=LINK_DIR_FORWARD):
		'''Generator listing links between pages

		@param path: the L{Path} for which to list links
		@param direction: the link direction to be listed. This can be
		one of:
			- C{LINK_DIR_FORWARD}: for links from path
			- C{LINK_DIR_BACKWARD}: for links to path
			- C{LINK_DIR_BOTH}: for links from and to path
		@returns: yields L{IndexLink} objects
		@raises IndexNotFoundError: if C{path} is not found in the index
		'''
		with self._db as db:
			indexpath = self._pages.lookup_by_pagename(db, path)
			for link in self._list_links(db, indexpath, direction):
				yield link

	def list_links_section(self, path, direction=LINK_DIR_FORWARD):
		# Can be optimized with WITH clause, but not supported sqlite < 3.8.4
		with self._db as db:
			indexpath = self._pages.lookup_by_pagename(db, path)
			for link in self._list_links(db, indexpath, direction):
				yield link
			for child in self._pages.walk(indexpath):
				for link in self._list_links(db, child, direction):
					yield link

	def _list_links(self, db, indexpath, direction):
		if direction == LINK_DIR_FORWARD:
			c = db.execute(
				'SELECT DISTINCT source, target FROM links '
				'WHERE source = ?', (indexpath.id,)
			)
		elif direction == LINK_DIR_BOTH:
			c = db.execute(
				'SELECT DISTINCT source, target FROM links '
				'WHERE source = ? or target = ?', (indexpath.id, indexpath.id)
			)
		else:
			c = db.execute(
				'SELECT DISTINCT source, target FROM links '
				'WHERE target = ?', (indexpath.id,)
			)

		for row in c:
			if row['source'] == indexpath.id:
				source = indexpath
				target = self._pages.lookup_by_id(db, row['target'])
			else:
				source = self._pages.lookup_by_id(db, row['source'])
				target = indexpath

			yield IndexLink(source, target)

	def n_list_links(self, path, direction=LINK_DIR_FORWARD):
		with self._db as db:
			indexpath = self._pages.lookup_by_pagename(db, path)
			return self._n_list_links(db, indexpath, direction)

	def n_list_links_section(self, path, direction=LINK_DIR_FORWARD):
		# Can be optimized with WITH clause, but not supported sqlite < 3.8.4
		with self._db as db:
			indexpath = self._pages.lookup_by_pagename(db, path)
			n = self._n_list_link(db, indexpath, direction)
			for child in self._pages.walk(indexpath):
				n += self._n_list_links(db, child)
			return n

	def _n_list_links(self, db, indexpath, direction):
		if direction == LINK_DIR_FORWARD:
			c = db.execute(
				'SELECT count(*) FROM links '
				'WHERE source=?', (indexpath.id,)
			)
		elif direction == LINK_DIR_BOTH:
			c = db.execute(
				'SELECT count(*) FROM links '
				'WHERE source=? or target=?', (indexpath.id, indexpath.id)
			)
		else:
			c = db.execute(
				'SELECT count(*) FROM links '
				'WHERE target=?', (indexpath.id,)
			)

		return c.fetchone()[0]

