# -*- coding: utf-8 -*-

# Copyright 2008-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module defined the base class for storage backends

Each store sub-module should implement exactly one class which
inherits from StoreClass. These classes can be loaded with the function
L{get_store()}.


Storage Model
=============

Stores handle content in terms of Page objects. How the pages are mapped
to files or other data storage concepts is up to the store implementation.
For example in the default store each page is mapped to a text file,
but there could also be store implementations that store many pages in the
same file, or that use a database.

Pages can be stored in a hierarchical way where each page can have
sub-pages. The full page name for a page consists of the names of all
it's parents plus it's own base name separated with the ':' character.

The API consistently uses L{Path} objects to represent page names. These
paths just map to a specific page name but do not contain any information
about the actual existence of the page etc. In the store interface page
names are always assumed to be case sensitive. However the store is
allowed to be case in-sensitive if the storage backend does not support
this (e.g. a file system that is not case sensitive).

The store exposes it's content using L{Page} objects and lists of L{Page}
objects. Each page object has two boolean attributes 'C{hascontent}'
and 'C{haschildren}'. Typically in a page listing at least one of these
attributes should be True, as a page either has content of it's own, or
is used as a container for sub-pages, or both. However, the API allows
for L{Page} objects to exist representing pages that do not exist in
the store backend (e.g. when the user opens a not-yet-existing page).
In that case both these attributes will be C{False}.

The C{Index} will remember page lists also indexes page contents. It
uses the L{get_children_etag()} and L{get_content_etag()} methods to
query the store for changes.


Concurency
==========

The store should not need to worry about concurrency of the backend
(e.g. files changed behind our back by another process) as long as
conflicts are infrequent. For zim, the notebook index represents the
consistent state, regardless of not-yet-known changes in the store.
When pages are stored an etag check is done to aoid over-writing
concurrent changed. However some operations, like updating links after
moving a page, may touch a lot of pages and concurrent changes during
such an operation can not be handled fully gracefully. This may be a
problem for stores that have high concurency as the likelyhood of
conflicts becomes bigger. For these cases the locking mechanism should
be overruled to really lock the backend.
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
	mod = zim.plugins.get_module('zim.notebook.stores.' + name.lower())
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


class PageError(Error):

	def __init__(self, path):
		self.path = path
		self.msg = self._msg % path.name


class PageNotFoundError(PageError):
	_msg = _('No such page: %s') # T: message for PageNotFoundError


class PageNotAllowedError(PageNotFoundError):
	_msg = _('Page not allowed: %s') # T: message for PageNotAllowedError
	description = _('This page name cannot be used due to technical limitations of the storage')
			# T: description for PageNotAllowedError


class PageExistsError(Error):
	_msg = _('Page already exists: %s') # T: message for PageExistsError


class PageReadOnlyError(Error):
	_msg = _('Can not modify page: %s') # T: error message for read-only pages


class StoreNode(object):
	'''Proxy object that exposes page data based on source files.
	**Temporary class to deal with refactoring, will be removed again**
	'''

	__slots__ = ('basename', 'hascontent', 'haschildren', 'source_file', 'attachments_dir', 'ctime', 'mtime')

	def __init__(self, basename, hascontent, haschildren, source_file, attachments_dir, ctime, mtime):
		self.basename = basename
		self.hascontent = hascontent
		self.haschildren = haschildren
		self.source_file = source_file
		self.attachments_dir = attachments_dir
		self.ctime = ctime
		self.mtime = mtime

	def exists(self):
		return self.hascontent or self.haschildren

	def get_parsetree(self):
		raise NotImplementedError

	def store_parsetree(self, parsetree):
		raise NotImplementedError

	def get_children_etag(self):
		'''Get key for checking cached state of a page list

		This method should return a key that can be checked by the index
		to determine if a list of pages should be indexed again.
		A typical implementation would be to return the modification time
		of the directory where the pages are stored.

		@returns: a string encoding the state of the page list for
		sub-pages of C{path} or C{None} if C{path} does not have sub-pages

		@implementation: must be implemented in subclasses
		'''
		raise NotImplementedError

	def get_content_etag(self):
		'''Get key for checking cached state of a page

		This method should return a key that can be checked by the index
		to determine if the page contents should be indexed again.
		A typical implementation would be to return the modification time
		of the file where the page is stored.

		@returns: a string encoding the state of the page content
		or C{None} if the page has no content

		@implementation: must be implemented in subclasses
		'''
		raise NotImplementedError



class StoreClass(object):
	'''Base class for store classes, see module docs L{zim.notebook.stores}'''

	def get_node(self, path):
		'''Returns the L{StoreNode} object for C{path}
		@raises PageNotAllowedError: when node cannot be accessed
		'''
		raise NotImplementedError

	def get_children(self, path):
		'''Iterator that yields L{StoreNode} objects for children of
		C{path}
		'''
		raise NotImplementedError

	def move_page(self, path, newpath):
		'''Move a page and all it's sub-pages and attachments

		Move content, sub-pages and attachments from C{path} to
		C{newpath}. Must raise an error if C{path} does not exist,
		or if C{newpath} already exists.

		If C{path} is in fact a L{Page} object this should result
		in C{page.exists} being False after the move was successful.

		@param path: a L{Path} object for the the current path
		@param newpath: a L{Path} object for the new path
		@raises PageNotFoundError: if C{path} does not exist
		@raises PageExistsError: if C{newpath} already exists

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

		@implementation: optional to be implemented by subclasses if the
		store is writable
		'''
		raise TrashNotSupportedError, 'Not implemented'

	#~ def get_attachments_dir(self, path):
		#~ '''Get the folder for storing attachments for a page
#~
		#~ @param path: a L{Path} object
		#~ @returns: a L{Dir} object for the attachment folder of C{path}
		#~ @implementation: must be implemented in subclasses
		#~ '''
		#~ raise NotImplementedError

	#~ def walk(self, path=None):
		#~ '''Generator to walk all pages under this store
#~
		#~ @returns: yields all pages under this store as L{Page} objects
		#~ depth-first
		#~ '''
		#~ if path is None:
			#~ path = Path(':')
#~
		#~ for page in self.get_pagelist(path):
			#~ yield page
			#~ for child in self.walk(page): # recurs
				#~ yield child
