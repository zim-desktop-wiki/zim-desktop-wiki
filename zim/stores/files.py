# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Basic store module for storing pages as files.

See StoreClass in zim.stores for the API documentation.

Each page maps to a single text file in a normal directory structure.
Page names map almost one on one to the relative directory path.
Sub-namespaces are contained in directories of the same basename as
the coresponding file name.

File extensions are determined by the source format used.
When doing a lookup we try to be case insensitive, but preserve case
once we have it resolved.
'''

import sys
import logging

import zim.fs
import zim.datetimetz as datetime
from zim.fs import File, Dir, FilteredDir, FileNotFoundError
from zim.async import AsyncOperation
from zim.formats import get_format
from zim.notebook import Path, Page, LookupError, PageExistsError
from zim.stores import StoreClass, encode_filename, decode_filename
from zim.config import HeadersDict
from zim.formats.wiki import WIKI_FORMAT_VERSION # FIXME hard coded preference for wiki format

logger = logging.getLogger('zim.stores.files')


class Store(StoreClass):

	def __init__(self, notebook, path, dir=None):
		'''Contruct a files store.

		Takes an optional 'dir' attribute.
		'''
		StoreClass.__init__(self, notebook, path)
		self.dir = dir
		if not self.store_has_dir():
			raise AssertionError, 'File store needs directory'
			# not using assert here because it could be optimized away
		self.format = get_format('wiki') # TODO make configable

	def _get_file(self, path):
		'''Returns a File object for a notebook path'''
		assert path != self.namespace, 'Can not get a file for the toplevel namespace'
		name = path.relname(self.namespace)
		filepath = encode_filename(name)+'.txt' # FIXME hard coded extension
		file = self.dir.file(filepath)
		file.checkoverwrite = True
		file.endofline = self.notebook.endofline
		return file

	def _get_dir(self, path):
		'''Returns a dir object for a notebook path'''
		if path == self.namespace:
			return self.dir
		else:
			name = path.relname(self.namespace)
			dirpath = encode_filename(name)
			return self.dir.subdir(dirpath)

	def get_page(self, path):
		file = self._get_file(path)
		dir = self._get_dir(path)
		return FileStorePage(path,
				haschildren=dir.exists(), source=file, format=self.format)

	def get_pagelist(self, path):
		dir = self._get_dir(path)
		names = set() # collide files and dirs with same name

		# We skip files with a space in them, because we can not resolve
		# them uniquely.
		for file in dir.list():
			if file.startswith('.') or file.startswith('_'):
				continue # no hidden files or directories
			elif file.endswith('.txt'): # TODO: do not hard code extension
				if ' ' in file:
					logger.warn('Ignoring file: "%s" invalid file name', file)
				else:
					names.add(decode_filename(file[:-4]))
			elif zim.fs.isdir( zim.fs.joinpath(dir.path, file) ):
				if ' ' in file:
					logger.warn('Ignoring file: "%s" invalid file name', file)
				else:
					names.add(decode_filename(file))
			else:
				pass # unknown file type

		for name in names: # sets are sorted by default
			yield self.get_page(path + name)

	def store_page(self, page):
		# FIXME assert page is ours and page is FilePage
		page._store()

	def store_page_async(self, page, lock, callback, data):
		page._store_async(lock, callback, data)

	def move_page(self, path, newpath):
		file = self._get_file(path)
		dir = self._get_dir(path)
		if not (file.exists() or dir.exists()):
			raise LookupError, 'No such page: %s' % path.name

		newfile = self._get_file(newpath)
		newdir = self._get_dir(newpath)
		if (newfile.exists() or newdir.exists()):
			if file.path.lower() == newfile.path.lower() \
			and (not newfile.exists() or file.compare(newfile)):
					pass # renaming on case-insensitive filesystem
			else:
				raise PageExistsError, 'Page already exists: %s' % newpath.name

		if file.exists():
			file.rename(newfile)

		if dir.exists():
			dir.rename(newdir)


	def delete_page(self, path):
		file = self._get_file(path)
		dir = self._get_dir(path)
		if not (file.exists() or dir.exists()):
			return False
		else:
			assert dir.path.startswith(self.dir.path)
			file.cleanup()
			dir.remove_children()
			dir.cleanup()
			if isinstance(path, Page):
				path.haschildren = False
				# hascontent is determined based on file existence
			return True

	def trash_page(self, path):
		file = self._get_file(path)
		dir = self._get_dir(path)
		re = False
		if file.exists():
			if not file.trash():
				return False
			re = True
		
		if dir.exists():
			re = dir.trash() or re
			dir.cleanup()
			if isinstance(path, Page):
				path.haschildren = False

		return re

	def page_exists(self, path):
		return self._get_file(path).exists()

	# It could be argued that we should use e.g. MD5 checksums to verify
	# integrity of the page content instead of mtime. It is true the mtime
	# can be unreliable, for example when files are read from a remote
	# network filesystem. However calculating the MD5 and refreshing the
	# index both require an operation on the actual file contents, so it is
	# more efficient to just re-index whenever the timestamps are out of
	# sync instead of calculating the MD5 for each page to be checked.

	def get_pagelist_indexkey(self, path):
		dir = self._get_dir(path)
		if dir.exists():
			return dir.mtime()
		else:
			return None

	def get_page_indexkey(self, path):
		file = self._get_file(path)
		if file.exists():
			return file.mtime()
		else:
			return None

	def get_attachments_dir(self, path):
		dir = StoreClass.get_attachments_dir(self, path)
		if not dir is None:
			dir = FilteredDir(dir)
			dir.ignore('*.txt') # FIXME hardcoded extendion
		return dir


class FileStorePage(Page):

	def __init__(self, path, haschildren=False, source=None, format=None):
		assert source and format
		Page.__init__(self, path, haschildren)
		self.source = source
		self.format = format
		self.readonly = not self.source.iswritable()
		self.properties = None

	def _source_hascontent(self):
		return self.source.exists()

	def _fetch_parsetree(self, lines=None):
		'''Fetch a parsetree from source or returns None'''
		#~ print '!! fetch tree', self
		try:
			lines = lines or self.source.readlines()
			self.properties = HeadersDict()
			self.properties.read(lines)
			# TODO: detect other formats by the header as well
			if 'Wiki-Format' in self.properties:
				version = self.properties['Wiki-Format']
			else:
				version = 'Unknown'
			parser = self.format.Parser(version)
			return parser.parse(lines)
		except FileNotFoundError:
			return None

	def _store(self):
		lines = self._dump()
		self._store_lines(lines)
		self.modified = False

	def _store_async(self, lock, callback, data):
		# Get lines before forking a new thread, otherwise the parsetree
		# could change in a non-atomic way in the GUI in the mean time
		try:
			lines = self._dump()
		except Exception, error:
			if callback:
				exc_info = sys.exc_info()
				callback(False, error, exc_info, data)
			return
		else:
			self.modified = False

		#~ print '!! STORE PAGE ASYNC in files'
		operation = AsyncOperation(
			self._store_lines, (lines,), lock=lock, callback=callback, data=data)
		operation.start()

	def _store_lines(self, lines):
		# Enable these lines to test error handling in the UI
		#~ import random
		#~ if random.random() > 0.5:
			#~ raise IOError, 'This is a test error'
		###

		if lines:
			self.source.writelines(lines)
		else:
			# Remove the file - this is not the same as remove_page()
			self.source.cleanup()

		return True # Need to return True for async callback

	def _dump(self):
		'''Returns the page source'''
		tree = self.get_parsetree()
		if tree is None:
			raise AssertionError, 'BUG: Can not store a page without content'

		#~ print 'STORE', tree.tostring()
		if tree.hascontent:
			new = False
			if self.properties is None:
				self.properties = HeadersDict()
				new = True
			self.properties['Content-Type'] = 'text/x-zim-wiki'
			self.properties['Wiki-Format'] = WIKI_FORMAT_VERSION
			if new:
				now = datetime.now()
				self.properties['Creation-Date'] = now.isoformat()

			# Note: No "Modification-Date" here because it causes conflicts
			# when merging branches with version control, use mtime from filesystem
			# If we see this header, remove it because it will not be updated.
			try:
				del self.properties['Modification-Date']
			except:
				pass

			lines = self.properties.dump()
			lines.append('\n')
			lines.extend(self.format.Dumper().dump(tree))
			return lines
		else:
			return []
