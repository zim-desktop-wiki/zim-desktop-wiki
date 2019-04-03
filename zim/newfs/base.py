
# Copyright 2015-2016 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Base classes for filesystem and storage implementation'''

import os
import re
import hashlib
import contextlib

import logging

logger = logging.getLogger('zim.newfs')


from . import FS_SUPPORT_NON_LOCAL_FILE_SHARES

from zim.errors import Error
from zim.parsing import url_encode


is_url_re = re.compile('^\w{2,}:/')
is_share_re = re.compile(r'^\\\\\w')


if os.name == 'nt':
	SEP = '\\' # os.path.sep can still be "/" under msys
	_EOL = 'dos'
else:
	SEP = os.path.sep
	_EOL = 'unix'




class FileNotFoundError(Error):

	# TODO - description and translation

	def __init__(self, path):
		self.file = path
		path = path.path if hasattr(path, 'path') else path
		Error.__init__(self, 'No such file or folder: %s' % path)


class FileExistsError(Error):

	# TODO - description and translation

	def __init__(self, path):
		self.file = path
		path = path.path if hasattr(path, 'path') else path
		Error.__init__(self, 'File or folder already exists: %s' % path)


class FileUnicodeError(Error):
	'''Error raised when there is an issue decoding the file contents.
	Typically due to different encoding where UTF-8 is expected.
	'''

	def __init__(self, file, error):
		self.file = file
		self.error = error
		self.msg = _('Could not read: %s') % file.path
			# T: message for FileUnicodeError (%s is the file name)
		self.description = _('This usually means the file contains invalid characters')
			# T: message for FileUnicodeError
		self.description += '\n\n' + _('Details') + ':\n' + str(error)
			# T: label for detailed error


class FileChangedError(Error):

	# TODO - description and translation

	def __init__(self, path):
		self.file = path
		path = path.path if hasattr(path, 'path') else path
		Error.__init__(self, 'File changed on disk: %s' % path)


class FileNotWritableError(Error):

	# TODO - description and translation

	def __init__(self, path):
		self.file = path
		path = path.path if hasattr(path, 'path') else path
		Error.__init__(self, 'No permission to write file: %s' % path)


class FolderNotEmptyError(Error):

	# TODO - description and translation

	def __init__(self, path):
		path = path.path if hasattr(path, 'path') else path
		Error.__init__(self, 'Folder not empty: %s' % path)



def _split_file_url(url):
	scheme, path = url.replace('\\', '/').split(':/', 1)
	if scheme not in ('file', 'smb'):
		raise ValueError('Not a file URL: %s' % url)

	if path.startswith('/localhost/'): # exact 2 '/' before 'localhost'
		path = path[11:]
		isshare = False
	elif scheme == 'smb' or re.match('^/\w', path): # exact 2 '/' before 'localhost'
		isshare = True
	else:
		isshare = False # either 'file:/' or 'file:///'

	return path.strip('/').split('/'), isshare


def _splitnormpath(path, force_rel=False):
	# Takes either string or list of names and returns a normalized tuple
	# Keeps leading "/" or "\\" to distinguish absolute paths
	# Split must be robust for both "/" and "\" pathseperators regardless of
	# the os we are running on !
	if isinstance(path, str) and not force_rel:
		if is_url_re.match(path):
			makeroot = True
			path, makeshare = _split_file_url(path)
		else:
			if path.startswith('~'):
				makeroot = True
				path = _os_expanduser(path)
			else:
				makeroot = path.startswith('/')
			makeshare = re.match(r'^\\\\\w', path) is not None # exact 2 "\"
			path = re.split(r'[/\\]+', path.strip('/\\'))
	else:
		makeshare = False
		makeroot = False
		if isinstance(path, str):
			path = re.split(r'[/\\]+', path.strip('/\\'))

	names = []
	for name in path:
		if name == '.' and names:
			pass
		elif name == '..':
			if names and names[-1] != '..':
				names.pop()
			else:
				names.append(name)
				makeroot = False
		else:
			names.append(name)

	if not names:
		raise ValueError('path reduces to empty string')
	elif makeshare:
		names[0] = '\\\\' + names[0] # UNC host needs leading "\\"
	elif makeroot and os.name != 'nt' and not names[0].startswith('/'):
		names[0] = '/' + names[0]

	return tuple(names)


if os.name == 'nt':
	def _joinabspath(names):
		# first element must be either drive letter or UNC host
		if not re.match(r'^(\w:|\\\\\w)', names[0]):
			raise ValueError('Not an absolute path: %s' % '\\'.join(names))
		else:
			return '\\'.join(names) # Don't rely on SEP here, msys sets it to '/'

	def _joinuri(names):
		# first element must be either drive letter or UNC host
		if not re.match(r'^(\w:|\\\\\w)', names[0]):
			raise ValueError('Not an absolute path: %s' % '\\'.join(names))
		elif re.match(r'^\w:$', names[0]): # Drive letter - e.g. file:///C:/foo
			return 'file:///' + names[0] + '/' + url_encode('/'.join(names[1:]))
		elif re.match(r'^\\\\\w+$', names[0]): # UNC path - e.g. file://host/share
			return 'file://' + url_encode(names[0].strip('\\') + '/' + '/'.join(names[1:]))

else:
	def _joinabspath(names):
		if names[0].startswith('\\\\'):
			return '\\'.join(names) # Windows share drive
		elif names[0].startswith('/'):
			return '/'.join(names)
		else:
			raise ValueError('Not an absolute path: %s' % '/'.join(names))

	def _joinuri(names):
		if names[0][0] == '/':
			return 'file://' + url_encode('/'.join(names))
		else:
			return 'file:///' + url_encode('/'.join(names))


def _os_expanduser(path):
	assert path.startswith('~')
	path = os.path.expanduser(path)

	if path.startswith('~'):
		# expansion failed - do a simple fallback
		home = os.environ['HOME']
		parts = path.replace('\\', '/').strip('/').split('/')
		if parts[0] == '~':
			path = SEP.join([home] + parts[1:])
		else: # ~user
			dir = os.path.dirname(home) # /home or similar ?
			path = SEP.join([dir, parts[0][1:]] + parts[1:])

	return path


class FilePath(object):
	'''Class to represent filesystem paths and the base class for all
	file and folder objects. Contains methods for file path manipulation.

	File paths should always be absolute paths and can e.g. not start
	with "../" or "./". On windows they should always start with either
	a drive letter or a share drive. On unix they should start at the
	root of the filesystem.

	Paths can be handled either as strings representing a local file
	path ("/" or "\" separated), strings representing a file uri
	("file:///" or "smb://") or list of path names.
	'''

	__slots__ = ('path', 'pathnames', 'islocal')

	def __init__(self, path):
		if isinstance(path, (tuple, list, str)):
			self.pathnames = _splitnormpath(path)
			self.path = _joinabspath(self.pathnames)
		elif isinstance(path, FilePath):
			self.pathnames = path.pathnames
			self.path = path.path
		else:
			raise TypeError('Cannot convert %r to a FilePath' % path)

		self.islocal = not self.pathnames[0].startswith('\\\\')

	def __repr__(self):
		return "<%s: %s>" % (self.__class__.__name__, self.path)

	def __str__(self):
		return self.path

	def __eq__(self, other):
		return isinstance(other, self.__class__) and other.path == self.path

	def serialize_zim_config(self):
		'''Returns the file path as string for serializing the object'''
		return self.userpath

	@classmethod
	def new_from_zim_config(klass, string):
		'''Returns a new object based on the string representation for
		that path
		'''
		return klass(string)

	@property
	def uri(self):
		return _joinuri(self.pathnames)

	@property
	def basename(self):
		return self.pathnames[-1]

	@property
	def dirname(self):
		if len(self.pathnames) >= 2:
			return _joinabspath(self.pathnames[:-1])
		else:
			return None

	@property
	def userpath(self):
		if self.ischild(_HOME):
			return '~' + SEP + self.relpath(_HOME)
		else:
			return self.path

	def get_childpath(self, path):
		assert path
		names = _splitnormpath(path, force_rel=True)
		if not names or names[0] == '..':
			raise ValueError('Relative path not below parent: %s' % path)
		return FilePath(self.pathnames + names)

	def get_abspath(self, path):
		'''Returns a C{FilePath} for C{path} where C{path} can be
		either an absolute path or a path relative to this path
		(either upward or downward - use L{get_childpath()} to only
		get child paths).
		'''
		try:
			return FilePath(path)
		except ValueError:
			# Not an absolute path
			names = _splitnormpath(path)
			return FilePath(self.pathnames + names)

	def ischild(self, parent):
		names = parent.pathnames
		return len(names) < len(self.pathnames) \
			and self.pathnames[:len(names)] == names

	def relpath(self, start, allowupward=False):
		if allowupward and not self.ischild(start):
			parent = self.commonparent(start)
			if parent is None:
				raise ValueError('No common parent between %s and %s' % (self.path, start.path))
			relpath = self.relpath(parent)
			level_up = len(start.pathnames) - len(parent.pathnames)
			return (('..' + SEP) * level_up) + relpath
		else:
			names = start.pathnames
			if not self.pathnames[:len(names)] == names:
				raise ValueError('Not a parent path: %s' % start.path)
			return SEP.join(self.pathnames[len(names):])

	def commonparent(self, other):
		if self.pathnames[0] != other.pathnames[0]:
			return None # also prevent other drives and other shares
		elif self.ischild(other):
			return other
		elif other.ischild(self):
			return self
		else:
			for i in range(1, len(self.pathnames)):
				if self.pathnames[:i + 1] != other.pathnames[:i + 1]:
					return FilePath(self.pathnames[:i])



_HOME = FilePath('~')

class FSObjectMeta(type):
	'''This meta class allows implementing wrappers for file and folder objects
	with C{isinstance()} checking the wrapped class as well as the wrapper.
	Main use case is filtered version of folder object where e.g.
	C{isinstance(folder, LocalFolder)} is used to check whether the underlying
	resources exist external to the application.
	'''

	def __instancecheck__(cls, instance):
		if instance.__class__ == cls or issubclass(instance.__class__, cls):
			return True
		elif hasattr(instance, '_inner_fs_object') and isinstance(instance._inner_fs_object, cls):
			return True
		else:
			return False


class FSObjectBase(FilePath, metaclass=FSObjectMeta):
	'''Base class for L{File} and L{Folder}'''

	def __init__(self, path, watcher=None):
		FilePath.__init__(self, path)
		if not FS_SUPPORT_NON_LOCAL_FILE_SHARES and not self.islocal:
			raise ValueError('File system does not support non-local files')

		self.watcher = watcher

	def isequal(self, other):
		'''Check file paths are equal based on stat results (inode
		number etc.). Intended to detect when two files or dirs are the
		same on case-insensitive filesystems. Does not explicitly check
		the content is the same.
		@param other: an other L{FilePath} object
		@returns: C{True} when the two paths are one and the same file
		'''
		raise NotImplementedError

	def parent(self):
		raise NotImplementedError

	def ctime(self):
		raise NotImplementedError

	def mtime(self):
		raise NotImplementedError

	def exists(self):
		raise NotImplementedError

	def iswritable(self):
		raise NotImplementedError

	def touch(self):
		raise NotImplementedError

	def moveto(self, other):
		raise NotImplementedError

	def copyto(self, other):
		raise NotImplementedError

	def _set_mtime(self, mtime):
		raise NotImplementedError

	def _moveto(self, other):
		logger.debug('Cross FS type move %s --> %s', (self, other))
		self._copyto(other)
		self.remove()

	def remove(self, cleanup=True):
		raise NotImplementedError

	def _cleanup(self):
		try:
			self.parent().remove()
		except (ValueError, FolderNotEmptyError):
			pass


class Folder(FSObjectBase):
	'''Base class for folder implementations. Cannot be intatiated
	directly; use one of the subclasses instead. Main use outside of
	this module is to check C{isinstance(object, Folder)}.
	'''

	def __init__(self, path):
		raise NotImplementedError('This class is not meant to be instantiated directly')

	def __iter__(self):
		names = self.list_names()
		return self._object_iter(names, True, True)

	def list_files(self):
		names = self.list_names()
		return self._object_iter(names, True, False)

	def list_folders(self):
		names = self.list_names()
		return self._object_iter(names, False, True)

	def _object_iter(self, names, showfile, showdir):
		raise NotImplementedError

	def list_names(self, include_hidden=False):
		raise NotImplementedError

	def walk(self):
		for child in self:
			yield child
			if isinstance(child, Folder):
				for grandchild in child.walk():
					yield grandchild

	def file(self, path):
		raise NotImplementedError

	def folder(self, path):
		raise NotImplementedError

	def child(self, path):
		raise NotImplementedError

	def new_file(self, path, check=None):
		'''Get a L{File} object for a new file below this folder.
		Like L{file()} but guarantees the file does not yet exist by
		adding sequential numbers if needed. So the resulting file
		may have a modified name.

		@param path: the relative file path
		@param check: a function that can check and reject the choice before it
		is given back
		@returns: a L{File} object
		'''
		return self._new_child(path, self.file, check)

	def new_folder(self, path, check=None):
		'''Get a L{Folder} object for a new folder below this folder.
		Like L{folder()} but guarantees the file does not yet exist by
		adding sequential numbers if needed. So the resulting file
		may have a modified name.

		@param path: the relative file path
		@param check: a function that can check and reject the choice before it
		is given back
		@returns: a L{Folder} object
		'''
		return self._new_child(path, self.folder, check)

	def _new_child(self, path, factory, check=None):
		p = self.get_childpath(path.replace('%', '%%'))
		if '.' in p.basename:
			basename, ext = p.basename.split('.', 1)
			pattern = p.relpath(self)[:len(basename)] + '%03i.' + ext
		else:
			pattern = p.relpath(self) + '%03i'

		i = 0
		trypath = path
		while i < 1000:
			try:
				file = self.child(trypath) # this way we catch both exiting files and folders
			except FileNotFoundError:
				child = factory(trypath)
				if check is None or check(child):
					return child
				else:
					logger.debug('File rejected by check "%s" trying increment', child.path)
			else:
				logger.debug('File exists "%s" trying increment', file.path)

			i += 1
			trypath = pattern % i
		else:
			raise Exception('Could not find new file for: %s' % path)

	def remove_children(self):
		'''Recursively remove everything below this folder .

		B{WARNING:} This is quite powerful and can do a lot of damage
		when executed for the wrong folder, so please make sure to double
		check the dir is actually what you think it is before calling this.
		'''
		for name in self.list_names(include_hidden=True):
			child = self.child(name)
			assert child.path.startswith(self.path) # just to be real sure
			if isinstance(child, Folder):
				child.remove_children()
			child.remove()

	def _copyto(self, other):
		if other.exists():
			raise FileExistsError(other)
		other.touch()
		for child in self:
			if isinstance(child, File):
				child.copyto(other.file(child.basename))
			else:
				child.copyto(other.folder(child.basename))
		other._set_mtime(self.mtime())


xdgmime = None
mimetypes = None
try:
	import xdg.Mime as xdgmime
except ImportError:
	if os.name != 'nt':
		logger.info("Can not import 'xdg.Mime' - falling back to 'mimetypes'")
	else:
		pass # Ignore this error on Windows; doesn't come with xdg.Mime
	import mimetypes


#: Extensions to determine image mimetypes - used in L{File.isimage()}
IMAGE_EXTENSIONS = (
	# Gleaned from Gdk.get_formats()
	'bmp', # image/bmp
	'gif', # image/gif
	'icns', # image/x-icns
	'ico', # image/x-icon
	'cur', # image/x-icon
	'jp2', # image/jp2
	'jpc', # image/jp2
	'jpx', # image/jp2
	'j2k', # image/jp2
	'jpf', # image/jp2
	'jpeg', # image/jpeg
	'jpe', # image/jpeg
	'jpg', # image/jpeg
	'pcx', # image/x-pcx
	'png', # image/png
	'pnm', # image/x-portable-anymap
	'pbm', # image/x-portable-anymap
	'pgm', # image/x-portable-anymap
	'ppm', # image/x-portable-anymap
	'ras', # image/x-cmu-raster
	'tga', # image/x-tga
	'targa', # image/x-tga
	'tiff', # image/tiff
	'tif', # image/tiff
	'wbmp', # image/vnd.wap.wbmp
	'xbm', # image/x-xbitmap
	'xpm', # image/x-xpixmap
	'wmf', # image/x-wmf
	'apm', # image/x-wmf
	'svg', # image/svg+xml
	'svgz', # image/svg+xml
	'svg.gz', # image/svg+xml
)


def _md5(content):
	# Provide encoded content to avoid double work
	if isinstance(content, str):
		content = (content,)

	m = hashlib.md5()
	for l in content:
		m.update(l.encode('UTF-8'))
	return m.digest()


class File(FSObjectBase):
	'''Base class for folder implementations. Cannot be intatiated
	directly; use one of the subclasses instead. Main use outside of
	this module is to check C{isinstance(object, Folder)}.
	'''

	def __init__(self, path, endofline=_EOL):
		raise NotImplementedError('This class is not meant to be instantiated directly')

	def __iter__(self):
		return iter(self.readlines())

	def isimage(self):
		'''Check if this is an image file. Convenience method that
		works even when no real mime-type suport is available.
		If this method returns C{True} it is no guarantee
		this image type is actually supported by Gtk.
		@returns: C{True} when this is an image file
		'''
		# Quick shortcut to be able to load images in the gui even if
		# we have no proper mimetype support
		if '.' in self.basename:
			_, ext = self.basename.rsplit('.', 1)
			if ext in IMAGE_EXTENSIONS:
				return True

		return self.mimetype().startswith('image/')

	def mimetype(self):
		'''Get the mime-type for this file.
		Will use the XDG mimetype system if available, otherwise
		fallsback to the standard library C{mimetypes}.
		@returns: the mimetype as a string, e.g. "text/plain"
		'''
		if self._mimetype is None:
			if xdgmime:
				mimetype = xdgmime.get_type(self.path, name_pri=80)
				self._mimetype = str(mimetype)
			else:
				mimetype, encoding = mimetypes.guess_type(self.path, strict=False)
				if encoding == 'gzip':
					return 'application/x-gzip'
				elif encoding == 'bzip2':
					return 'application/x-bzip2'
				elif encoding == 'compress':
					return 'application/x-compress'
				else:
					self._mimetype = mimetype or 'application/octet-stream'

		return self._mimetype

	def size(self):
		raise NotImplementedError

	def read(self):
		raise NotImplementedError

	def readlines(self):
		raise NotImplementedError

	def read_binary(self):
		raise NotImplementedError

	def touch(self):
		if not self.exists():
			self.write('')

	def write(self, text):
		raise NotImplementedError

	def writelines(self, lines):
		raise NotImplementedError

	def write_binary(self, data):
		raise NotImplementedError

	@contextlib.contextmanager
	def _write_decoration(self):
		existed = self.exists()
		if not existed:
			self.parent().touch()
		elif not self.iswritable():
			raise FileNotWritableError(self)

		yield

		if self.watcher:
			if existed:
				self.watcher.emit('changed', self)
			else:
				self.watcher.emit('created', self)

	def read_with_etag(self):
		return self._read_with_etag(self.read)

	def readlines_with_etag(self):
		return self._read_with_etag(self.readlines)

	def _read_with_etag(self, func):
		mtime = self.mtime() # Get before read!
		content = func()
		etag = (mtime, _md5(content))
		return content, etag

	def write_with_etag(self, text, etag):
		return self._write_with_etag(self.write, text, etag)

	def writelines_with_etag(self, lines, etag):
		return self._write_with_etag(self.writelines, lines, etag)

	def _write_with_etag(self, func, content, etag):
		# TODO, to make rock-solid would also need to lock the file
		# before etag check and release after write

		if not self.exists():
			# Goal is to prevent overwriting new content. If the file
			# does not yet exist or went missing, just write it anyway.
			pass
		else:
			if not self.verify_etag(etag):
				raise FileChangedError(self)

		func(content)
		return (self.mtime(), _md5(content))

	def verify_etag(self, etag):
		if isinstance(etag, tuple) and len(etag) == 2:
			mtime = self.mtime()
			if etag[0] != mtime:
				# mtime fails .. lets see about md5
				md5 = _md5(self.read())
				return etag[1] == md5
			else:
				return True
		else:
			raise AssertionError('Invalid etag: %r' % etag)

	def _copyto(self, other):
		if other.exists():
			raise FileExistsError(other)
		other.write_binary(self.read_binary())
		other._set_mtime(self.mtime())
