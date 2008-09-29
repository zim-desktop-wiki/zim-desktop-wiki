# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Base class for store modules.

This module contains a base class for store modules.
It contains a number of convenience methods that can be shared by
all implementations. But most of the methods defined here are
abstract and will raise a NotImplementedError when called.
These definitions are there as documentation for module authors
implementing sub-classes.

Each store module should implement a class named "Store" which
inherits from StoreClass. Also each module should define a variable
'__store__' with it's own name.
'''

from zim.fs import *


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
		'''FIXME'''
		raise NotImplementedError

	def copy_page(self, old, new):
		'''FIXME'''
		raise NotImplementedError

	def clone_page(self, name, page):
		'''Turn page 'name' into a clone of 'page'.
		This method is used to export pages from one store to another,
		or even from one notebook to another.
		Clones will not be exact copies, but should be close.
		'''
		assert not page.isempty()
		mypage = self.get_page(name)
		tree = page.get_parse_tree()
		mypage.set_parse_tree(tree)

	def del_page(self, page):
		'''FIXME'''
		raise NotImplementedError

	def search(self):
		'''FIXME'''
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
		'''Remove our namespace from a page name'''
		if self.namespace:
			assert name.startswith(self.namespace)
			i = len(self.namespace)
			name = name[i:]
		return name.lstrip(':')
