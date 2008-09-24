# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

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
		'''
		if hasattr(self, 'dir'): return True
		elif hasattr(self.notebook, 'dir'):
			path = self.namespace.replace(':', '/')
			self.dir = Dir([self.notebook.dir, path])
			return True
		else:
			return False

	def relname(self, name):
		'''Remove our namespace from a page name'''
		if self.namespace == '' and name.startswith(':'):
			i = 1
		else:
			i = len(self.namespace)
		return name[i:]

