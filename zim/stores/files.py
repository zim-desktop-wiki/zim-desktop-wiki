# -*- coding: utf8 -*-

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

from zim.fs import *
from zim import formats
from zim.notebook import Page
from zim.stores import StoreClass

__store__ = 'files'


class Store(StoreClass):

	def __init__(self, dir=None, **args):
		'''Contruct a files store.

		Takes an optional 'dir' attribute.
		'''
		StoreClass.__init__(self, **args)
		self.dir = dir
		assert self.store_has_dir()
		self.format = formats.get_format('wiki') # TODO make configable

	def _get_file(self, path):
		'''Returns a File object for a notebook path'''
		assert path != self.namespace, 'Can not get a file for the toplevel namespace'
		name = path.relname(self.namespace)
		# TODO map strange characters
		filepath = name.replace(':', '/')+'.txt'
		return File([self.dir, filepath])

	def _get_dir(self, path):
		'''Returns a dir object for a notebook path'''
		if path == self.namespace:
			return self.dir
		else:
			name = path.relname(self.namespace)
			# TODO map strange characters
			dirpath = name.replace(':', '/')
			return Dir([self.dir, dirpath])

	def get_page(self, path):
		file = self._get_file(path)
		dir = self._get_dir(path)
		# TODO check if file exists and if it is writable
		#	return None if does not exist and can not be created
		#	set read-only when exists but not writable
		return Page(path,
				haschildren=dir.exists(), source=file, format=self.format)

	def get_pagelist(self, path):
		dir = self._get_dir(path)
		names = set() # collide files and dirs with same name

		for file in dir.list():
			if file.startswith('.') or file.startswith('_'):
				continue # no hidden files or directories
			elif file.endswith('.txt'): # TODO: do not hard code extension
				names.add(file[:-4])
			elif os.path.isdir( os.path.join(dir.path, file) ):
				names.add(file)
			else:
				pass # unknown file type

		for name in names: # sets are sorted by default
			yield self.get_page(path + name)

	#~ def move_page(self, name, newname):
		#~ '''FIXME'''

	#~ def copy_page(self, name, newname):
		#~ '''FIXME'''

	#~ def delete_page(self, name):
		#~ '''FIXME'''

	def get_index_key(self, path):
		'''Returns a string consisting of the mtime of the file and the mtime
		of the directory corresponding to this page. Both timestamps are taken
		as utime and joined by a ":" character. If either of these timestamps
		change this will cause the index to re-read the page and the asociated
		namespace.

		( It could be argued that we should use e.g. MD5 checksums to verify
		integrity of the page content instead of mtime. It is true the mtime
		can be unreliable, for example when files are read from a remote
		network filesystem. However calculating the MD5 and refreshing the
		index both require an operation on the actual file contents, so it is
		more efficient to just re-index whenever the timestamps are out of
		sync instead of calculating the MD5 for each page to be checked. )
		'''
		mtime = []
		for o in (self._get_file(path), self._get_dir(path)):
			if o.exists():
				mtime.append(o.mtime())
			else:
				mtime.append('')
		return ':'.join(mtime)
