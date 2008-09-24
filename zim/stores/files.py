# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

from base import *
from zim.notebook import Page, PageList

import os

from zim import formats

class Store(StoreClass):

	def __init__(self, **args):
		'''Contruct a files store.
		Pass args needed for StoreClass init.
		Pass at least a directory.
		'''
		assert args.has_key('dir')
		StoreClass.__init__(self, **args)
		self.dir = args['dir']
		self.format = formats.get_format('wiki')

	def get_page(self, name, file=None):
		'''Return a Page object for name
		If file is specified already we can skip file lookup.
		'''
		if not file:
			file = self.get_file(name)
		source = Source(file, self.format)
		page = Page(name, self, source=source)

		dir = self.get_dir(name)
		if os.path.exists(dir):
			page.children = PageList(name, self)
			#print "page", page.name, '\n', page.children

		return page

	def list_pages(self, namespace):
		'''Generator function to iterate over pages in a namespace'''
		# TODO need to add more logic to pair files and dirs
		path = self.get_dir(namespace)
		for file in os.listdir(path):
			if file.startswith('.'):
				continue # no hidden files in our page list
			elif file.endswith('.txt'):
				#print "file", file
				name = namespace + ':' + file[:-4]
				file = path + '/' + file
				yield self.get_page(name, file=path)
			elif os.path.isdir( os.path.join(path, file) ):
				#print "dir", file
				name = namespace + ':' + file
				yield self.get_page(name)
			else:
				pass # unknown file type

	def get_file(self, name):
		'''Returns a file path for a page name'''
		relname = self.relname(name)
		path = relname.replace(':', '/')
		return self.dir + '/' + path + '.txt'

	def get_dir(self, name):
		'''Returns a dir path for a page name'''
		relname = self.relname(name)
		path = relname.replace(':', '/')
		return self.dir + '/' + path

class Source():
	'''Class to wrap file objects and attach a format'''

	def __init__(self, path, format):
		'''Constructor needs a file path and a format module'''
		self.path = path
		self.format = format

	def exists(self):
		'''Returns true is file exists'''
		return os.path.exists(self.path)

	def parse(self):
		'''Returns a parse tree from file or None'''
		if not os.path.exists(self.path):
			return None
		parser = self.format.Parser()
		file = open(self.path, 'r')
		tree = parser.parse(file)
		file.close()
		return tree

	def dump(self, tree):
		'''Dump the parse tree to file'''
		dumper = self.format.Dumper()
		file = open(self.path, 'w')
		dumper.dump(file, tree)
		file.close()
