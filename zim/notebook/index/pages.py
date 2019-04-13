
# Copyright 2009-2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>


from datetime import datetime

import sqlite3
import logging

logger = logging.getLogger('zim.notebook.index')

from zim.utils import natural_sort_key
from zim.notebook.page import Path, HRef, \
	HREF_REL_ABSOLUTE, HREF_REL_FLOATING, HREF_REL_RELATIVE
from zim.tokenparser import TokenBuilder

from zim.formats import ParseTreeBuilder

from .base import *


from zim.notebook.layout import \
FILE_TYPE_PAGE_SOURCE, \
FILE_TYPE_ATTACHMENT

ROOT_PATH = Path(':')
ROOT_ID = 1 # Constant for the ID of the root namespace in "pages"
			# (Primary key starts count at 1 and first entry will be root)

PAGE_EXISTS_UNCERTAIN = 0 # e.g. folder with unknown children - not shown to outside world
PAGE_EXISTS_AS_LINK = 1 # placeholder for link target
PAGE_EXISTS_HAS_CONTENT = 2 # either has content or children have content


def emptyParseTree():
	b = ParseTreeBuilder()
	b.start('zim-tree')
	b.end('zim-tree')
	return b.get_parsetree()


class PagesIndexer(IndexerBase):
	'''Indexer for the "pages" table.

	@signal: C{page-row-inserted (row)}: new row inserted
	@signal: C{page-row-changed (row, oldrow)}: row changed
	@signal: C{page-row-delete (row)}: row to be deleted
	@signal: C{page-row-deleted (row)}: row that has been deleted

	@signal: C{page-changed (row, content)}: page contents changed
	'''

	__signals__ = {
		'page-row-inserted': (None, None, (object,)),
		'page-row-changed': (None, None, (object, object)),
		'page-row-delete': (None, None, (object,)),
		'page-row-deleted': (None, None, (object,)),
		'page-changed': (None, None, (object, object))
	}

	def __init__(self, db, layout, filesindexer):
		IndexerBase.__init__(self, db)
		self.layout = layout
		self.connectto_all(filesindexer, (
			'file-row-inserted', 'file-row-changed', 'file-row-deleted'
		))

		self.db.executescript('''
			CREATE TABLE IF NOT EXISTS pages(
				id INTEGER PRIMARY KEY,
				parent INTEGER REFERENCES pages(id),
				n_children INTEGER DEFAULT 0,

				name TEXT UNIQUE NOT NULL,
				lowerbasename TEXT NOT NULL,
				sortkey TEXT NOT NULL,
				mtime TIMESTAMP,

				source_file INTEGER REFERENCES files(id),
				is_link_placeholder BOOLEAN DEFAULT 0

				CONSTRAINT no_self_ref CHECK (parent <> id)
			);
			CREATE UNIQUE INDEX IF NOT EXISTS pages_name ON pages(name);
			CREATE INDEX IF NOT EXISTS pages_sortkey ON pages(sortkey);
			CREATE INDEX IF NOT EXISTS pages_parent ON pages(parent);
		''')
		row = self.db.execute('SELECT * FROM pages WHERE id == 1').fetchone()
		if row is None:
			c = self.db.execute(
				'INSERT INTO pages(parent, name, lowerbasename, sortkey, source_file) '
				'VALUES (?, ?, ?, ?, ?)',
				(0, '', '', '', 1)
			)
			assert c.lastrowid == 1 # ensure we start empty

	def _select(self, pagename):
		return self.db.execute(
			'SELECT * FROM pages WHERE name=?', (pagename.name,)
		).fetchone()

	# We should not read file contents on db-file-inserted because
	# there can be many in one iterarion when the FileIndexer indexes
	# a folder. Therefore we only send page-changed in response to
	# db-file-updated and trust we get this signal for each file
	# that is inserted in a separate iteration.

	def on_file_row_inserted(self, o, filerow):
		pagename, file_type = self.layout.map_filepath(filerow['path'])
		if file_type != FILE_TYPE_PAGE_SOURCE:
			return # nothing to do

		row = self._select(pagename)
		if row is None:
			self.insert_page(pagename, filerow['id'])
		elif row['source_file'] is None:
			self.db.execute(
				'UPDATE pages SET source_file=?, mtime=?, is_link_placeholder=? WHERE name=?',
				(filerow['id'], None, False, pagename.name)
			)
			self.update_parent(pagename.parent)
			newrow = self._select(pagename)
			self.emit('page-row-changed', newrow, row)
		else:
			# TODO: Flag conflict
			raise NotImplementedError

	def on_file_row_changed(self, o, filerow):
		pagename, file_type = self.layout.map_filepath(filerow['path'])
		if file_type != FILE_TYPE_PAGE_SOURCE:
			return # nothing to do

		row = self._select(pagename)
		assert row is not None

		if row['source_file'] == filerow['id']:
			file = self.layout.root.file(filerow['path'])
			format = self.layout.get_format(file)
			mtime = file.mtime()
			tree = format.Parser().parse(file.read())
			self.update_page(pagename, mtime, tree)
		else:
			pass # some conflict file changed

	def on_file_row_deleted(self, o, filerow):
		pagename, file_type = self.layout.map_filepath(filerow['path'])
		if file_type != FILE_TYPE_PAGE_SOURCE:
			return # nothing to do

		row = self._select(pagename)
		assert row is not None

		if row['source_file'] == filerow['id']:
			if row['n_children'] > 0:
				self.db.execute(
					'UPDATE pages SET source_file=?, mtime=? WHERE name=?',
					(None, None, pagename.name)
				)
				self.update_parent(pagename, oldrow=row)
					# checks if any children have sources - else will be removed
				try:
					row = self._select(pagename)
					self.emit('page-changed', row, emptyParseTree())
				except IndexNotFoundError:
					pass
			else:
				self.remove_page(pagename)
		else:
			raise NotImplemented # some conflict removed

	def insert_page(self, pagename, file_id):
		return self._insert_page(pagename, False, file_id)

	def insert_link_placeholder(self, pagename):
		return self._insert_page(pagename, True)

	def delete_link_placeholder(self, pagename):
		row = self._select(pagename)
		assert row is not None

		if not row['is_link_placeholder']:
			raise AssertionError('Not a placeholder')
		else:
			self.remove_page(pagename)

	def _insert_page(self, pagename, is_link_placeholder, file_id=None):
		assert not (is_link_placeholder and file_id)

		# insert parents
		parent_row = self._select(pagename.parent)
		if parent_row is None:
			self._insert_page(pagename.parent, is_link_placeholder) # recurs
			parent_row = self._select(pagename.parent)
			assert parent_row is not None

		# insert new page
		lowerbasename = pagename.basename.lower()
		sortkey = natural_sort_key(pagename.basename)
		try:
			self.db.execute(
				'INSERT INTO pages(name, lowerbasename, sortkey, parent, is_link_placeholder, source_file)'
				'VALUES (?, ?, ?, ?, ?, ?)',
				(pagename.name, lowerbasename, sortkey, parent_row['id'], is_link_placeholder, file_id)
			)
		except sqlite3.IntegrityError:
			# This can occur in rare edge cases when resolve_page failed to
			# see a page existed already - typically due to locale changes
			# affecting sortkey
			logger.exception('Error while inserting page - re-index needed?')
			self.db.execute(
				'UPDATE pages SET sortkey=? WHERE name=?',
				(sortkey, pagename.name)
			)
			row = self._select(pagename)
		else:
			row = self._select(pagename)
			self._update_parent_nchildren(pagename.parent)
			self.emit('page-row-inserted', row)

		# update parent(s)
		self.update_parent(pagename.parent)

		return row['id']

	def update_parent(self, parentname, allow_cleanup=lambda r: True, oldrow=None):
		row = self._select(parentname)
		assert row is not None

		# get new status
		n_children, all_child_are_placeholder = self.db.execute(
			'SELECT count(*), min(is_link_placeholder) FROM pages WHERE parent=?',
				# "min()" works as "any(not is_link_placeholder)"
				# because False is "0" in sqlite
			(row['id'],)
		).fetchone()
		if all_child_are_placeholder is None:
			all_child_are_placeholder = True

		if n_children == 0 and row['source_file'] is None and allow_cleanup(row):
			# cleanup if no longer needed
			self.db.execute(
				'UPDATE pages SET n_children=? WHERE id=?',
				(n_children, row['id'])
			)
			self.remove_page(parentname, allow_cleanup) # indirect recurs
		else:
			# update table
			is_placeholder = row['source_file'] is None and all_child_are_placeholder
			self.db.execute(
				'UPDATE pages SET n_children=?, is_link_placeholder=? WHERE id=?',
				(n_children, is_placeholder, row['id'])
			)
			if bool(row['is_link_placeholder']) is not is_placeholder:
				self.update_parent(parentname.parent) # recurs

			# notify others
			if not parentname.isroot:
				newrow = self._select(parentname)
				self.emit('page-row-changed', newrow, oldrow or row)

	def update_page(self, pagename, mtime, content):
		self.db.execute(
			'UPDATE pages SET mtime=? WHERE name=?',
			(mtime, pagename.name),
		)

		row = self._select(pagename)
		self.emit('page-changed', row, content)
		self.emit('page-row-changed', row, row)

	def remove_page(self, pagename, allow_cleanup=lambda r: True):
		# allow_cleanup is used by LinksIndexer when cleaning up placeholders

		row = self._select(pagename)
		assert row['id'] != 1, 'BUG: can\'t delete notebook root'
		if row['n_children'] > 0:
			raise AssertionError('Page has child pages')

		self.emit('page-row-delete', row)
		self.db.execute('DELETE FROM pages WHERE name=?', (pagename.name,))
		self._update_parent_nchildren(pagename.parent)
		self.emit('page-row-deleted', row)
		self.update_parent(pagename.parent, allow_cleanup)

	def _update_parent_nchildren(self, parentname):
		# parent n_children needs to be up-to-date when we emit the "deleted"
		# signal, else Gtk.TreeView sees an inconsistency
		# We still call update_parent() after the fact to do the rest of the
		# house keeping
		row = self._select(parentname)
		assert row is not None

		n_children, = self.db.execute(
			'SELECT count(*) FROM pages WHERE parent=?',
			(row['id'],)
		).fetchone()
		self.db.execute(
			'UPDATE pages SET n_children=? WHERE id=?',
			(n_children, row['id'])
		)


class PageIndexRecord(Path):
	'''Object representing a page L{Path} in the index, with data
	for the corresponding row in the C{pages} table.
	'''

	__slots__ = ('_row')

	def __init__(self, row):
		'''Constructor
		@param row: a C{sqlite3.Row} object for this page in the
		"pages" table, specifies most other attributes for this object
		The property C{hasdata} is C{True} when the row is set.
		'''
		Path.__init__(self, row['name'])
		self._row = row

	@property
	def id(self): return self._row['id']

	@property
	def hascontent(self): return self._row['source_file'] is not None

	@property
	def haschildren(self): return self._row['n_children'] > 0

	@property
	def n_children(self): return self._row['n_children']

	@property
	def mtime(self): return self._row['mtime']

	def exists(self):
		return not self._row['is_link_placeholder']


class PagesViewInternal(object):
	'''This class defines private methods used by L{PagesView},
	L{LinksView}, L{TagsView} and others.
	'''

	def __init__(self, db):
		self.db = db

	def get_pagename(self, page_id):
		row = self.db.execute(
			'SELECT * FROM pages WHERE id=?', (page_id,)
		).fetchone()
		if row is None:
			raise IndexConsistencyError('No page for page_id "%r"' % page_id)
		return PageIndexRecord(row)

	def get_page_id(self, pagename):
		row = self.db.execute(
			'SELECT id FROM pages WHERE name=?', (pagename.name,)
		).fetchone()
		if row is None:
			raise IndexNotFoundError('Page not found in index: %s' % pagename.name)
		return row['id']

	def resolve_link(self, source, href, ignore_link_placeholders=True, source_id=None):
		parent, parent_id, names = self._resolve_link(source, href, ignore_link_placeholders, source_id)
		return self.resolve_pagename(parent, names)

	def _resolve_link(self, source, href, ignore_link_placeholders=True, source_id=None):
		if href.rel == HREF_REL_ABSOLUTE or source.isroot:
			return (ROOT_PATH, ROOT_ID, href.parts())

		start, start_id, relnames = source, source_id, []
		while start_id is None:
			# Do not assume source exists, find start point that does
			try:
				start_id = self.get_page_id(start)
			except IndexNotFoundError:
				relnames.insert(0, start.basename)
				start = start.parent
			else:
				break

		if href.rel == HREF_REL_RELATIVE:
			return (start, start_id, relnames + href.parts())
		else:
			# HREF_REL_FLOATING
			# Search upward namespaces for existing pages,
			# By default ignore link placeholders to avoid circular
			# dependencies between links and placeholders
			assert href.rel == HREF_REL_FLOATING
			anchor_key = natural_sort_key(href.parts()[0])

			if relnames:
				# Check if we are anchored in non-existing part
				keys = list(map(natural_sort_key, relnames))
				if anchor_key in keys:
					i = [c for c, k in enumerate(keys) if k == anchor_key][-1]
					return (start, start_id, relnames[:i] + href.parts())

			if ignore_link_placeholders:
				c = self.db.execute(
					'SELECT name, id FROM pages '
					'WHERE sortkey=? and is_link_placeholder=0 '
					'ORDER BY name DESC',
					(anchor_key,)
				) # sort longest first
			else:
				c = self.db.execute(
					'SELECT name, id FROM pages '
					'WHERE sortkey=? '
					'ORDER BY name DESC',
					(anchor_key,)
				) # sort longest first

			maxdepth = source.name.count(':')
			depth = -1 # level where items were found
			found = [] # candidates that match the link - these can only differ in case of the basename
			for name, pid in c:
				mydepth = name.count(':')
				if mydepth > maxdepth:
					continue
				elif mydepth < depth:
					break

				if mydepth > 0: # check whether we have a common parent
					parentname = name.rsplit(':', 1)[0]
					if start.name.startswith(parentname):
						depth = mydepth
						found.append((name, pid))
				else: # resolve from root namespace
					found.append((name, pid))

			if found: # try to match case first, else just use first match
				parts = href.parts()
				anchor = parts.pop(0)
				for name, pid in found:
					if name.endswith(anchor):
						return (Path(name), pid, parts)
				else:
					name, pid = found[0]
					return (Path(name), pid, parts)

			else:
				# Return "brother" of source
				if relnames:
					return (start, start_id, relnames[:-1] + href.parts())
				else:
					return (start.parent, None, href.parts())

	def resolve_pagename(self, parent, names, parent_id=None):
		'''Resolve a pagename in the right case'''
		# We do not ignore placeholders here. This can lead to a dependencies
		# in how links are resolved based on order of indexing. However, this
		# is not really a problem. Ignoring them means you could see duplicates
		# if the tree for multiple links with slightly different spelling.
		# Also we would need another call to return the page_id if a resolved
		# page happens to exist.
		assert isinstance(parent, Path)
		pagename = parent
		page_id = parent_id or self.get_page_id(parent)
		for i, basename in enumerate(names):
			sortkey = natural_sort_key(basename)
			candidates = self.db.execute(
				'SELECT id, name FROM pages '
				'WHERE parent=? and sortkey=? ORDER BY name',
				(page_id, sortkey)
			).fetchall()

			exact = pagename.child(basename).name
			for row in candidates:
				if row['name'] == exact:
					pagename = Path(row['name'])
					page_id = row['id']
					break
			else:
				if candidates: # case insensitive match(es)
					row = candidates[0]
					pagename = Path(row['name'])
					page_id = row['id']
				else: # no match
					return None, pagename.child(':'.join(names[i:]))
		else:
			return page_id, pagename

	def walk(self, parent_id):
		# Need to do this recursive to preserve sorting
		#              else we could just do "name LIKE parent%"
		for row in self.db.execute(
			'SELECT * FROM pages WHERE parent=? '
			'ORDER BY sortkey, name',
			(parent_id,)
		):
			yield PageIndexRecord(row)
			if row['n_children'] > 0:
				for child in self.walk(row['id']): # recurs
					yield child

	def walk_bottomup(self, parent_id):
		for row in self.db.execute(
			'SELECT * FROM pages WHERE parent=? '
			'ORDER BY sortkey, name',
			(parent_id,)
		):
			if row['n_children'] > 0:
				for child in self.walk_bottomup(row['id']): # recurs
					yield child
			yield PageIndexRecord(row)


class PagesView(IndexView):
	'''Index view that exposes the "pages" table in the index'''

	def __init__(self, db):
		IndexView.__init__(self, db)
		self._pages = PagesViewInternal(db)

	def lookup_by_pagename(self, pagename):
		r = self.db.execute(
			'SELECT * FROM pages WHERE name=?', (pagename.name,)
		).fetchone()
		if r is None:
			raise IndexNotFoundError
		else:
			return PageIndexRecord(r)

	def list_pages(self, path=None):
		'''Generator for child pages of C{path}
		@param path: a L{Path} object
		@returns: yields L{Path} objects for children of C{path}
		@raises IndexNotFoundError: if C{path} is not found in the index
		'''
		if path is None:
			page_id = ROOT_ID
		else:
			page_id = self._pages.get_page_id(path) # can raise
		return self._list_pages(page_id)

	def _list_pages(self, page_id):
		for row in self.db.execute(
			'SELECT * FROM pages WHERE parent=? ORDER BY sortkey, name',
			(page_id,)
		):
			yield PageIndexRecord(row)

	def n_list_pages(self, path=None):
		page_id = self._pages.get_page_id(path or ROOT_PATH)
		c, = self.db.execute(
			'SELECT COUNT(*) FROM pages WHERE parent=?', (page_id,)
		).fetchone()
		return c

	def match_pages(self, path, text, limit=10):
		'''Generator for child pages of C{path} that match C{text} in their name
		@param path: a L{Path} object
		@param text: a string
		@param limit: max number of results
		@returns: yields L{Path} objects for children of C{path}
		@raises IndexNotFoundError: if C{path} is not found in the index
		'''
		if path is None:
			page_id = ROOT_ID
		else:
			page_id = self._pages.get_page_id(path) # can raise
		return self._match_pages(page_id, text, limit)

	def _match_pages(self, page_id, text, limit):
		# The LIKE keyword does not handle unicode case-insensitivity
		# therefore we need python lower() to do the job
		for row in self.db.execute(
			'SELECT * FROM pages WHERE parent=? and lowerbasename LIKE ? ORDER BY sortkey, name LIMIT ?',
			(page_id, "%%%s%%" % text.lower(), limit)
		):
			yield PageIndexRecord(row)

	def match_all_pages(self, text, limit=10):
		'''Like C{match_pages()} except not limited a specific namespace'''
		for row in self.db.execute(
			'SELECT * FROM pages WHERE lowerbasename LIKE ? ORDER BY length(name), sortkey, name LIMIT ?',
			("%%%s%%" % text.lower(), limit)
		):
			yield PageIndexRecord(row)

	def walk(self, path=None):
		'''Generator function to yield all pages in the index, depth
		first

		@param path: a L{Path} object for the starting point, can be
		used to only iterate a sub-tree. When this is C{None} the
		whole notebook is iterated over
		@returns: an iterator that yields L{Path} objects
		@raises IndexNotFoundError: if C{path} does not exist in the index
		'''
		# Need to do this recursive to preserve sorting
		#              else we could just do "name LIKE parent%"
		page_id = self._pages.get_page_id(path) if path else ROOT_ID # can raise
		return self._pages.walk(page_id)

	def walk_bottomup(self, path=None):
		page_id = self._pages.get_page_id(path) if path else ROOT_ID # can raise
		return self._pages.walk_bottomup(page_id)

	def n_all_pages(self):
		'''Returns to total number of pages in the index'''
		c, = self.db.execute('SELECT COUNT(*) FROM pages').fetchone()
		return c - 1 # don't count ROOT

	def get_has_previous_has_next(self, path):
		if path.isroot:
			raise ValueError('Can\'t use root')

		r = self.db.execute(
			'SELECT * FROM pages WHERE parent=? '
			'ORDER BY sortkey ASC, name ASC LIMIT 1',
			(ROOT_ID,)
		).fetchone()
		is_first = (r['name'] == path.name) if r else True

		r = self.db.execute(
			'SELECT * FROM pages WHERE parent=? '
			'ORDER BY sortkey DESC, name DESC LIMIT 1',
			(ROOT_ID,)
		).fetchone()
		is_last = (r['name'] == path.name) if r else True

		return not is_first, not is_last

	def get_previous(self, path):
		'''Get the previous path in the index, in the same order that
		L{walk()} will yield them
		@param path: a L{Path} object
		@returns: a L{Path} object or C{None} if {path} is the first page in
		the index
		'''
		# Find last (grand)child of previous item with same parent
		# If no previous item, yield parent
		if path.isroot:
			raise ValueError('Can\'t use root')

		r = self.db.execute(
			'SELECT parent FROM pages WHERE name=?', (path.name,)
		).fetchone()
		if r is None:
			raise IndexNotFoundError('No such page: %s' % path)
		else:
			parent_id = r[0]

		sortkey = natural_sort_key(path.basename)
		r = self.db.execute('''
			SELECT * FROM pages WHERE parent=? and (
				sortkey<? or (sortkey=? and name<?)
			) ORDER BY sortkey DESC, name DESC LIMIT 1''',
			(parent_id, sortkey, sortkey, path.name)
		).fetchone()
		if not r:
			parent = self._pages.get_pagename(parent_id)
			return None if parent.isroot else parent
		else:
			while r['n_children'] > 0:
				r = self.db.execute(
					'SELECT * FROM pages WHERE parent=? '
					'ORDER BY sortkey DESC, name DESC LIMIT 1',
					(r['id'],)
				).fetchone()
				if r is None:
					raise IndexConsistencyError('Missing children')
			else:
				return PageIndexRecord(r)

	def get_next(self, path):
		'''Get the next path in the index, in the same order that
		L{walk()} will yield them
		@param path: a L{Path} object
		@returns: a L{Path} object or C{None} if C{path} is the last page in
		the index
		'''
		# If item has children, yield first child
		# Else find next item with same parent
		# If no next item, find next item for parent
		if path.isroot:
			raise ValueError('Can\'t use root')

		r = self.db.execute(
			'SELECT * FROM pages WHERE name=?', (path.name,)
		).fetchone()
		if r is None:
			raise IndexNotFoundError('No such page: %s' % path)

		if r['n_children'] > 0:
			r = self.db.execute(
				'SELECT name FROM pages WHERE parent=? '
				'ORDER BY sortkey, name LIMIT 1',
				(r['id'],)
			).fetchone()
			if r is None:
				raise IndexConsistencyError('Missing children')
			else:
				return PageIndexRecord(r)
		else:
			while True:
				n = self.db.execute('''
					SELECT * FROM pages WHERE parent=? and (
						sortkey>? or (sortkey=? and name>?)
					) ORDER BY sortkey, name LIMIT 1''',
					(r['parent'], r['sortkey'], r['sortkey'], r['name'])
				).fetchone()
				if n is not None:
					return PageIndexRecord(n)
				elif r['parent'] == ROOT_ID:
					return None
				else:
					r = self.db.execute(
						'SELECT * FROM pages WHERE id=?', (r['parent'],)
					).fetchone()
					if r is None:
						raise IndexConsistencyError('Missing parent')

	def lookup_from_user_input(self, name, reference=None):
		'''Lookup a pagename based on user input
		@param name: the user input as string
		@param reference: a L{Path} in case relative links are supported as
		customer input
		@returns: a L{Path} object for C{name}
		@raises ValueError: when C{name} would reduce to empty string
		after removing all invalid characters, or if C{name} is a
		relative link while no C{reference} page is given.
		@raises IndexNotFoundError: when C{reference} is not indexed
		'''
		# This method re-uses most of resolve_link() but is defined
		# separate because it has a distinct different purpose.
		# Only accidental that we treat user input as links ... ;)
		href = HRef.new_from_wiki_link(name)
		if reference is None and href.rel == HREF_REL_RELATIVE:
			raise ValueError('Got relative page name without parent: %s' % name)
		else:
			source = reference or ROOT_PATH
			id, pagename = self._pages.resolve_link(
								source, href, ignore_link_placeholders=False)
			return pagename

	def resolve_link(self, source, href):
		'''Find the end point of a link
		Depending on the link type (absolute, relative, or floating),
		this method first determines the starting point of the link
		path. Then it goes downward doing a case insensitive match
		against the index.
		@param source: a L{Path} for the starting point of the link
		@param href: a L{HRef} object for the link
		@returns: a L{Path} object for the target of the link.
		'''
		assert isinstance(source, Path)
		assert isinstance(href, HRef)
		id, pagename = self._pages.resolve_link(source, href)
		return pagename

	def create_link(self, source, target):
		'''Determine best way to represent a link between two pages
		@param source: a L{Path} object
		@param target: a L{Path} object
		@returns: a L{HRef} object
		'''
		if target == source: # weird edge case ..
			return HRef(HREF_REL_FLOATING, target.basename)
		elif target.ischild(source):
			return HRef(HREF_REL_RELATIVE, target.relname(source))
		else:
			href = self._find_floating_link(source, target)
			return href or HRef(HREF_REL_ABSOLUTE, target.name)

	def _find_floating_link(self, source, target):
		# Relative links only resolve for pages that have a common parent
		# with the source page. So we start finding the common parents and
		# if that does not resolve (e.g. because same name also occurs on a
		# lower level) try one level up to "anchor" the link.
		# It is absolute must to use resolve_link() here - this ensures the
		# outcome is always consistent between these functions.
		parentnames = []
		for n1, n2 in zip(source.parts, target.parts):
			if n1 == n2:
				parentnames.append(n1)
			else:
				break

		def try_link(names):
			assert names
			href = HRef(HREF_REL_FLOATING, ':'.join(names))
			pid, pagename = self._pages.resolve_link(source, href)
			return href if pagename == target else None

		relnames = target.parts[len(parentnames):]
		if not relnames: # Target is direct parent
			relnames.insert(0, parentnames.pop())
		href = try_link(relnames)
		if href is not None:
			return href
		else:
			while parentnames:
				relnames.insert(0, parentnames.pop())
				href = try_link(relnames)
				if href:
					return href
			else:
				return None # no floating link possible

	def list_recent_changes(self, limit=None, offset=None):
		assert not (offset and not limit), "Can't use offset without limit"
		if limit:
			selection = ' LIMIT %i OFFSET %i' % (limit, offset or 0)
		else:
			selection = ''

		for row in self.db.execute(
			'SELECT * FROM pages WHERE id<>1 ORDER BY mtime DESC' + selection,
		):
			yield PageIndexRecord(row)


try:
	from gi.repository import Gtk
except ImportError:
	Gtk = None


IS_PAGE = 1 #: Hint for MyTreeIter

class PagesTreeModelMixin(TreeModelMixinBase):

	# Optimize lookup for finding records in the same level
	# - always cache parent, to retrieve other children more quickly
	# - cache a range of 20 records at once

	# Signals use "find_all" instead of "find" to allow for subclasses that
	# have multiple entries, like models for tags

	def __init__(self, index, root=None, reverse=False):
		TreeModelMixinBase.__init__(self, index)
		self._REVERSE = reverse
		if root is None:
			self._MY_ROOT_NAME = ''
			self._MY_ROOT_NAME_C = ''
			self._MY_ROOT_ID = ROOT_ID
		else:
			self._MY_ROOT_NAME = root.name
			self._MY_ROOT_NAME_C = root.name + ':'
			self._set_root_id()

		self._deleted_paths = None

	def _set_root_id(self):
		myrow = self.db.execute(
			'SELECT * FROM pages WHERE name=?', (self._MY_ROOT_NAME,)
		).fetchone()
		self._MY_ROOT_ID = myrow['id'] if myrow else None

	def connect_to_updateiter(self, index, update_iter):
		self.connectto_all(update_iter.pages,
			('page-row-inserted', 'page-row-changed', 'page-row-delete', 'page-row-deleted')
		)

	def on_page_row_inserted(self, o, row):
		self.flush_cache()
		if row['name'] == self._MY_ROOT_NAME:
			self._set_root_id()
		else:
			for treepath in self._find_all_pages(row['name']):
				treeiter = self.get_iter(treepath) # not mytreeiter !
				self.emit('row-inserted', treepath, treeiter)
				if treepath[-1] == 0 and len(treepath) > 1:
					self._check_parent_has_child_toggled(treepath, 1)

	def _check_parent_has_child_toggled(self, treepath, count):
		parent = self.get_mytreeiter(treepath[:-1])
		if parent.n_children == count:
			treeiter = self.get_iter(parent.treepath) # not mytreeiter !
			self.emit('row-has-child-toggled', parent.treepath, treeiter)

	def on_page_row_changed(self, o, row, oldrow):
		# no clear cache here - just update row
		for treepath in self._find_all_pages(row['name']):
			treeiter = self.get_iter(treepath) # not mytreeiter !
			self.cache[tuple(treepath)].row = row # ensure uptodate info
			self.emit('row-changed', treepath, treeiter)

	def on_page_row_delete(self, o, row):
		self._deleted_paths = list(self._find_all_pages(row['name']))

	def on_page_row_deleted(self, o, row):
		# Technically "_deleted_paths" should always be a single path
		# here, else two things changed at once, and Gtk.TreeView cannot
		# always deal with that.

		self.flush_cache()
		if row['name'] == self._MY_ROOT_NAME:
			self._MY_ROOT_ID = None
		else:
			for treepath in self._deleted_paths:
				self.emit('row-deleted', treepath)
				if treepath[-1] == 0 and len(treepath) > 1:
					self._check_parent_has_child_toggled(treepath, 0)

		self._deleted_paths = None

	def n_children_top(self):
		if self._MY_ROOT_ID is None:
			return 0
		else:
			return self.db.execute(
				'SELECT COUNT(*) FROM pages WHERE parent=?', (self._MY_ROOT_ID,)
			).fetchone()[0]

	def get_mytreeiter(self, treepath):
		if self._MY_ROOT_ID is None:
			return None

		treepath = tuple(treepath) # used to cache
		if treepath in self.cache:
			return self.cache[treepath]

		# Find parent
		parentpath = treepath[:-1]
		if not parentpath:
			parent_id = self._MY_ROOT_ID
		else:
			parent_iter = self.cache.get(parentpath, None) \
							or self.get_mytreeiter(parentpath) # recurs
			if parent_iter:
				parent_id = parent_iter.row['id']
			else:
				return None

		# Now cache a slice at the target level
		offset = treepath[-1]
		if self._REVERSE:
			rows = self.db.execute('''
				SELECT * FROM pages WHERE parent=?
				ORDER BY sortkey DESC, name DESC LIMIT 20 OFFSET ?
				''',
				(parent_id, offset)
			)
		else:
			rows = self.db.execute('''
				SELECT * FROM pages WHERE parent=?
				ORDER BY sortkey ASC, name ASC LIMIT 20 OFFSET ?
				''',
				(parent_id, offset)
			)
		for i, row in enumerate(rows):
			mytreepath = tuple(parentpath) + (offset + i,)
			if mytreepath not in self.cache:
				self.cache[mytreepath] = MyTreeIter(
					Gtk.TreePath(mytreepath),
					row,
					row['n_children'],
					IS_PAGE
				)
			else:
				break # avoid overwriting cache because of ref count

		return self.cache.get(treepath, None)

	def find(self, path):
		'''Returns the C{Gtk.TreePath} for a notebook page L{Path}
		If the L{Path} appears multiple times returns the first occurrence
		@raises IndexNotFoundError: if path not found
		'''
		if path.isroot:
			raise ValueError
		treepaths = sorted(self._find_all_pages(path.name))
		try:
			return treepaths[0]
		except IndexError:
			raise IndexNotFoundError(path)

	def find_all(self, path):
		'''Returns a list of C{Gtk.TreePath} for a notebook page L{Path}
		Returns all occurrences in the treeview
		@raises IndexNotFoundError: if path not found
		'''
		if path.isroot:
			raise ValueError
		treepaths = self._find_all_pages(path.name)
		if not treepaths:
			raise IndexNotFoundError(path)
		else:
			return treepaths

	def _find_all_pages(self, name, update_cache=True):
		if self._MY_ROOT_ID is None or \
			not name.startswith(self._MY_ROOT_NAME_C):
				return []

		parent_id = self._MY_ROOT_ID
		names = name[len(self._MY_ROOT_NAME_C):].split(':')
		treepath = []
		for i, basename in enumerate(names):
			# Get treepath
			name = self._MY_ROOT_NAME_C + ':'.join(names[:i + 1])
			myrow = self.db.execute(
				'SELECT * FROM pages WHERE name=?', (name,)
			).fetchone()
			if myrow is None:
				raise IndexNotFoundError

			sortkey = myrow['sortkey']
			if self._REVERSE:
				row = self.db.execute('''
					SELECT COUNT(*) FROM pages
					WHERE parent=? and (
						sortkey>? or (sortkey=? and name>?)
					)''',
					(parent_id, sortkey, sortkey, name)
				).fetchone()
			else:
				row = self.db.execute('''
					SELECT COUNT(*) FROM pages
					WHERE parent=? and (
						sortkey<? or (sortkey=? and name<?)
					)''',
					(parent_id, sortkey, sortkey, name)
				).fetchone()
			treepath.append(row[0])
			parent_id = myrow['id']

			if update_cache:
				# Update cache (avoid overwriting because of ref count)
				mytreepath = tuple(treepath)
				if mytreepath not in self.cache:
					myiter = MyTreeIter(
						Gtk.TreePath(mytreepath),
						myrow,
						myrow['n_children'],
						IS_PAGE
					)
					self.cache[mytreepath] = myiter

		return [Gtk.TreePath(treepath)]


########################################################################

class TestPagesDBTable(object):
	# Mixin for test cases, defined here to have all SQL in one place

	def assertPagesDBConsistent(self, db):
		for row in db.execute('SELECT * FROM pages'):
			count, = db.execute(
				'SELECT count(*) FROM pages WHERE parent=?',
				(row['id'],)
			).fetchone()
			self.assertEqual(row['n_children'], count,
				'Count for "%s" is %i while n_children=%i' % (row['name'], row['n_children'], count)
			)

			if row['source_file'] is not None:
				self.assertFalse(row['is_link_placeholder'],
					'Placeholder status for %s is wrong (has source itself)' % row['name']
				)
			elif not row['is_link_placeholder']:
				# Check downwards - at least one child that is not a placeholder either
				child = db.execute(
					'SELECT * FROM pages WHERE parent=? and is_link_placeholder=?',
					(row['id'], False),
				).fetchone()
				self.assertIsNotNone(child,
					'Missing child with source for %s' % row['name'])

			if row['id'] > 1:
				parent = db.execute(
					'SELECT * FROM pages WHERE id=?',
					(row['id'],)
				).fetchone()
				self.assertIsNotNone(parent,
					'Missing parent for %s' % row['name'])

				if not row['is_link_placeholder']:
					# Check upwards - parent(s) must not be placeholder either
					self.assertFalse(parent['is_link_placeholder'],
						'Placeholder status for parent of %s is inconsistent' % row['name']
					)

	def assertPagesDBEquals(self, db, pages):
		rows = db.execute('SELECT * FROM pages WHERE id>1').fetchall()
		in_db = set(r['name'] for r in rows)
		self.assertEqual(in_db, set(pages))

	def assertPagesDBContains(self, db, pages):
		rows = db.execute('SELECT * FROM pages WHERE id>1').fetchall()
		in_db = set(r['name'] for r in rows)
		self.assertTrue(set(pages).issubset(in_db))
