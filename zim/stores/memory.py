# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Store module that keeps a tree of pages in memory.

See StoreClass in zim.stores for the API documentation.

FIXME document nodetree
FIXME document subclassing
'''

from zim.formats import get_format
from zim.notebook import Page, LookupError, PageExistsError
from zim.stores import StoreClass


class Store(StoreClass):

	def __init__(self, **args):
		'''Contruct a memory store.
		Pass args needed for StoreClass init.
		'''
		StoreClass.__init__(self, **args)
		self.format = get_format('wiki') # TODO make configable
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

		page = Page(path, haschildren)
		if text:
			page.set_parsetree(self.format.Parser().parse(text))
			page.modified = False
		return page

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

	def store_page(self, page):
		text = self.format.Dumper().dump(page.get_parsetree())
		self._set_node(page, text)
		page.modified = False

	def move_page(self, path, newpath):
		node = self._get_node(path)
		if node is None:
			raise LookupError, 'No such page: %s' % path.name

		newnode = self._get_node(newpath)
		if not newnode is None:
			raise PageExistsError, 'Page already exists: %s' % newpath.name

		self.delete_page(path)

		newnode = self._get_node(newpath, vivificate=True)
		newnode[1] = node[1] # text
		newnode[2] = node[2] # children


	def delete_page(self, path):
		# Make sure not to destroy the actual content, we are used by
		# move_page, which could be keeping a reference to the content
		node = self._get_node(path)
		if node is None:
			return False

		parent = path.get_parent()
		if parent.isroot:
			self._nodetree.remove(node)
		else:
			pnode = self._get_node(parent)
			pnode[2].remove(node)
			if not (pnode[1] or pnode[2]):
				self.delete_page(parent) # recurs to cleanup empty parent

		return True

	def page_exists(self, path):
		return bool(self._get_node(path))
