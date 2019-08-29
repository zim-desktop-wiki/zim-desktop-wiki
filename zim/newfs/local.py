
# Copyright 2015-2016 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Local file system object'''



import sys
import os
import time
import shutil
import tempfile
import errno

import logging

logger = logging.getLogger('zim.newfs')


from . import FS_CASE_SENSITIVE
from .base import *
from .base import _EOL, SEP

from zim.parsing import url_encode, URL_ENCODE_READABLE
from zim.errors import Error


def _os_lrmdir(path):
	'''Wrapper for C{os.rmdir} that also knows how to unlink symlinks.
	Fails when the folder is not a link and is not empty.
	@param path: a file system path as string
	'''
	try:
		os.rmdir(path)
	except OSError:
		if os.path.islink(path) and os.path.isdir(path) and not os.listdir(path):
			os.unlink(path)
		else:
			raise


class FileNameLenghtError(Error):
	description = _('''\
Cannot write this file. Probably this is due to the lenght
of the file name, please try using a name with less
than 255 characters''') # T: Error explanation

	def __init__(self, basename):
		Error.__init__(self, _('File name too long: %s') % basename)


class PathLenghtError(Error):
	description = _('''\
Cannot write this file. Probably this is due to the lenght
of the file path, please try using a folder structure resulting in less
than 4096 characters''') # T: Error explanation

	def __init__(self, path):
		Error.__init__(self, _('File path too long: %s') % path)


class LocalFSObjectBase(FSObjectBase):

	def _stat(self):
		try:
			return os.stat(self.path)
		except OSError:
			raise FileNotFoundError(self)

	def _set_mtime(self, mtime):
		os.utime(self.path, (mtime, mtime))

	def parent(self):
		dirname = self.dirname
		if dirname is None:
			raise ValueError('Can not get parent of root')
		else:
			return LocalFolder(dirname, watcher=self.watcher)

	def ctime(self):
		return self._stat().st_ctime

	def mtime(self):
		return self._stat().st_mtime

	def iswritable(self):
		if self.exists():
			return os.access(self.path, os.W_OK)
		else:
			return self.parent().iswritable() # recurs

	def isequal(self, other):
		# Do NOT assume paths are the same - could be hard link
		# or it could be a case-insensitive filesystem
		try:
			stat_result = os.stat(self.path)
			other_stat_result = os.stat(other.path)
		except OSError:
			return False
		else:
			return stat_result == other_stat_result

	def moveto(self, other):
		# Using shutil.move instead of os.rename because move can cross
		# file system boundaries, while rename can not
		if isinstance(self, File):
			if isinstance(other, Folder):
				other = other.file(self.basename)

			assert isinstance(other, File)
		else:
			assert isinstance(other, Folder)

		if not isinstance(other, LocalFSObjectBase):
			raise NotImplementedError('TODO: support cross object type move')

		assert not other.path == self.path # case sensitive
		logger.info('Rename %s to %s', self.path, other.path)

		if not FS_CASE_SENSITIVE \
		and self.path.lower() == other.path.lower():
			# Rename to other case - need in between step
			other = self.__class__(other, watcher=self.watcher)
			tmp = self.parent().new_file(self.basename)
			shutil.move(self.path, tmp.path)
			shutil.move(tmp.path, other.path)
		elif os.path.exists(other.path):
			raise FileExistsError(other)
		else:
			# normal case
			other = self.__class__(other, watcher=self.watcher)
			other.parent().touch()
			shutil.move(self.path, other.path)

		if self.watcher:
			self.watcher.emit('moved', self, other)

		self._cleanup()
		return other


class LocalFolder(LocalFSObjectBase, Folder):

	def __init__(self, path, watcher=None):
		LocalFSObjectBase.__init__(self, path, watcher=watcher)

	def exists(self):
		return os.path.isdir(self.path)

	def touch(self, mode=None):
		if not self.exists():
			self.parent().touch(mode)
			try:
				if mode is not None:
					os.mkdir(self.path, mode)
				else:
					os.mkdir(self.path)
			except OSError as e:
				if e.errno != errno.EEXIST:
					raise
			else:
				if self.watcher:
					self.watcher.emit('created', self)

	def _object_iter(self, names, showfile, showdir):
		for name in names:
			path = self.path + SEP + name
			if os.path.isdir(path):
				if showdir:
					yield self.folder(name)
			else:
				if showfile:
					yield self.file(name)

	def list_names(self, include_hidden=False):
		try:
			names = os.listdir(self.path)
		except OSError:
			raise FileNotFoundError(self)

		if not include_hidden:
			# Ignore hidden files and tmp files
			names = [n for n in names
						if n[0] not in ('.', '~') and n[-1] != '~']

		return sorted(names)

	def file(self, path):
		return LocalFile(self.get_childpath(path), watcher=self.watcher)

	def folder(self, path):
		return LocalFolder(self.get_childpath(path), watcher=self.watcher)

	def child(self, path):
		childpath = self.get_childpath(path)
		if os.path.isdir(childpath.path):
			return self.folder(path)
		elif os.path.isfile(childpath.path):
			return self.file(path)
		else:
			raise FileNotFoundError(childpath)

	def copyto(self, other):
		assert isinstance(other, Folder)
		assert not other.path == self.path

		logger.info('Copy dir %s to %s', self.path, other.path)

		if isinstance(other, LocalFolder):
			if os.path.exists(other.path):
				raise FileExistsError(other)

			shutil.copytree(self.path, other.path, symlinks=True)
		else:
			self._copyto(other)

		if self.watcher:
			self.watcher.emit('created', other)

		return other

	def remove(self, cleanup=True):
		if os.path.isdir(self.path):
			try:
				_os_lrmdir(self.path)
			except OSError:
				raise FolderNotEmptyError('Folder not empty: %s' % self.path)
			else:
				if self.watcher:
					self.watcher.emit('removed', self)

		if cleanup:
			self._cleanup()



# Replace logic based on discussion here:
# http://stupidpythonideas.blogspot.nl/2014/07/getting-atomic-writes-right.html
#
# The point is to get a function to replace an old file with a new
# file as "atomic" as possible

if hasattr(os, 'replace'):
	_replace_file = os.replace
elif sys.platform == 'win32':
	# The win32api.MoveFileEx method somehow does not like our unicode,
	# the ctypes version does ??!
	import ctypes
	_MoveFileEx = ctypes.windll.kernel32.MoveFileExW
	_MoveFileEx.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
	_MoveFileEx.restype = ctypes.c_bool
	def _replace_file(src, dst):
		try:
			if not _MoveFileEx(src, dst, 1): # MOVEFILE_REPLACE_EXISTING
				raise OSError('Could not replace "%s" -> "%s"' % (src, dst))
		except:
			# Sometimes it fails - we play stupid and try again...
			time.sleep(0.5)
			if not _MoveFileEx(src, dst, 1): # MOVEFILE_REPLACE_EXISTING
				raise OSError('Could not replace "%s" -> "%s"' % (src, dst))
else:
	_replace_file = os.rename


class AtomicWriteContext(object):
	# Functions for atomic write as a context manager
	# used by LocalFile.read and .readlines
	# Exposed as separate object to make it testable.
	# Should not be needed outside this module

	def __init__(self, path, **kwargs):
		self.path = path if isinstance(path, str) else path.path
		self.tmppath = self.path + '.zim-new~'
		self.kwargs = kwargs
		self.kwargs.setdefault('mode', 'w')
		if 'b' not in self.kwargs['mode']:
			self.kwargs.setdefault('encoding', 'UTF-8')

	def __enter__(self):
		path = self.tmppath
		try:
			self.fh = open(path, **self.kwargs)
		except OSError as e:
			if e.errno == errno.ENOENT:
				if len(os.path.basename(path)) > 255:
					raise FileNameLenghtError(os.path.basename(path))
				elif len(path) > 4096:
					raise PathLenghtError(path)
				else:
					raise
			else:
				raise
		return self.fh

	def __exit__(self, *exc_info):
		# flush to ensure write is done
		self.fh.flush()
		os.fsync(self.fh.fileno())
		self.fh.close()

		if not any(exc_info) and os.path.isfile(self.tmppath):
			# do the replace magic
			_replace_file(self.tmppath, self.path)
		else:
			# errors happened - try to clean up
			try:
				os.remove(self.tmppath)
			except:
				pass



class LocalFile(LocalFSObjectBase, File):

	def __init__(self, path, endofline=_EOL, watcher=None):
		LocalFSObjectBase.__init__(self, path, watcher=watcher)
		self._mimetype = None
		self.endofline = endofline

	def exists(self):
		return os.path.isfile(self.path)

	def size(self):
		return self._stat().st_size

	def read_binary(self):
		try:
			with open(self.path, 'rb') as fh:
				return fh.read()
		except IOError:
			if not self.exists():
				raise FileNotFoundError(self)
			else:
				raise

	def read(self):
		try:
			with open(self.path, mode='r', encoding='UTF-8') as fh:
				try:
					text = fh.read()
				except UnicodeDecodeError as err:
					raise FileUnicodeError(self, err)
				else:
					return text.lstrip('\ufeff').replace('\x00', '')
					# Strip unicode byte order mark
					# And remove any NULL byte since they screw up parsing
		except IOError:
			if not self.exists():
				raise FileNotFoundError(self)
			else:
				raise

	def readlines(self):
		try:
			with open(self.path, mode='r', encoding='UTF-8') as fh:
				return [l.lstrip('\ufeff').replace('\x00', '') for l in fh]
				# Strip unicode byte order mark
				# And remove any NULL byte since they screw up parsing
		except UnicodeDecodeError as err:
			raise FileUnicodeError(self, err)
		except IOError:
			if not self.exists():
				raise FileNotFoundError(self)
			else:
				raise

	def write(self, text):
		newline = '\r\n' if self.endofline == 'dos' else '\n'
		with self._write_decoration():
			with AtomicWriteContext(self, newline=newline) as fh:
				fh.write(text)

	def writelines(self, lines):
		newline = '\r\n' if self.endofline == 'dos' else '\n'
		with self._write_decoration():
			with AtomicWriteContext(self, newline=newline) as fh:
				fh.writelines(lines)

	def write_binary(self, data):
		with self._write_decoration():
			with AtomicWriteContext(self, mode='wb') as fh:
				fh.write(data)

	def touch(self):
		# overloaded because atomic write can cause mtime < ctime
		if not self.exists():
			with self._write_decoration():
				with open(self.path, 'w') as fh:
					fh.write('')

	def copyto(self, other):
		if isinstance(other, Folder):
			other = other.file(self.basename)

		assert isinstance(other, File)
		assert other.path != self.path

		logger.info('Copy %s to %s', self.path, other.path)

		if isinstance(other, LocalFile):
			if os.path.exists(other.path):
				raise FileExistsError(other)

			other.parent().touch()
			shutil.copy2(self.path, other.path)
		else:
			self._copyto(other)

		if self.watcher:
			self.watcher.emit('created', other)

		return other

	def remove(self, cleanup=True):
		if os.path.isfile(self.path):
			os.remove(self.path)

		if self.watcher:
			self.watcher.emit('removed', self)

		if cleanup:
			self._cleanup()



def get_tmpdir():
	'''Get a folder in the system temp dir for usage by zim.
	This zim specific temp folder has permission set to be readable
	only by the current users, and is touched if it didn't exist yet.
	Used as base folder by L{TmpFile}.
	@returns: a L{LocalFolder} object for the zim specific tmp folder
	'''
	# We encode the user name using urlencoding to remove any non-ascii
	# characters. This is because sockets are not always unicode safe.

	root = tempfile.gettempdir()
	name = url_encode(os.environ['USER'], URL_ENCODE_READABLE)
	dir = LocalFolder(tempfile.gettempdir()).folder('zim-%s' % name)

	try:
		dir.touch(mode=0o700) # Limit to single user
		os.chmod(dir.path, 0o700) # Limit to single user when dir already existed
			# Raises OSError if not allowed to chmod
		os.listdir(dir.path)
			# Raises OSError if we do not have access anymore
	except OSError:
		raise AssertionError('Either you are not the owner of "%s" or the permissions are un-safe.\n'
			'If you can not resolve this, try setting $TMP to a different location.' % dir.path)
	else:
		# All OK, so we must be owner of a safe folder now ...
		return dir


class TmpFile(LocalFile):
	'''Class for temporary files. These are stored in the temp directory
	and by default they are deleted again when the object is destructed.
	'''

	def __init__(self, basename, unique=True, persistent=False):
		'''Constructor
		@param basename: gives the name for this tmp file.
		@param unique: if C{True} the L{Dir.new_file()} method is used
		to make sure we have a new file.
		@param persistent: if C{False} the file will be removed when the
		object is destructed, if C{True} we leave it alone
		'''
		dir = get_tmpdir()
		if unique:
			LocalFile.__init__(self, dir.new_file(basename))
		else:
			LocalFile.__init__(self, dir.get_childpath(basename))

		self.persistent = persistent

	def __del__(self):
		if not self.persistent:
			self.remove()
