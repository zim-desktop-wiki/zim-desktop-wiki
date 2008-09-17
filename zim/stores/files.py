
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
		return Page(name, self, source=source)


	def list_pages(self, namespace):
		'''...'''
		# TODO need to add more logic to pair files in dirs
		path = self.get_dir(namespace)
		for file in os.listdir(path):
			if file.startswith('.'):
				continue
			elif file.endswith('.txt'):
				name = namespace + ':' + file[:-4]
				file = path + '/' + file
				yield self.get_page(name, file=path)
			else:
				name = namespace + ':' + file
				page = Page(name, self)
				page.children = PageList(name, self)
				yield page

	def get_file(self, name):
		'''...'''
		relname = self.relname(name)
		path = '/'.join( relname.split(':') )
		return self.dir + '/' + path + '.txt'

	def get_dir(self, name):
		'''...'''
		relname = self.relname(name)
		path = '/'.join( relname.split(':') )
		return self.dir + '/' + path

class Source():
	'''Class to wrap file objects and attach a format'''

	def __init__(self, path, format):
		'''...'''
		self.path = path
		self.format = format

	def parse(self):
		'''...'''
		parser = self.format.Parser()
		file = open(self.path, 'r')
		tree = parser.parse(file)
		file.close()
		return tree

	def dump(self, tree):
		'''...'''
		dumper = self.format.Dumper()
		file = open(self.path, 'w')
		dumper.dump(file, tree)
		file.close()
