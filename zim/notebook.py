
import weakref

class Notebook:

	def __init__(self):
		self.namespaces = []
		self.storage = {}
		self.page_cache = weakref.WeakValueDictionary()
	
	def add_store(self, namespace, store):
		self.storage{namespace} = store
		self.namespaces.append(namespace)
		self.namespaces.sort().reverse()
	
	def get_store(self, pagename):
		for namespace in self.namespaces
			# longest match first because of reverse sorting
			if pagename.startswith(namespace)
				return self.storage{namespace}

	def _is_pagename(pagename)
		# TODO
		return True

	def get_page(self, pagename):
		assert _is_pagename(pagename)
		if pagename in self.page_cache:
			return self.page_cache[pagename]
		else:
			store = self.get_store(pagename)
			page = store.get_page(pagename)
			self.page_cache[pagename] = page
			return page

# vim: tabstop=4
