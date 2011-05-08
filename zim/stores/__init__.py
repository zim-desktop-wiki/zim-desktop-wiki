# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Base class for storage backends

This module contains a base class for store modules. It implements
some common methods and provides API documentation for the store
modules.

Each store module should implement a class named "Store" which
inherits from StoreClass. All methods marked with "ABSTRACT" need to
be implemented in the sub class. When called directly they will raise
a NotImplementedError. Overloading other methods is optional.

=== Storage Model ===

Stores handle content in terms of Page objects. How the data that is
managed by the store is mapped to pages is up to the store implementation.
For example in the default store each page is mapped to a text file,
but there can also be store impementations that store many pages in the
same file, or that use for example a database. The store is however
expected to be consistent. So when a page is stored under a specific name
it should also be retrievable under that name.

Pages can be stored in a hierarchic way where each page can have sub-pages.
Or, in other terms, each page has a like names namespace that can store
sub pages. In the default store this structure is mapped to a directory
structure where for each page there can be a like named directory which
contains the files used to store sub-pages. The full page name for a page
consists of the names of all it's parents plus it's own base name seperated
with the ':' character. It is advised that each page should have a unique
name. Symbolic links or aliases for pages should be handled on a different
level. In the store interface page names are always assumed to be case
sensitive. However the store is allowed to be not case sensitive if the storage
backend does not support this (e.g. a file system that is not case sensitive).

The store exposes it's content using Page objects and lists of Page objects.
Each page object has two boolean attributes 'hascontent' and 'haschildren'.
Typically in a page listing at least one of these attributes should be true,
as a page either has content of it's own, or is used as a container for
sub-pages, or both. However both attributed can be False for new pages, or
for pages that have just been deleted.

The index will cache page listings in order to speed up the performance,
so it should not be necessary to do speed optializations in the store lookups.
However for eficient caching, store objects should implement the
'get_pagelist_indexkey()' and 'get_page_indexkey()' methods.

The notebook will use Path objects when requesting a specific page. These
paths just map to a specific page name but do not contain any information
about the actual existence of the page etc.

If a non-exising page is requested the store should check if we are allowed
to create the page. If so, a new page object should be returned, but actually
creating the page can be delayed until content is stored in it. Creating
the page also implicitly creates all of it's parents page, since it should
be visible in the hierarchy of page listings. If we are not allowed to create
the page (e.g. in case of a read-only notebook) no page object should be
returned.

If a page list for a non-existing path is requested, the store can just
return an empty list.
'''

from __future__ import with_statement

import sys
import re
import codecs

import zim.fs
from zim.fs import *
from zim.parsing import is_url_re
from zim.errors import TrashNotSupportedError


def get_store(name):
	'''Returns the module object for a specific store type.'''
	# __import__ has some quirks, soo the reference manual
	mod = __import__('zim.stores.'+name)
	mod = getattr(mod, 'stores')
	mod = getattr(mod, name)
	return mod


def _url_encode_on_error(error):
	string = error.object
	section = string[error.start:error.end].encode('utf-8')
	replace = u''
	for char in section:
		replace += u'%%%02X' % ord(char)
	return replace, error.end

codecs.register_error('urlencode', _url_encode_on_error)


def encode_filename(pagename):
	'''Encodes a pagename to a filename. Namespaces are mapped to directories.
	Returns basename without extension.
	Characters not allowed for the filesystem are encoded with url encoding.
	'''
	assert not '%' in pagename # just to be sure
	if not zim.fs.ENCODING in ('utf-8', 'mbcs'):
		# if not utf-8 we may not be able to encode all characters
		# enforce safe encoding, but do not actually encode here
		# ('mbcs' means we are running on windows and filesystem can
		# handle unicode natively )
		pagename = pagename.encode(zim.fs.ENCODING, 'urlencode')
		pagename = pagename.decode(zim.fs.ENCODING)
	return pagename.replace(':', '/').replace(' ', '_')


_url_decode_re = re.compile('%([a-fA-F0-9]{2})')

def _url_decode(match):
	return chr(int(match.group(1), 16))


def decode_filename(filename):
	'''Decodes a file basename to a pagename'''
	if zim.fs.ENCODING != 'utf-8':
		filename = filename.encode('utf-8')
		filename = _url_decode_re.sub(_url_decode, filename)
		filename = filename.decode('utf-8')
	return filename.replace('/', ':').replace('_', ' ')


class StoreClass():

	def __init__(self, notebook, path):
		'''Constructor for stores.
		At least pass a notebook and the path for our namespace.
		'''
		self.notebook = notebook
		self.namespace = path

	def get_page(self, path):
		'''ABSTRACT METHOD, must be implemented in all sub-classes.

		Return a new Page object for a path.
		'''
		raise NotImplementedError

	def get_pagelist(self, path):
		'''ABSTRACT METHOD, must be implemented in all sub-classes.

		Should return a list (or iterator) of page objects below a specific
		path. Used by the index to recursively find all pages in the store.
		'''
		raise NotImplementedError

	def store_page(self, page):
		'''ABSTRACT METHOD, must be implemented in all sub-classes.

		Store a page in the backend storage.
		'''
		raise NotImplementedError

	def store_page_async(self, page, lock, callback, data):
		'''OPTIONAL METHOD, could be implemented by sub-classes. In this
		base class it defaults to store_page()
		'''
		try:
			with lock:
				self.store_page(page)
		except Exception, error:
			if callback:
				exc_info = sys.exc_info()
				callback(False, error, exc_info, data)
		else:
			if callback:
				callback(True, None, None, data)

	def move_page(self, path, newpath):
		'''ABSTRACT METHOD, must be implemented in sub-class if store is
		writable.

		Move content from "oldpath" to "newpath". If oldpath is a Page
		object this should result in 'page.hascontent' being False if
		succesfull.

		Raises an error if path does not exist, or if newpath already exists.
		'''
		raise NotImplementedError

	def delete_page(self, path):
		'''ABSTRACT METHOD, must be implemented in sub-class if store is
		writable.

		Deletes a page. If path is a Page object this should result
		in 'page.hascontent' and 'page.haschildren' being False if succesfull.

		Returns False if page did not exist in the first place, True otherwise.
		'''
		raise NotImplementedError

	def trash_page(self, path):
		'''ABSTRACT METHOD, optional to be implemented in sub-class
		if store is writable.

		Deletes a page by moving content to trash. If path is a Page
		object this should result in 'page.hascontent' and 'page.haschildren'
		being False if succesfull.

		Returns False if page did not exist in the first place, True otherwise.
		Raises TrashNotSupportedError when not subclassed or when trash
		is not available due to some other reason.
		'''
		raise TrashNotSupportedError, 'Not implemented'

	def page_exists(self, path):
		'''ABSTRACT METHOD, must be implemented in sub-class.

		Should return boolean whether a page exists or not. Differs from
		page.hascontent because this method should only look at what is stored
		already.
		'''
		raise NotImplementedError

	def get_pagelist_indexkey(self, path):
		'''This method should return a key that can be checked by the index to
		determine if a list of (sub-)pages should be indexed again. A typical
		implementation would be to return the modification time of the directory
		where the pages are stored. The default in the base class returns None,
		forcing the index to always re-index the page. This is not very
		efficient and should be overloaded by the store.
		'''
		return None

	def get_page_indexkey(self, path):
		'''Like get_pagelist_indexkey() but used to decide whether page contents
		should be indexed or not.
		'''
		return None

	def store_has_dir(self):
		'''Returns True if we have a directory attribute 'dir'.
		Auto-vivicates the dir based on namespace if needed.
		'''
		if hasattr(self, 'dir') and not self.dir is None:
			return isinstance(self.dir, Dir)
		elif hasattr(self.notebook, 'dir'):
			path = self.namespace.name.replace(':', '/')
			if path.strip(':') == '':
				self.dir = self.notebook.dir
			else:
				self.dir = self.notebook.dir.subdir(path)
			return True
		else:
			return False

	def store_has_file(self):
		'''Returns True if we have a file attribute 'file'.
		If we are the toplevel namespace we can take a file source set for
		the whole notebook.
		'''
		if hasattr(self, 'file') and not self.file is None:
			return isinstance(self.file, File)
		elif hasattr(self.notebook, 'file') and self.namespace.isroot:
			self.file = self.notebook.file
			return isinstance(self.file, File)
		else:
			return False

	def get_attachments_dir(self, path):
		'''Returns a Dir object for storing attachements for 'path'.
		Assumes the store has a directory set already and aplies the
		default heuristic for mapping page names to file names.
		Sub-classes that do not have a directory or want a different
		layout need to subclass this method.
		'''
		# TODO merge with _get_dir and _get_file in stores/files.py
		assert self.dir, 'Stores without a dir attribute need to overload this method'
		if path == self.namespace:
			return self.dir
		else:
			name = path.relname(self.namespace)
			dirpath = encode_filename(name)
			return Dir([self.dir, dirpath])

	def walk(self, path=None):
		'''Generator walking all pages under this store. This is intended
		for some low level operations. From the application you typically
		want to use either notebook.walk() or index.walk() which traverse
		all stores.
		'''
		if path is None:
			path = self.namespace

		for page in self.get_pagelist(path):
			yield page
			for child in self.walk(page): # recurs
				yield child
