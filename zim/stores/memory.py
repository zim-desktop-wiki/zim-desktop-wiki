# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

from base import *
from zim import formats
from zim.notebook import Page, Namespace

__store__ = 'memory'


class Store(StoreClass):

	def __init__(self, **args):
		'''Contruct a memory store.
		Pass args needed for StoreClass init.
		'''
		StoreClass.__init__(self, **args)
		self.format = formats.get_format('wiki') # TODO make configable
		self.pages = []


	# Private methods

	def _set_node(self, name, text):
		'''Sets node for 'page' and return it.'''
		node = self._get_node(name, vivificate=True)
		node[1] = text
		return node

	def _get_node(self, name, vivificate=False):
		'''Returns node for page 'name' or None.
		If 'vivificate is True nodes are created on the fly.
		'''
		name = self.relname(name)
		assert name # can not get node for root namespace
		path = name.split(':')  # list with names
		namespace = self.pages  # list of page nodes
		while path:
			p = path.pop(0) # get next item
			node = None
			for n in namespace:
				if n[0] == p:
					node = n
					break
			if node is None:
				if vivificate:
					node = [p, '', []]
					namespace.append(node)
				else:
					return None
			if path: # more items to go
				namespace = node[2]
			else:
				return node
		assert False, '!? we should never get here'

	def _on_write(self, buffer):
		'''Hook called after a write to a Buffer object'''
		self._set_node(buffer.pagename, buffer.getvalue())


	# Public interface

	def get_page(self, name, _node=None):
		'''Returns a Page object for 'name'.
		(_node is a private argument)
		'''
		if _node is None:
			_node = self._get_page(name)

		text = None
		if not _node is None:
			text = _node[1]

		source = Buffer(text, on_write=self._on_write)
		source.pagename = name
		page = Page(name, self, source=source, format=self.format)

		if not _node is None and _node[2]:
			page.children = Namespace(name, self)

		return page

	def list_pages(self, namespace):
		'''Generator function to iterate over pages in a namespace'''
		if namespace:
			node = self._get_node(namespace)
			children = node[2]
		else:
			children = self.pages
		for child in children:
			name = namespace+':'+child[0]
			yield self.get_page(name, _node=child)

