# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

class StoreClass():

	def __init__(self, **args):
		'''Constructor for stores.
		At least pass a store and a namespace.
		'''
		assert args.has_key('notebook')
		assert args.has_key('namespace')
		self.notebook = args['notebook']
		self.namespace = args['namespace']

	def relname(self, name):
		'''Remove our namespace from a page name'''
		if self.namespace == '' and name.startswith(':'):
			i = 1
		else:
			i = len(self.namespace)
		return name[i:]



