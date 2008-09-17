
'''
This package contains the main Notebook class together
with basic classed like Page and PageList.

This package defines the public interface towards the
noetbook.  As a backend it uses one of more packages from
the 'stores' namespace.
'''

import weakref

class Notebook():

	def __init__(self, path):
		self.namespaces = []
		self.stores = {}
		self.page_cache = weakref.WeakValueDictionary()

		## TODO: load namespaces and stores from config ##
		import stores.files
		self.add_store('', stores.files, dir=path) # set root

	def __iter__(self):
		'''Same as list_root()'''
		return self.list_root

	def add_store(self, namespace, store, **args):
		'''Add a store to the notebook
		Store is the package for the store type
		All other args will be passed to the store
		'''
		mystore = store.Store(
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
		for namespace in self.namespaces:
			# longest match first because of reverse sorting
			if pagename.startswith(namespace):
				return self.stores[namespace]

	def get_page(self, pagename):
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


class Page():

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

	def get_parse_tree(self):
		if self.source:
			return self.source.parse()
		else:
			return self._tree

	def set_parse_tree(self, tree):
		if self.source:
			self.source.dump(tree)
		else:
			self._tree = tree

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



class PageList():
	'''...'''

	def __init__(self, namespace, store):
		'''...'''
		self.name = namespace
		self.store = store

	def __iter__(self):
		'''...'''
		return self.store.list_pages( self.name )

	def walk(self):
		'''Generator to walk page tree recursively'''
		for page in self:
			yield page
			if page.children:
				for page in page.children.walk(): # recurs
					yield page

# vim: tabstop=4
