# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Module with basic filesystem objects.

Used as a base library for most other zim modules.

FIXME more docs

There is a singleton object to represent the whole filesystem. THis
is stored in 'zim.fs.FS'. This object provides signals when a file or
folder is created, moved or deleted.

'''

# From the python doc: If you're starting with a Python file object f, first
# do f.flush(), and then do os.fsync(f.fileno()), to ensure that all internal
# buffers associated with f are written to disk. Availability: Unix, and
# Windows starting in 2.2.3.
#
# (Remember the ext4 issue with truncated files in case of failure within
# 60s after write. This way of working should prevent that kind of issue.)

# It could be considered to use a weakref dictionary to ensure the same
# identity for objects representing the same physical file. (Like we do
# for page objects in zim.notebook.) However this is not done for a good
# reason: each part of the code that uses a specific file must do it's
# own checks to detect if the file was changed outside it's control.
# So it is e.g. possible to have multiple instances of File() which
# represent the same file but independently manage the mtime and md5
# checksums to ensure the file is what they think it should be.

import gobject

import os
import re
import shutil
import errno
import codecs
import logging
from StringIO import StringIO

from zim.errors import Error
from zim.parsing import url_encode, url_decode


__all__ = ['Dir', 'File']

logger = logging.getLogger('zim.fs')


def get_tmpdir():
	import tempfile
	root = tempfile.gettempdir()
	dir = Dir((root, 'zim-%s' % os.environ['USER']))
	dir.touch()
	os.chmod(dir.path, 0700) # Limit to single user
	return dir


def normalize_win32_share(path):
	if os.name == 'nt':
		if path.startswith('smb://'):
			# smb://host/share/.. -> \\host\share\..
			path = path[4:].replace('/', '\\')
			path = url_decode(path)
	else:
		if path.startswith('\\\\'):
			# \\host\share\.. -> smb://host/share/..
			path = 'smb:' + path.replace('\\', '/')
			path = url_encode(path)

	return path


class PathLookupError(Error):
	pass # TODO description


class OverWriteError(Error):
	pass # TODO description


# TODO actually hook the signal for deleting files and folders

class _FS(gobject.GObject):
	'''Class used for the singleton 'zim.fs.FS' instance'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'path-created': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'path-moved': (gobject.SIGNAL_RUN_LAST, None, (object, object)),
		'path-deleted': (gobject.SIGNAL_RUN_LAST, None, (object,)),
	}

# Need to register classes defining gobject signals
gobject.type_register(_FS)


FS = _FS()


class UnixPath(object):
	'''Parent class for Dir and File objects'''

	def __init__(self, path):
		if isinstance(path, (list, tuple)):
			path = map(unicode, path)
				# Any path objects in list will also be flattened
			path = os.path.sep.join(path)
				# os.path.join is too intelligent for it's own good
				# just join with the path seperator..
		elif isinstance(path, Path):
			path = path.path

		if path.startswith('file:/'):
			path = self._parse_uri(path)
		elif path.startswith('~'):
			path = os.path.expanduser(path)

		self.path = self._abspath(path)

	@staticmethod
	def _abspath(path):
		return os.path.abspath(path)

	@staticmethod
	def _parse_uri(uri):
		# Spec is file:/// or file://host/
		# But file:/ is sometimes used by non-compliant apps
		# Windows uses file:///C:/ which is compliant
		if uri.startswith('file:///'): return uri[7:]
		elif uri.startswith('file://localhost/'): return uri[16:]
		elif uri.startswith('file://'): assert False, 'Can not handle non-local file uris'
		elif uri.startswith('file:/'): return uri[5:]
		else: assert False, 'Not a file uri: %s' % uri

	def __iter__(self):
		parts = self.split()
		for i in range(1, len(parts)):
			path = os.path.join(*parts[0:i])
			yield Dir(path)

		#~ if self.isdir():
		yield Dir(self.path)
		#~ else:
			#~ yield self

	def __str__(self):
		return self.path

	def __repr__(self):
		return '<%s: %s>' % (self.__class__.__name__, self.path)

	def __add__(self, other):
		'''Concatonates paths, only creates objects of the same class. See
		Dir.file() and Dir.subdir() instead to create other objects.
		'''
		return self.__class__((self, other))

	def __eq__(self, other):
		return self.path == other.path

	def __ne__(self, other):
		return not self.__eq__(other)

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
		'''Returns a Dir object for the parent dir'''
		path = os.path.dirname(self.path)
		return Dir(path)

	def exists(self):
		'''Abstract method'''
		raise NotImplementedError

	def iswritable(self):
		if self.exists():
			return os.access(self.path, os.W_OK)
		else:
			return self.dir.iswritable() # recurs

	def mtime(self):
		stat_result = os.stat(self.path)
		return stat_result.st_mtime

	def split(self):
		'''Returns the directory parsts of the path as a list.
		If the OS uses the concept of a drive the first part will
		include the drive. (So using split() to count the number of
		path elements will not be robust for the path "/".)
		'''
		drive, path = os.path.splitdrive(self.path)
		parts = path.replace('\\', '/').strip('/').split('/')
		parts[0] = drive + os.path.sep + parts[0]
		return parts

	def relpath(self, reference, allowupward=False):
		'''Returns a relative path with respect to 'reference',
		which should be a parent directory unless 'allowupward' is True.
		If 'allowupward' is True the relative path is allowed to start
		with '../'.

		This method always returns paths using "/" as separator,
		even on windows.
		'''
		sep = os.path.sep # '/' or '\'
		if allowupward and not self.path.startswith(reference.path):
			parent = self.commonparent(reference)
			if parent is None:
				return None

			i = len(parent.path)
			j = reference.path[i:].strip(sep).count(sep) + 1
			reference = parent
			path = '../' * j
		else:
			assert self.path.startswith(reference.path)
			path = ''

		i = len(reference.path)
		path += self.path[i:].lstrip(sep).replace(sep, '/')
		return path

	def commonparent(self, other):
		'''Returns a common path between self and other as a Dir object.'''
		path = os.path.commonprefix((self.path, other.path))
		i = path.rfind(os.path.sep) # win32 save...
		if i >= 0:
			return Dir(path[:i+1])
		else:
			# different drive ?
			return None

	def rename(self, newpath):
		# Using shutil.move instead of os.rename because move can cross
		# file system boundies, but rename can not
		logger.info('Rename %s to %s', self, newpath)
		newpath.dir.touch()
		# TODO: check against newpath existing and being a directory
		shutil.move(self.path, newpath.path)
		FS.emit('path-moved', self, newpath)
		self.dir.cleanup()

	# FIXME we could define overloaded operators same as for notebook.Path
	def ischild(self, parent):
		return self.path.startswith(parent.path + os.path.sep)

	def isdir(self):
		'''Used to detect if e.g. a File object should have really been
		a Dir object
		'''
		return os.path.isdir(self.path)

	def get_mimetype(self):
		try:
			import xdg.Mime
			mimetype = xdg.Mime.get_type(self.path, name_pri=80)
			return str(mimetype)
		except ImportError:
			# Fake mime typing (e.g. for win32)
			if '.' in self.basename:
				_, ext = self.basename.rsplit('.', 1)
				if ext == 'txt':
					return 'text/plain'
				else:
					return 'x-file-extension/%s' % ext
			else:
				return 'application/octet-stream'



class WindowsPath(UnixPath):

	@staticmethod
	def _abspath(path):
		# Strip leading / for absolute paths
		if re.match(r'^[/\\][A-Z]:[/\\]', path):
			path = path[1:]
		return os.path.abspath(path)

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
	logger.critical('os name "%s" unknown, falling back to posix', os.name)
	Path = UnixPath


class Dir(Path):
	'''OO wrapper for directories'''

	def __eq__(self, other):
		if isinstance(other, Dir):
			return self.path == other.path
		else:
			return False

	def exists(self):
		'''Returns True if the dir exists and is actually a dir'''
		return os.path.isdir(self.path)

	def list(self):
		'''Returns a list of names for files and subdirectories'''
		# For os.listdir(path) if path is a Unicode object, the result
		# will be a list of Unicode objects.
		path = self.path
		if not isinstance(path, unicode):
			path = path.decode('utf-8')

		if self.exists():
			files = [f for f in os.listdir(path) if not f.startswith('.')]
			files.sort()
			return files
		else:
			return []

	def touch(self):
		'''Create this dir and any parent directories that do not yet exist'''
		try:
			os.makedirs(self.path)
		except OSError, e:
			if e.errno != errno.EEXIST:
				raise

	def remove(self):
		'''Remove this dir, fails if dir is non-empty.'''
		logger.info('Remove dir: %s', self)
		os.rmdir(self.path)

	def cleanup(self):
		'''Removes this dir and any empty parent dirs.

		Ignores if dir does not exist. Fails silently if dir is not empty.
		Returns boolean for success (so False means dir still exists).
		'''
		if not self.exists():
			return True

		try:
			os.removedirs(self.path)
		except OSError:
			return False # probably dir not empty
		else:
			return True

	def remove_children(self):
		'''Remove everything below this dir.

		WARNING: This is quite powerful and recursive, so make sure to double
		check the dir is actually what you think it is before calling this.
		'''
		assert self.path and self.path != '/'
		logger.info('Remove file tree: %s', self)
		for root, dirs, files in os.walk(self.path, topdown=False):
			for name in files:
				os.remove(os.path.join(root, name))
			for name in dirs:
				os.rmdir(os.path.join(root, name))

	def file(self, path):
		'''Returns a File object for a path relative to this directory'''
		assert isinstance(path, (File, basestring, list, tuple))
		if isinstance(path, File):
			file = path
		elif isinstance(path, basestring):
			file = File((self.path, path))
		else:
			file = File((self.path,) + tuple(path))
		if not file.path.startswith(self.path):
			raise PathLookupError, '%s is not below %s' % (file, self)
		return file

	def new_file(self, path):
		'''Like file() but guarantees the file does not yet exist by adding
		sequentional numbers if needed.
		'''
		file = self.file(path)
		basename = file.basename
		if '.' in basename: basename = basename.split('.', 1)
		else: basename = (basename, '')
		dir = file.dir
		i = 0
		while file.exists():
			logger.debug('File exists "%s" trying increment', file)
			i += 1
			file = dir.file(
				''.join((basename[0], '%03i' % i, '.', basename[1])) )
		return file

	def subdir(self, path):
		'''Returns a Dir object for a path relative to this directory'''
		assert isinstance(path, (File, basestring, list, tuple))
		if isinstance(path, Dir):
			dir = path
		elif isinstance(path, basestring):
			dir = Dir((self.path, path))
		else:
			dir = Dir((self.path,) + tuple(path))
		if not dir.path.startswith(self.path):
			raise PathLookupError, '%s is not below %s' % (dir, self)
		return dir


def _glob_to_regex(glob):
	glob = glob.replace('.', '\\.')
	glob = glob.replace('*', '.*')
	glob = glob.replace('?', '.?')
	return re.compile(glob)


class FilteredDir(Dir):

	def __init__(self, path):
		Dir.__init__(self, path)
		self._ignore = []

	def ignore(self, glob):
		regex = _glob_to_regex(glob)
		self._ignore.append(regex)

	def filter(self, name):
		for regex in self._ignore:
			if regex.match(name):
				return False
		else:
			return True

	def list(self):
		files = Dir.list(self)
		files = filter(self.filter, files)
		return files



def _convert_newlines(text):
	'''Method to strip out any \\r characters. This is needed because
	we typically read in binary mode and therefore do not use the
	universal newlines feature.
	'''
	return text.replace('\r', '')


class File(Path):
	'''OO wrapper for files. Implements more complex logic than
	the default python file objects. On writing we first write to a
	temporary files, then flush and sync and finally replace the file we
	intended to write with the temporary file. This makes it much more
	difficult to loose file contents when something goes wrong during
	the writing.

	When 'checkoverwrite' this class checks mtime to prevent overwriting a
	file that was changed on disk, if mtime fails MD5 sums are used to verify
	before raising an exception. However this check only works when using
	read(), readlines(), write() or writelines(), but not when calling open()
	directly. Unfortunately this logic is not atomic, so your mileage may vary.
	'''

	def __init__(self, path, checkoverwrite=False):
		Path.__init__(self, path)
		self.checkoverwrite = checkoverwrite
		self._mtime = None

	def __eq__(self, other):
		if isinstance(other, File):
			return self.path == other.path
		else:
			return False

	def exists(self):
		'''Returns True if the file exists and is actually a file'''
		return os.path.isfile(self.path)

	def open(self, mode='r', encoding='utf-8'):
		'''Returns an io object for reading or writing.
		Opening a non-exisiting file for writing will cause the whole path
		to this file to be created on the fly.
		To open the raw file specify 'encoding=None'.
		'''
		assert mode in ('r', 'w')
		if mode == 'w':
			if not self.iswritable():
				raise OverWriteError, 'File is not writable'
			elif not self.exists():
				self.dir.touch()
			else:
				pass # exists and writable

		if encoding:
			mode += 'b'

		if mode in ('w', 'wb'):
			tmp = self.path + '.zim.new~'
			fh = FileHandle(tmp, mode=mode, on_close=self._on_write)
		else:
			fh = open(self.path, mode=mode)

		if encoding:
			# code copied from codecs.open() to wrap our FileHandle objects
			info = codecs.lookup(encoding)
			srw = codecs.StreamReaderWriter(
				fh, info.streamreader, info.streamwriter, 'strict')
			srw.encoding = encoding
			return srw
		else:
			return fh

	def _on_write(self):
		# flush and sync are already done before close()
		tmp = self.path + '.zim.new~'
		assert os.path.isfile(tmp)
		if isinstance(self, WindowsPath):
			# On Windows, if dst already exists, OSError will be raised
			# and no atomic operation to rename the file :(
			if os.path.isfile(self.path):
				isnew = False
				back = self.path + '~'
				if os.path.isfile(back):
					os.remove(back)
				os.rename(self.path, back)
				os.rename(tmp, self.path)
				os.remove(back)
			else:
				isnew = True
				os.rename(tmp, self.path)
		else:
			# On UNix, dst already exists it is replaced in an atomic operation
			isnew = not os.path.isfile(self.path)
			os.rename(tmp, self.path)

		logger.debug('Wrote %s', self)

		if isnew:
			FS.emit('path-created', self)

	def read(self, encoding='utf-8'):
		if not self.exists():
			return ''
		else:
			file = self.open('r', encoding)
			content = file.read()
			self._checkoverwrite(content)
			return _convert_newlines(content)

	def readlines(self):
		if not self.exists():
			return []
		else:
			file = self.open('r')
			content = file.readlines()
			self._checkoverwrite(content)
			return map(_convert_newlines, content)

	def write(self, text):
		self._assertoverwrite()
		file = self.open('w')
		file.write(text)
		file.close()
		self._checkoverwrite(text)

	def writelines(self, lines):
		self._assertoverwrite()
		file = self.open('w')
		file.writelines(lines)
		file.close()
		self._checkoverwrite(lines)

	def _checkoverwrite(self, content):
		if self.checkoverwrite:
			self._mtime = self.mtime()
			self._content = content

	def _assertoverwrite(self):
		# do not prohibit writing without reading first

		def md5(content):
			import hashlib
			m = hashlib.md5()
			if isinstance(content, basestring):
				m.update(content)
			else:
				for l in content:
					m.update(l)
			return m.digest()

		if self._mtime and self._mtime != self.mtime():
			logger.warn('mtime check failed for %s, trying md5', self.path)
			if md5(self._content) != md5(self.open('r').read()):
				raise OverWriteError, 'File changed on disk: %s' % self.path

	def touch(self):
		'''Create this file and any parent directories if it does not yet exist.
		Only needed for place holders - will happen automatically at first write.
		'''
		if self.exists():
			return
		else:
			io = self.open('w')
			io.write('')
			io.close()

	def remove(self):
		'''Remove this file and any related temporary files we made.
		Ignores if page did not exist in the first place.
		'''
		logger.info('Remove file: %s', self)
		if os.path.isfile(self.path):
			os.remove(self.path)

		tmp = self.path + '.zim.new~'
		if os.path.isfile(tmp):
			os.remove(tmp)

	def cleanup(self):
		'''Remove this file and deletes any empty parent directories.'''
		self.remove()
		self.dir.cleanup()

	def copyto(self, dest):
		'''Copy this file to 'dest'. 'dest can be either a file or a dir'''
		assert isinstance(dest, (File, Dir))
		if isinstance(dest, Dir):
			assert not dest == self.dir, 'BUG: trying to copy a file to itself'
		else:
			assert not dest == self, 'BUG: trying to copy a file to itself'
		logger.info('Copy %s to %s', self, dest)
		if isinstance(dest, Dir):
			dest.touch()
		else:
			dest.dir.touch()
		shutil.copy(self.path, dest.path)
		# TODO - not hooked with FS signals

	def compare(self, other):
		'''Uses MD5 to tell you if files are the same or not.
		This can e.g. be used to detect case-insensitive filsystems
		when renaming files.
		'''
		def md5(file):
			import hashlib
			m = hashlib.md5()
			m.update(file.read())
			return m.digest()

		return md5(self) == md5(other)


class TmpFile(File):
	'''Class for temporary files. These are stored in the temp directory and
	by deafult they are deleted again when the object is destructed.
	'''

	def __init__(self, basename, unique=True, persistent=False):
		'''Constructor, 'basename' gives the name for this tmp file.
		If 'unique' is True dir.new_file() is used to make sure we have a new
		file. If 'persistent' is False the file will be removed when the
		object is destructed.
		'''
		dir = get_tmpdir()
		if unique:
			file = dir.new_file(basename)
			File.__init__(self, file.path)
		else:
			File.__init__(self, (dir, basename))

		self.persistent = persistent

	def __del__(self):
		if not self.persistent:
			self.remove()


class FileHandle(file):
	'''Subclass of builtin file type that uses flush and fsync on close
	and supports a callback'''

	def __init__(self, path, on_close=None, **opts):
		file.__init__(self, path, **opts)
		self.on_close = on_close

	def close(self):
		self.flush()
		os.fsync(self.fileno())
		file.close(self)
		if not self.on_close is None:
			self.on_close()
