# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Basic store module for storing pages as files.

See StoreClass in zim.stores for the API documentation.

Each page maps to a single text file in a normal directory structure.
Page names map almost one on one to the relative directory path.
Sub-namespaces are contained in directories of the same basename as
the coresponding file name.

File extensions are determined by the source format used.
When doing a lookup we try to be case insensitive, but preserve case
once we have it resolved.
'''

from zim.fs import *
from zim import formats
from zim.notebook import Page, Namespace
from zim.stores import StoreClass

__store__ = 'files'


class Store(StoreClass):

	def __init__(self, **args):
		'''Contruct a files store.

		Takes an optional 'dir' attribute.
		'''
		StoreClass.__init__(self, **args)
		if 'dir' in args:
			self.dir = args['dir']
		assert self.has_dir()
		self.format = formats.get_format('wiki') # TODO make configable


	# Private methods

	def _get_file(self, name):
		'''Returns a file path for a page name'''
		relname = self.relname(name)
		path = relname.replace(':', '/')
		return File([self.dir, path + '.txt'])

	def _get_dir(self, name):
		'''Returns a dir path for a page name'''
		relname = self.relname(name)
		path = relname.replace(':', '/')
		return Dir([self.dir, path])


	# Public interface

	def get_page(self, name, _file=None):
		'''Returns a Page object for 'name'.
		(_file is a private argument)
		'''
		if _file is None:
			_file = self._get_file(name)
		page = Page(name, self, source=_file, format=self.format)

		dir = self._get_dir(name)
		if dir.exists():
			page.children = Namespace(name, self)
			#print "page", page.name, '\n', page.children

		return page

	def list_pages(self, namespace):
		'''Generator function to iterate over pages in a namespace'''
		import os # using os directly here for efficiency
		dir = self._get_dir(namespace)
		pages = set() # collide files and dirs with same name
		for file in dir.list():
			if file.startswith('.'):
				continue # no hidden files in our page list
			elif file.endswith('.txt'): # TODO: do not hard code extension
				pages.add(file[:-4])
			elif os.path.isdir( os.path.join(dir.path, file) ):
				pages.add(file)
			else:
				pass # unknown file type
		for name in pages:
			yield self.get_page(namespace+':'+name)

	#~ def move_page(self, name, newname):
		#~ '''FIXME'''

	#~ def copy_page(self, name, newname):
		#~ '''FIXME'''

	#~ def del_page(self, name):
		#~ '''FIXME'''

	#~ def search(self):
		#~ '''FIXME'''
		#~ pass # TODO search code
