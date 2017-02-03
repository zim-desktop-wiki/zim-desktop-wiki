

import logging

logger = logging.getLogger('zim.notebook.index')


# In addition allow indexing a page directly - file sync to happen later
# Allow on_move, on_delete etc.
# Allow force re-index

# Files are indexed relative to the notebook folder, allow for absolute
# path to change, e.g. when notebook is on an USB stick

# Priority sorted, higher number overrules lower number
STATUS_UPTODATE = 0
STATUS_CHECK = 1
STATUS_CHECK_RECURS = 2
STATUS_NEED_UPDATE = 3

TYPE_FOLDER = 1
TYPE_FILE = 2

from zim.newfs import File


class FilesIndexer(object):
	'''Class that will update the "files" table in the index based on
	changes seen on the file system.

	Logic is spread over two generator functions:

	  - C{check_iter()}: will find changes on the file system and is
	    intended to run in a background thread.
	    Requires usage of C{queue_check()} first to schedule which
	    records to be checked.
	  - C{update_iter()}: will update records that have been flagged
	    as out-of-date. This iterator is intended to run in main loop.
	'''

	# Note that there are no methods for new files or folders,
	# only methods for updating.
	# Logic is that we always start with update of a parent folder.
	# This means root folder always needs to be present in the table.
	#
	# Exception is a callback to let explicitly add a new file from
	# page save in notebook

	# Callbacks to the PageIndexer could have been implemented as
	# signals, but made 1-to-1 function calls because the object
	# configuration is fixed and logic is intertwined.

	# PageIndexer is a constructor argument to keep the indexers
	# testable

	def __init__(self, db, folder, page_indexer):
		self.db = db
		self.folder = folder
		self.page_indexer = page_indexer

	def init_db(self):
		self.db.executescript('''
		CREATE TABLE IF NOT EXISTS files(
			id INTEGER PRIMARY KEY,
			parent INTEGER REFERENCES files(id),

			path TEXT UNIQUE NOT NULL,
			node_type INTEGER NOT NULL,
			mtime TIMESTAMP,

			index_status INTEGER DEFAULT 3
		);
		''')
		row = self.db.execute('SELECT * FROM files WHERE id == 1').fetchone()
		if row is None:
			c = self.db.execute(
				'INSERT INTO files(parent, path, node_type, index_status)'
				' VALUES (?, ? , ?, ?)',
				(0, '.', TYPE_FOLDER, STATUS_NEED_UPDATE)
			)
			assert c.lastrowid == 1 # ensure we start empty
			return True

		return False

	def check_and_update_all(self):
		'''Convenience method to do a full update at once'''
		checker = FilesIndexChecker(self.db, self.folder)
		checker.queue_check()
		for out_of_date in checker.check_iter():
			if out_of_date:
				for i in self.update_iter():
					pass
		self.db.commit()

	def update_iter(self):
		'''Generator function for the actual update'''
		self.start_update()

		# sort folders before files: first index structure, then contents
		# this makes e.g. index links more efficient and robust
		# sort by id to ensure parents are found before children
		while True:
			row = self.db.execute(
				'SELECT id, path, node_type FROM files'
				' WHERE index_status = ?'
				' ORDER BY node_type, id',
				(STATUS_NEED_UPDATE, )
			).fetchone()

			if row:
				node_id, path, node_type = row
				#~ print ">> UPDATE", node_id, path, node_type
			else:
				break

			try:
				if node_type == TYPE_FOLDER:
					folder = self.folder.folder(path)
					if folder.exists():
						self.update_folder(node_id, folder)
					else:
						self.delete_folder(node_id)
				else:
					file = self.folder.file(path)
					if file.exists():
						self.update_file(node_id, file)
					else:
						self.delete_file(node_id)
			except:
				logger.exception('Error while indexing: %s', path)
				self.db.execute( # avoid looping
					'UPDATE files SET index_status = ? WHERE id = ?',
					(STATUS_UPTODATE, node_id)
				)

			yield

		self.finish_update()

	def start_update(self):
		self.page_indexer.on_db_start_update(self)

	def finish_update(self):
		self.page_indexer.on_db_finish_update(self)

	def interactive_add_file(self, file):
		assert isinstance(file, File) and file.exists()
		parent_id = self._add_parent(file.parent())
		path = file.relpath(self.folder)
		self.db.execute(
			'INSERT INTO files(path, node_type, index_status, parent)'
			' VALUES (?, ?, ?, ?)',
			(path, TYPE_FILE, STATUS_NEED_UPDATE, parent_id),
		)
		node_id, = self.db.execute(
			'SELECT id FROM files WHERE path=?', (path,)
		).fetchone()

		self.page_indexer.on_db_file_inserted(self, node_id, file)

		self.update_file(node_id, file)

	def _add_parent(self, folder):
		if folder.path == self.folder.path:
			return 1

		path = folder.relpath(self.folder)
		r = self.db.execute(
			'SELECT id FROM files WHERE path=?', (path,)
		).fetchone()
		if r is None:
			parent_id = self._add_parent(folder.parent()) # recurs
			self.db.execute(
				'INSERT INTO files(path, node_type, index_status, parent) '
				'VALUES (?, ?, ?, ?)',
				(path, TYPE_FOLDER, STATUS_NEED_UPDATE, parent_id)
			)
			r = self.db.execute(
				'SELECT id FROM files WHERE path=?', (path,)
			).fetchone()
			return r[0]
		else:
			return r[0]

	def update_folder(self, node_id, folder):
		# First invalidate all, so any children that are not found in
		# update will be left with this status
		#~ print '  update folder'
		self.db.execute(
			'UPDATE files SET index_status = ? WHERE parent = ?',
			(STATUS_NEED_UPDATE, node_id)
		)

		children = {}
		for childpath, child_id, mtime in self.db.execute(
			'SELECT path, id, mtime FROM files WHERE parent = ?',
			(node_id,)
		):
			children[childpath] = (child_id, mtime)

		mtime = folder.mtime() # get mtime before getting contents
		for child in folder:
			path = child.relpath(self.folder)
			if path in children:
				child_id, child_mtime = children[path]
				if child.mtime() == child_mtime:
					self.set_node_uptodate(child_id, child_mtime)
				else:
					pass # leave the STATUS_NEED_UPDATE for next loop
			else:
				# new child
				node_type = TYPE_FILE if isinstance(child, File) else TYPE_FOLDER
				if node_type == TYPE_FILE:
					self.db.execute(
						'INSERT INTO files(path, node_type, index_status, parent)'
						' VALUES (?, ?, ?, ?)',
						(path, node_type, STATUS_NEED_UPDATE, node_id),
					)
					child_id, = self.db.execute(
						'SELECT id FROM files WHERE path=?', (path,)
					).fetchone()

					self.page_indexer.on_db_file_inserted(self, child_id, child)
				else:
					self.db.execute(
						'INSERT INTO files(path, node_type, index_status, parent)'
						' VALUES (?, ?, ?, ?)',
						(path, node_type, STATUS_NEED_UPDATE, node_id),
					)

		self.set_node_uptodate(node_id, mtime)

	def update_file(self, node_id, file):
		# get mtime before contents /signal
		self.set_node_uptodate(node_id, file.mtime())

		self.page_indexer.on_db_file_updated(self, node_id, file)

	def set_node_uptodate(self, node_id, mtime):
		self.db.execute(
			'UPDATE files SET index_status = ?, mtime = ? WHERE id = ?',
			(STATUS_UPTODATE, mtime, node_id)
		)

	def delete_file(self, node_id):
		path, = self.db.execute('SELECT path FROM files WHERE id=?', (node_id,)).fetchone()
		file = self.folder.file(path)
		self.db.execute('DELETE FROM files WHERE id == ?', (node_id,))

		self.page_indexer.on_db_file_deleted(self, node_id, file)

	def delete_folder(self, node_id):
		for child_id, child_type in self.db.execute(
			'SELECT id, node_type FROM files WHERE parent == ?',
			(node_id,)
		):
			if child_type == TYPE_FOLDER:
				self.delete_folder(child_id) # recurs
			else:
				self.delete_file(child_id)

		self.db.execute('DELETE FROM files WHERE id == ?', (node_id,))


class FilesIndexChecker(object):

	def __init__(self, db, folder):
		self.db = db
		self.folder = folder

	def queue_check(self, path=None, recursive=True):
		if path is None:
			# check root
			node_id = 1
			path, status = self.db.execute(
				'SELECT path, index_status FROM files WHERE id = 1'
			).fetchone()
		else:
			raise NotImplementedError, 'TODO'

			# check specific path
			node_id, status = self.db.execute(
				'SELECT id, index_status FROM files WHERE path = ?',
				(path,)
			).fetchone()
			# TODO: if fail, find parent

		new_status = STATUS_CHECK_RECURS if recursive else STATUS_CHECK
		if status < new_status:
			self.db.execute(
				'UPDATE files SET index_status = ? WHERE id = ?',
				(new_status, node_id)
			)

	def check_iter(self):
		'''Generator function that walks existing records and flags
		records that are not longer valid. Yields in between checks
		to allow embedding in a loop.
		@return: Yields C{True} when an out of
		date record is found.
		'''
		# Check for pending updates first
		row = self.db.execute(
			'SELECT id FROM files WHERE index_status=?',
			(STATUS_NEED_UPDATE,)
		)
		if row is not None:
			yield True

		# sort folders before files: first index structure, then contents
		# this makes e.g. index links more efficient and robust
		# sort by id to ensure parents are found before children

		while True:
			row = self.db.execute(
				'SELECT id, path, node_type, mtime, index_status FROM files'
				' WHERE index_status > ? '
				' ORDER BY node_type, id',
				(STATUS_UPTODATE,)
			).fetchone()

			if row:
				node_id, path, node_type, mtime, check = row
			else:
				break

			if check == STATUS_NEED_UPDATE:
				yield True
				continue
			# else in (STATUS_CHECK, STATUS_CHECK_RECURS)

			try:
				if node_type == TYPE_FOLDER:
					obj = self.folder.folder(path)
				else:
					obj = self.folder.file(path)

				if not obj.exists():
					check = STATUS_CHECK # update will drop children, no need to recurs anymore
					new_status = STATUS_NEED_UPDATE

				else:
					if mtime == obj.mtime():
						new_status = STATUS_UPTODATE
					else:
						new_status = STATUS_NEED_UPDATE

				self.db.execute(
					'UPDATE files SET index_status = ?'
					' WHERE id = ?',
					(new_status, node_id)
				)

				if check == STATUS_CHECK_RECURS \
				and node_type == TYPE_FOLDER:
					self.db.execute(
						'UPDATE files SET index_status = ? '
						'WHERE parent = ? and index_status < ?',
						(STATUS_CHECK_RECURS, node_id, STATUS_CHECK_RECURS)
					)
					# the "<" prevents overwriting a more important flag

			except:
				logger.exception('Error while indexing: %s', path)
				self.db.execute( # avoid looping
					'UPDATE files SET index_status = ? WHERE id = ?',
					(STATUS_NEED_UPDATE, node_id)
				)
				new_status = STATUS_NEED_UPDATE

			yield new_status == STATUS_NEED_UPDATE



class TestFilesDBTable(object):
	# Mixin for test cases, defined here to have all SQL in one place

	def assertFilesDBConsistent(self, db):
		for row in db.execute('SELECT * FROM files'):
			if row['id'] > 1:
				parent = db.execute(
					'SELECT * FROM files WHERE id=?',
					(row['id'],)
				).fetchone()
				self.assertIsNotNone(parent,
					'Missing parent for %s' % row['path'])


	def assertFilesDBEquals(self, db, paths):
		rows = db.execute('SELECT * FROM files WHERE id>1').fetchall()

		in_db = dict((r['path'], r['node_type']) for r in rows)
		wanted = dict(
			(p.strip('/'), TYPE_FOLDER if p.endswith('/') else TYPE_FILE)
				for p in paths
		)

		self.assertEqual(in_db, wanted)
