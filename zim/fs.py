# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Module with basic filesystem objects.

Used as a base library for most other zim modules.
'''

# TODO - use weakref ?

import os
from StringIO import StringIO


class Path(object):
	'''Parent class for Dir and File objects'''

	def __init__(self, path):
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

	@property
	def basename(self):
		'''Basename property'''
		return os.path.basename(self.path)

	@property
	def uri(self):
		'''File uri property'''
		return 'file://'+self.path

	def exists(self):
		'''Abstract method'''
		raise NotImplementedError


class Dir(Path):
	'''OO wrapper for directories'''

	def exists(self):
		'''Returns True if the dir exists and is actually a dir'''
		return os.path.isdir(self.path)

	def list(self):
		return os.listdir(self.path)


class File(Path):
	'''OO wrapper for files'''

	def exists(self):
		'''Returns True if the file exists and is actually a file'''
		return os.path.isfile(self.path)

	def open(self, mode='r'):
		'''Returns an io object for reading or writing.'''
		return open(self.path, mode)


class Buffer(StringIO):
	'''StringIO subclass with methods mimicing File objects.

	The constructor takes an optional callback function. This
	function is called when the io handle is closed after writing.
	'''

	def __init__(self, text='', on_write=None):
		if not on_write is None:
			assert callable(on_write)
		self.on_write = on_write
		self.mode = None
		StringIO.__init__(self, text)

	def exists(self):
		'''Returns True if the buffer contains any text'''
		return len(self.getvalue()) > 0

	def open(self, mode='r'):
		'''Resets internal state and returns the buffer itself.
		Since we derive from StringIO we can act as an io object.
		Only modes 'r' and 'w' are supported.
		'''
		if not self.mode is None:
			raise IOError, 'Buffer is already opened'
		self.pos = 0 # reset internal cursor
		if mode == 'r':
			if not self.exists():
				raise IOError, 'Buffer does not exist'
			self.mode = mode
			return self
		elif mode == 'w':
			self.mode = mode
			return self
		else:
			assert False, 'Unknown mode: %s' % mode

	def close(self):
		'''Reset internal state and optionally calls the callback.
		Unlink StringIO.close() the buffer will be preserved.
		'''
		if self.mode == 'w' and self.on_write:
			self.on_write(self)
		self.mode = None
