# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Store module that keeps a tree of pages in memory.

See StoreClass in zim.stores for the API documentation.

FIXME document nodetree
FIXME document subclassing
'''

from zim.formats import get_format
from zim.notebook import Page, LookupError, PageExistsError
from zim.stores import StoreClass


class Node(object):

	__slots__ = ('basename', 'text', 'children')

	def __init__(self, basename, text=None):
		self.basename = basename
		self.text = text
		self.children = []


class MemoryStore(StoreClass):

	def __init__(self, notebook, path):
		'''Construct a memory store.
		Pass args needed for StoreClass init.
		'''
		StoreClass.__init__(self, notebook, path)
		self.format = get_format('wiki') # TODO make configable
		self._nodetree = []
		self.readonly = False

	def set_node(self, path, text):
		'''Sets node for 'page' and return it.'''
		node = self.get_node(path, vivificate=True)
		node.text = text
		return node

	def get_node(self, path, vivificate=False):
		'''Returns node for page 'name' or None.
		If 'vivificate' is True nodes are created on the fly.
		'''
		assert path != self.namespace, 'Can not get node for root namespace'
		name = path.relname(self.namespace)
		names = name.split(':')  # list with names
		branch = self._nodetree  # list of page nodes
		while names:
			n = names.pop(0) # get next item
			node = None
			for leaf in branch:
				if leaf.basename == n:
					node = leaf
					break
			if node is None:
				if vivificate:
					node = Node(basename=n)
					branch.append(node)
				else:
					return None
			branch = node.children

		return node

	def get_page(self, path):
		node = self.get_node(path)
		return self._build_page(path, node)

	def _build_page(self, path, node):
		if node is None:
			text = None
			haschildren = False
		else:
			text = node.text
			haschildren = bool(node.children)

		page = Page(path, haschildren)
		if text:
			page.readonly = False
			page.set_parsetree(self.format.Parser().parse(text))
			page.modified = False
		page.readonly = self.readonly
		return page

	def get_pagelist(self, path):
		if path == self.namespace:
			nodes = self._nodetree
		else:
			node = self.get_node(path)
			if node is None:
				return # implicit generate empty list
			else:
				nodes = node.children

		for node in nodes:
			childpath = path + node.basename
			yield self._build_page(childpath, node)

	def store_page(self, page):
		text = self.format.Dumper().dump(page.get_parsetree())
		self.set_node(page, text)
		page.modified = False

	def move_page(self, path, newpath):
		node = self.get_node(path)
		if node is None:
			raise LookupError, 'No such page: %s' % path.name

		newnode = self.get_node(newpath)
		if not newnode is None:
			raise PageExistsError, 'Page already exists: %s' % newpath.name

		self.delete_page(path)

		newnode = self.get_node(newpath, vivificate=True)
		newnode.text = node.text
		newnode.children = node.children # children

	def delete_page(self, path):
		# Make sure not to destroy the actual content, we are used by
		# move_page, which could be keeping a reference to the content
		node = self.get_node(path)
		if node is None:
			return False

		parent = path.parent
		if parent.isroot:
			self._nodetree.remove(node)
		else:
			pnode = self.get_node(parent)
			pnode.children.remove(node)
			if not (pnode.text or pnode.children):
				self.delete_page(parent) # recurs to cleanup empty parent

		if isinstance(path, Page):
			path.haschildren = False
			path.set_parsetree(None)
			path.modified = False

		return True

