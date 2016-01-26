# -*- coding: utf-8 -*-

# Copyright 2008-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Store module for storing pages as files.

With this store each page maps to a single text file. Sub-pages and
attachments go into a directory of the same name as the page. So
page names are mapped almost one on one to filesystem paths::

	page            notebook_folder/page.txt
	page:subpage    notebook_folder/page/subpage.txt

'''

import sys
import logging

logger = logging.getLogger('zim.notebook.stores.files')

import zim.fs
import zim.datetimetz as datetime

from zim.fs import File, Dir, FilteredDir, FileNotFoundError
from zim.utils import FunctionThread
from zim.formats import get_format
from zim.config import HeadersDict
from zim.formats.wiki import WIKI_FORMAT_VERSION # FIXME hard coded preference for wiki format


from zim.notebook.page import Page


from . import StoreClass, encode_filename, decode_filename, \
	PageExistsError, PageNotFoundError, StoreNode


# It could be argued that we should use e.g. MD5 checksums to verify
# integrity of the page content instead of mtime. It is true the mtime
# can be unreliable, for example when files are read from a remote
# network filesystem. However calculating the MD5 and refreshing the
# index both require an operation on the actual file contents, so it is
# more efficient to just re-index whenever the timestamps are out of
# sync instead of calculating the MD5 for each page to be checked.



class FileStoreNode(StoreNode):
	'''Proxy object that exposes page data based on source files.
	**Temporary class to deal with refactoring, will be removed again**
	'''

	__slots__ = ('format', 'properties')

	def __init__(self, basename, source_file, attachments_dir, format):
		StoreNode.__init__(self,
			basename	=	basename,
			hascontent	=	source_file and source_file.exists(),
			haschildren	=	attachments_dir.exists(),
			source_file	=	source_file,
			attachments_dir	=	attachments_dir,
			ctime		=	source_file.ctime() if source_file and source_file.exists() else None,
			mtime		=	source_file.mtime() if source_file and source_file.exists() else None,
		)
		self.format = format
		self.properties = None

	def get_parsetree(self):
		#~ print '!! fetch tree', self
		## Enable these lines to test error handling in the UI
		#~ import random
		#~ if random.random() > 0.5:
			#~ raise Exception, 'This is a test error'
		###
		try:
			lines = self.source_file.readlines()
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

	def store_parsetree(self, tree):
		## Enable these lines to test error handling in the UI
		#~ import random
		#~ if random.random() > 0.5:
			#~ raise IOError, 'This is a test error'
		###

		#~ print 'STORE', tree.tostring()
		if tree and tree.hascontent:
			self._store_parsetree(tree)
		else:
			self.source_file.cleanup()

	def _store_parsetree(self, tree):
		if self.hascontent and not self.properties:
			self.get_parsetree()
			assert self.properties is not None

		if self.properties is None:
			self.properties = HeadersDict()
			now = datetime.now()
			self.properties['Creation-Date'] = now.isoformat()

		self.properties['Content-Type'] = 'text/x-zim-wiki'
		self.properties['Wiki-Format'] = WIKI_FORMAT_VERSION

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

		self.source_file.writelines(lines)

	def get_children_etag(self):
		if self.attachments_dir.exists():
			return str(self.attachments_dir.mtime())
		else:
			return None

	def get_content_etag(self):
		if self.source_file.exists():
			try:
				return str(self.source_file.mtime())
			except OSError:
				# This should never happen - but it did, see lp:809086
				logger.exception('BUG:')
				return None
		else:
			return None


class FilesStore(StoreClass):

	def __init__(self, dir, endofline='unix'):
		'''Constructor
		@param dir: a L{Dir} object
		@param endofline: property for new L{File} objects

		This property can be one of 'unix' or 'dos'. Typically this
		property reflects the platform on which the notebook was created.

		For page files etc. this convention should be used when writing
		the file. This way a notebook can be edited from different
		platforms and we avoid showing the whole file as changed after
		every edit. (Especially important when a notebook is under
		version control.)
		'''
		self.dir = dir
		self.endofline = endofline
		self.format = get_format('wiki') # TODO make configurable

	def get_node(self, path):
		'''Returns the L{StoreNode} object for C{path}
		@raises PageNotAllowedError: when node cannot be accessed
		'''
		if path.isroot:
			return FileStoreNode(None, None, self.dir, self.format)
		else:
			file = self._get_file(path)
			dir = FilteredDir(self._get_dir(path))
			dir.ignore('*.txt') # FIXME hardcoded extension
			return FileStoreNode(path.basename, file, dir, self.format)

	def get_children(self, path):
		'''Iterator that yields L{StoreNode} objects for children of
		C{path}
		'''
		if path.isroot:
			dir = self.dir
		else:
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

		for name in sorted(names):
			yield self.get_node(path + name)


	def _get_file(self, path):
		'''Returns a File object for a notebook path'''
		filepath = encode_filename(path.name)+'.txt' # FIXME hard coded extension
		file = self.dir.file(filepath)
		file.checkoverwrite = True
		file.endofline = self.endofline
		return file

	def _get_dir(self, path):
		'''Returns a dir object for a notebook path'''
		if path.isroot:
			raise ValueError, 'No dir for root path'
		dirpath = encode_filename(path.name)
		return self.dir.subdir(dirpath)

	def move_page(self, path, newpath):
		file = self._get_file(path)
		dir = self._get_dir(path)
		if not (file.exists() or dir.exists()):
			raise PageNotFoundError(path)

		newfile = self._get_file(newpath)
		newdir = self._get_dir(newpath)
		if file.path.lower() == newfile.path.lower():
			if (newfile.exists() and newfile.isequal(file)) \
			or (newdir.exists() and newdir.isequal(dir)):
				# renaming on case-insensitive filesystem
				pass
			elif newfile.exists() or newdir.exists():
				raise PageExistsError(newpath)
		elif newfile.exists() or newdir.exists():
			raise PageExistsError(newpath)

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

