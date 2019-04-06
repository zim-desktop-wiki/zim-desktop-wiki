
# Copyright 2009-2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>




from zim.utils import natural_sort_key
from zim.signals import SIGNAL_NORMAL


from .base import IndexerBase, IndexView, IndexNotFoundError
from .pages import PagesViewInternal, ROOT_PATH, \
	PageIndexRecord  #, get_treepath_for_indexpath_factory


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


class TagsIndexer(IndexerBase):

	__signals__ = {
		'tag-row-inserted': (SIGNAL_NORMAL, None, (object,)),
		'tag-row-deleted': (SIGNAL_NORMAL, None, (object,)),
		'tag-added-to-page': (SIGNAL_NORMAL, None, (object, object)),
		'tag-remove-from-page': (SIGNAL_NORMAL, None, (object, object)),
		'tag-removed-from-page': (SIGNAL_NORMAL, None, (object, object)),
	}

	def __init__(self, db, pagesindexer):
		IndexerBase.__init__(self, db)
		self.connectto_all(pagesindexer, (
			'page-changed', 'page-row-delete'
		))

		self.db.executescript('''
			CREATE TABLE IF NOT EXISTS tags (
				id INTEGER PRIMARY KEY,
				name TEXT,
				sortkey TEXT,

				CONSTRAINT uc_TagOnce UNIQUE (name)
			);
			CREATE TABLE IF NOT EXISTS tagsources (
				source INTEGER REFERENCES pages(id),
				tag INTEGER REFERENCES tags(id),

				CONSTRAINT uc_TagSourceOnce UNIQUE (source, tag)
			);
		''')

	def on_page_changed(self, pagesindexer, pagerow, doc):
		oldtags = dict(
			(r[0], r) for r in self.db.execute(
				'SELECT tags.sortkey, tags.name, tags.id FROM tagsources '
				'LEFT JOIN tags ON tagsources.tag = tags.id '
				'WHERE tagsources.source=?',
				(pagerow['id'],)
			)
		)

		seen = set()
		for name in doc.iter_tag_names():
			sortkey = natural_sort_key(name)
			if sortkey in seen:
				continue
			elif sortkey in oldtags:
				oldtags.pop(sortkey)
			else:
				seen.add(sortkey)
				row = self.db.execute(
					'SELECT * FROM tags WHERE sortkey=?', (sortkey,)
				).fetchone()
				if not row:
					# Create new tag
					self.db.execute(
						'INSERT INTO tags(name, sortkey) VALUES (?, ?)',
						(name, sortkey)
					)
					row = self.db.execute(
						'SELECT * FROM tags WHERE sortkey=?', (sortkey,)
					).fetchone()
					assert row
					self.emit('tag-row-inserted', row)

				self.db.execute(
					'INSERT INTO tagsources(source, tag) VALUES (?, ?)',
					(pagerow['id'], row['id'])
				)
				self.emit('tag-added-to-page', row, pagerow)

		for row in list(oldtags.values()):
			self._remove_tag_from_page(row, pagerow)

	def on_page_row_delete(self, pageindexer, pagerow):
		# Before the actual page delete, break the tags one by one
		# this allows the treestore to drop rows one by one and have a better
		# chance of keeping the treeview in sync

		for row in self.db.execute(
			'SELECT tags.sortkey, tags.name, tags.id FROM tagsources '
			'LEFT JOIN tags ON tagsources.tag = tags.id '
			'WHERE tagsources.source=?'
			'ORDER BY tags.sortkey',
			(pagerow['id'],)
		):
			self._remove_tag_from_page(row, pagerow)

	def _remove_tag_from_page(self, row, pagerow):
		self.emit('tag-remove-from-page', row, pagerow)
		self.db.execute(
			'DELETE FROM tagsources WHERE source=? and tag=?',
			(pagerow['id'], row['id'])
		)
		self.emit('tag-removed-from-page', row, pagerow)
		n_children, = self.db.execute(
			'SELECT COUNT(*) FROM tagsources WHERE tag = ?', (row['id'],)
		).fetchone()
		if n_children == 0:
			self.db.execute('DELETE FROM tags WHERE id == ?', (row['id'],))
			self.emit('tag-row-deleted', row)

	def update_iter(self):
		rows = self.db.execute(
			'SELECT tags.name, tags.id FROM tags '
			'WHERE id not in (SELECT DISTINCT tag FROM tagsources)'
		).fetchall()

		self.db.execute(
			'DELETE FROM tags '
			'WHERE id not in (SELECT DISTINCT tag FROM tagsources)'
		)

		for row in rows:
			yield self.emit('tag-row-deleted', row)

		self.db.commit()


class TagsView(IndexView):

	def __init__(self, db):
		IndexView.__init__(self, db)
		self._pages = PagesViewInternal(db)

	def lookup_by_tagname(self, tag):
		if isinstance(tag, IndexTag):
			tag = tag.name
		row = self.db.execute(
			'SELECT name, id FROM tags WHERE name=?', (tag.lstrip('@'),)
		).fetchone()
		if not row:
			raise IndexNotFoundError
		return IndexTag(*row)

	def list_all_tags(self):
		'''Returns all tags in the index as L{IndexTag} objects'''
		for row in self.db.execute(
			'SELECT tags.name, tags.id '
			'FROM tags '
			'ORDER BY tags.sortkey, tags.name'
		):
			yield IndexTag(*row)

	def list_all_tags_by_n_pages(self):
		'''Returns all tags in the index as L{IndexTag} objects'''
		for row in self.db.execute(
			'SELECT tags.name, tags.id '
			'FROM tags '
			'INNER JOIN tagsources ON tags.id=tagsources.tag '
			'GROUP BY tags.id '
			'ORDER BY count(*) DESC'
		):
			yield IndexTag(*row)

	def n_list_all_tags(self):
		r = self.db.execute(
			'SELECT COUNT(*) '
			'FROM tags '
		).fetchone()
		return r[0]

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
		for row in self.db.execute(
			# The sub-query filters on pages that match all of the given tags
			# The main query selects all tags occuring on those pages and sorts
			# them by number of matching pages
			'SELECT tags.name, tags.id '
			'FROM tags '
			'INNER JOIN tagsources ON tags.id = tagsources.tag '
			'WHERE tagsources.source IN ('
			'   SELECT source FROM tagsources '
			'   WHERE tag IN %s '
			'   GROUP BY source '
			'   HAVING count(tag) = ? '
			' ) '
			'GROUP BY tags.id '
			'ORDER BY count(*) DESC' % tag_ids, (len(tags),)
		):
			yield IndexTag(*row)

	def list_tags(self, path):
		'''Returns all tags for a given page
		@param path: a L{Path} object for the page
		@returns: yields L{IndexTag} objects
		@raises IndexNotFoundError: if C{path} is not found in the index
		'''
		page_id = self._pages.get_page_id(path) # can raise
		return self._list_tags(page_id)

	def _list_tags(self, page_id):
		for row in self.db.execute(
			'SELECT tags.name, tags.id '
			'FROM tagsources '
			'LEFT JOIN tags ON tagsources.tag=tags.id '
			'WHERE tagsources.source = ?'
			'ORDER BY tags.sortkey, tags.name',
			(page_id,)
		):
			yield IndexTag(*row)

	def n_list_tags(self, path):
		page_id = self._pages.get_page_id(path) # can raise
		r = self.db.execute(
			'SELECT COUNT(*) '
			'FROM tagsources '
			'LEFT JOIN tags ON tagsources.tag=tags.id '
			'WHERE tagsources.source = ?',
			(page_id,)
		).fetchone()
		return r[0]

	def list_pages(self, tag):
		'''List all pages tagged with a given tag.
		@param tag: a tag name as string or an C{IndexTag} object
		@returns: yields L{PageIndexRecord} objects
		'''
		tag = self.lookup_by_tagname(tag)
		return self._list_pages(tag)

	def _list_pages(self, tag):
		for row in self.db.execute(
			'SELECT tagsources.source '
			'FROM tagsources JOIN pages ON tagsources.source=pages.id '
			'WHERE tagsources.tag = ? '
			'ORDER BY pages.sortkey, LENGTH(pages.name), pages.name',
			(tag.id,)
		):
			yield self._pages.get_pagename(row['source'])

	def n_list_pages(self, tag):
		tag = self.lookup_by_tagname(tag)
		r = self.db.execute(
			'SELECT COUNT(*) '
			'FROM tagsources JOIN pages ON tagsources.source=pages.id '
			'WHERE tagsources.tag = ?',
			(tag.id,)
		).fetchone()
		return r[0]


from .pages import IS_PAGE, PagesTreeModelMixin, MyTreeIter

assert IS_PAGE == 1
IS_TAG = 2 #: Hint for MyTreeIter


class TagsTreeModelBase(PagesTreeModelMixin):

	def __init__(self, index, tags=()):
		PagesTreeModelMixin.__init__(self, index)
		assert all(isinstance(t, str) for t in tags)
		self.tags = tuple(t.lstrip('@') for t in tags)
		self._tagids = ()
		self._tagquery = ''
		self._update_ids()
		self._deleted_tag_path = None

	def _update_ids(self):
		if not self.tags:
			self._tagids = ()
			self._tagquery = ' > 0 '  # match any tag
			return

		# Cache the ids of the selected tags
		if len(self.tags) == 1:
			row = self.db.execute('''
						SELECT id FROM tags
						WHERE name = ?
						ORDER BY sortkey, name
						''', self.tags
					).fetchone()
			if row:
				self._tagids = (row['id'],)
			else:
				self._tagids = ()
		else:
			rows = self.db.execute('''
						SELECT id FROM tags
						WHERE name in %s
						ORDER BY sortkey, name
						''' % (self.tags,)
					)
			self._tagids = tuple(r['id'] for r in rows)

		if len(self._tagids) == 0:
			self._tagquery =  ' = -1 ' # don't match any tag
		elif len(self._tagids) == 1:
			self._tagquery = ' = %i ' % self._tagids[0]
		else:
			self._tagquery = ' in %s ' % (self._tagids,)

	def _emit_children_inserted(self, pageid, treepath):
		treeiter = self.get_iter(treepath) # not mytreeiter !
		self.emit('row-has-child-toggled', treepath, treeiter)
		for row in self.db.execute(
			'SELECT id, name, n_children FROM pages WHERE parent = ?',
			(pageid,)
		):
			for childtreepath in self._find_all_pages(row['name']):
				if Gtk.TreePath(childtreepath[:-1]) == treepath:
					treeiter = self.get_iter(childtreepath) # not mytreeiter !
					self.emit('row-inserted', childtreepath, treeiter)
					if row['n_children'] > 0:
						self._emit_children_inserted(row['id'], childtreepath) # recurs
					break

	def connect_to_updateiter(self, index, update_iter):
		self.connectto_all(update_iter.pages,
			('page-row-inserted', 'page-row-changed', 'page-row-delete', 'page-row-deleted')
		)
		self.connectto_all(update_iter.tags,
			('tag-row-inserted', 'tag-row-deleted', 'tag-added-to-page', 'tag-remove-from-page', 'tag-removed-from-page')
		)

	def on_tag_row_inserted(self, o, row):
		if row['name'] in self.tags:
			self._update_ids()

	def on_tag_row_deleted(self, o, row):
		if row['name'] in self.tags:
			self._update_ids()

	def on_tag_removed_from_page(self, o, row, pagerow):
		if self._deleted_tag_path:
			self.flush_cache()
			self.emit('row-deleted', Gtk.TreePath(self._deleted_tag_path))
			self._deleted_tag_path = None


try:
	from gi.repository import Gtk
except ImportError:
	Gtk = None


class TaggedPagesTreeModelMixin(TagsTreeModelBase):
	'''Tree model that shows all pages for a given set of tags'''

	def _matches_all(self, pageid):
		if len(self._tagids) < len(self.tags):
			return False
		else:
			count, = self.db.execute('''
				SELECT COUNT(*) FROM tagsources
				LEFT JOIN pages ON tagsources.source = pages.id
				WHERE source = ? AND tag ''' + self._tagquery,
				(pageid,)
			).fetchone()
			return count == len(self._tagids)

	def on_tag_added_to_page(self, o, row, pagerow):
		self.flush_cache()
		if row['name'] in self.tags \
		and self._matches_all(pagerow['id']):
			# Without the new tag it did not match, so add to view
			# Find top level entry - ignore possible deeper matches
			for treepath in self._find_all_pages(pagerow['name']):
				if len(treepath) == 1:
					treeiter = self.get_iter(treepath) # not mytreeiter !
					self.emit('row-inserted', treepath, treeiter)
					if pagerow['n_children'] > 0:
						self._emit_children_inserted(pagerow['id'], treepath)

	def on_tag_remove_from_page(self, o, row, pagerow):
		if row['name'] in self.tags \
		and self._matches_all(pagerow['id']):
			# Still matches, but no longer after tag is removed
			# Find top level entry - ignore possible deeper matches
			for treepath in self._find_all_pages(pagerow['name']):
				if len(treepath) == 1:
					self._deleted_tag_path = treepath
					break

	def n_children_top(self):
		c, = self.db.execute('''
			SELECT COUNT(DISTINCT pages.id) FROM pages
			INNER JOIN tagsources ON pages.id = tagsources.source
			WHERE tagsources.tag''' + self._tagquery
		).fetchone()
		return c

	def get_mytreeiter(self, treepath):
		# Since we derive from PagesTreeModelMixin, we only need to manage the
		# top level. For lower levels the parent class will manage,
		# as long as we make sure the parent treepath is in the cache
		treepath = tuple(treepath) # used to cache
		if treepath in self.cache:
			return self.cache[treepath]

		if len(treepath) == 1:
			offset, = treepath
			for i, row in enumerate(self.db.execute('''
					SELECT pages.* FROM pages
					INNER JOIN tagsources ON pages.id = tagsources.source
					WHERE tagsources.tag %s
					GROUP BY source HAVING count(tag) = ?
					ORDER BY sortkey, LENGTH(name), name LIMIT 20 OFFSET ?
				''' % self._tagquery,
				(len(self._tagids), offset,)
			)):
				mytreepath = (offset + i,)
				if mytreepath not in self.cache:
					self.cache[mytreepath] = MyTreeIter(
						Gtk.TreePath(mytreepath),
						row,
						row['n_children'],
						IS_PAGE
					)
				else:
					break

			return self.cache.get(treepath, None)
		else:
			return PagesTreeModelMixin.get_mytreeiter(self, treepath)

	def _find_all_pages(self, name):
		# multiple top levels, below remainder is always the same
		treepaths = []
		names = name.split(':')
		pagetreepath = PagesTreeModelMixin._find_all_pages(self, name, update_cache=False)[0]
		assert len(names) == len(pagetreepath)
		for i in range(len(names)):
			n = ':'.join(names[:i + 1])
			row = self.db.execute('SELECT * FROM pages WHERE name=?', (n,)).fetchone()
			if row is None:
				raise IndexNotFoundError(name)
			else:
				if self._matches_all(row['id']):
					offset, = self.db.execute('''
							SELECT COUNT(*) FROM (
								SELECT * FROM pages
								INNER JOIN tagsources ON pages.id = tagsources.source
								WHERE tagsources.tag %s AND (
										sortkey < ?
										or (sortkey = ? and LENGTH(name) < ?)
										or (sortkey = ? and LENGTH(name) = ? and name < ?)
								)
								GROUP BY source HAVING count(tag) = ?
							)
						''' % self._tagquery,
						(
							row['sortkey'],
							row['sortkey'], len(row['name']),
							row['sortkey'], len(row['name']), row['name'],
							len(self._tagids)
						)
					).fetchone()
					mytreepath = (offset,)

					if mytreepath not in self.cache:
						myiter = MyTreeIter(
							Gtk.TreePath(mytreepath),
							row,
							row['n_children'],
							IS_PAGE
						)
						self.cache[mytreepath] = myiter

					treepaths.append(Gtk.TreePath(mytreepath + tuple(pagetreepath[i + 1:])))

		treepaths.sort()
		return treepaths


class TagsTreeModelMixin(TagsTreeModelBase):
	'''Tree model mixin class that uses tags as the toplevel

		tag1
			page_with_tag1
				child
				child
			...
		tag2
			page_with_tag2
		...

	If any tags are given on construction, the top level will be limitted
	to that set.
	'''

	def _get_offset_n_children(self, row):
		offset = self._tagids.index(row['id'])
		n_children, = self.db.execute(
			'SELECT COUNT(*) FROM tagsources WHERE tag = ?', (row['id'],)
		).fetchone()
		return offset, n_children

	def on_tag_added_to_page(self, o, row, pagerow):
		if row['name'] in self.tags:
			offset, n_children = self._get_offset_n_children(row)

			# emit row-insert for toplevel tag if needed
			if n_children == 1:
				treepath = (offset,)
				treeiter = self.get_iter(treepath) # not mytreeiter !
				self.emit('row-inserted', Gtk.TreePath(treepath), treeiter)

			# emit row-inserted 2nd level - recurs for children
			for treepath in self._find_all_pages(pagerow['name']):
				if len(treepath) == 2 and treepath[0] == offset:
					treeiter = self.get_iter(treepath) # not mytreeiter !
					self.emit('row-inserted', treepath, treeiter)
					if pagerow['n_children'] > 0:
						self._emit_children_inserted(pagerow['id'], treepath)
					break

			# emit parent changes
			treepath = (offset,)
			treeiter = self.get_iter(treepath) # not mytreeiter !
			if n_children == 1:
				self.emit('row-has-child-toggled', Gtk.TreePath(treepath), treeiter)
			self.emit('row-changed', Gtk.TreePath(treepath), treeiter)

	def on_tag_remove_from_page(self, o, row, pagerow):
		if row['name'] in self.tags:
			offset = self._tagids.index(row['id'])
			for treepath in self._find_all_pages(pagerow['name']):
				if treepath[0] == offset and len(treepath) == 2:
					self._deleted_tag_path = treepath
					break

	def on_tag_removed_from_page(self, o, row, pagerow):
		if self._deleted_tag_path:
			parent = self._deleted_tag_path[:-1]
			TagsTreeModelBase.on_tag_removed_from_page(self, o, row, pagerow)
			if parent:
				self.emit('row-changed', Gtk.TreePath(parent), self.get_iter(parent))

	def on_tag_row_deleted(self, o, row):
		if row['name'] in self.tags:
			offset = self._tagids.index(row['id'])
			self._update_ids()
			self.emit('row-deleted', Gtk.TreePath((offset,)))

	def get_mytreeiter(self, treepath):
		# Since we derive from PagesTreeModelMixin, we only need to manage the
		# two highest levels. For lower levels the parent class will manage,
		# as long as we make sure the parent treepath is in the cache
		treepath = tuple(treepath) # used to cache
		if treepath in self.cache:
			return self.cache[treepath]

		if len(treepath) == 1: # Toplevel tag
			offset, = treepath
			if self._tagids: # Selection
				row = self.db.execute('''
						SELECT * FROM tags WHERE id %s
						ORDER BY sortkey, name LIMIT 1 OFFSET ?
					''' % (self._tagquery,),
					(offset,)
				).fetchone()
			else: # Full set
				row = self.db.execute('''
						SELECT * FROM tags
						ORDER BY sortkey, name LIMIT 1 OFFSET ?
					''',
					(offset,)
				).fetchone()

			if row is None:
				return None
			else:
				n_children, = self.db.execute(
					'SELECT COUNT(*) FROM tagsources WHERE tag = ?', (row['id'],)
				).fetchone()
				mytreeiter = MyTreeIter(Gtk.TreePath(treepath), row, n_children, IS_TAG)
				self.cache[treepath] = mytreeiter
				return mytreeiter

		elif len(treepath) == 2: # Top level page below tag
			tag_path = treepath[:-1]
			tag_iter = self.get_mytreeiter(tag_path) # recurs
			if not tag_iter:
				return None

			offset = treepath[-1]
			for i, row in enumerate(self.db.execute('''
					SELECT DISTINCT pages.* FROM pages
					INNER JOIN tagsources ON pages.id = tagsources.source
					WHERE tagsources.tag = ?
					ORDER BY sortkey, LENGTH(name), name LIMIT 20 OFFSET ?
				''',
				(tag_iter.row['id'], offset,)
			)):
				mytreepath = tag_path + (offset + i,)
				if mytreepath not in self.cache:
					self.cache[mytreepath] = MyTreeIter(
						Gtk.TreePath(mytreepath),
						row,
						row['n_children'],
						IS_PAGE
					)
				else:
					break

			return self.cache.get(treepath, None)

		else:
			return PagesTreeModelMixin.get_mytreeiter(self, treepath)

	def find(self, path):
		treepaths = self.find_all(path)
		if treepaths:
			return treepaths[0]
		else:
			raise IndexNotFoundError(path.name)

	def find_all(self, path):
		if isinstance(path, IndexTag):
			return [self._find_tag(path.name)]
		else:
			if path.isroot:
				raise ValueError
			return self._find_all_pages(path.name)

	def _find_tag(self, tag):
		if isinstance(tag, int):
			row = self.db.execute(
				'SELECT * FROM tags WHERE id = ?', (tag,)
			).fetchone()
		else:
			row = self.db.execute(
				'SELECT * FROM tags WHERE name = ?', (tag,)
			).fetchone()

		if row is None:
			raise IndexNotFoundError

		offset, = self.db.execute('''
				SELECT COUNT(*) FROM tags
				WHERE (sortkey < ? or (sortkey < ? and name < ?))
			''',
			(row['sortkey'], row['sortkey'], row['name'])
		).fetchone()
		mytreepath = (offset,)
		if mytreepath not in self.cache:
			n_children, = self.db.execute(
				'SELECT COUNT(*) FROM tagsources WHERE tag = ?', (row['id'],)
			).fetchone()
			myiter = MyTreeIter(Gtk.TreePath(mytreepath), row, n_children, IS_TAG)
			self.cache[mytreepath] = myiter
		return Gtk.TreePath(mytreepath)

	def _find_all_pages(self, name):
		# multiple top levels, below remainder is always the same
		treepaths = []
		names = name.split(':')
		pagetreepath = PagesTreeModelMixin._find_all_pages(self, name, update_cache=False)[0]
		assert len(names) == len(pagetreepath)
		for i in range(len(names)):
			n = ':'.join(names[:i + 1])
			row = self.db.execute('SELECT * FROM pages WHERE name=?', (n,)).fetchone()
			if row is None:
				raise IndexNotFoundError(name)
			else:
				for tagid in self._matching_tag_ids(row['id']):
					mytreepath = self._find_tag(tagid)

					offset, = self.db.execute('''
							SELECT COUNT(DISTINCT pages.id) FROM pages
							INNER JOIN tagsources ON pages.id = tagsources.source
							WHERE tagsources.tag = ? AND (
								sortkey < ?
								or (sortkey = ? and LENGTH(name) < ?)
								or (sortkey = ? and LENGTH(name) = ? and name < ?)
							)
							ORDER BY sortkey, LENGTH(name), name
						''',
						(tagid,
							row['sortkey'],
							row['sortkey'], len(row['name']),
							row['sortkey'], len(row['name']), row['name']
						)
					).fetchone()

					mytreepath = tuple(mytreepath) + (offset,)
					if mytreepath not in self.cache:
						myiter = MyTreeIter(Gtk.TreePath(mytreepath), row, row['n_children'], IS_PAGE)
						self.cache[mytreepath] = myiter

					treepaths.append(Gtk.TreePath(mytreepath + tuple(pagetreepath[i + 1:])))

		treepaths.sort()
		return treepaths

	def _matching_tag_ids(self, pageid):
		# Returns tag ids for tags from our set that include page
		if self._tagids:
			rows = self.db.execute('''
				SELECT tag FROM tagsources
				WHERE source = ? AND tag ''' + self._tagquery,
				(pageid,)
			)
		else:
			rows = self.db.execute('''
				SELECT tag FROM tagsources
				WHERE source = ?''',
				(pageid,)
			)
		return tuple(r[0] for r in rows)
