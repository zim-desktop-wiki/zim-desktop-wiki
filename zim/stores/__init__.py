# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Base class for storage backends

This module contains a base class for store modules. It implements
some common methods and provides API documentation for the store
modules.

Each store sub-module should implement exactly one class which
inherits from StoreClass. These classes can be loaded with the function
L{get_store()}.


Storage Model
=============

Stores handle content in terms of Page objects. How the data that is
managed by the store is mapped to pages is up to the store implementation.
For example in the default store each page is mapped to a text file,
but there can also be store implementations that store many pages in the
same file, or that use for example a database. The store is however
expected to be consistent. So when a page is stored under a specific name
it should also be retrievable under that name.

Pages can be stored in a hierarchical way where each page can have sub-pages.
Or, in other terms, each page has a namespace of the same name that can store
sub pages. In the default store this structure is mapped to a directory
structure where for each page there can be a like named directory which
contains the files used to store sub-pages. The full page name for a page
consists of the names of all it's parents plus it's own base name separated
with the ':' character. It is advised that each page should have a unique
name. Symbolic links or aliases for pages should be handled on a different
level. In the store interface page names are always assumed to be case
sensitive. However the store is allowed to be not case sensitive if the storage
backend does not support this (e.g. a file system that is not case sensitive).

The API consistently uses L{Path} objects to represent page names. These
paths just map to a specific page name but do not contain any information
about the actual existence of the page etc.

The store exposes it's content using Page objects and lists of Page objects.
Each page object has two boolean attributes 'C{hascontent}' and 'C{haschildren}'.
Typically in a page listing at least one of these attributes should be True,
as a page either has content of it's own, or is used as a container for
sub-pages, or both. However both attributes can be False for new pages, or
for pages that have just been deleted.

The index will cache page listings in order to speed up the performance,
so it should not be necessary to do speed optimizations in the store lookups.
However for efficient caching, store objects must implement the
L{get_children_etag()} and L{get_content_etag()} methods.
'''

from __future__ import with_statement

import sys
import re
import codecs

import zim.fs
import zim.plugins
from zim.fs import File, Dir
from zim.parsing import is_url_re
from zim.errors import Error, TrashNotSupportedError


def get_store(name):
	'''Get a store class

	@param name: the module name of the store (e.g. "files")
	@returns: the subclass of L{StoreClass} found in the module
	'''
	mod = zim.plugins.get_module('zim.stores.' + name.lower())
	obj = zim.plugins.lookup_subclass(mod, StoreClass)
	return obj


def _url_encode_on_error(error):
	string = error.object
	section = string[error.start:error.end].encode('utf-8')
	replace = u''
	for char in section:
		replace += u'%%%02X' % ord(char)
	return replace, error.end

codecs.register_error('urlencode', _url_encode_on_error)


def encode_filename(pagename):
	'''Encode a pagename to a filename

	Since the filesystem may use another encoding than UTF-8 it may
	not be able to use all valid page names directly as file names.
	Therefore characters that are not allowed for the filesystem are
	replaced with url encoding. The result is still unicode, which can
	be used to construct a L{File} object. (The File object
	implementation takes care of actually encoding the string when
	needed.)

	Namespaces are mapped to directories by replacing ":" with "/".

	@param pagename: the pagename as string or unicode object
	@returns: the filename as unicode object but with characters
	incompatble with the filesystem encoding replaced
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
	'''Decodes a filename to a pagename

	Reverse operation of L{encode_filename()}.

	@param filename: the filename as string or unicode object
	@returns: the pagename as unicode object
	'''
	if zim.fs.ENCODING != 'utf-8':
		filename = filename.encode('utf-8')
		filename = _url_decode_re.sub(_url_decode, filename)
		filename = filename.decode('utf-8')
	return filename.replace('/', ':').replace('_', ' ')


class StoreClass():
	'''Base class for all storage backends

	Defines API that should be implemented in store objects as well
	as some convenience methods.

	Note that typically stores are only called by the L{Notebook} object,
	which does varies sanity checks. So although we should still make
	sure parameters in the API are sane, we may assume the requestor
	already verified for example that the path we get really
	belongs to this store.
	'''

	def get_page(self, path):
		'''Get a L{Page} object

		If a non-existing page is requested the store should check if we
		are allowed to create the page. If so, a new page object should
		be returned, but actually creating the page can be delayed until
		content is stored in it. If we are not allowed to create
		the page (e.g. in case of a read-only notebook) C{None} may
		be returned but a read-only Page object is also allowed.

		@param path: a L{Path} object
		@returns: a L{Page} object or C{None}

		@implementation: must be implemented by subclasses
		'''
		raise NotImplementedError

	def get_pagelist(self, path):
		'''Get a list (or iterator) of page objects in a namespace

		This method is used by the index to recursively find all pages
		in the store, so it should also include empty pages that do
		have sub-pages. Otherwise those sub-pages are never indexed.

		@param path: a L{Path} object
		@returns: A list or iterator for a list of L{Page} objects or
		an empty list when C{path} does not exist.

		@implementation: must be implemented by subclasses
		'''
		raise NotImplementedError

	def store_page(self, page):
		'''Store a page

		This method should save pages that were changed in the user
		interface. If the page does not yet exist it should be
		created automatically. Also all parent pages that did not yet
		exist should be created when needed.

		@param page: a L{Page} object obtained from L{get_page()} on
		this same object. The object must be from the same store
		to allow stores to sub-class the Page class and add additional
		internal state.

		@implementation: must be implemented by subclasses
		'''
		raise NotImplementedError

	def store_page_async(self, page):
		'''Store a page asynchronously

		Like L{store_page()} but with asynchronous operation.

		@param page: a L{Page} object

		@implementation: optional, can be implemented in subclasses.
		If not implemented in the subclass it will fall back to just
		calling L{store_page()} and then call the callback function.
		'''
		self.store_page(page)

	def revert_page(self, page):
		'''Revert the state of an un-stored page object

		Does not return a page object, changes are in the object
		supplied. This allows to revert an object that is being
		edited by the user interface.

		Kind of opposite to L{store_page()}.

		@implementation: optional, can be implemented in subclasses. In
		this base class it defaults to requesting a new copy of the page
		and copying the parse tree to the old object. Needs to be
		overloaded when the page has more internal state
		(e.g. a file object with mtime check).
		'''
		newpage = self.get_page(page)
		page.set_parsetree(newpage.get_parsetree())
		page.modified = False

	def move_page(self, path, newpath):
		'''Move a page and all it's sub-pages

		Move content, sub-pages and attachments from C{path} to
		C{newpath}. Must raise an error if C{path} does not exist,
		or if C{newpath} already exists.

		If C{path} is in fact a L{Page} object this should result
		in C{page.exists} being False after the move was successful.

		@param path: a L{Path} object for the the current path
		@param newpath: a L{Path} object for the new path

		@implementation: must be implemented by subclasses if the
		store is writable
		'''
		raise NotImplementedError

	def delete_page(self, path):
		'''Deletes a page and all it's sub-pages

		Delete a page, it's sub-pages and attachments

		Must raise an error when delete failed.

		If C{path} is in fact a L{Page} object this should result
		in C{page.exists} being False after the deletion was successful.

		@param path: a :{Path} object
		@returns: C{False} if page did not exist in the first place,
		C{True} otherwise.

		@implementation: must be implemented by subclasses if the
		store is writable
		'''
		raise NotImplementedError

	def trash_page(self, path):
		'''Move a page and all it's sub-pages to trash

		Like L{delete_page()} but instead of permanent deltion move
		the pages and attachments to the system trash so they can
		be restored by the user.

		@raises TrashNotSupportedError: when not subclassed or when trash
		is not available due to some other reason.
		@raises TrashCancelledError: when the user cancelled trashing.

		@param path: a :{Path} object
		@returns: C{False} if page did not exist in the first place,
		C{True} otherwise.

		@implementation: must be implemented by subclasses if the
		store is writable
		'''
		raise TrashNotSupportedError, 'Not implemented'

	def get_children_etag(self, path):
		'''Get key for checking cached state of a page list

		This method should return a key that can be checked by the index
		to determine if a list of pages should be indexed again.
		A typical implementation would be to return the modification time
		of the directory where the pages are stored.

		@param path: a L{Path} object
		@returns: a string encoding the state of the page list for
		sub-pages of C{path} or C{None} if C{path} does not have sub-pages

		@implementation: must be implemented in subclasses
		'''
		raise NotImplementedError

	def get_content_etag(self, path):
		'''Get key for checking cached state of a page

		This method should return a key that can be checked by the index
		to determine if the page contents should be indexed again.
		A typical implementation would be to return the modification time
		of the file where the page is stored.

		@param path: a L{Path} object
		@returns: a string encoding the state of the page content
		or C{None} if the page has no content

		@implementation: must be implemented in subclasses
		'''
		raise NotImplementedError

	def get_attachments_dir(self, path):
		'''Get the folder for storing attachments for a page

		@param path: a L{Path} object
		@returns: a L{Dir} object for the attachment folder of C{path}
		@implementation: must be implemented in subclasses
		'''
		raise NotImplementedError

	def walk(self, path=None):
		'''Generator to walk all pages under this store

		@returns: yields all pages under this store as L{Page} objects
		depth-first
		'''
		if path is None:
			path = Path(':')

		for page in self.get_pagelist(path):
			yield page
			for child in self.walk(page): # recurs
				yield child
