# -*- coding: utf-8 -*-

# Copyright 2008-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Store module that keeps a tree of pages in memory'''

import time
import copy
import hashlib

from zim.formats import get_format

from zim.notebook.page import Page

from . import StoreClass, PageExistsError, PageNotFoundError


# We could also just use time stamps here to determine etags
# however using hashes here makes this class more interesting as a
# for the test suite. It helps to verify that etags are really treated
# as etags and not as timestamps.
def _md5(content):
	m = hashlib.md5()
	if isinstance(content, unicode):
		m.update(content.encode('utf-8'))
	elif isinstance(content, basestring):
		m.update(content)
	else:
		for l in content:
			m.update(l)
	return m.hexdigest()



class Node(object):

	__slots__ = ('basename', 'text', 'children', 'content_etag', 'children_etag', 'ctime', 'mtime')

	def __init__(self, basename, text=None):
		self.basename = basename
		self.text = text
		self.children = {}
		self.content_etag = _md5(text) if text else None
		self.children_etag = None
		self.ctime = time.time()
		self.mtime = None

	def set_content_etag(self):
		self.content_etag = _md5(self.text) if self.text else None
		self.mtime = time.time()

	def set_children_etag(self):
		self.children_etag = _md5(';'.join(self.children.keys()))


class MemoryStore(StoreClass):

	def __init__(self):
		self.format = get_format('wiki') # TODO make configurable
		self._root = Node('')
		self.readonly = False

	def copy(self):
		new = self.__class__()
		new._root = copy.deepcopy(self._root)
		return new

	def get_node(self, path, vivificate=False):
		'''Returns node for page 'name' or None.
		If 'vivificate' is True nodes are created on the fly.
		'''
		if path.isroot:
			return self._root

		node = self._root
		for basename in path.parts:
			if basename not in node.children:
				if vivificate:
					node.children[basename] = Node(basename)
					node.set_children_etag()
				else:
					return None

			node = node.children[basename]

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

		if node:
			page.ctime = node.ctime
			page.mtime = node.mtime
		else:
			page.ctime = None
			page.mtime = None

		return page

	def get_pagelist(self, path):
		node = self.get_node(path)
		if node:
			for basename in sorted(node.children):
				child = path + basename
				yield self._build_page(child, node.children[basename])

	def store_page(self, page):
		self.store_node(
			page, self.format.Dumper().dump(page.get_parsetree())
		)
		page.modified = False

	def store_node(self, path, text):
		node = self.get_node(path, vivificate=True)
		node.text = text
		node.set_content_etag()

	def move_page(self, path, newpath):
		node = self.get_node(path)
		if node is None:
			raise PageNotFoundError(path)

		newnode = self.get_node(newpath)
		if not newnode is None:
			raise PageExistsError(newpath)

		self.delete_page(path)

		newnode = self.get_node(newpath, vivificate=True)
		newnode.text = node.text
		newnode.set_content_etag()
		newnode.children = node.children
		newnode.set_children_etag()

	def delete_page(self, path):
		# Make sure not to destroy the actual content, we are used by
		# move_page, which could be keeping a reference to the content
		assert not path.isroot
		node = self.get_node(path)
		if node:
			pnode = self.get_node(path.parent)
			pnode.children.pop(path.basename)
			pnode.set_children_etag()

			if not (path.parent.isroot or pnode.text or pnode.children):
				self.delete_page(path.parent) # recurs to cleanup empty parent

			return True
		else:
			return False

	def get_content_etag(self, path):
		node = self.get_node(path)
		return node.content_etag

	def get_children_etag(self, path):
		node = self.get_node(path)
		return node.children_etag
