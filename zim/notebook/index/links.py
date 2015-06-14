# -*- coding: utf-8 -*-

# Copyright 2009-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement


from zim.utils import natural_sort_key
from zim.notebook.page import HRef, \
	HREF_REL_ABSOLUTE, HREF_REL_FLOATING, HREF_REL_RELATIVE


from .base import IndexerBase, IndexViewBase
from .pages import PagesViewInternal, IndexPath, \
	ROOT_ID, PAGE_EXISTS_AS_LINK


LINK_DIR_FORWARD = 1 #: Constant for forward links
LINK_DIR_BACKWARD = 2 #: Constant for backward links
LINK_DIR_BOTH = 3 #: Constant for links in any direction


# Links come in 3 flavors:
# 1/ HREF_REL_ABSOLUTE - starting from the top level e.g. ":foo"
# 2/ HREF_REL_FLOATING - relative to the source namespace, or parents, e.g. "foo"
# 3/ HREF_REL_RELATIVE - below the source page, e.g. "+foo"
#
# If the target page does not exist, a "placeholder" is created for this
# page with the flag PAGE_EXISTS_AS_LINK.
#
# Floating links are resolved to existing pages in parent namespaces
# therefore they may need to be recalculated when pages of the same name
# are created or deleted. This is done by the 'anchorkey' field in the
# links table.
# To avoid circular dependencies between the existance of placeholder
# pages and links, floating links do /not/ resolve to placeholders in
# parent namespaces. (Else we would need to drop all placeholders and
# re-calculate all links on every page index to ensure the outcome.)


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


class StateFlag(object):

	def __init__(self):
		self._state = False

	def __nonzero__(self):
		return self._state

	def __enter__(self):
		self._state = True

	def __exit__(self, *a):
		self._state = False


class LinksIndexer(IndexerBase):

	__signals__ = {}

	INIT_SCRIPT = '''
		CREATE TABLE if not exists links (
			source INTEGER REFERENCES pages(id),
			target INTEGER REFERENCES pages(id),

			-- attributes of a HRef object
			rel INTEGER,
			names TEXT,

			-- sortkey of anchor for floating HRef
			anchorkey TEXT,

			-- flag for the updater
			needscheck BOOLEAN DEFAULT 0,

			CONSTRAINT uc_LinkOnce UNIQUE (source, rel, names)
		);
	'''

	def __init__(self):
		IndexerBase.__init__(self)
		self._pages = PagesViewInternal()
		self._recursing = StateFlag()

	def on_new_page(self, index, db, indexpath):
		db.execute(
			'UPDATE links SET needscheck=1 '
			'WHERE rel=? and anchorkey=? '
			'AND target in (SELECT id FROM pages WHERE page_exists=?)',
			(HREF_REL_FLOATING, indexpath.sortkey, PAGE_EXISTS_AS_LINK)
		)
		self.check_links(index, db)

	def on_index_page(self, index, db, indexpath, page):
		db.execute(
			'DELETE FROM links WHERE source=?',
			(indexpath.id,)
		)

		for href in page.iter_page_href():
			target = self._pages.resolve_link(db, indexpath, href)
			if not isinstance(target, IndexPath):
				target = self.touch_placeholder(index, db, target)

			anchorkey = natural_sort_key(href.parts()[0])
			db.execute(
				'INSERT INTO links(source, target, rel, names, anchorkey) '
				'VALUES (?, ?, ?, ?, ?)',
				(indexpath.id, target.id, href.rel, href.names, anchorkey)
			)

		self.cleanup_placeholders(index, db)

	def on_moved_page(self, index, db, indexpath, oldpath):
		db.execute(
			'UPDATE links SET needscheck=1 WHERE source=? or target=?',
			(indexpath, indexpath)
		)
		for child in self._pages.walk(indexpath):
			db.execute(
				'UPDATE links SET needscheck=1 WHERE source=? or target=?',
				(child, child)
			)
		self.check_links(index, db)

	def on_delete_page(self, index, db, indexpath):
		db.execute(
			'DELETE FROM links WHERE source=?',
			(indexpath.id,)
		)
		db.execute(
			'UPDATE links SET needscheck=1, target=? WHERE target=?',
			(ROOT_ID, indexpath.id,)
		) # Need to link somewhere, if target is gone, use ROOT instead

	def on_deleted_page(self, index, db, parent, basename):
		self.check_links(index, db)
			# Can result in page being resurrected as placeholder for link target

	def check_links(self, index, db):
		if self._recursing:
			return # Result from touch path for placeholders

		for row in db.execute(
			'SELECT * FROM links WHERE needscheck=1 '
			'ORDER BY anchorkey, names'
		):
			source = self._pages.lookup_by_id(db, row['source'])
			href = HRef(row['rel'], row['names'])
			target = self._pages.resolve_link(db, source, href)
			if not isinstance(target, IndexPath):
				target = self.touch_placeholder(index, db, target)
			db.execute(
				'UPDATE links SET target=?, needscheck=? WHERE source=? and names=?',
				(target.id, False, row['source'], row['names'])
			)

		self.cleanup_placeholders(index, db)

	def cleanup_placeholders(self, index, db):
		for row in db.execute(
			'SELECT pages.id '
			'FROM pages LEFT JOIN links ON pages.id=links.target '
			'WHERE pages.page_exists=? and pages.n_children=0 and links.source IS NULL ',
			(PAGE_EXISTS_AS_LINK,)
		):
			indexpath = self._pages.lookup_by_id(db, row['id'])
			index.delete_page(db, indexpath, cleanup=True)

	def touch_placeholder(self, index, db, target):
		with self._recursing:
			# Create placeholder for link target
			target = index.touch_path(db, target)
			index.set_page_exists(db, target, PAGE_EXISTS_AS_LINK)
			#~ print "Touch target", target
			return target


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
			for child in self._pages.walk(db, indexpath):
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
			n = self._n_list_links(db, indexpath, direction)
			for child in self._pages.walk(db, indexpath):
				n += self._n_list_links(db, child, direction)
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

	def list_floating_links(self, name):
		with self._db as db:
			for row in db.execute(
				'SELECT DISTINCT source, target FROM links '
				'WHERE names=? or names LIKE ?',
				(name, name + ':%')
			):
				target = self._pages.lookup_by_id(db, row['target'])
				source = self._pages.lookup_by_id(db, row['source'])
				yield IndexLink(source, target)
