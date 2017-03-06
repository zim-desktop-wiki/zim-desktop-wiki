# -*- coding: utf-8 -*-

# Copyright 2009-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement


from datetime import datetime

from zim.utils import natural_sort_key
from zim.notebook.page import Path, HRef, \
	HREF_REL_ABSOLUTE, HREF_REL_FLOATING, HREF_REL_RELATIVE

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


class PagesIndexer(IndexerBase):
	'''Indexer for the "pages" table.

	@signal: C{page-row-inserted (row)}: new row inserted
	@signal: C{page-row-changed (row)}: row changed
	@signal: C{page-row-deleted (row)}: row to be deleted

	@signal: C{page-changed (row, content)}: page contents changed
	'''

	__signals__ = {
		'page-row-inserted': (None, None, (object,)),
		'page-row-changed':  (None, None, (object,)),
		'page-row-deleted':  (None, None, (object,)),
		'page-changed':      (None, None, (object, object))
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
				sortkey TEXT NOT NULL,
				mtime TIMESTAMP,

				source_file INTEGER REFERENCES files(id),
				is_link_placeholder BOOLEAN DEFAULT 0
			);
			CREATE UNIQUE INDEX IF NOT EXISTS pages_name ON pages(name)
		''')
		row = self.db.execute('SELECT * FROM pages WHERE id == 1').fetchone()
		if row is None:
			c = self.db.execute(
				'INSERT INTO pages(parent, name, sortkey, source_file) '
				'VALUES (? , ?, ?, ?)',
				(0, '', '', 1)
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
			self._set_source_file(pagename, filerow['id'])
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
			doc = ParseTreeMask(tree)
			self.update_page(pagename, mtime, doc)
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
				self._set_source_file(pagename, None)
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
			raise AssertionError, 'Not a placeholder'
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

		# update table
		sortkey = natural_sort_key(pagename.basename)
		self.db.execute(
			'INSERT INTO pages(name, sortkey, parent, is_link_placeholder, source_file)'
			'VALUES (?, ?, ?, ?, ?)',
			(pagename.name, sortkey, parent_row['id'], is_link_placeholder, file_id)
		)
		self.update_parent(pagename.parent)

		# notify others
		row = self._select(pagename)
		self.emit('page-row-inserted', row)

		return row['id']

	def update_parent(self, parentname, allow_cleanup=lambda r: True):
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

			parentname = PageIndexRecord(self._select(parentname))

			# notify others
			if not parentname.isroot:
				#if (row['n_children'] != n_children) \
				#and (row['n_children'] == 0 or n_children == 0):
				#	self.emit('page-row-has-child-changed', row)

				self.emit('page-row-changed', row)

	def update_page(self, pagename, mtime, content):
		self.db.execute(
			'UPDATE pages SET mtime=? WHERE name=?',
			(mtime, pagename.name),
		)

		row = self._select(pagename)
		self.emit('page-changed', row, content)
		self.emit('page-row-changed', row)

	def _set_source_file(self, pagename, file_id):
		self.db.execute(
			'UPDATE pages SET source_file=?, mtime=?, is_link_placeholder=? WHERE name=?',
			(file_id, None, False, pagename.name)
		)

		if file_id is None:
			# check any children have sources - else will be removed
			self.update_parent(pagename)
		else:
			self.update_parent(pagename.parent)
			row = self._select(pagename)
			self.emit('page-row-changed', row)

	def remove_page(self, pagename, allow_cleanup=lambda r: True):
		# allow_cleanup is used by LinksIndexer when cleaning up placeholders

		row = self._select(pagename)
		if row['n_children'] > 0:
			raise AssertionError, 'Page has child pages'

		self.emit('page-row-deleted', row)
		self.db.execute('DELETE FROM pages WHERE name=?', (pagename.name,))
		self.update_parent(pagename.parent, allow_cleanup)


class ParseTreeMask(object):
	## XXX temporary object, replace when refactoring formats

	def __init__(self, tree):
		self._tree = tree

	def iter_href(self):
		return self._tree.iter_href()

	def iter_tag_names(self):
		return self._tree.iter_tag_names()


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
			raise IndexConsistencyError, 'No page for page_id "%r"' % page_id
		return PageIndexRecord(row)

	def get_page_id(self, pagename):
		row = self.db.execute(
			'SELECT id FROM pages WHERE name=?', (pagename.name,)
		).fetchone()
		if row is None:
			raise IndexNotFoundError, 'Page not found in index: %s' % pagename.name
		return row['id']

	def resolve_link(self, source, href, ignore_link_placeholders=True):
		if href.rel == HREF_REL_ABSOLUTE or source.isroot:
			return self.resolve_pagename(ROOT_PATH, href.parts())

		start, relnames = source, []
		while True:
			# Do not assume source exists, find start point that does
			try:
				start_id = self.get_page_id(start)
			except IndexNotFoundError:
				relnames.append(start.basename)
				start = start.parent
			else:
				break

		if href.rel == HREF_REL_RELATIVE:
			return self.resolve_pagename(start, relnames + href.parts())
		else:
			# HREF_REL_FLOATING
			# Search upward namespaces for existing pages,
			# By default ignore link placeholders to avoid circular
			# dependencies between links and placeholders
			assert href.rel == HREF_REL_FLOATING
			anchor_key = natural_sort_key(href.parts()[0])

			if relnames:
				# Check if we are anchored in non-existing part
				keys = map(natural_sort_key, relnames)
				if anchor_key in keys:
					i = [c for c,k in enumerate(keys) if k==anchorkey][-1]
					return self.resolve_pagename(db, root, relnames[:i] + href.parts()[1:])

			if ignore_link_placeholders:
				c = self.db.execute(
					'SELECT name FROM pages '
					'WHERE sortkey=? and is_link_placeholder=0 '
					'ORDER BY name DESC',
					(anchor_key,)
				) # sort longest first
			else:
				c = self.db.execute(
					'SELECT name FROM pages '
					'WHERE sortkey=? '
					'ORDER BY name DESC',
					(anchor_key,)
				) # sort longest first

			maxdepth = source.name.count(':')
			depth = -1 # level where items were found
			found = [] # candidates that match the link - these can only differ in case of the basename
			for name, in c:
				mydepth = name.count(':')
				if mydepth > maxdepth:
					continue
				elif mydepth < depth:
					break

				if mydepth > 0: # check whether we have a common parent
					parentname = name.rsplit(':', 1)[0]
					if start.name.startswith(parentname):
						depth = mydepth
						found.append(name)
				else: # resolve from root namespace
					found.append(name)

			if found: # try to match case first, else just use first match
				parts = href.parts()
				anchor = parts.pop(0)
				for name in found:
					if name.endswith(anchor):
						return self.resolve_pagename(Path(name), parts)
				else:
					return self.resolve_pagename(Path(found[0]), parts)

			else:
				# Return "brother" of source
				if relnames:
					return self.resolve_pagename(start, relnames[:-1] + href.parts())
				else:
					return self.resolve_pagename(start.parent, href.parts())


	def resolve_pagename(self, parent, names):
		'''Resolve a pagename in the right case'''
		# We do not ignore placeholders here. This can lead to a dependencies
		# in how links are resolved based on order of indexing. However, this
		# is not really a problem. Ignoring them means you could see duplicates
		# if the tree for multiple links with slightly different spelling.
		# Also we would need another call to return the page_id if a resolved
		# page happens to exist.
		pagename = parent
		page_id = self.get_page_id(parent)
		for i, basename in enumerate(names):
			if page_id == ROOT_ID:
				row = self.db.execute(
					'SELECT id, name FROM pages WHERE name=?',
					(basename,)
				).fetchone()
			else:
				row = self.db.execute(
					'SELECT id, name FROM pages WHERE parent=? and name LIKE ?',
					(page_id, "%:"+basename)
				).fetchone()

			if row: # exact match
				pagename = Path(row['name'])
				page_id = row['id']
			else:
				sortkey = natural_sort_key(basename)
				row = self.db.execute(
					'SELECT id, name FROM pages '
					'WHERE parent=? and sortkey=? ORDER BY name',
					(page_id, sortkey)
				).fetchone()
				if row: # case insensitive match
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

	def get_previous(self, path):
		'''Get the previous path in the index, in the same order that
		L{walk()} will yield them
		@param path: a L{Path} object
		@returns: a L{Path} object or C{None} if {path} is the first page in
		the index
		'''
		# Find last (grand)child of previous item with same parent
		# If no previous item, yield parent
		if path.isroot: raise ValueError, 'Can\'t use root'

		r = self.db.execute(
			'SELECT parent FROM pages WHERE name=?', (path.name,)
		).fetchone()
		if r is None:
			raise IndexNotFoundError, 'No such page: %s', path
		else:
			parent_id = r[0]

		r = self.db.execute(
			'SELECT * FROM pages WHERE parent=? and sortkey<? and name<? '
			'ORDER BY sortkey DESC, name DESC LIMIT 1',
			(parent_id, natural_sort_key(path.basename), path.name)
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
					raise IndexConsistencyError, 'Missing children'
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
		if path.isroot: raise ValueError, 'Can\'t use root'

		r = self.db.execute(
			'SELECT * FROM pages WHERE name=?', (path.name,)
		).fetchone()
		if r is None:
			raise IndexNotFoundError, 'No such page: %s', path

		if r['n_children'] > 0:
			r = self.db.execute(
				'SELECT name FROM pages WHERE parent=? '
				'ORDER BY sortkey, name LIMIT 1',
				(r['id'],)
			).fetchone()
			if r is None:
				raise IndexConsistencyError, 'Missing children'
			else:
				return PageIndexRecord(r)
		else:
			while True:
				n = self.db.execute(
					'SELECT * FROM pages WHERE parent=? and sortkey>? and name>? '
					'ORDER BY sortkey, name LIMIT 1',
					(r['parent'], r['sortkey'], r['name'])
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
						raise IndexConsistencyError, 'Missing parent'

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
			raise ValueError, 'Got relative page name without parent: %s' % name
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
		# First try if basename resolves, then extend link names untill match is found
		parts = target.parts
		names = []
		while parts:
			names.insert(0, parts.pop())
			href = HRef(HREF_REL_FLOATING, ':'.join(names))
			pid, pagename = self._pages.resolve_link(source, href)
			if pagename == target:
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


IS_PAGE = 1

class PagesTreeModelMixin(TreeModelMixinBase):

	# TODO: also caching name --> treepath in _find

	def connect_to_updateiter(self, index, update_iter):
		self.connectto_all(update_iter.pages,
			('page-row-inserted', 'page-row-changed', 'page-row-deleted')
		)

	def on_page_row_inserted(self, o, row):
		self.flush_cache()
		treepath = self._find(row['name'])
		treeiter = self.get_iter(treepath)
		self.emit('row-inserted', treepath, treeiter)

	def on_page_row_changed(self, o, row):
		# no clear cache here - just update one row
		treepath = self._find(row['name'])
		self.cache[treepath].row = row # ensure uptodate info
		treeiter = self.get_iter(treepath)
		self.emit('row-changed', treepath, treeiter)

	def on_page_row_deleted(self, o, row):
		self.flush_cache()
		treepath = self._find(row['name'])
		self.emit('row-deleted', treepath)

	def n_children_top(self):
		return self.db.execute(
			'SELECT COUNT(*) FROM pages WHERE parent=?', (ROOT_ID,)
		).fetchone()[0]

	def get_mytreeiter(self, treepath):
		assert isinstance(treepath, tuple)
		if treepath in self.cache:
			return self.cache[treepath]

		# Iterate parent paths
		parent_id = ROOT_ID
		for i in range(1, len(treepath)):
			mytreepath = tuple(treepath[:i])
			if mytreepath in self.cache:
				parent_id = self.cache[mytreepath].row['id']
			else:
				row = self.db.execute('''
					SELECT * FROM pages WHERE parent=?
					ORDER BY sortkey, name LIMIT 1 OFFSET ?
					''',
					(parent_id, mytreepath[-1])
				).fetchone()
				if row:
					self.cache[mytreepath] = MyTreeIter(mytreepath, row, IS_PAGE)
					parent_id = row['id']
				else:
					return None

		# Now cache a slice at the target level
		parentpath = treepath[:-1]
		offset = treepath[-1]
		for i, row in enumerate(self.db.execute('''
			SELECT * FROM pages WHERE parent=?
			ORDER BY sortkey, name LIMIT 20 OFFSET ?
			''',
			(parent_id, offset)
		)):
			mytreepath = parentpath + (offset + i,)
			if mytreepath not in self.cache:
				self.cache[mytreepath] = MyTreeIter(mytreepath, row, IS_PAGE)

		try:
			return self.cache[treepath]
		except KeyError:
			return None

	def find(self, path):
		if path.isroot:
			raise ValueError
		return self._find(path.name)

	def _find(self, name):
		parent_id = ROOT_ID
		names = name.split(':')
		treepath = []
		for i, basename in enumerate(names):
			# Get treepath
			name = ':'.join(names[:i+1])
			myrow = self.db.execute(
				'SELECT * FROM pages WHERE name=?', (name,)
			).fetchone()
			if myrow is None:
				raise IndexNotFoundError

			sortkey = myrow['sortkey']
			row = self.db.execute('''
				SELECT COUNT(*) FROM pages
				WHERE parent=? and (
					sortkey<? or (sortkey=? and name<?)
				)''',
				(parent_id, sortkey, sortkey, name)
			).fetchone()
			treepath.append(row[0])
			parent_id = myrow['id']

			# Update cache (avoid overwriting because of ref count)
			mytreepath = tuple(treepath)
			if mytreepath not in self.cache:
				myiter = MyTreeIter(mytreepath, myrow, IS_PAGE)
				self.cache[mytreepath] = myiter

		return tuple(treepath)


###################
################

def get_indexpath_for_treepath_flatlist_factory(db, cache):
	'''Factory for the "get_indexpath_for_treepath()" method
	used by the page index Gtk widget.
	This method stores the corresponding treepaths in the C{treepath}
	attribute of the indexpath.
	The "flatlist" version lists all pages in the toplevel of the tree,
	followed by their children. This is intended to be filtered
	dynamically.
	@param db: an L{sqlite3.Connection} object
	@param cache: a dict used to store (intermediate) results
	@returns: a function
	'''
	# This method is constructed by a factory to speed up all lookups
	# it is defined here to keep all SQL code in the same module
	assert not cache, 'Better start with an empty cache!'

	def get_indexpath_for_treepath_flatlist(treepath):
		assert isinstance(treepath, tuple)
		if treepath in cache:
			return cache[treepath]

		# Get toplevel
		mytreepath = (treepath[0],)
		if mytreepath in cache:
			parent = cache[mytreepath]
		else:
			row = db.execute(
				'SELECT * FROM pages '
				'WHERE id<>? '
				'ORDER BY sortkey, name '
				'LIMIT 1 OFFSET ? ',
				(ROOT_ID, treepath[0])
			).fetchone()
			if row:
				parent = PageIndexRecord(row, mytreepath)
				cache[mytreepath] = parent
			else:
				return None

		# Iterate parent paths
		for i in range(2, len(treepath)):
			mytreepath = tuple(treepath[:i])
			if mytreepath in cache:
				parent = cache[mytreepath]
			else:
				row = db.execute(
					'SELECT * FROM pages '
					'WHERE parent=? '
					'ORDER BY sortkey, name '
					'LIMIT 1 OFFSET ? ',
					(parent.id, mytreepath[-1])
				).fetchone()
				if row:
					parent = PageIndexRecord(row, mytreepath)
					cache[mytreepath] = parent
				else:
					return None

		# Now cache a slice at the target level
		parentpath = treepath[:-1]
		offset = treepath[-1]
		for i, row in enumerate(db.execute(
			'SELECT * FROM pages '
			'WHERE parent=? '
			'ORDER BY sortkey, name '
			'LIMIT 20 OFFSET ? ',
			(parent.id, offset)
		)):
			mytreepath = parentpath + (offset + i,)
			if not mytreepath in cache:
				indexpath = PageIndexRecord(row, mytreepath)
				cache[mytreepath] = indexpath

		try:
			return cache[treepath]
		except KeyError:
			return None

	return get_indexpath_for_treepath_flatlist


def get_treepaths_for_indexpath_flatlist_factory(db, cache):
	'''Factory for the "get_treepath_for_indexpath()" method
	used by the page index Gtk widget.
	The "flatlist" version lists all pages in the toplevel of the tree,
	followed by their children. This is intended to be filtered
	dynamically.
	@param db: an L{sqlite3.Connection} object
	@param cache: a dict used to store (intermediate) results
	@returns: a function
	'''
	# This method is constructed by a factory to speed up all lookups
	# it is defined here to keep all SQL code in the same module
	#
	# We don't do a reverse cache lookup - faster to just go forwards.
	# Only cache to ensure subsequent get_indexpath_for_treepath calls
	# are faster. Don't overwrite existing items in the cache to ensure
	# ref count on paths.
	#
	# For the flatlist, all parents are toplevel, so number of results
	# are equal to number of parents + self
	# Below toplevel, paths are all the same
	assert not cache, 'Better start with an empty cache!'

	normal_cache = {}
	get_treepath_for_indexpath = get_treepath_for_indexpath_factory(db, normal_cache)

	def get_treepaths_for_indexpath_flatlist(indexpath):
		if not cache:
			normal_cache.clear() # flush 2nd cache as well..
		normalpath = get_treepath_for_indexpath(indexpath)

		parent = ROOT_PATH
		treepaths = []
		names = indexpath.parts
		for i, basename in enumerate(names):
			name = ':'.join(names[:i+1])
			sortkey = natural_sort_key(basename)
			row = db.execute(
				'SELECT COUNT(*) FROM pages '
				'WHERE id<>? and ('
				'	sortkey<? '
				'	or (sortkey=? and name<?)'
				')',
				(ROOT_ID, sortkey, sortkey, name)
			).fetchone()
			mytreepath = (row[0],) + normalpath[i+1:]
				# toplevel + remainder of real treepath
			treepaths.append(mytreepath)

		return treepaths

	return get_treepaths_for_indexpath_flatlist


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
						'Placeholder status for parent of %s is inconcsisten' % row['name']
					)

	def assertPagesDBEquals(self, db, pages):
		rows = db.execute('SELECT * FROM pages WHERE id>1').fetchall()
		in_db = set(r['name'] for r in rows)
		self.assertEqual(in_db, set(pages))

	def assertPagesDBContains(self, db, pages):
		rows = db.execute('SELECT * FROM pages WHERE id>1').fetchall()
		in_db = set(r['name'] for r in rows)
		self.assertTrue(set(pages).issubset(in_db))
