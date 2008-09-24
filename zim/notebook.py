# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''
This package contains the main Notebook class together
with basic classed like Page and PageList.

This package defines the public interface towards the
noetbook.  As a backend it uses one of more packages from
the 'stores' namespace.
'''

import os
import weakref

from zim.fs import *
import zim.stores

def get_notebook(notebook):
	'''Takes a path or name and returns a notebook object'''
	# TODO check notebook list if notebook is not a path
	if os.path.isdir(notebook):
		return Notebook(notebook)
	else:
		raise Exception, 'no such notebook: %s' % notebook


class Notebook(object):
	'''FIXME'''

	def __init__(self, path):
		'''Constructor needs at least the path to the notebook'''
		self.dir = Dir(path)
		self.namespaces = []
		self.stores = {}
		self.page_cache = weakref.WeakValueDictionary()

		## TODO: load namespaces and stores from config ##
		self.add_store('', 'files', dir=path) # set root

	def add_store(self, namespace, store, **args):
		'''Add a store to the notebook under a specific namespace.

		All other args will be passed to the store
		'''
		mod = zim.stores.get_store(store)
		mystore = mod.Store(
			notebook=self,
			namespace=namespace,
			**args
		)
		self.stores[namespace] = mystore
		self.namespaces.append(namespace)

		# keep order correct for lookup
		self.namespaces.sort()
		self.namespaces.reverse()


	def get_store(self, pagename):
		'''Returns the store object to handle a specific page'''
		for namespace in self.namespaces:
			# longest match first because of reverse sorting
			if pagename.startswith(namespace):
				return self.stores[namespace]

	def get_page(self, pagename):
		'''Returns a Page object'''
		#assert _is_pagename(pagename)
		if pagename in self.page_cache:
			return self.page_cache[pagename]
		else:
			store = self.get_store(pagename)
			page = store.get_page(pagename)
			self.page_cache[pagename] = page
			return page

	def get_root(self):
		'''Returns a PageList for root namespace'''
		mystore = self.stores[''] # root
		return PageList('', mystore)


class Page(object):
	'''FIXME'''

	def __init__(self, name, store, source=None):
		'''Construct Page object.
		Needs at least a name and a store object.
		Setting a source object is optional.
		'''
		#assert name is valid
		self.name     = name
		self.store    = store
		self.children = None
		self.source   = source
		self._tree    = None


	def get_basename(self):
		i = self.name.rfind(':') + 1
		return self.name[i:]

	def raise_set():
		# TODO raise ro property
		pass

	basename = property(get_basename, raise_set)

	def isempty(self):
		'''Returns True if this page has no content'''
		if self.source:
			return not self.source.exists()
		else:
			return not self._tree

	def get_parse_tree(self):
		'''Returns contents as a parse tree or None'''
		if self.source:
			return self.source.parse()
		else:
			return self._tree

	def set_parse_tree(self, tree):
		'''Save a parse tree to page source'''
		if self.source:
			self.source.dump(tree)
		else:
			self._tree = tree

	def get_text(self, format='wiki'):
		'''Returns contents as string'''
		tree = self.get_parse_tree()
		if tree:
			import zim.formats
			dumper = zim.formats.get_format(format).Dumper()
			return dumper.dump_string(tree)
		else:
			return ''

	def path(self):
		'''Generator function for parent names
		can be used for:

			for namespace in page.path():
				if namespace.page('foo').exists:
					# ...
		'''
		path = self.name.split(':')
		path.pop(-1)
		while len(path) > 0:
			namespace = path.join(':')
			yield Namespace(namespace, self.store)



class PageList(object):
	'''Iterable object for namespaces'''

	def __init__(self, namespace, store):
		'''Constructor needs a namespace and a store object'''
		self.name = namespace
		self.store = store

	def __iter__(self):
		'''Calls the store.listpages generator function'''
		return self.store.list_pages( self.name )

	def walk(self):
		'''Generator to walk page tree recursively'''
		for page in self:
			yield page
			if page.children:
				for page in page.children.walk(): # recurs
					yield page

