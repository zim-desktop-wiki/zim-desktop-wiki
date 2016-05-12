# -*- coding: utf-8 -*-

# Copyright 2016 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Adapter to keep using "store" interface for index while porting
notebook to use folder directly.
'''

from zim.newfs import File, FileNotFoundError, _EOL
from zim.formats import get_format

from .layout import FilesLayout, encode_filename, decode_filename


class MockStore(object):

	def __init__(self, folder, endofline=_EOL):
		self._folder = folder
		self._format = get_format('wiki')
		self._eol = endofline

	def get_node(self, path):
		#~ print "NODE", path
		if path.isroot:
			return MockStoreNode(None, None, self._folder, self._format)
		else:
			return MockStoreNode(
				path.basename,
				self._get_file(path),
				self._get_folder(path),
				self._format,
			)

	def get_children(self, path):
		#~ print "CHILDREN", path
		if path.isroot:
			folder = self._folder
		else:
			folder = self._get_folder(path)

		if folder.exists():
			names = set()
			for child in folder:
				if ' ' in child.basename \
				or child.basename[0] in ('.', '_'):
					continue
				elif isinstance(child, File):
					if child.basename.endswith('.txt'):
						names.add(decode_filename(child.basename[:-4]))
					else:
						pass
				else:
					names.add(decode_filename(child.basename))

			#~ print ">", names

			for name in sorted(names):
				yield self.get_node(path + name)

	def _get_file(self, path):
		'''Returns a File object for a notebook path'''
		path = encode_filename(path.name) + '.txt'
		file = self._folder.file(path)
		file.endofline = self._eol
		return file

	def _get_folder(self, path):
		'''Returns a dir object for a notebook path'''
		path = encode_filename(path.name)
		return self._folder.folder(path)


class MockStoreNode(object):

	def __init__(self, basename, file, folder, format):
		self.basename = basename
		self.hascontent = file and file.exists()
		self.haschildren = folder.exists()
		self.ctime = file.ctime() if file and file.exists() else None
		self.mtime = file.mtime() if file and file.exists() else None

		self._file = file
		self._folder = folder
		self._format = format

	def exists(self):
		return self.hascontent or self.haschildren

	def get_parsetree(self):
		try:
			text = self._file.read()
			parser = self._format.Parser()
			return parser.parse(text)
		except FileNotFoundError:
			return None

	def get_children_etag(self):
		try:
			return str(self._folder.mtime())
		except FileNotFoundError:
			return None

	def get_content_etag(self):
		try:
			return str(self._file.mtime())
		except FileNotFoundError:
			return None
