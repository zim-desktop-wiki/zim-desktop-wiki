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
'''

from zim.fs import *
from zim.utils import is_url_re


def get_store(name):
	'''Returns the module object for a specific store type.'''
	# __import__ has some quirks, soo the reference manual
	mod = __import__('zim.stores.'+name)
	mod = getattr(mod, 'stores')
	mod = getattr(mod, name)
	assert mod.__store__ == name
	return mod


class StoreClass():

	def __init__(self, **args):
		'''Constructor for stores.
		At least pass a notebook and a namespace.
		'''
		assert 'notebook' in args
		assert 'namespace' in args
		self.notebook = args['notebook']
		self.namespace = args['namespace']


	# Public interface

	def resolve_name(self, name, namespace=None):
		'''Returns a page name in correct case or None.
		Used by the resolve_name() method in Notebook.

		If no namespace is given, check existence of at least part of
		the name. If so, return the name in proper case, else return
		None.

		If 'namespace' is given, do the above for a page below
		namespace or any of the parents of namespace that are handled
		by this store. ( 'namespace' can be expected to be in the
		correct case. )

		The default implementation in this class will iterate through
		each part of the namespace in turn, and tries to resolve the
		page below them by looking through the results of list_pages().
		'''
		#~ print "RESOLVE '%s', '%s'" % (namespace or '', name)
		if namespace is None:
			name = self.relname(name)
			return self._resolve_name(self.namespace, name)
		else:
			namespace = self.relname(namespace)
			path = namespace.split(':')
			while path:
				# iterate backwards through the namespace path
				ns = self.namespace+':'+':'.join(path)
				n = self._resolve_name(ns, name)
				if n is None:
					path.pop()
				else:
					return n
			return self._resolve_name(self.namespace, name)

	def _resolve_name(self, namespace, name):
		'''Resolve the case of a page below a specific namespace.
		Return None if the first part of name does not exist.
		'''
		#~ print "=> TEST '%s', '%s'" % (namespace, name)
		parts = name.split(':')
		case = []
		while parts:
			# iterate forward through the page name parts
			ns = namespace+':'+':'.join(case)
			ns = ns.rstrip(':')
			pl = parts[0].lower()
			#~ print "LIST", [p.basename for p in self.list_pages(ns)]
			matches = [ p.basename for p in self.list_pages(ns)
				if p.basename.lower() == pl ]
			#~ print 'MATCHES', matches
			if matches:
				if parts[0] in matches: # case was already ok
					case.append(parts[0])
				else:
					matches.sort() # make it predictable
					case.append(matches[0])
				parts.pop(0)
			else:
				break
		if case:
			case.extend(parts)
			return namespace+':'+':'.join(case)
		else:
			return None

	def document_dir(self, page=None):
		'''Returns the attachments dir for page, or the main
		attachments dir for the notebook if page is None.
		'''
		if page is None:
			return self.notebook.dir
		else:
			path = page.name.split(':')
			return self.notebook.dir.subdir(path)

	def resolve_file(self, link, page=None):
		'''Returns a File object for a file link.

		In case 'link' is an url or a path starting with '~/' it is
		considered an absolute paths. "file://" urls are converted
		to for other urls an exception is thrown.

		In case 'link' is a path starting with './' or '../' it is
		resolved relative to the document dir for 'page'. If 'page'
		is None the top level document dir is used.

		In case 'link' is a path starting with '/' the document root
		is used. This can be the toplevel document dir but may also
		be some other dir. If no document root is set, the file system
		root is used.
		'''
		# TODO security argument for www interface
		#		- turn everything outside notebook into file:// urls
		#		- do not leek info on existence of files etc.
		# TODO convert win32 to unix style path ?
		# TODO should we handle smb:// URLs here ?

		def dirs():
			# Generator for dir path needed below
			if not page is None:
				yield self.document_dir(page)
			yield self.document_dir()
			yield self.notebook.document_root
			# TODO add VCS dir

		if link.startswith('/'):
			# path below document root or filesystem root
			if self.notebook.document_root:
				file = self.notebook.document_root.file(link)
			else:
				file = File(link)
		elif link.startswith('~'):
			# absolute path
			file = File(link)
		elif is_url_re.match(link):
			# absolute path
			assert is_url_re[1] == 'file', 'Not a file:// URL'
			file = File(link)
		else:
			# relative to document dir for page or notebook
			# TODO for BACKWARD compat check one level up
			dir = self.document_dir(page)
			file = File([dir, link])

		if file.parent:
			# File is nested already below a dir
			return file
		else:
			# Try nesting below any of the standard dirs
			for dir in dirs():
				if not dir is None and file.path.startswith(dir.path):
					return dir.file(file)
			return file

	def get_page(self, name):
		'''ABSTRACT METHOD, needs to be implemented in sub-class.

		Return a Page object for page 'name'.
		'''
		raise NotImplementedError

	def get_root(self):
		'''Returns a Namespace object for our root namespace.'''
		# import Namespace here to avoid circular import
		from zim.notebook import Namespace
		return Namespace(self.namespace, self)

	def get_namespace(self, namespace):
		'''Returns a Namespace object for 'namespace'.'''
		# import Namespace here to avoid circular import
		from zim.notebook import Namespace
		return Namespace(namespace, self)

	def list_pages(self, namespace):
		'''ABSTRACT METHOD, needs to be implemented in sub-class.

		Returns an iterator for Page objects in a namespace.
		This method is normally encapsuled by the Namespace object,
		which will call this method to generate a page list.

		Should return an iterator for an empty list when namespace
		does not exist.
		'''
		raise NotImplementedError

	def move_page(self, old, new):
		'''ABSTRACT METHOD, needs to be implemented in sub-class.

		Move content from page object "old" to object "new".
		Should result in 'old.isempty()' returning True if succesfull.
		'''
		raise NotImplementedError

	def copy_page(self, old, new):
		'''ABSTRACT METHOD, needs to be implemented in sub-class.

		Copy content from page object "old" to object "new".
		'''
		raise NotImplementedError

	def clone_page(self, name, page):
		'''Turn page 'name' into a clone of 'page'.
		This method is used to export pages from one store to another,
		or even from one notebook to another.
		Clones will not be exact copies, but should be close.
		'''
		assert not page.isempty()
		mypage = self.get_page(name)
		tree = page.get_parsetree()
		mypage.set_parsetree(tree)

	def del_page(self, page):
		'''ABSTRACT METHOD, needs to be implemented in sub-class.

		Deletes a page. Should result in 'page.isempty()' returning
		True if succesfull.
		'''
		raise NotImplementedError

	def search(self):
		'''FIXME interface not yet defined'''
		raise NotImplementedError


	# Interface for sub-classes

	def has_dir(self):
		'''Returns True if we have a directory attribute.
		Auto-vivicates the dir based on namespace if needed.
		Intended to be used in an 'assert' statement by subclasses.
		'''
		if hasattr(self, 'dir'):
			return isinstance(self.dir, Dir)
		elif hasattr(self.notebook, 'dir'):
			path = self.namespace.replace(':', '/')
			self.dir = Dir([self.notebook.dir, path])
			return True
		else:
			return False

	def relname(self, name):
		'''Removes our namespace from a page name.'''
		if self.namespace:
			assert name.startswith(self.namespace)
			i = len(self.namespace)
			name = name[i:]
		return name.lstrip(':')
