# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

import os

from base import *
from zim.fs import *
from zim import formats
from zim.notebook import Page, PageList

__store__ = 'files'


class Store(StoreClass):

	def __init__(self, **args):
		'''Contruct a files store.
		Pass args needed for StoreClass init.
		Pass at least a directory.
		'''
		StoreClass.__init__(self, **args)
		assert self.has_dir()
		self.format = formats.get_format('wiki')

	def get_page(self, name):
		'''Return a Page object for name'''
		file = self.get_file(name)
		source = Source(file, format=self.format)

		page = Page(name, self, source=source)

		dir = self.get_dir(name)
		if dir.exists():
			page.children = PageList(name, self)
			#print "page", page.name, '\n', page.children

		return page

	def list_pages(self, namespace):
		'''Generator function to iterate over pages in a namespace'''
		# TODO need to add more logic to pair files and dirs
		dir = self.get_dir(namespace)
		for file in dir.list():
			if file.startswith('.'):
				continue # no hidden files in our page list
			elif file.endswith('.txt'):
				#print "file", file
				name = namespace + ':' + file[:-4]
				yield self.get_page(name)
			elif os.path.isdir( os.path.join(dir.path, file) ):
				#print "dir", file
				name = namespace + ':' + file
				yield self.get_page(name)
			else:
				pass # unknown file type

	def get_file(self, name):
		'''Returns a file path for a page name'''
		relname = self.relname(name)
		path = relname.replace(':', '/')
		return File([self.dir, path + '.txt'])

	def get_dir(self, name):
		'''Returns a dir path for a page name'''
		relname = self.relname(name)
		path = relname.replace(':', '/')
		return Dir([self.dir, path])


class Source(File):
	'''Class to wrap file objects and attach a format'''

	def __init__(self, path, format=None):
		'''Constructor needs a file path and a format module'''
		assert not format is None and format.__format__
		File.__init__(self, path)
		self.format = format

	def parse(self):
		'''Returns a parse tree from file or None'''
		if not self.exists():
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
