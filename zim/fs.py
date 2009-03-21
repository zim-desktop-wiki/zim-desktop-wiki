# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Module with basic filesystem objects.

Used as a base library for most other zim modules.
'''

# TODO - use weakref ?

# TODO Make sre files are *really* written before rename step
# remember the ext4 issue with truncated files in case of failure within
# 60s after write.
#
# From the pyton doc: If you’re starting with a Python file object f, first
# do f.flush(), and then do os.fsync(f.fileno()), to ensure that all internal
# buffers associated with f are written to disk. Availability: Unix, and
# Windows starting in 2.2.3.

import os
import errno
import codecs
from StringIO import StringIO

__all__ = ['Dir', 'File', 'Buffer']

class PathLookupError(Exception):
	'''FIXME'''


class UnixPath(object):
	'''Parent class for Dir and File objects'''

	def __init__(self, path):
		# TODO keep link to parent dir if first arg is Dir object
		#      but only if there is no '../' after that arg
		if isinstance(path, (list, tuple)):
			path = map(str, path)
				# Any path objects in list will also be flattened
			path = os.path.join(*path)
		elif isinstance(path, Path):
			path = path.path

		if path.startswith('file:/'):
			assert False, 'TODO convert file url to path'
		elif path.startswith('~'):
			path = os.path.expanduser(path)

		self.path = os.path.abspath(path)

	def __iter__(self):
		parts = self.split()
		for i in range(1, len(parts)+1):
			path = os.path.join('/', *parts[0:i]) # FIXME posix specific
			yield path

	def __str__(self):
		return self.path

	def __repr__(self):
		return '<%s: %>' % (self.__class__.__name__, self.path)

	def __add__(self, other):
		'''Concatonates paths, only creates path objects. See
		Dir.file() and Dir.subdir() instead to create otehr objects.
		'''
		return self.__class__((self, other))

	@property
	def basename(self):
		'''Basename property'''
		return os.path.basename(self.path)

	@property
	def uri(self):
		'''File uri property'''
		return 'file://'+self.path

	@property
	def dir(self):
		'''FIXME'''
		path = os.path.dirname(self.path)
		# TODO make this persistent - weakref ?
		return Dir(path)

	def exists(self):
		'''Abstract method'''
		raise NotImplementedError

	def split(self):
		'''FIXME'''
		path = self.path
		parts = []
		while path:
			path, part = os.path.split(path)
			if part	:
				parts.insert(0, part)
			if path == '/':
				break
		return parts


class WindowsPath(UnixPath):

    @property
    def uri(self):
        '''File uri property with win32 logic'''
        # win32 paths do not start with '/', so add another one
        return 'file:///'+self.canonpath

    @property
    def canonpath(self):
        path = self.path.replace('\\', '/')
        return path


# Determine which base class to use for classes below
if os.name == 'posix':
	Path = UnixPath
elif os.name == 'nt':
	Path = WindowsPath
else:
	import logging
	logger = logging.getLogger('zim')
	logger.critical('os name "%s" unknown, falling back to posix', os.name)
	Path = UnixPath


class Dir(Path):
	'''OO wrapper for directories'''

	def exists(self):
		'''Returns True if the dir exists and is actually a dir'''
		return os.path.isdir(self.path)

	def list(self):
		'''FIXME'''
		# TODO check notes on handling encodings in os.listdir
		if self.exists():
			return [f.decode('utf8')
				for f in os.listdir(self.path) if not f.startswith('.')]
		else:
			return []

	def touch(self):
		'''FIXME'''
		try:
			os.makedirs(self.path)
		except OSError, e:
			if e.errno != errno.EEXIST:
				raise

	def cleanup(self):
		'''FIXME'''
		os.removedirs(self.path)

	def file(self, path):
		'''FIXME'''
		if isinstance(path, File):
			file = path
		else:
			file = File((self.path, path))
		if not file.path.startswith(self.path):
			raise PathLookupError, '%s is not below %s' % (file, self)
		# TODO set parent dir on file
		return file

	def subdir(self, path):
		'''FIXME'''
		if isinstance(path, Dir):
			dir = path
		else:
			dir = Dir((self.path, path))
		if not dir.path.startswith(self.path):
			raise PathLookupError, '%s is not below %s' % (dir, self)
		# TODO set parent dir on file
		return dir


class File(Path):
	'''OO wrapper for files'''

	def exists(self):
		'''Returns True if the file exists and is actually a file'''
		return os.path.isfile(self.path)

	def open(self, mode='r'):
		'''Returns an io object for reading or writing.
		Opening a non-exisiting file for writing will cause the whole path
		to this file to be created on the fly.
		'''
		if not self.exists() and mode == 'w':
			self.dir.touch()
		return codecs.open(self.path, mode=mode, encoding='utf8')

	def read(self):
		if not self.exists():
			return ''
		else:
			file = self.open('r')
			return file.read()

	def readlines(self):
		if not self.exists():
			return []
		else:
			file = self.open('r')
			return file.readlines()

	def write(self, text):
		file = self.open('w')
		file.write(text)
		file.close()

	def touch(self):
		'''FIXME'''
		if self.exists():
			return
		else:
			io = self.open('w')
			io.write('')
			io.close()

	def cleanup(self):
		'''FIXME'''
		os.remove(self.path)
		self.dir.cleanup()



class Buffer(StringIO):
	'''StringIO subclass with methods mimicing File objects.

	The constructor takes an optional callback function. This
	function is called when the io handle is closed after writing.

	Unlike StringIO we assume everything to be encoded in utf8.
	Also unlike StringIO objects these objects can be opened and
	closed multiple times; and getvalue() still works after close.
	'''

	def __init__(self, text=u'', on_write=None):
		if not on_write is None:
			assert callable(on_write)
		self.on_write = on_write
		self.mode = None
		StringIO.__init__(self, text)

	def write(self, s):
		if not isinstance(s, unicode):
			s = s.decode('utf8')
		StringIO.write(self, s)

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
