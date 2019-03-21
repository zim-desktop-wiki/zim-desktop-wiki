

import os
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
STATUS_NEED_UPDATE = 2
STATUS_NEED_DELETION = 3

TYPE_FOLDER = 1
TYPE_FILE = 2

from zim.newfs import File, Folder, SEP
from zim.signals import SignalEmitter


class FilesIndexer(SignalEmitter):
	'''Class that will update the "files" table in the index based on
	changes seen on the file system.

	@signal: C{file-row-inserted (row, file)}: on new file found
	@signal: C{file-row-changed (row, file)}: on file content changed
	@signal: C{file-row-deleted (row)}: on file deleted

	'''

	# Note that there are no methods for new files or folders,
	# only methods for updating.
	# Logic is that we always start with update of a parent folder.
	# This means root folder always needs to be present in the table.
	#
	# Exception is a callback to let explicitly add a new file from
	# page save in notebook

	__signals__ = {
		'file-row-inserted': (None, None, (object,)),
		'file-row-changed': (None, None, (object,)),
		'file-row-deleted': (None, None, (object,)),
	}

	def __init__(self, db, folder):
		self.db = db
		self.folder = folder

		self.db.executescript('''
		CREATE TABLE IF NOT EXISTS files(
			id INTEGER PRIMARY KEY,
			parent INTEGER REFERENCES files(id),

			path TEXT UNIQUE NOT NULL,
			node_type INTEGER NOT NULL,
			mtime TIMESTAMP,

			index_status INTEGER DEFAULT 3

			CONSTRAINT no_self_ref CHECK (parent <> id)
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

	def is_uptodate(self):
		row = self.db.execute(
			'SELECT * FROM files WHERE index_status=?',
			(STATUS_NEED_UPDATE,)
		).fetchone()
		return row is None

	def update_iter(self):
		'''Generator function for the actual update'''
		for i in self._update_iter_inner():
			yield

	def _update_iter_inner(self, prefix=''):
		# sort folders before files: first index structure, then contents
		# this makes e.g. index links more efficient and robust
		# sort by id to ensure parents are found before children
		while True:
			row = self.db.execute(
				'SELECT id, path, node_type FROM files'
				' WHERE index_status = ? AND path LIKE ?'
				' ORDER BY node_type, id',
				(STATUS_NEED_UPDATE, prefix + '%')
			).fetchone()

			if row:
				node_id, path, node_type = row
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

			self.db.commit()
			yield

	def interactive_add_file(self, file):
		assert isinstance(file, File) and file.exists()
		parent_id = self._add_parent(file.parent())
		path = file.relpath(self.folder)
		self.db.execute(
			'INSERT INTO files(path, node_type, index_status, parent)'
			' VALUES (?, ?, ?, ?)',
			(path, TYPE_FILE, STATUS_NEED_UPDATE, parent_id),
		)
		row = self.db.execute(
			'SELECT * FROM files WHERE path=?', (path,)
		).fetchone()

		self.emit('file-row-inserted', row)

		self.update_file(row['id'], file)

	def interactive_add_folder(self, folder):
		assert isinstance(folder, Folder) and folder.exists()
		parent_id = self._add_parent(folder.parent())
		path = folder.relpath(self.folder)
		self.db.execute(
			'INSERT INTO files(path, node_type, index_status, parent)'
			' VALUES (?, ?, ?, ?)',
			(path, TYPE_FOLDER, STATUS_NEED_UPDATE, parent_id),
		)
		row = self.db.execute(
			'SELECT * FROM files WHERE path=?', (path,)
		).fetchone()

		self.emit('file-row-inserted', row)

		self.update_folder(row['id'], folder)
		for i in self._update_iter_inner(prefix=path):
			pass

	def _add_parent(self, folder):
		if folder == self.folder:
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
				(path, TYPE_FOLDER, STATUS_CHECK, parent_id)
				# We set status to check because we assume the file being
				# added is the only child, but makes sense to verify later on
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
		logger.debug('Index folder: %s', folder)

		children = {}
		for childpath, child_id, mtime, index_status in self.db.execute(
			'SELECT path, id, mtime, index_status FROM files WHERE parent = ?',
			(node_id,)
		):
			children[childpath] = (child_id, mtime, index_status)

		self.db.execute(
			'UPDATE files SET index_status = ? WHERE parent = ?',
			(STATUS_NEED_DELETION, node_id)
		)

		mtime = folder.mtime() # get mtime before getting contents
		for child in folder:
			path = child.relpath(self.folder)
			if path in children:
				child_id, child_mtime, index_status = children[path]
				if index_status == STATUS_NEED_UPDATE or child.mtime() != child_mtime:
					# If the status was "need update" already, don't overrule it
					# here with mtime check - else we break flag_reindex()
					self.db.execute(
						'UPDATE files SET index_status = ? WHERE id = ?',
						(STATUS_NEED_UPDATE, child_id)
					)
				else:
					self.set_node_uptodate(child_id, child_mtime)
			else:
				# new child
				node_type = TYPE_FILE if isinstance(child, File) else TYPE_FOLDER
				if node_type == TYPE_FILE:
					self.db.execute(
						'INSERT INTO files(path, node_type, index_status, parent)'
						' VALUES (?, ?, ?, ?)',
						(path, node_type, STATUS_NEED_UPDATE, node_id),
					)
					row = self.db.execute(
						'SELECT * FROM files WHERE path=?', (path,)
					).fetchone()
					self.emit('file-row-inserted', row)
				else:
					self.db.execute(
						'INSERT INTO files(path, node_type, index_status, parent)'
						' VALUES (?, ?, ?, ?)',
						(path, node_type, STATUS_NEED_UPDATE, node_id),
					)

		# Clean up nodes not found in listing
		for child_id, child_type in self.db.execute(
			'SELECT id, node_type FROM files WHERE parent=? AND index_status=?',
			(node_id, STATUS_NEED_DELETION)
		):
			if child_type == TYPE_FOLDER:
				self.delete_folder(child_id)
			else:
				self.delete_file(child_id)

		self.set_node_uptodate(node_id, mtime)

	def update_file(self, node_id, file):
		logger.debug('Index file: %s', file)
		# get mtime before contents /signal
		self.set_node_uptodate(node_id, file.mtime())
		row = self.db.execute('SELECT * FROM files WHERE id=?', (node_id,)).fetchone()
		assert row is not None, 'No row matching id: %r' % node_id
		self.emit('file-row-changed', row)

	def set_node_uptodate(self, node_id, mtime):
		self.db.execute(
			'UPDATE files SET index_status = ?, mtime = ? WHERE id = ?',
			(STATUS_UPTODATE, mtime, node_id)
		)

	def delete_file(self, node_id):
		row = self.db.execute('SELECT * FROM files WHERE id=?', (node_id,)).fetchone()
		logger.debug('Drop file: %s', row['path'])
		self.emit('file-row-deleted', row)
		self.db.execute('DELETE FROM files WHERE id == ?', (node_id,))

	def delete_folder(self, node_id):
		assert node_id != 1, 'BUG: notebook folder went missing ?'
		for child_id, child_type in self.db.execute(
			'SELECT id, node_type FROM files WHERE parent == ?',
			(node_id,)
		):
			if child_type == TYPE_FOLDER:
				self.delete_folder(child_id) # recurs
			else:
				self.delete_file(child_id)

		row = self.db.execute('SELECT * FROM files WHERE id=?', (node_id,)).fetchone()
		logger.debug('Drop folder: %s', row['path'])
		self.db.execute('DELETE FROM files WHERE id == ?', (node_id,))


class FilesIndexChecker(object):

	def __init__(self, db, folder):
		self.db = db
		self.folder = folder

	def queue_check(self, file=None, recursive=True):
		if file is None:
			file = self.folder
		elif not (file == self.folder or file.ischild(self.folder)):
			raise ValueError('file must be child of %s' % self.folder)

		# If path is not indexed, find parent that is
		while not file == self.folder:
			row = self.db.execute(
				'SELECT * FROM files WHERE path = ?',
				(file.relpath(self.folder), )
			).fetchone()
			if row is None:
				file = file.parent()
			else:
				break # continue with this file or folder

		# Queue check
		if recursive and file == self.folder:
			self.db.execute(
				'UPDATE files SET index_status = ? WHERE index_status < ?',
				(STATUS_CHECK, STATUS_CHECK)
			)
		else:
			path = '.' if file == self.folder else file.relpath(self.folder)
			self.db.execute(
				'UPDATE files SET index_status = ? WHERE path = ? and index_status < ?',
				(STATUS_CHECK, path, STATUS_CHECK)
			)
			if recursive and isinstance(file, Folder):
				self.db.execute(
					'UPDATE files SET index_status = ? WHERE path LIKE ? and index_status < ?',
					(STATUS_CHECK, path + SEP + '%', STATUS_CHECK)
				)
			self.db.commit()

	def check_iter(self):
		'''Generator function that walks existing records and flags
		records that are not longer valid. Yields in between checks
		to allow embedding in a loop.
		@returns: Yields C{True} when an out of
		date record is found.
		'''
		# Check for pending updates first
		row = self.db.execute(
			'SELECT id FROM files WHERE index_status=?',
			(STATUS_NEED_UPDATE,)
		).fetchone()
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
				#~ logger.debug('Check %s', row['path'])
				node_id, path, node_type, mtime, check = row
			else:
				break # done

			if check == STATUS_NEED_UPDATE:
				yield True
				continue # let updater handle this first

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
				self.db.commit()

			except:
				logger.exception('Error while indexing: %s', path)
				self.db.execute( # avoid looping
					'UPDATE files SET index_status = ? WHERE id = ?',
					(STATUS_NEED_UPDATE, node_id)
				)
				self.db.commit()
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
		import os
		rows = db.execute('SELECT * FROM files WHERE id>1').fetchall()

		in_db = dict((r['path'], r['node_type']) for r in rows)
		wanted = dict(
			(p.strip(SEP), TYPE_FOLDER if p.endswith(SEP) else TYPE_FILE)
				for p in paths
		)

		self.assertEqual(in_db, wanted)
