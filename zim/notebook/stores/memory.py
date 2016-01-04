# -*- coding: utf-8 -*-

# Copyright 2008-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Store module that keeps a tree of pages in memory'''

import time
import copy
import hashlib

from zim.formats import get_format

from zim.notebook.page import Page

from . import StoreClass, PageExistsError, PageNotFoundError, StoreNode


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


_FORMAT = get_format('wiki') # TODO make configurable
_PARSER = _FORMAT.Parser()
_DUMPER = _FORMAT.Dumper()


class MemoryStoreNode(StoreNode):

	__slots__ = ('text', 'children', 'content_etag', 'children_etag', 'format')

	def __init__(self, basename, text=None):
		ctime = time.time()
		StoreNode.__init__(self,
			basename	=	basename,
			hascontent	=	bool(text),
			haschildren	=	False,
			source_file	=	None,
			attachments_dir	=	None,
			ctime		=	ctime,
			mtime		=	ctime,
		)
		self.text = text
		self.children = {}
		self.content_etag = _md5(text) if text else None
		self.children_etag = None

	def get_parsetree(self):
		if self.text:
			return _PARSER.parse(self.text)
		else:
			return None

	def store_parsetree(self, parsetree):
		if parsetree and parsetree.hascontent:
			self.text = ''.join(_DUMPER.dump(parsetree))
			self.set_content_etag()
		else:
			self.text = None
			self.set_content_etag()
			self.ctime = None
			self.mtime = None

	def get_children_etag(self):
		return self.children_etag

	def get_content_etag(self):
		return self.content_etag

	def set_content_etag(self):
		self.hascontent = bool(self.text)

		self.content_etag = _md5(self.text) if self.text else None
		self.mtime = time.time()

	def set_children_etag(self):
		self.haschildren = bool(self.children)

		if self.children:
			self.children_etag = _md5(';'.join(self.children.keys()))
		else:
			self.children_etag = None


class MemoryStore(StoreClass):

	def __init__(self):
		self._root = MemoryStoreNode('')
		self.readonly = False

	def copy(self):
		new = self.__class__()
		new._root = copy.deepcopy(self._root)
		return new

	def get_node(self, path, vivificate=True):
		'''Returns node for page 'name' or None.
		If 'vivificate' is True nodes are created on the fly.
		'''
		# FIX ME, make "vivicate on write" nodes, more like how file based version works with real FS
		if path.isroot:
			return self._root

		node = self._root
		for basename in path.parts:
			if basename not in node.children:
				if vivificate:
					node.children[basename] = MemoryStoreNode(basename)
					node.set_children_etag()
				else:
					return None

			node = node.children[basename]

		return node

	def get_children(self, path):
		node = self.get_node(path)
		if node:
			for basename in sorted(node.children):
				yield node.children[basename]

	def move_page(self, path, newpath):
		node = self.get_node(path)
		if node is None:
			raise PageNotFoundError(path)

		if self.get_node(newpath).exists():
			raise PageExistsError(newpath)

		self.delete_page(path)

		newnode = self.get_node(newpath) # in case newnode is child of path ...
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
