# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Base class for store modules.

This module contains a base class for store modules. It implements
some common methods and provides API documentation for the store
modules.

Each store module should implement a class named "Store" which
inherits from StoreClass. All methods marked with "ABSTRACT" need to
be implemented in the sub class. When called directly they will raise
a NotImplementedError. Overloading other methods is optional. Also
each module should define a variable '__store__' with it's own name.

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
'get_index_key()' method.

The notebook will use Path objects when requesting a specific page. These
paths just map to a specific page name but do not contain any information
about the actual existence of the page etc.

If a non-exising page is requested the store should check if we are allowed
to create the page. If so, a new page object should be returned, but actually
creating the page can be delayed untill content is stored in it. Creating
the page also implicitly creates all of it's parents page, since it should
be visible in the hierarchy of page listings. If we are not allowed to create
the page (e.g. in case of a read-only notebook) no page object should be
returned.

If a page list for a non-existing path is requested, the store can just
return an empty list.
'''

from zim.fs import *
from zim.parsing import is_url_re


def get_store(name):
	'''Returns the module object for a specific store type.'''
	# __import__ has some quirks, soo the reference manual
	mod = __import__('zim.stores.'+name)
	mod = getattr(mod, 'stores')
	mod = getattr(mod, name)
	assert mod.__store__ == name
	return mod


class StoreClass():

	def __init__(self, notebook, path):
		'''Constructor for stores.
		At least pass a notebook and the path for our namespace.
		'''
		self.notebook = notebook
		self.namespace = path

	def get_page(self, path):
		'''ABSTRACT METHOD, must be implemented in all sub-classes.

		Return a Page object for page 'name'.
		'''
		raise NotImplementedError

	def get_pagelist(self, path):
		'''ABSTRACT METHOD, must be implemented in all sub-classes.

		Should return a list (or iterator) of page objects below a specific
		path. Used by the index to recursively find all pages in the store.
		'''
		raise NotImplementedError

	def move_page(self, oldpath, newpath):
		'''ABSTRACT METHOD, must be implemented in sub-class if store is
		writable.

		Move content from "oldpath" to "newpath". If oldpath is a Page
		object this should result in 'page.hascontent' being False if
		succesfull.
		'''
		raise NotImplementedError

	def copy_page(self, oldpath, newpath):
		'''ABSTRACT METHOD, must be implemented in sub-class if store is
		writable.

		Copy content from "oldpath" to object "newpath".
		'''
		raise NotImplementedError

	def delete_page(self, path):
		'''ABSTRACT METHOD, must be implemented in sub-class if store is
		writable.

		Deletes a page. If path is a Page object this should result
		in 'page.hascontent' being False if succesfull.
		'''
		raise NotImplementedError

	def get_index_key(self, path):
		'''Optional ABSTRACT METHOD, should be implemented in sub-class
		to optimize indexing.

		See documentation for zim.index for more details.
		'''
		raise NotImplementedError

	def store_has_dir(self):
		'''Returns True if we have a directory attribute.
		Auto-vivicates the dir based on namespace if needed.
		Intended to be used in an 'assert' statement by subclasses that
		require a directory to store their content.
		'''
		if hasattr(self, 'dir') and not self.dir is None:
			return isinstance(self.dir, Dir)
		elif hasattr(self.notebook, 'dir'):
			path = self.namespace.name.replace(':', '/')
			self.dir = Dir([self.notebook.dir, path])
			return True
		else:
			return False

