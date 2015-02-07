# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Store module for storing pages as files.

With this store each page maps to a single text file. Sub-pages and
attachments go into a directory of the same name as the page. So
page names are mapped almost one on one to filesystem paths::

	page            notebook_folder/page.txt
	page:subpage    notebook_folder/page/subpage.txt

(The exact file extension can be determined by the source format used.)
'''

import sys
import logging

import zim.fs
import zim.datetimetz as datetime
from zim.fs import File, Dir, FilteredDir, FileNotFoundError
from zim.utils import FunctionThread
from zim.formats import get_format
from zim.notebook import Path, Page, LookupError, PageExistsError
from zim.stores import StoreClass, encode_filename, decode_filename
from zim.config import HeadersDict
from zim.formats.wiki import WIKI_FORMAT_VERSION # FIXME hard coded preference for wiki format

logger = logging.getLogger('zim.stores.files')


class FilesStore(StoreClass):

	def __init__(self, notebook, path, dir=None):
		'''Constructor

		@param notebook: a L{Notebook} object
		@param path: a L{Path} object for the mount point within the notebook
		@keyword dir: a L{Dir} object

		When no dir is given and the notebook has a dir already
		the dir is derived based on the path parameter. In the easiest
		case when path is the root, the notebook dir is copied.
		'''
		StoreClass.__init__(self, notebook, path)
		self.dir = dir
		if not self.store_has_dir():
			raise AssertionError, 'File store needs directory'
			# not using assert here because it could be optimized away
		self.format = get_format('wiki') # TODO make configurable

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
		return FileStorePage(path, source=file, folder=dir, format=self.format)

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

	def store_page_async(self, page):
		return page._store_async()

	def revert_page(self, page):
		# FIXME assert page is ours and page is FilePage
		newpage = self.get_page(page)
		page.source = newpage.source
		page.set_parsetree(newpage.get_parsetree())
			# use set_parsetree because it triggers ui_object
		page.modified = False

	def move_page(self, path, newpath):
		file = self._get_file(path)
		dir = self._get_dir(path)
		if not (file.exists() or dir.exists()):
			raise LookupError, 'No such page: %s' % path.name

		newfile = self._get_file(newpath)
		newdir = self._get_dir(newpath)
		if file.path.lower() == newfile.path.lower():
			if (newfile.exists() and newfile.isequal(file)) \
			or (newdir.exists() and newdir.isequal(dir)):
				# renaming on case-insensitive filesystem
				pass
			elif newfile.exists() or newdir.exists():
				raise PageExistsError, 'Page already exists: %s' % newpath.name
		elif newfile.exists() or newdir.exists():
			raise PageExistsError, 'Page already exists: %s' % newpath.name

		if file.exists():
			file.rename(newfile)

		if dir.exists():
			if newdir.ischild(dir):
				# special case where we want to move a page down
				# into it's own namespace
				parent = dir.dir
				tmpdir = parent.new_subdir(dir.basename)
				dir.rename(tmpdir)
				tmpdir.rename(newdir)

				# check if we also moved the file inadvertently
				if newfile.ischild(dir):
					movedfile = newdir.file(newfile.basename)
					movedfile.rename(newfile)
			else:
				dir.rename(newdir)

	def delete_page(self, path):
		file = self._get_file(path)
		dir = self._get_dir(path)
		if not (file.exists() or dir.exists()):
			return False
		else:
			assert file.path.startswith(self.dir.path)
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
			try:
				return file.mtime()
			except OSError:
				# This should never happen - but it did, see lp:809086
				logger.exception('BUG:')
				return None
		else:
			return None

	def get_attachments_dir(self, path):
		dir = StoreClass.get_attachments_dir(self, path)
		if not dir is None:
			dir = FilteredDir(dir)
			dir.ignore('*.txt') # FIXME hardcoded extension
		return dir


class FileStorePage(Page):
	'''Implementation of L{Page} that has a file as source

	The source is expected to consist of an header section (which have
	the same format as email headers) and a body that is some dialect
	of wiki text.

	Parsing the source file is delayed till the first call to
	L{get_parsetree()} so creating an object instance does not have
	the overhead of file system access.

	@ivar source: the L{File} object for this page
	@ivar format: the L{zim.formats} sub-module used for parsing the file
	'''

	def __init__(self, path, source=None, folder=None, format=None):
		assert source and format
		Page.__init__(self, path, haschildren=folder.exists())
		self.source = source
		self.folder = folder
		self.format = format
		self.readonly = not self.source.iswritable()
		self.properties = None

	def isequal(self, other):
		print "IS EQUAL", self, other
		if not isinstance(other, FileStorePage):
			return False

		if self == other:
			# If object equal by definition they are the equal
			return True

		# If we have an existing source check it
		# If we have an existing folder check it
		# If either fails we are not equal
		# If both do not exist we are also not equal

		ok = False
		if self.source and self.source.exists():
			ok = (
				other.source
				and self.source.isequal(other.source)
			)
			if not ok:
				return False


		if self.folder and self.folder.exists():
			ok = (
				other.folder
				and self.folder.isequal(other.folder)
			)

		return ok

	def _source_hascontent(self):
		return self.source.exists()

	def _fetch_parsetree(self, lines=None):
		'''Fetch a parsetree from source or returns None'''
		#~ print '!! fetch tree', self
		## Enable these lines to test error handling in the UI
		#~ import random
		#~ if random.random() > 0.5:
			#~ raise Exception, 'This is a test error'
		###
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

	def _store_async(self):
		# Get lines before forking a new thread, otherwise the parsetree
		# could change in a non-atomic way in the GUI in the mean time
		lines = self._dump()
		self.modified = False

		#~ print '!! STORE PAGE ASYNC in files'
		func = FunctionThread(self._store_lines, (lines,))
		func.start()
		return func

	def _store_lines(self, lines):
		## Enable these lines to test error handling in the UI
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
