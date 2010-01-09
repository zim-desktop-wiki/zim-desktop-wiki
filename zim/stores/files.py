# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

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

import os # using os directly in get_pagelist()
from datetime import datetime

from zim.fs import *
from zim.fs import FilteredDir
from zim.formats import get_format
from zim.notebook import Path, Page, LookupError, PageExistsError
from zim.stores import StoreClass, encode_filename, decode_filename
from zim.config import HeadersDict


class Store(StoreClass):

	def __init__(self, notebook, path, dir=None):
		'''Contruct a files store.

		Takes an optional 'dir' attribute.
		'''
		StoreClass.__init__(self, notebook, path)
		self.dir = dir
		assert self.store_has_dir()
		self.format = get_format('wiki') # TODO make configable

	def _get_file(self, path):
		'''Returns a File object for a notebook path'''
		assert path != self.namespace, 'Can not get a file for the toplevel namespace'
		name = path.relname(self.namespace)
		filepath = encode_filename(name)+'.txt' # FIXME hard coded extension
		return File([self.dir, filepath])

	def _get_dir(self, path):
		'''Returns a dir object for a notebook path'''
		if path == self.namespace:
			return self.dir
		else:
			name = path.relname(self.namespace)
			dirpath = encode_filename(name)
			return Dir([self.dir, dirpath])

	def get_page(self, path):
		file = self._get_file(path)
		dir = self._get_dir(path)
		# TODO check if file exists and if it is writable
		#	return None if does not exist and can not be created
		#	set read-only when exists but not writable
		return FileStorePage(path,
				haschildren=dir.exists(), source=file, format=self.format)

	def get_pagelist(self, path):
		dir = self._get_dir(path)
		names = set() # collide files and dirs with same name

		for file in dir.list():
			if file.startswith('.') or file.startswith('_'):
				continue # no hidden files or directories
			elif file.endswith('.txt'): # TODO: do not hard code extension
				names.add(decode_filename(file[:-4]))
			elif os.path.isdir( os.path.join(dir.path, file) ):
				names.add(decode_filename(file))
			else:
				pass # unknown file type

		for name in names: # sets are sorted by default
			yield self.get_page(path + name)

	def store_page(self, page):
		# FIXME assert page is ours and page is FilePage
		page._store_parsetree()

	def move_page(self, path, newpath):
		file = self._get_file(path)
		dir = self._get_dir(path)
		if not (file.exists() or dir.exists()):
			raise LookupError, 'No such page: %s' % path.name

		newfile = self._get_file(newpath)
		newdir = self._get_dir(newpath)
		if (newfile.exists() or newdir.exists()):
			if file.path.lower() == newfile.path.lower() \
			and file.compare(newfile):
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
			file.cleanup()
			assert dir.path.startswith(self.dir.path)
			dir.remove_children()
			dir.cleanup()
			return True

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
		self.source.checkoverwrite = True
		self.readonly = not self.source.iswritable()

	def _source_hascontent(self):
		return self.source.exists()

	def _fetch_parsetree(self, lines=None):
		'''Fetch a parsetree from source or returns None'''
		#~ print '!! fetch tree', self
		if lines or self.source.exists():
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
		else:
			return None

	def _store_parsetree(self):
		'''Save a parse tree to page source'''
		tree = self.get_parsetree()
		assert tree, 'BUG: Can not store a page without content'

		#~ print 'STORE', tree.tostring()
		if tree.hascontent:
			new = False
			if not self.properties:
				self.properties = HeadersDict()
				new = True
			self.properties['Content-Type'] = 'text/x-zim-wiki'
			self.properties['Wiki-Format'] = 'zim 0.26'
			if new:
				now = datetime.now()
				self.properties['Creation-Date'] = now.isoformat()

			# Note: No "Modification-Date" here because it causes conflicts
			# when merging branches with version control, use mtime from filesystem

			lines = self.properties.dump()
			lines.append('\n')
			lines.extend(self.format.Dumper().dump(tree))
			self.source.writelines(lines)
		else:
			# Remove the file - this is not the same as remove_page()
			self.source.cleanup()

		self.modified = False

	def get_links(self):
		# Optimised version of get_links, just check if we contain
		# links at all - if not don't bother parsing the content,
		# but if we do only trust the parse to get it right
		# (e.g. taking care of verbatim, escapes etc.)
		if not (self._parsetree or self._ui_object) \
		and hasattr(self.format, 'contains_links'):
			#~ print '!! FileStorePage.get_links() Optimisation used'
			if self.source.exists():
				lines = self.source.readlines()
				if self.format.contains_links(lines):
					self._parsetree = self._fetch_parsetree(lines)
					for link in Page.get_links(self):
						yield link
		else:
			for link in Page.get_links(self):
				yield link

		# TODO: should we cache 'lines' as well in case we get asked
		# for the parsetree after all ?
