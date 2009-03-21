# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Store module that keeps a tree of pages in memory.

See StoreClass in zim.stores for the API documentation.

FIXME document nodetree
FIXME document subclassing
'''

from zim import formats
from zim.fs import Buffer
from zim.notebook import Page
from zim.stores import StoreClass

__store__ = 'memory'


class Store(StoreClass):

	def __init__(self, **args):
		'''Contruct a memory store.
		Pass args needed for StoreClass init.
		'''
		StoreClass.__init__(self, **args)
		self.format = formats.get_format('wiki') # TODO make configable
		self._nodetree = []

	def _set_node(self, path, text):
		'''Sets node for 'page' and return it.'''
		node = self._get_node(path, vivificate=True)
		node[1] = text
		return node

	def _get_node(self, path, vivificate=False):
		'''Returns node for page 'name' or None.
		If 'vivificate is True nodes are created on the fly.
		'''
		assert path != self.namespace, 'Can not get node for root namespace'
		name = path.relname(self.namespace)
		names = name.split(':')  # list with names
		branch = self._nodetree  # list of page nodes
		while names:
			n = names.pop(0) # get next item
			node = None
			for leaf in branch:
				if leaf[0] == n:
					node = leaf
					break
			if node is None:
				if vivificate:
					node = [n, '', []] # basename, text, children
					branch.append(node)
				else:
					return None
			branch = node[2]

		return node

	def get_page(self, path):
		node = self._get_node(path)
		return self._build_page(path, node)

	def _build_page(self, path, node):
		if node is None:
			text = None
			haschildren = False
		else:
			text = node[1]
			haschildren = len(node[2])

		on_write = lambda b: self._set_node(path, b.getvalue())
		source = Buffer(text, on_write=on_write)
		return Page(path, haschildren, source=source, format=self.format)

	def get_pagelist(self, path):
		if path == self.namespace:
			nodes = self._nodetree
		else:
			node = self._get_node(path)
			if node is None:
				return # implicit generate empty list
			else:
				nodes = node[2]

		for node in nodes:
			childpath = path + node[0]
			yield self._build_page(childpath, node)

	#~ def move_page(self, name, newname):
		#~ '''FIXME'''

	#~ def copy_page(self, name, newname):
		#~ '''FIXME'''

	#~ def delete_page(self, name):
		#~ '''FIXME'''
