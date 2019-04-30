
# Copyright 2009-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>



import logging

logger = logging.getLogger('zim.notebook.index')


from zim.utils import natural_sort_key
from zim.notebook.page import Path, HRef, \
	HREF_REL_ABSOLUTE, HREF_REL_FLOATING, HREF_REL_RELATIVE


from .base import IndexerBase, IndexView, IndexNotFoundError
from .pages import PagesViewInternal, ROOT_ID


LINK_DIR_FORWARD = 1 #: Constant for forward links
LINK_DIR_BACKWARD = 2 #: Constant for backward links
LINK_DIR_BOTH = 3 #: Constant for links in any direction


# Links come in 3 flavors:
# 1/ HREF_REL_ABSOLUTE - starting from the top level e.g. ":foo"
# 2/ HREF_REL_FLOATING - relative to the source namespace, or parents, e.g. "foo"
# 3/ HREF_REL_RELATIVE - below the source page, e.g. "+foo"
#
# If the target page does not exist, a "placeholder" is created for this
# page.
#
# Floating links are resolved to existing pages in parent namespaces
# therefore they may need to be recalculated when pages of the same name
# are created or deleted. This is done by the 'anchorkey' field in the
# links table.
# To avoid circular dependencies between the existance of placeholder
# pages and links, floating links do /not/ resolve to placeholders,
# but only to existing links.
# (Else we would need to drop all placeholders and
# re-calculate all links on every page index to ensure the outcome.)



class IndexLink(object):
	'''Class used to represent links between two pages

	@ivar source: L{Path} object for the source of the link
	@ivar target: L{Path} object for the target of the link
	'''

	__slots__ = ('source', 'target')

	def __init__(self, source, target):
		self.source = source
		self.target = target

	def __repr__(self):
		return '<%s: %s to %s>' % (self.__class__.__name__, self.source, self.target)


class LinksIndexer(IndexerBase):

	__signals__ = {}

	def __init__(self, db, pagesindexer):
		IndexerBase.__init__(self, db)
		self._pages = PagesViewInternal(db)
		self._pagesindexer = pagesindexer
		self.connectto_all(pagesindexer, (
			'page-row-inserted', 'page-row-changed', 'page-row-deleted',
			'page-changed'
		))

		self.db.execute('''
			CREATE TABLE IF NOT EXISTS links (
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
		''')

	def on_page_changed(self, o, row, doc):
		# Drop links for this page and add new ones (don't bother
		# determining delta and updating).
		self.db.execute(
			'DELETE FROM links WHERE source=?',
			(row['id'],)
		)
		for href in doc.iter_href():
			anchorkey = natural_sort_key(href.parts()[0])
			self.db.execute(
				'INSERT INTO links(source, target, rel, names, anchorkey, needscheck) '
				'VALUES (?, ?, ?, ?, ?, ?)',
				(row['id'], ROOT_ID, href.rel, href.names, anchorkey, 1)
			)

	def on_page_row_inserted(self, o, row):
		# Placeholders for pages of the same name need to be
		# recalculated, flag links to be checked with same anchorkey.
		if not row['is_link_placeholder']:
			self.db.execute( # NOTE using subquery because sqlite does not have JOIN for UPDATE
				'UPDATE links SET needscheck=1 '
				'WHERE rel=? and anchorkey=? and target in ( '
				'	SELECT id FROM pages WHERE is_link_placeholder=1 '
				')',
				(HREF_REL_FLOATING, row['sortkey'])
			)

	def on_page_row_changed(self, o, newrow, oldrow):
		if oldrow['is_link_placeholder'] and not newrow['is_link_placeholder']:
			self.on_page_row_inserted(o, newrow)

	def on_page_row_deleted(self, o, row):
		# Drop all outgoing links, flag incoming links to be checked.
		# Check could result in page being re-created as placeholder
		# at end of db update.
		if not row['is_link_placeholder']:
			self.db.execute(
				'DELETE FROM links WHERE source=?',
				(row['id'],)
			)
			self.db.execute(
				'UPDATE links SET needscheck=1, target=? WHERE target=?',
				(ROOT_ID, row['id'],)
			) # Need to link somewhere, if target is gone, use ROOT instead

	def is_uptodate(self):
		row = self.db.execute(
			'SELECT * FROM links WHERE needscheck=1 '
		).fetchone()
		return row is None

	def update_iter(self):
		# Check for ghost links - warn but still clean them up
		for row in self.db.execute('''
			SELECT DISTINCT pages.* FROM pages INNER JOIN links ON pages.id=links.source
			WHERE pages.source_file IS NULL
		''').fetchall():
			logger.warn('Found ghost links from: %s', row['name'])
			self.on_page_row_deleted(None, row)
			yield

		# Check total
		n, = self.db.execute('SELECT COUNT(*) FROM links WHERE needscheck=1').fetchone()

		# Resolve pending links
		for i, row in enumerate(self.db.execute(
			'SELECT * FROM links WHERE needscheck=1 '
			'ORDER BY anchorkey, names'
		)):
			if i > 0 and i % 100 == 0:
				self.db.commit()
				logger.debug('Update link %i of %i', i, n)

			href = HRef(row['rel'], row['names'])
			source = self._pages.get_pagename(row['source'])
			target_id, targetname = self._pages.resolve_link(source, href, source_id=row['source'])
			if target_id is None:
				target_id = self._pagesindexer.insert_link_placeholder(targetname)

			self.db.execute(
				'UPDATE links SET target=?, needscheck=0 WHERE source=? and names=? and rel=?',
				(target_id, row['source'], row['names'], row['rel'])
			)
			yield

		# Delete un-used placeholders
		for row in self.db.execute('''
			SELECT pages.id FROM pages LEFT JOIN links ON pages.id=links.target
			WHERE pages.is_link_placeholder=1 and pages.n_children=0 and links.source IS NULL
		'''):
			pagename = self._pages.get_pagename(row['id'])
			self._pagesindexer.remove_page(pagename, self._allow_cleanup)
			yield

			# The allow_cleanup function checks whether a parent has links or not.
			# Without this guard function we would need to iterate several times
			# through this cleanup function.

		self.db.commit()

	def _allow_cleanup(self, row):
		c, = self.db.execute(
			'SELECT COUNT(*) FROM links WHERE target=?', (row['id'],)
		).fetchone()
		return c == 0



class LinksView(IndexView):

	def __init__(self, db):
		IndexView.__init__(self, db)
		self._pages = PagesViewInternal(db)

	def list_links(self, pagename, direction=LINK_DIR_FORWARD):
		'''Generator listing links between pages

		@param pagename: the L{Path} for which to list links
		@param direction: the link direction to be listed. This can be
		one of:
			- C{LINK_DIR_FORWARD}: for links from path
			- C{LINK_DIR_BACKWARD}: for links to path
			- C{LINK_DIR_BOTH}: for links from and to path
		@returns: yields L{IndexLink} objects
		@raises IndexNotFoundError: if C{path} is not found in the index
		'''
		page_id = self._pages.get_page_id(pagename) # can raise IndexNotFoundError
		return self._list_links(page_id, pagename, direction)

	def _list_links(self, page_id, pagename, direction):
		if direction == LINK_DIR_FORWARD:
			c = self.db.execute(
				'SELECT DISTINCT source, target FROM links '
				'WHERE source = ?', (page_id,)
			)
		elif direction == LINK_DIR_BOTH:
			c = self.db.execute(
				'SELECT DISTINCT source, target FROM links '
				'WHERE source = ? or target = ?', (page_id, page_id)
			)
		else:
			c = self.db.execute(
				'SELECT DISTINCT source, target FROM links '
				'WHERE target = ?', (page_id,)
			)

		for row in c:
			if row['source'] == page_id:
				source = pagename
				target = self._pages.get_pagename(row['target'])
			elif row['source'] == ROOT_ID:
				continue # hack used to create placeholders
			else:
				source = self._pages.get_pagename(row['source'])
				target = pagename

			yield IndexLink(source, target)

	def n_list_links(self, pagename, direction=LINK_DIR_FORWARD):
		page_id = self._pages.get_page_id(pagename)
		return self._n_list_links(page_id, direction)

	def _n_list_links(self, page_id, direction):
		if direction == LINK_DIR_FORWARD:
			c = self.db.execute(
				'SELECT count(*) FROM links '
				'WHERE source=?', (page_id,)
			)
		elif direction == LINK_DIR_BOTH:
			c = self.db.execute(
				'SELECT count(*) FROM links '
				'WHERE source=? or (target=? and source<>?)', (page_id, page_id, ROOT_ID)
					# Excluding root here because linking from root
					# is used as a hack to create placeholders
			)
		else:
			c = self.db.execute(
				'SELECT count(*) FROM links '
				'WHERE target=? and source<>?', (page_id, ROOT_ID)
					# Excluding root here because linking from root
					# is used as a hack to create placeholders
			)

		return c.fetchone()[0]

	def list_links_section(self, pagename, direction=LINK_DIR_FORWARD):
		page_id = self._pages.get_page_id(pagename)
		return self._list_links_section(page_id, pagename, direction)

	def _list_links_section(self, page_id, pagename, direction):
		# Can be optimized with WITH clause, but not supported sqlite < 3.8.4

		for link in self._list_links(page_id, pagename, direction):
			yield link

		for child in self._pages.walk(page_id):
			for link in self._list_links(child.id, child, direction):
				yield link

	def n_list_links_section(self, pagename, direction=LINK_DIR_FORWARD):
		# Can be optimized with WITH clause, but not supported sqlite < 3.8.4
		page_id = self._pages.get_page_id(pagename)
		n = self._n_list_links(page_id, direction)
		for child in self._pages.walk(page_id):
			n += self._n_list_links(child.id, direction)
		return n

	def list_floating_links(self, basename):
		anchorkey = natural_sort_key(basename)
		for row in self.db.execute(
			'SELECT DISTINCT source, target FROM links '
			'WHERE rel=? and anchorkey=?',
			(HREF_REL_FLOATING, anchorkey)
		):
			target = self._pages.get_pagename(row['target'])
			source = self._pages.get_pagename(row['source'])
			yield IndexLink(source, target)
