# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Module with basic filesystem objects.

Used as a base library for most other zim modules.

FIXME more docs

There is a singleton object to represent the whole filesystem. This
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

# ----

# Unicode notes from: http://kofoto.rosdahl.net/wiki/UnicodeInPython
# no guarantees that this is correct, but most detailed info I could find.
#
# On Unix, the file system encoding is taken from the locale settings.
# On Windows, the encoding is always mbcs, which indicates that the
# "wide" versions of API calls should be used.
#
# Note: File system operations raise a UnicodeEncodeError if given a
# path that can't be encoded in the encoding returned by
# sys.getfilesystemencoding().
#
# os.listdir(u"path") returns Unicode strings for names that
# can be decoded with sys.getfilesystemencoding() but silently returns
# byte strings for names that can't be decoded. That is, the return
# value of os.listdir(u"path") is potentially a mixed list of Unicode
# and byte strings.
#
# os.readlink chokes on Unicode strings that aren't coercable to the
# default encoding. The argument must therefore be a byte string.
# (Not applicable to Windows.)
#
# glob.glob(u"pattern") does not return Unicode strings.
#
# On Unix, os.path.abspath throws UnicodeDecodeError when given a
# Unicode string with a relative path and os.getcwd() returns a
# non-ASCII binary string (or rather: a
# non-sys.getdefaultencoding()-encoded binary string). Therefore, the
# argument must be a byte string. On Windows, however, the argument
# must be a Unicode string so that the "wide" API calls are used.
#
# os.path.realpath behaves the same way as os.path.abspath.
#
# os.path.expanduser (on both UNIX and Windows) doesn't handle Unicode
# when ~ expands to a non-ASCII path. Therefore, a byte string must be
# passed in and the result decoded.
#
# Environment variables in the os.environ dictionary are byte strings
# (both names and values).

# So we need to encode paths before handing them over to these
# filesystem functions and catch any UnicodeEncodeError errors.
# Also we use this encoding for decoding filesystem paths. However if
# we get some unexpected encoding from the filesystem we are in serious
# trouble, as it will be difficult to resolve. So we refuse to handle
# files with inconsistend encoding.
#
# Fortunately the only place where we (should) get arbitrary unicode
# paths are page names, so we should apply url encoding when mapping
# page names to file names. Seems previous versions of zim simply
# failed in this case when the page name contained characters outside
# of the set supported by the encoding supported.
#
# Seems zim was broken before for non-utf-8 filesystems as soon as you
# use characters in page names that did not fit in the filesystem
# encoding scheme. So no need for compatibility function, just try to
# do the right thing.
#
# As a special case we map ascii to utf-8 because LANG=C will set encoding
# to ascii and this is usually not what the user intended. Also utf-8
# is the most common filesystem encoding on modern perating systems.

# Note that we do this logic for the filesystem encoding - however the
# file contents remain utf-8.
# TODO could try fallback to locale if decoding utf-8 fails for file contents

# From other sources:
# about os.path.supports_unicode_filenames:
# The only two platforms that currently support unicode filenames properly
# are Windows NT/XP and MacOSX, and for one of them
# os.path.supports_unicode_filenames returns False :(
# see http://python.org/sf/767645
# So don't rely on it.

# ----

# It could be considered to use a weakref dictionary to ensure the same
# identity for objects representing the same physical file. (Like we do
# for page objects in zim.notebook.) However this is not done for a good
# reason: each part of the code that uses a specific file must do it's
# own checks to detect if the file was changed outside it's control.
# So it is e.g. possible to have multiple instances of File() which
# represent the same file but independently manage the mtime and md5
# checksums to ensure the file is what they think it should be.
#
# TODO - we could support weakref for directories to allow locking via
# the dir object

from __future__ import with_statement

import gobject

import os
import re
import sys
import shutil
import errno
import codecs
import logging
from StringIO import StringIO

from zim.errors import Error, TrashNotSupportedError
from zim.parsing import url_encode, url_decode
from zim.async import AsyncOperation, AsyncLock

logger = logging.getLogger('zim.fs')

gio = None
try:
	import gio
	if not gio.File.trash:
		gio = None
except ImportError:
	pass

if not gio:
	logger.warn("Trashing of files not supported, could not import 'gio'")


xdgmime = None
mimetypes = None
try:
	import xdg.Mime as xdgmime
except ImportError:
	if os.name != 'nt':
		logger.warn("Can not import 'xdg.Mime' - falling back to 'mimetypes'")
	else:
		pass # Ignore this error on Windows; doesn't come with xdg.Mime
	import mimetypes


__all__ = ['Dir', 'File']


IMAGE_EXTENSIONS = (
	# Gleaned from gtk.gdk.get_formats()
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


ENCODING = sys.getfilesystemencoding()
if ENCODING.upper() in (
	'ASCII', 'US-ASCII', 'ANSI_X3.4-1968', 'ISO646-US', # some aliases for ascii
	'LATIN1', 'ISO-8859-1', 'ISO_8859-1', 'ISO_8859-1:1987', # aliases for latin1
):
	logger.warn('Filesystem encoding is set to ASCII or Latin1, using UTF-8 instead')
	ENCODING = 'utf-8'


if ENCODING == 'mbcs':
	# Encoding 'mbcs' means we run on windows and filesystem can handle utf-8 natively
	# so here we just convert everything to unicode strings
	def encode(path):
		if isinstance(path, unicode):
			return path
		else:
			return unicode(path)

	def decode(path):
		if isinstance(path, unicode):
			return path
		else:
			return unicode(path)

else:
	# Here we encode files to filesystem encoding. Fails if encoding is not possible.
	def encode(path):
		if isinstance(path, unicode):
			try:
				return path.encode(ENCODING)
			except UnicodeEncodeError:
				raise Error, 'BUG: invalid filename %s' % path
		else:
			return path # assume encoding is correct


	def decode(path):
		if isinstance(path, unicode):
			return path # assume encoding is correct
		else:
			try:
				return path.decode(ENCODING)
			except UnicodeDecodeError:
				raise Error, 'BUG: invalid filename %s' % path


def isabs(path):
	return path.startswith('file:/') or os.path.isabs(path)


def isdir(path):
	'''Unicode safe wrapper for os.path.isdir()'''
	return os.path.isdir(encode(path))


def isfile(path):
	'''Unicode safe wrapper for os.path.isfile()'''
	return os.path.isfile(encode(path))


def joinpath(*parts):
	'''Wrapper for os.path.join()'''
	return os.path.join(*parts)


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
			path = 'smb:' + url_encode(path.replace('\\', '/'))

	return path


def lrmdir(path):
	'''Like os.rmdir but handles symlinks gracefully'''
	try:
		os.rmdir(path)
	except OSError:
		if os.path.islink(path) and os.path.isdir(path):
			os.unlink(path)
		else:
			raise


def _md5(content):
	import hashlib
	m = hashlib.md5()
	if isinstance(content, basestring):
		m.update(content)
	else:
		for l in content:
			m.update(l)
	return m.digest()


class PathLookupError(Error):
	pass # TODO description


class FileWriteError(Error):
	pass # TODO description


class FileNotFoundError(PathLookupError):

	def __init__(self, file):
		self.file = file
		self.msg = _('No such file: %s') % file.path
			# T: message for FileNotFoundError


# TODO actually hook the signal for deleting files and folders

class _FS(gobject.GObject):
	'''Class used for the singleton 'zim.fs.FS' instance'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'path-created': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'path-moved': (gobject.SIGNAL_RUN_LAST, None, (object, object)),
		'path-deleted': (gobject.SIGNAL_RUN_LAST, None, (object,)),
	}

	def __init__(self):
		gobject.GObject.__init__(self)
		self._lock = AsyncLock()

	def get_async_lock(self, path):
		'''Return a lock for async operation for path'''
		# FUTURE: we may actually use path to allow parallel async
		# operations for files & folders that do not belong to the
		# same tree. Problem there is that we do not aquire the lock
		# in this method. So we need a new kind of lock type that can
		# track dependency on other locks.
		# Make sure to allow for the fact that other obejcts can keep
		# the lock that are returned here indefinitely for re-use.
		# But for now we keep things simple.
		assert isinstance(path, UnixPath)
		return self._lock

# Need to register classes defining gobject signals
gobject.type_register(_FS)


FS = _FS()


class UnixPath(object):
	'''Parent class for Dir and File objects'''

	def __init__(self, path):
		if isinstance(path, Path):
			self.path = path.path
			self.encodedpath = path.encodedpath
			return

		try:
			if isinstance(path, (list, tuple)):
				path = map(unicode, path)
					# Flatten objects - strings should be unicode or ascii already
				path = os.path.sep.join(path)
					# os.path.join is too intelligent for it's own good
					# just join with the path seperator..
			else:
				path = unicode(path) # make sure we can decode
		except UnicodeDecodeError:
			raise Error, 'BUG: invalid input, file names should be in ascii, or given as unicode'

		if path.startswith('file:/'):
			path = self._parse_uri(path)
		elif path.startswith('~'):
			path = decode(os.path.expanduser(encode(path)))

		self._set_path(path) # overloaded in WindowsPath

	def serialize_zim_config(self):
		return self.path

	@staticmethod
	def _parse_uri(uri):
		# Spec is file:/// or file://host/
		# But file:/ is sometimes used by non-compliant apps
		# Windows uses file:///C:/ which is compliant
		if uri.startswith('file:///'): uri = uri[7:]
		elif uri.startswith('file://localhost/'): uri = uri[16:]
		elif uri.startswith('file://'): assert False, 'Can not handle non-local file uris'
		elif uri.startswith('file:/'): uri = uri[5:]
		else: assert False, 'Not a file uri: %s' % uri
		return url_decode(uri)

	def _set_path(self, path):
		# For unix we need to use proper encoding
		self.encodedpath = os.path.abspath(encode(path))
		self.path = decode(self.encodedpath)

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
		return os.path.basename(self.path) # encoding safe

	@property
	def uri(self):
		'''File uri property'''
		return 'file://' + url_encode(self.path)

	@property
	def dir(self):
		'''Returns a Dir object for the parent dir'''
		path = os.path.dirname(self.path) # encoding safe
		return Dir(path)

	def exists(self):
		'''Abstract method'''
		raise NotImplementedError

	def iswritable(self):
		if self.exists():
			return os.access(self.encodedpath, os.W_OK)
		else:
			return self.dir.iswritable() # recurs

	def mtime(self):
		stat_result = os.stat(self.encodedpath)
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
		refdir = reference.path + sep
		if allowupward and not self.path.startswith(refdir):
			parent = self.commonparent(reference)
			if parent is None:
				return None # maybe on different drive under win32

			i = len(parent.path)
			j = refdir[i:].strip(sep).count(sep) + 1
			reference = parent
			path = '../' * j
		else:
			assert self.path.startswith(refdir)
			path = ''

		i = len(reference.path)
		path += self.path[i:].lstrip(sep).replace(sep, '/')
		return path

	def commonparent(self, other):
		'''Returns a common path between self and other as a Dir object.'''
		path = os.path.commonprefix((self.path, other.path)) # encoding safe
		i = path.rfind(os.path.sep) # win32 save...
		if i >= 0:
			return Dir(path[:i+1])
		else:
			# different drive ?
			return None

	def ischild(self, parent):
		'''Returns True if this path is a child path of parent'''
		return self.path.startswith(parent.path + os.path.sep)

	def isdir(self):
		'''Used to detect if e.g. a File object should have really been
		a Dir object
		'''
		return os.path.isdir(self.encodedpath)

	def isimage(self):
		'''Returns True if the file is an image type. But no guarantee
		this image type is actually supported by gtk.
		'''

		# Quick shortcut to be able to load images in the gui even if
		# we have no proper mimetype support
		basename = self.basename
		if '.' in self.basename:
			_, ext = self.basename.rsplit('.', 1)
			if ext in IMAGE_EXTENSIONS:
				return True

		return self.get_mimetype().startswith('image/')

	def get_mimetype(self):
		'''Returns the mimetype as a string like e.g. "text/plain"'''
		if xdgmime:
			mimetype = xdgmime.get_type(self.path, name_pri=80)
			return str(mimetype)
		else:
			mimetype, encoding = mimetypes.guess_type(self.path, strict=False)
			if encoding == 'gzip': return 'application/x-gzip'
			elif encoding == 'bzip': return 'application/x-bzip'
			elif encoding == 'compress': return 'application/x-compress'
			else: return mimetype or 'application/octet-stream'


	def rename(self, newpath):
		# Using shutil.move instead of os.rename because move can cross
		# file system boundries, while rename can not
		logger.info('Rename %s to %s', self, newpath)
		with FS.get_async_lock(self):
			# Do we also need a lock for newpath (could be the same as lock for self) ?
			# TODO: check against newpath existing and being a directory
			newpath.dir.touch()
			shutil.move(self.encodedpath, newpath.encodedpath)
		FS.emit('path-moved', self, newpath)
		self.dir.cleanup()

	def trash(self):
		'''Trash a file or folder, returns boolean for success.
		Raises a TrashNotSupportedError if trashing is not possible.
		'''
		if not gio:
			raise TrashNotSupportedError, 'gio not imported'

		if self.exists():
			f = gio.File(uri=self.uri)
			if not f.trash():
				# FIXME is this how to catch gio.ERROR_NOT_SUPPORTED ?
				raise TrashNotSupportedError, 'Trashing failed'
			return True
		else:
			return False


class WindowsPath(UnixPath):

	def _set_path(self, path):
		# For windows unicode is supported natively,
		# but may need to strip leading / for absolute paths
		if re.match(r'^[/\\]+[A-Za-z]:[/\\]', path):
			path = path.lstrip('/').lstrip('\\')
		self.path = os.path.abspath(path)
		self.encodedpath = self.path # so encodedpath in unicode

	@property
	def uri(self):
		'''File uri property with win32 logic'''
		# win32 paths do not start with '/', so add another one
		# and avoid url encoding the second ":" in "file:///C:/..."
		path = self.canonpath # replaces \ with /
		if re.match('[A-Za-z]:/', path):
			return 'file:///' + path[:2] + url_encode(path[2:])
		else:
			return 'file:///' + url_encode(path)

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
		return os.path.isdir(self.encodedpath)

	def list(self, raw=False):
		'''Returns a list of names for files and subdirectories.
		Will not return names that could not be decoded properly and
		will throw warnings if those are encountered.
		Hidden files are silently ignored.

		The argument 'raw' doesn't doe anything here. It is there for
		compatibility with the FilteredDir interface.
		'''
		files = []
		if ENCODING == 'mbcs':
			# We are running on windows and os.listdir will handle unicode natively
			assert isinstance(self.encodedpath, unicode)
			for file in self._list():
				if isinstance(file, unicode):
					files.append(file)
				else:
					logger.warn('Ignoring file: "%s" invalid file name', file)
		else:
			# If filesystem does not handle unicode natively and path for
			# os.listdir(path) is _not_ a unicode object, the result will
			# be a list of byte strings. We can decode them ourselves.
			assert not isinstance(self.encodedpath, unicode)
			for file in self._list():
				try:
					files.append(file.decode(ENCODING))
				except UnicodeDecodeError:
					logger.warn('Ignoring file: "%s" invalid file name', file)
		files.sort()
		return files

	def _list(self):
		if self.exists():
			files = []
			for file in os.listdir(self.encodedpath):
				if not file.startswith('.'): # skip hidden files
					files.append(file)
			return files
		else:
			return []

	def walk(self, raw=True):
		'''Generator that yields all files and folders below this dir
		as objects.
		'''
		for name in self.list(raw=raw):
			path = self.path + os.path.sep + name
			if os.path.isdir(path):
				dir = self.subdir(name)
				yield dir
				for child in dir.walk(raw=raw):
					yield child
			else:
				yield self.file(name)

	def get_file_tree_as_text(self, raw=True):
		'''Returns an overview of files and folders below this dir
		as text.
		'''
		text = ''
		for child in self.walk(raw=raw):
			path = child.relpath(self)
			if isinstance(child, Dir):
				path += '/'
			text += path + '\n'
		return text

	def touch(self):
		'''Create this dir and any parent directories that do not yet exist'''
		try:
			os.makedirs(self.encodedpath)
		except OSError, e:
			if e.errno != errno.EEXIST:
				raise

	def remove(self):
		'''Remove this dir, fails if dir is non-empty.'''
		logger.info('Remove dir: %s', self)
		lrmdir(self.encodedpath)

	def cleanup(self):
		'''Removes this dir and any empty parent dirs.

		Ignores if dir does not exist. Fails silently if dir is not empty.
		Returns boolean for success (so False means dir still exists).
		'''
		if not self.exists():
			return True

		try:
			os.removedirs(self.encodedpath)
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
		for root, dirs, files in os.walk(self.encodedpath, topdown=False):
			# walk should not decent into symlinked folders by default
			# remove() and rmdir() both should remove a symlink rather
			# than the target of the link
			for name in files:
				os.remove(os.path.join(root, name))
			for name in dirs:
				lrmdir(os.path.join(root, name))

	def file(self, path):
		'''Returns a File object for a path relative to this directory

		When 'path' is in fact a L{File} object already this method
		still enforces is to be below this directory. So this method can
		be used as check as well.

		@param path: a (relative) file path as string, tuple or L{Path} object

		@returns: a L{File} object

		@raises PathLookupError: if the file is not below this dir
		'''
		file = self.resolve_file(path)
		if not file.path.startswith(self.path):
			raise PathLookupError, '%s is not below %s' % (file, self)
		return file

	def resolve_file(self, path):
		'''Like L{file()} but allows the path to start with "../"'''
		assert isinstance(path, (Path, basestring, list, tuple))
		if isinstance(path, basestring):
			return File((self.path, path))
		elif isinstance(path, (list, tuple)):
			return File((self.path,) + tuple(path))
		elif isinstance(path, File):
			return path
		elif isinstance(path, Path):
			return File(path.path)

	def new_file(self, path):
		'''Like file() but guarantees the file does not yet exist by adding
		sequentional numbers if needed.
		'''
		file = self.file(path)
		basename = file.basename
		if '.' in basename:
			basename, ext = basename.split('.', 1)
		else:
			ext = ''
		dir = file.dir
		i = 0
		while file.exists():
			logger.debug('File exists "%s" trying increment', file)
			i += 1
			newname = basename + '%03i' % i
			if ext:
				newname += '.' + ext
			file = dir.file(newname)
		return file

	def subdir(self, path):
		'''Returns a Dir object for a path relative to this directory

		When 'path' is in fact a L{Dir} object already this method
		still enforces is to be below this directory. So this method can
		be used as check as well.

		@param path: a (relative) file path as string, tuple or L{Path} object

		@returns: a L{Dir} object

		@raises PathLookupError: if the subdir is not below this dir
		'''

		dir = self.resolve_dir(path)
		if not dir.path.startswith(self.path):
			raise PathLookupError, '%s is not below %s' % (dir, self)
		return dir

	def resolve_dir(self, path):
		'''Like L{subdir()} but allows the path to start with "../"'''
		assert isinstance(path, (Path, basestring, list, tuple))
		if isinstance(path, basestring):
			return Dir((self.path, path))
		elif isinstance(path, (list, tuple)):
			return Dir((self.path,) + tuple(path))
		elif isinstance(path, Dir):
			return path
		elif isinstance(path, Path):
			return Dir(path.path)


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

	def list(self, raw=False):
		'''As Dir.list() but filteres the results with the preset
		filter. If 'raw' is True filtering is disabled.
		'''
		files = Dir.list(self)
		if not raw:
			files = filter(self.filter, files)
		return files


class UnixFile(Path):
	'''OO wrapper for files. Implements more complex logic than
	the default python file objects. On writing we first write to a
	temporary files, then flush and sync and finally replace the file we
	intended to write with the temporary file. This makes it much more
	difficult to loose file contents when something goes wrong during
	the writing.

	When 'checkoverwrite' is True this class checks mtime to prevent
	overwriting a file that was changed on disk, if mtime fails MD5 sums
	are used to verify before raising an exception. However this check
	only works when using read(), readlines(), write() or writelines(),
	but not when calling open() directly. Unfortunately this logic is
	not atomic, so your mileage may vary.

	The *_async functions can be used to read or write files in a separate
	thread. See zim.async for details. An AsyncLock is used to ensure
	reading and writing is done sequentally between several threads.
	However, this does not work when using open() directly.
	'''

	# For atomic write we first write a tmp file which has the extension
	# .zim-new~ when is was written succesfully we replace the actual file
	# with the tmp file. Because rename is atomic on POSIX platforms and
	# replaces the existing file this either succeeds or not, it can never
	# truncate the existing file but fail to write the new file. So if writing
	# fails we should always at least have the old file still present.
	# If we encounter a left over .zim-new~ we ignore it since it may be
	# corrupted.
	#
	# For Window the behavior is more complicated, see the WindowsFile class
	# below.
	#
	# Note that the mechanism to avoid overwriting files that changed on disks
	# does not prevent conflicts when two processes try to write to the same
	# file at the same time. This is a hard problem that is currently not
	# addressed in this implementation.

	def __init__(self, path, checkoverwrite=False, endofline=None):
		Path.__init__(self, path)
		self.checkoverwrite = checkoverwrite
		self.endofline = endofline
		self._mtime = None
		self._lock = FS.get_async_lock(self)

	def __eq__(self, other):
		if isinstance(other, File):
			return self.path == other.path
		else:
			return False

	def exists(self):
		'''Returns True if the file exists and is actually a file'''
		return os.path.isfile(self.encodedpath)

	def open(self, mode='r'):
		'''Returns an io object for reading or writing.
		Opening a non-exisiting file for writing will cause the whole path
		to this file to be created on the fly.
		'''
		# When we open for writing, we actually open the tmp file
		# and return a FileHandle object that will call _on_write()
		# when it is closed. This handler will take care of replacing
		# the actual file with the newly written tmp file.
		assert mode in ('r', 'w')
		if mode == 'w':
			if not self.iswritable():
				raise FileWriteError, _('File is not writable') # T: Error message
			elif not self.exists():
				self.dir.touch()
			else:
				pass # exists and writable

		mode += 'b'
		if mode == 'wb':
			tmp = self.encodedpath + '.zim-new~'
			fh = FileHandle(tmp, mode=mode, on_close=self._on_write)
		else:
			fh = open(self.encodedpath, mode=mode)

		# code copied from codecs.open() to wrap our FileHandle objects
		info = codecs.lookup('utf-8')
		srw = codecs.StreamReaderWriter(
			fh, info.streamreader, info.streamwriter, 'strict')
		srw.encoding = 'utf-8'
		return srw

	def _on_write(self):
		# Handler executed after successfull writing the .zim-new~ tmp file
		# to replace the actual file with the tmp file.
		# Note that flush() and sync() are already done before close()
		#
		# On Unix, for rename() if dest already exists it is replaced in an
		# atomic operation. And other processes reading our file will not
		# block moving it :)
		tmp = self.encodedpath + '.zim-new~'
		if not os.path.isfile(tmp):
			raise AssertionError, 'BUG: File should exist: %s' % tmp

		os.rename(tmp, self.encodedpath)
		logger.debug('Wrote %s', self)

	def raw(self):
		'''Like read() but without encoding and newline logic.
		Used to read binary data, e.g. when serving files over www.
		Note that this function also does not integrates with checking
		mtime, so intended for read only usage.
		'''
		with self._lock:
			try:
				fh = open(self.encodedpath, mode='rb')
				content = fh.read()
				fh.close()
				return content
			except IOError:
				raise FileNotFoundError(self)

	def read(self):
		'''Returns the content as string. Raises a
		FileNotFoundError exception when the file does not exist.
		'''
		with self._lock:
			text = self._read()
		return text

	def read_async(self, callback=None, data=None):
		'''Like read() but as asynchronous operation.
		Returns a AsyncOperation object, see there for documentation
		for 'callback'. Try operation.result for content.
		'''
		if not self.exists():
			raise FileNotFoundError(self)
		operation = AsyncOperation(
			self._read, lock=self._lock, callback=callback, data=data)
		operation.start()
		return operation

	def _read(self):
		try:
			file = self.open('r')
			content = file.read()
			self._checkoverwrite(content)
			return content.replace('\r', '').replace('\x00', '')
				# Internally we use unix line ends - so strip out \r
				# And remove any NULL byte since they skrew up parsing
		except IOError:
			raise FileNotFoundError(self)

	def readlines(self):
		'''Returns the content as list of lines. Raises a
		FileNotFoundError exception when the file does not exist.
		'''
		with self._lock:
			lines = self._readlines()
		return lines

	def readlines_async(self, callback=None, data=None):
		'''Like readlines() but as asynchronous operation.
		Returns a AsyncOperation object, see there for documentation
		for 'callback'. Try operation.result for content.
		'''
		if not self.exists():
			raise FileNotFoundError(self)
		operation = AsyncOperation(
			self._readlines, lock=self._lock, callback=callback, data=data)
		operation.start()
		return operation

	def _readlines(self):
		try:
			file = self.open('r')
			lines = file.readlines()
			self._checkoverwrite(lines)
			return [line.replace('\r', '').replace('\x00', '') for line in lines]
				# Internally we use unix line ends - so strip out \r
				# And remove any NULL byte since they skrew up parsing
		except IOError:
			raise FileNotFoundError(self)

	def write(self, text):
		'''Overwrite file with text'''
		with self._lock:
			self._write(text)
		self._check_isnew()

	def write_async(self, text, callback=None, data=None):
		'''Like write() but as asynchronous operation.
		Returns a AsyncOperation object, see there for documentation
		for 'callback'.
		'''
		#~ print '!! ASYNC WRITE'
		def mycallback(result, error, *args):
			if error is None: self._check_isnew()
			if callback: callback(result, error, *args)

		operation = AsyncOperation(
			self._write, (text,), lock=self._lock, callback=mycallback, data=data)
		operation.start()
		return operation

	def get_endofline(self):
		'''Returns the end-of-line character(s) to be used when writing this file'''
		if self.endofline is None:
			if isinstance(self, WindowsPath): return '\r\n'
			else: return '\n'
		else:
			assert self.endofline in ('unix', 'dos')
			if self.endofline == 'dos': return '\r\n'
			else: return '\n'

	def _write(self, text):
		self._assertoverwrite()
		self._isnew = not os.path.isfile(self.encodedpath)
			# Put this check here because here we are sure to have a lock
		endofline = self.get_endofline()
		if endofline != '\n':
			text = text.replace('\n', endofline)
		file = self.open('w')
		file.write(text)
		file.close()
		self._checkoverwrite(text)

	def _check_isnew(self):
		# Make sure the 'path-created' signal is emitted in the main
		# thread, so do not put this in _write(), but call from write()
		# or from async callback.
		# Also make sur this is called after lock is released to prevent
		# deadlock when event handler tries to access the file.
		if self._isnew:
			FS.emit('path-created', self)

	def writelines(self, lines):
		'''Overwrite file with a list of lines'''
		with self._lock:
			self._writelines(lines)
		self._check_isnew()

	def writelines_async(self, text, callback=None, data=None):
		'''Like writelines() but as asynchronous operation.
		Returns a AsyncOperation object, see there for documentation
		for 'callback'.
		'''
		#~ print '!! ASYNC WRITE'
		def mycallback(result, error, *args):
			if error is None: self._check_isnew()
			if callback: callback(result, error, *args)

		operation = AsyncOperation(
			self._writelines, (text,), lock=self._lock, callback=mycallback, data=data)
		operation.start()
		return operation

	def _writelines(self, lines):
		self._assertoverwrite()
		self._isnew = not os.path.isfile(self.encodedpath)
			# Put this check here because here we are sure to have a lock
		endofline = self.get_endofline()
		if endofline != '\n':
			lines = [line.replace('\n', endofline) for line in lines]
		file = self.open('w')
		file.writelines(lines)
		file.close()
		self._checkoverwrite(lines)

	def _checkoverwrite(self, content):
		# Set properties needed by assertoverwrite for the in-memory object
		if self.checkoverwrite:
			self._mtime = self.mtime()
			self._content = content

	def _assertoverwrite(self):
		# When we read a file and than write it, this method asserts the file
		# did not change in between (e.g. by another process, or another async
		# function of our own process). We use properties of this object instance
		# We check the timestamp, if that does not match we check md5 to be sure.
		# (Sometimes e.g. netwerk filesystems do not maintain timestamps as strict
		# as we would like.)
		#
		# This function should not prohibit writing without reading first.
		# Also we just write the file if it went missing in between
		if self._mtime:
			try:
				mtime = self.mtime()
			except OSError:
				if not  os.path.isfile(self.encodedpath):
					logger.critical('File missing: %s', self.path)
					return
				else:
					raise

			if not self._mtime == mtime:
				logger.warn('mtime check failed for %s, trying md5', self.path)
				if _md5(self._content) != _md5(self.open('r').read()):
					raise FileWriteError, 'File changed on disk: %s' % self.path

	def touch(self):
		'''Create this file and any parent directories if it does not yet exist.
		Only needed for place holders - will happen automatically at first write.
		'''
		if self.exists():
			return
		else:
			with self._lock:
				io = self.open('w')
				io.write('')
				io.close()

	def remove(self):
		'''Remove this file and any related temporary files we made.
		Ignores if page did not exist in the first place.
		'''
		logger.info('Remove file: %s', self)
		with self._lock:
			if os.path.isfile(self.encodedpath):
				os.remove(self.encodedpath)

			tmp = self.encodedpath + '.zim-new~'
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
		shutil.copy(self.encodedpath, dest.encodedpath)
		# TODO - not hooked with FS signals

	def compare(self, other):
		'''Uses MD5 to tell you if files are the same or not.
		This can e.g. be used to detect case-insensitive filesystems
		when renaming files.
		'''
		return _md5(self.read()) == _md5(other.read())


class WindowsFile(UnixFile):

	# For the "atomic" write on Windows we use .zim-new~ and .zim-orig~.
	# When writing a new file, the sequence is the same as on Unix: we
	# write a tmp file and move it into place. However on windows the
	# rename() function does not allow replacing an existing file, so
	# there is no atomic operation to move the tmp file into place.
	# What we do instead:
	#
	# 1. Write file.zim-new~
	# 2. Move file to file.zim-orig~
	# 3. Move file.zim-new~ to file
	# 4. Remove file.zim-orig~
	#
	# But now we have to consider recovering the file if any of these
	# steps fails:
	#   * If we have .zim-new~ and the actual file either step 1 or 2
	#     failed, in this case the .zim-new~ file can be corrupted, so
	#     keep the file itself
	#   * If we have .zim-new~ and .zim-orig~ but the actual file is
	#     missing, step 3 failed. We use .zim-new~ because probably
	#     step 1 succeeded.
	#   * If we have the actual file and .zim-orig~ step 4 failed, we
	#     can throw away the .zim-orig~ file.
	#   * If we only have a .zim-orig~ file step 4 failed, was not
	#     recovered and maybe the file was removed (remove cleans up the
	#     .zim-new~). So we can not recover - file does not exist.
	#   * If only have a .zim-new~ file maybe writing a new file failed,
	#     the .zim-new~ file can be corrupted - so we can not recover
	#   * If we have all 3 files some combination of actions happened,
	#     keep using the actual file.
	#
	# So this results in two rules:
	#
	# 1. if the actual file exists, use it
	# 2. if the actual file does no exist but both .zim-new~ and .zim-orig~
	#    exist, use the .zim-new~ file.
	#
	# In any other cases we can not recover. What we can do is make a backup
	# of .zim-orig~ for future manual recovery.

	def __init__(self, path, checkoverwrite=False, endofline=None):
		UnixFile.__init__(self, path, checkoverwrite, endofline)
		self._recover() # just to be sure

	def exists(self):
		'''Returns True if the file exists and is actually a file'''
		orig = self.encodedpath + '.zim-orig~'
		new = self.encodedpath + '.zim-new~'
		return os.path.isfile(self.encodedpath) or \
			(os.path.isfile(new) and os.path.isfile(orig))
			# if both new and orig exists, we can recover

	def open(self, mode='r'):
		self._recover() # just to be sure
		return UnixFile.open(self, mode)

	def _on_write(self):
		# Handler executed after successfull writing the .zim-new~ tmp file
		# to replace the actual file with the tmp file.
		# Note that flush() and sync() are already done before close()
		#
		# On Windows, rename() does not allow atomic replace, so we need
		# more logic. Also we want to be robust for errors when file is
		# temporarily locked by e.g. a virus scanner.
		tmp = self.encodedpath + '.zim-new~'
		if not os.path.isfile(tmp):
			raise AssertionError, 'BUG: File should exist: %s' % tmp

		if os.path.isfile(self.encodedpath):
			orig = self.encodedpath + '.zim-orig~'
			if os.path.isfile(orig):
				os.remove(orig)
			self._rename(self.encodedpath, orig) # Step 2.
			self._rename(tmp, self.encodedpath)  # Step 3.
			try:
				os.remove(orig) # Step 4.
			except OSError:
				pass # If it fails we try again on next write
		else:
			self._rename(tmp, self.encodedpath)

		logger.debug('Wrote %s', self)

	@staticmethod
	def _rename(src, dst):
		# Wrapper for os.rename which handles the timeout for errors when file
		# is locked. Tries 10 times after 1s then fails.
		i = 0
		while True:
			try:
				os.rename(src, dst)
			except WindowsError, error:
				if error.errno == 13 and i < 10:
					# errno 13 means locked by other process
					i += 1
					logger.warn('File locked by other process: %s\nRe-try %i', src, i)
					import time
					time.sleep(1)
				else:
					raise
			else:
				break

	def _recover(self):
		# Try and recover the file after errors in writing the file,
		# see comment in class header.
		if os.path.isfile(self.encodedpath):
			return # no recovery needed

		orig = self.encodedpath + '.zim-orig~'
		new = self.encodedpath + '.zim-new~'
		def backup_orig(orig):
			bak = self.encodedpath + '.bak~'
			i = 1
			while os.path.isfile(bak):
				bak = self.encodedpath + '.bak%i~' % i
				i += 1
			self._rename(orig, bak)
			logger.warn('Left over file found: %s\nBacked up to: %s', orig, bak)

		if os.path.isfile(new) and os.path.isfile(orig):
			self._rename(new, self.encodedpath)
			backup_orig(orig)
		elif os.path.isfile(orig):
			backup_orig(orig)


# Determine which base class to use for files
if os.name == 'nt':
	File = WindowsFile
else:
	File = UnixFile


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
