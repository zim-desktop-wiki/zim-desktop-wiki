# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import os


class Path(object):
	'''Parent class for Dir and File objects'''

	# TODO - use weakref ?

	def __init__(self, path):
		'''FIXME'''
		assert not isinstance(path, tuple)
		# TODO keep link to parent dir if first arg is Dir object
		if isinstance(path, list):
			for i in range(0, len(path)):
				if isinstance(path[i], Path):
					path[i] = path[i].path
			path = os.path.join(*path)
		elif isinstance(path, Path):
			path = path.path
		self.path = os.path.abspath(path)

	def __str__(self):
		'''FIXME'''
		return self.path

	def uri(self):
		'''Returns a file uri for a path.'''
		return 'file://'+self.path

	def exists(self):
		return os.path.exists(self.path)


class Dir(Path):
	'''OO wrapper for directories'''

	def list(self):
		return os.listdir(self.path)


class File(Path):
	'''OO wrapper for files'''

	def open(self, mode='r'):
		'''FIXME'''
		return open(self.path, mode)
