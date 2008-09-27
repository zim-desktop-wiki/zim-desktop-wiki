# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

from zim.notebook import *
from zim.fs import *

class StoreClass():

	def __init__(self, **args):
		'''Constructor for stores.
		At least pass a store and a namespace.
		'''
		assert 'notebook' in args
		assert 'namespace' in args
		self.notebook = args['notebook']
		self.namespace = args['namespace']

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

	def get_root(self):
		'''Returns a Namespace object for root namespace'''
		return Namespace('', self)

	def set_page(self, page):
		'''Set a page object in this store.
		Intended for moving pages between stores.
		Do not use this to set object that were retrieved with get_page()
		from the same store.
		'''
		assert not page.isempty()
		mypage = self.get_page( page.name )
		mypage.set_parse_tree( page.get_parse_tree )
