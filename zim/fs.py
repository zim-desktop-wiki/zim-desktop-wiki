# -*- coding: utf-8 -*-

# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Module with basic filesystem objects.

This module must be used by all other zim modules for filesystem
interaction. It takes care of proper encoding file paths
(system dependent) and file contents (UTF-8) and implements a number
of sanity checks.

The main classes are L{File} and L{Dir} which implement file and
folder objects. There is also a singleton object to represent the whole
filesystem, whichprovides signals when a file or folder is created,
moved or deleted. This is stored in L{zim.fs.FS}.
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
# os.readlink chokes on Unicode strings that aren't coercible to the
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
# files with inconsistent encoding.
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
# is the most common filesystem encoding on modern operating systems.

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

import os
import re
import sys
import shutil
import errno
import codecs
import logging
import threading


from zim.errors import Error, TrashNotSupportedError, TrashCancelledError
from zim.parsing import url_encode, url_decode, URL_ENCODE_READABLE
from zim.signals import SignalEmitter, SIGNAL_AFTER

logger = logging.getLogger('zim.fs')

#: gobject and gio libraries are imported for optional features, like trash
gobject = None
gio = None
try:
	import gobject
	import gio
	if not gio.File.trash:
		gio = None
except ImportError:
	pass

if not gio:
	logger.info("Trashing of files not supported, could not import 'gio'")
	logger.info('No file monitor support - changes will go undetected')


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


#: Extensions to determine image mimetypes - used in L{File.isimage()}
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


ENCODING = sys.getfilesystemencoding() #: file system encoding for paths
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
	'''Wrapper for C{os.path.isabs}.
	@param path: a file system path as string
	@returns: C{True} when the path is absolute instead of a relative path
	'''
	return path.startswith('file:/') \
	or path.startswith('~') \
	or os.path.isabs(path)


def isdir(path):
	'''Wrapper for C{os.path.isdir()}, fixes encoding.
	@param path: a file system path as string
	@returns: C{True} when the path is an existing dir
	'''
	return os.path.isdir(encode(path))


def isfile(path):
	'''Wrapper for C{os.path.isfile()}, fixes encoding.
	@param path: a file system path as string
	@returns: C{True} when the path is an existing file
	'''
	return os.path.isfile(encode(path))


def joinpath(*parts):
	'''Wrapper for C{os.path.join()}
	@param parts: path elements
	@returns: the same paths joined with the proper path separator
	'''
	return os.path.join(*parts)

def expanduser(path):
	'''Wrapper for C{os.path.expanduser()} to get encoding right'''
	if ENCODING == 'mbcs':
		# This method is an exception in that it does not handle unicode
		# directly. This will cause and error when user name contains
		# non-ascii characters. See bug report lp:988041.
		# But also mbcs encoding does not handle all characters,
		# so only encode home part
		parts = path.replace('\\', '/').strip('/').split('/')
			# parts[0] now is "~" or "~user"

		if isinstance(path, unicode):
			part = parts[0].encode('mbcs')
			part = os.path.expanduser(part)
			parts[0] = part.decode('mbcs')
		else:
			# assume it is compatible
			parts[0] = os.path.expanduser(parts[0])

		path = '/'.join(parts)
	else:
		# Let encode() handle the unicode encoding
		path = decode(os.path.expanduser(encode(path)))

	if path.startswith('~'):
		# expansion failed - do a simple fallback
		from zim.environ import environ

		home = environ['HOME']
		parts = path.replace('\\', '/').strip('/').split('/')
		if parts[0] == '~':
			path = '/'.join([home] + parts[1:])
		else: # ~user
			dir = os.path.basename(home) # /home or similar ?
			path = '/'.join([dir, parts[0][1:]] + parts[1:])

	return path

def get_tmpdir():
	'''Get a folder in the system temp dir for usage by zim.
	This zim specific temp folder has permission set to be readable
	only by the current users, and is touched if it didn't exist yet.
	Used as base folder by L{TmpFile}.
	@returns: a L{Dir} object for the zim specific tmp folder
	'''
	# We encode the user name using urlencoding to remove any non-ascii
	# characters. This is because sockets are not always unicode safe.

	import tempfile
	from zim.environ import environ
	root = tempfile.gettempdir()
	user = url_encode(environ['USER'], URL_ENCODE_READABLE)
	dir = Dir((root, 'zim-%s' % user))

	try:
		dir.touch(mode=0700) # Limit to single user
		os.chmod(dir.path, 0700) # Limit to single user when dir already existed
			# Raises OSError if not allowed to chmod
		os.listdir(dir.path)
			# Raises OSError if we do not have access anymore
	except OSError:
		raise AssertionError, \
			'Either you are not the owner of "%s" or the permissions are un-safe.\n' \
			'If you can not resolve this, try setting $TMP to a different location.' % dir.path
	else:
		# All OK, so we must be owner of a safe folder now ...
		return dir


def normalize_file_uris(path):
	'''Function to deal with invalid or non-local file URIs.
	Translates C{file:/} to the proper C{file:///} form and replaces
	URIs of the form C{file://host/share} to C{smb://host/share}.
	@param path: a filesystem path or URL
	@returns: the proper URI or the original input path
	'''
	if path.startswith('file:///') \
	or path.startswith('file://localhost/'):
		return path
	elif path.startswith('file://'):
		return 'smb://' + path[7:]
	elif path.startswith('file:/'):
		return 'file:///' + path[6:]
	else:
		return path


def normalize_win32_share(path):
	'''Translates paths for windows shares in the platform specific
	form. So on windows it translates C{smb://} URLs to C{\\host\share}
	form, and vice versa on all other platforms.
	Just returns the original path if it was already in the right form,
	or when it is not a path for a share drive.
	@param path: a filesystem path or URL
	@returns: the platform specific path or the original input path
	'''
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
	'''Wrapper for C{os.rmdir} that also knows how to unlink symlinks.
	Fails when the folder is not a link and is not empty.
	@param path: a file system path as string
	'''
	try:
		os.rmdir(path)
	except OSError:
		if os.path.islink(path) and os.path.isdir(path):
			os.unlink(path)
		else:
			raise


def cleanup_filename(name):
	'''Removes all characters in 'name' that are not allowed as part
	of a file name. This function is intended for e.g. config files etc.
	B{not} for page files in a store.
	For file system filenames we can not use:
	'\\', '/', ':', '*', '?', '"', '<', '>', '|'
	And we also exclude "\\t" and "\\n".
	@param name: the filename as string
	@returns: the name with invalid characters removed
	'''
	for char in ("/", "\\", ":", "*", "?", '"', "<", ">", "|", "\t", "\n"):
		name = name.replace(char, '')
	return name


def format_file_size(bytes):
	'''Returns a human readable label  for a file size
	E.g. C{1230} becomes C{"1.23kb"}, idem for "Mb" and "Gb"
	@param bytes: file size in bytes as integer
	@returns: size as string
	'''
	for unit, label in (
		(1000000000, 'Gb'),
		(1000000, 'Mb'),
		(1000, 'kb'),
	):
		if bytes >= unit:
			size = float(bytes) / unit
			if size < 10:
				return "%.2f%s" % (size, label)
			elif size < 100:
				return "%.1f%s" % (size, label)
			else:
				return "%.0f%s" % (size, label)
	else:
		return str(bytes) + 'b'




def _md5(content):
	import hashlib
	m = hashlib.md5()
	if  isinstance(content, unicode):
		m.update(content.encode('utf-8'))
	elif isinstance(content, basestring):
		m.update(content)
	else:
		for l in content:
			m.update(l)
	return m.digest()


class PathLookupError(Error):
	'''Error raised when there is an error finding the specified path'''
	pass # TODO description


class FileWriteError(Error):
	'''Error raised when we can not write a file. Either due to file
	permissions or e.g. because it is detected the file changed on
	disk.
	'''
	pass # TODO description


class FileNotFoundError(PathLookupError):
	'''Error raised when a file does not exist that is expected to
	exist.

	@todo: reconcile this class with the NoSuchFileError in zim.gui
	'''

	def __init__(self, file):
		self.file = file
		self.msg = _('No such file: %s') % file.path
			# T: message for FileNotFoundError


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
		self.description += '\n\n' + _('Details') + ':\n' + unicode(error)
			# T: label for detailed error


# TODO actually hook the signal for deleting files and folders

class FSSingletonClass(SignalEmitter):
	'''Class used for the singleton 'zim.fs.FS' instance

	@signal: C{path-created (L{FilePath})}: Emitted when a new file or
	folder has been created
	@signal: C{path-moved (L{FilePath}, L{FilePath})}: Emitted when
	a file or folder has been moved
	@signal: C{path-deleted (L{FilePath})}: Emitted when a file or
	folder has been deleted

	@todo: fix the FS signals for folders as well
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'path-created': (SIGNAL_AFTER, None, (object,)),
		'path-moved': (SIGNAL_AFTER, None, (object, object)),
		'path-deleted': (SIGNAL_AFTER, None, (object,)),
	}

	def __init__(self):
		self._lock = threading.Lock()

	def get_async_lock(self, path):
		'''Get an C{threading.Lock} for filesytem operations on a path
		@param path: a L{FilePath} object
		@returns: an C{threading.Lock} object
		'''
		# FUTURE: we may actually use path to allow parallel async
		# operations for files & folders that do not belong to the
		# same tree. Problem there is that we do not acquire the lock
		# in this method. So we need a new kind of lock type that can
		# track dependency on other locks.
		# Make sure to allow for the fact that other objects can keep
		# the lock that are returned here indefinitely for re-use.
		# But for now we keep things simple.
		assert isinstance(path, FilePath)
		return self._lock

#: Singleton object for the system filesystem - see L{FSSingletonClass}
FS = FSSingletonClass()


class UnixPath(SignalEmitter):
	'''Base class for Dir and File objects, represents a file path

	@ivar path: the absolute file path as string
	@ivar encodedpath: the absolute file path as string in local
	file system encoding (should only be used by low-level functions)
	@ivar user_path: the absolute file path relative to the user's
	C{HOME} folder or C{None}
	@ivar uri: the C{file://} URI for this path
	@ivar basename: the basename of the path
	@ivar dirname: the dirname of the path
	@ivar dir: L{Dir} object for the parent folder

	@signal: C{changed (file, other_file, event_type)}: emitted when file
	changed - availability based on C{gio} support for file monitors on
	this platform
	'''

	# TODO __signals__

	def __init__(self, path):
		'''Constructor

		@param path: an absolute file path, file URL, L{FilePath} object
		or a list of path elements. When a list is given, the first
		element is allowed to be an absolute path, URL or L{FilePath}
		object as well.
		'''
		self._serialized = None

		if isinstance(path, FilePath):
			self.path = path.path
			self.encodedpath = path.encodedpath
			return

		try:
			if isinstance(path, (list, tuple)):
				path = map(unicode, path)
					# Flatten objects - strings should be unicode or ascii already
				path = os.path.sep.join(path)
					# os.path.join is too intelligent for it's own good
					# just join with the path separator.
			else:
				path = unicode(path) # make sure we can decode
		except UnicodeDecodeError:
			raise Error, 'BUG: invalid input, file names should be in ascii, or given as unicode'

		if path.startswith('file:/'):
			path = self._parse_uri(path)
		elif path.startswith('~'):
			path = expanduser(path)

		self._set_path(path) # overloaded in WindowsPath

	def serialize_zim_config(self):
		'''Returns the file path as string for serializing the object'''
		if self._serialized is None:
			self._serialized = self.user_path or self.path
		return self._serialized

	@classmethod
	def new_from_zim_config(klass, string):
		'''Returns a new object based on the string representation for
		that path
		'''
		return klass(string)

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
		# For Unix we need to use proper encoding
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
		'''Concatenates paths, only creates objects of the same class. See
		L{Dir.file()} and L{Dir.subdir()} instead to create other objects.
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
	def dirname(self):
		'''Dirname property'''
		return os.path.dirname(self.path) # encoding safe

	@property
	def user_path(self):
		'''User_path property'''
		dir = Dir('~') # FIXME: Should we cache this folder somewhere ?
		if self.ischild(dir):
			return '~/' + self.relpath(dir)
		else:
			return None

	@property
	def uri(self):
		'''File uri property'''
		return 'file://' + url_encode(self.path)

	@property
	def dir(self):
		'''Returns a L{Dir} object for the parent dir'''
		path = os.path.dirname(self.path) # encoding safe
		return Dir(path)

	def _setup_signal(self, signal):
		if signal != 'changed' \
		or not gio:
			return

		try:
			self._teardown_signal(signal) # just to be sure
			file = gio.File(uri=self.uri)
			self._gio_file_monitor = file.monitor()
			self._gio_file_monitor.connect('changed', self._do_changed)
		except:
			logger.exception('Error while setting up file monitor')

	def _teardown_signal(self, signal):
		if signal != 'changed' \
		or not hasattr(self, '_gio_file_monitor') \
		or not self._gio_file_monitor:
			return

		try:
			self._gio_file_monitor.cancel()
			self._gio_file_monitor = None
		except:
			logger.exception('Error while tearing down file monitor')

	def _do_changed(self, filemonitor, file, other_file, event_type):
		# 'FILE_MONITOR_EVENT_CHANGED' is always followed by
		# a 'FILE_MONITOR_EVENT_CHANGES_DONE_HINT' when the filehandle
		# is closed (or after timeout). Idem for "created", assuming it
		# is not created empty.
		#
		# TODO: do not emit changed on CREATED - separate signal that
		#       can be used when monitoring a file list, but reserve
		#       changed for changes-done-hint so that we ensure the
		#       content is complete.
		#       + emit on write and block redundant signals here
		#
		# Also note that in many cases "moved" will not be used, but a
		# sequence of deleted, created will be signaled
		#
		# For Dir objects, the event will refer to files contained in
		# the dir.

		#~ print 'MONITOR:', self, event_type
		if event_type in (
			gio.FILE_MONITOR_EVENT_CREATED,
			gio.FILE_MONITOR_EVENT_CHANGES_DONE_HINT,
			gio.FILE_MONITOR_EVENT_DELETED,
			gio.FILE_MONITOR_EVENT_MOVED,
		):
			self.emit('changed', None, None) # TODO translate otherfile and eventtype

	def exists(self):
		'''Check if a file or folder exists.
		@returns: C{True} if the file or folder exists
		@implementation: must be implemented by sub classes in order
		that they enforce the type of the resource as well
		'''
		return os.path.exists(self.encodedpath)

	def iswritable(self):
		'''Check if a file or folder is writable. Uses permissions of
		parent folder if the file or folder does not (yet) exist.
		@returns: C{True} if the file or folder is writable
		'''
		if self.exists():
			return os.access(self.encodedpath, os.W_OK)
		else:
			return self.dir.iswritable() # recurs

	def _stat(self):
		return os.stat(self.encodedpath)

	def mtime(self):
		'''Get the modification time of the file path.
		@returns: the mtime timestamp
		'''
		return self._stat().st_mtime

	def size(self):
		'''Get file size in bytes
		See L{format_file_size()} to get a human readable label
		@returns: file size in bytes
		'''
		return self._stat().st_size

	def isequal(self, other):
		'''Check file paths are equal based on stat results (inode
		number etc.). Intended to detect when two files or dirs are the
		same on case-insensitive filesystems. Does not explicitly check
		the content is the same.
		If you just want to know if two files have the same content,
		see L{File.compare()}
		@param other: an other L{FilePath} object
		@returns: C{True} when the two paths are one and the same file
		'''
		# Do NOT assume paths are the same - could be hard link
		# or it could be a case-insensitive filesystem
		try:
			stat_result = os.stat(self.encodedpath)
			other_stat_result = os.stat(other.encodedpath)
		except OSError:
			return False
		else:
			return stat_result == other_stat_result

	def split(self):
		'''Split the parts of the path on the path separator.
		If the OS uses the concept of a drive the first part will
		include the drive. (So using split() to count the number of
		path elements will not be robust for the path "/".)
		@returns: a list of path elements
		'''
		drive, path = os.path.splitdrive(self.path)
		parts = path.replace('\\', '/').strip('/').split('/')
		parts[0] = drive + os.path.sep + parts[0]
		return parts

	def relpath(self, reference, allowupward=False):
		'''Get a relative path for this file path with respect to
		another path. This method always returns paths using "/" as
		separator, even on windows.
		@param reference: a reference L{FilePath}
		@param allowupward: if C{True} the relative path is allowed to
		start with 'C{../}', if C{False} the reference should be a
		parent folder of this path.
		@returns: a relative file path
		@raises AssertionError: when C{allowupward} is C{False} and
		C{reference} is not a parent folder
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
			if not self.path.startswith(refdir):
				raise AssertionError, 'Not a parent folder'
			path = ''

		i = len(reference.path)
		path += self.path[i:].lstrip(sep).replace(sep, '/')
		return path

	def commonparent(self, other):
		'''Find a comon parent folder between two file paths.
		@param other: another L{FilePath}
		@returns: a L{Dir} object for the common parent folder, or
		C{None} when there is no common parent
		'''
		path = os.path.commonprefix((self.path, other.path)) # encoding safe
		i = path.rfind(os.path.sep) # win32 save...
		if i >= 0:
			return Dir(path[:i+1])
		else:
			# different drive ?
			return None

	def ischild(self, parent):
		'''Check if this path is a child path of a folder
		@returns: C{True} if this path is a child path of C{parent}
		'''
		return self.path.startswith(parent.path + os.path.sep)

	def isdir(self):
		'''Check if this path is a folder or not. Used to detect if
		e.g. a L{File} object should have really been a L{Dir} object.
		@returns: C{True} when this path is a folder
		'''
		return os.path.isdir(self.encodedpath)

	def rename(self, newpath):
		'''Rename (move) the content this file or folder to another
		location. This will B{not} change the current file path, so the
		object keeps pointing to the old location.
		@param newpath: the destination C{FilePath} which can either be a
		file or a folder.
		@emits: path-moved
		'''
		# Using shutil.move instead of os.rename because move can cross
		# file system boundaries, while rename can not
		logger.info('Rename %s to %s', self, newpath)
		if self.path == newpath.path:
			raise AssertionError, 'Renaming %s to itself !?' % self.path

		with FS.get_async_lock(self):
			# Do we also need a lock for newpath (could be the same as lock for self) ?
			if newpath.isdir():
				if self.isequal(newpath):
					# We checked name above, so must be case insensitive file system
					# but we still want to be able to rename to other case, so need to
					# do some moving around
					tmpdir = self.dir.new_subdir(self.basename)
					shutil.move(self.encodedpath, tmpdir.encodedpath)
					shutil.move(tmpdir.encodedpath, newpath.encodedpath)
				else:
					# Needed because shutil.move() has different behavior for this case
					raise AssertionError, 'Folder already exists: %s' % newpath.path
			else:
				# normal case
				newpath.dir.touch()
				shutil.move(self.encodedpath, newpath.encodedpath)
		FS.emit('path-moved', self, newpath)
		self.dir.cleanup()

	def trash(self):
		'''Trash a file or folder by moving it to the system trashcan
		if supported. Depends on the C{gio} library.
		@returns: C{True} when succesful
		@raises TrashNotSupportedError: if trashing is not supported
		or failed.
		@raises TrashCancelledError: if trashing was cancelled by the
		user
		'''
		if not gio:
			raise TrashNotSupportedError, 'gio not imported'

		if self.exists():
			logger.info('Move %s to trash' % self)
			f = gio.File(uri=self.uri)
			try:
				ok = f.trash()
			except gobject.GError, error:
				if error.code == gio.ERROR_CANCELLED \
				or (os.name == 'nt' and error.code == 0):
					# code 0 observed on windows for cancel
					logger.info('Trash operation cancelled')
					raise TrashCancelledError, 'Trashing cancelled'
				elif error.code == gio.ERROR_NOT_SUPPORTED:
					raise TrashNotSupportedError, 'Trashing failed'
				else:
					raise error
			else:
				if not ok:
					raise TrashNotSupportedError, 'Trashing failed'
			return True
		else:
			return False


class WindowsPath(UnixPath):
	'''Base class for Dir and File objects, represents a file path
	on windows.
	'''

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
		path = self.path.replace('\\', '/')
		if re.match('[A-Za-z]:/', path):
			return 'file:///' + path[:2] + url_encode(path[2:])
		else:
			return 'file:///' + url_encode(path)


# Determine which base class to use for classes below
if os.name == 'posix':
	FilePath = UnixPath
elif os.name == 'nt':
	FilePath = WindowsPath
else:
	logger.critical('os name "%s" unknown, falling back to posix', os.name)
	FilePath = UnixPath


class Dir(FilePath):
	'''Class representing a single file system folder'''

	def __eq__(self, other):
		if isinstance(other, Dir):
			return self.path == other.path
		else:
			return False

	def exists(self):
		return os.path.isdir(self.encodedpath)

	def list(self, glob=None, includehidden=False, includetmp=False, raw=False):
		'''List the file contents

		@param glob: a file name glob to filter the listed files, e.g C{"*.png"}
		@param includehidden: if C{True} include hidden files
		(e.g. names starting with "."), ignore otherwise
		@param includetmp: if C{True} include temporary files
		(e.g. names ending in "~"), ignore otherwise
		@param raw: for filtered folders (C{FilteredDir} instances)
		setting C{raw} to C{True} will disable filtering

		@returns: a sorted list of names for files and subdirectories.
		Will not return names that could not be decoded properly and
		will throw warnings if those are encountered.
		Hidden files are silently ignored.
		'''
		files = []
		if ENCODING == 'mbcs':
			# We are running on windows and os.listdir will handle unicode natively
			assert isinstance(self.encodedpath, unicode)
			for file in self._list(includehidden, includetmp):
				if isinstance(file, unicode):
					files.append(file)
				else:
					logger.warn('Ignoring file: "%s" invalid file name', file)
		else:
			# If filesystem does not handle unicode natively and path for
			# os.listdir(path) is _not_ a unicode object, the result will
			# be a list of byte strings. We can decode them ourselves.
			assert not isinstance(self.encodedpath, unicode)
			for file in self._list(includehidden, includetmp):
				try:
					files.append(file.decode(ENCODING))
				except UnicodeDecodeError:
					logger.warn('Ignoring file: "%s" invalid file name', file)

		if glob:
			expr = _glob_to_regex(glob)
			files = filter(expr.match, files)

		files.sort()
		return files

	def _list(self, includehidden, includetmp):
		if self.exists():
			files = []
			for file in os.listdir(self.encodedpath):
				if file.startswith('.') and not includehidden:
					continue # skip hidden files
				elif (file.endswith('~') or file.startswith('~')) and not includetmp:
					continue # skip temporary files
				else:
					files.append(file)
			return files
		else:
			return []

	def walk(self, raw=True):
		'''Generator that yields all files and folders below this dir
		as objects.
		@param raw: see L{list()}
		@returns: yields L{File} and L{Dir} objects, depth first
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
		as text. Used in tests.
		@param raw: see L{list()}
		@returns: file listing as string
		'''
		text = ''
		for child in self.walk(raw=raw):
			path = child.relpath(self)
			if isinstance(child, Dir):
				path += '/'
			text += path + '\n'
		return text

	def touch(self, mode=None):
		'''Create this folder and any parent folders that do not yet
		exist.
		@param mode: creation mode (e.g. 0700)
		'''
		if self.exists():
			# Additional check needed because makedirs can not handle
			# a path like "E:\" on windows (while "E:\foo" works fine)
			return

		try:
			if mode is not None:
				os.makedirs(self.encodedpath, mode=mode)
			else:
				os.makedirs(self.encodedpath)
		except OSError, e:
			if e.errno != errno.EEXIST:
				raise

	def remove(self):
		'''Remove this folder, fails if it is not empty.'''
		logger.info('Remove dir: %s', self)
		lrmdir(self.encodedpath)

	def cleanup(self):
		'''Remove this foldder and any empty parent folders. If the
		folder does not exist, still check for empty parent folders.
		Fails silently if the folder is not empty.
		@returns: C{True} when succesful (so C{False} means it still exists).
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
		'''Recursively remove everything below this folder .

		B{WARNING:} This is quite powerful and can do a lot of damage
		when executed for the wrong folder, so pleae make sure to double
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

	def copyto(self, dest):
		'''Recursively copy the contents of this folder.
		When the destination folder already exists the contents will be
		merged, so you need to check existence of the destination first
		if you want a clean new copy.
		@param dest: a L{Dir} object
		'''
		# We do not use shutil.copytree() because it requires that
		# the target dir does not exist
		assert isinstance(dest, Dir)
		assert not dest == self, 'BUG: trying to copy a dir to itself'
		logger.info('Copy dir %s to %s', self, dest)

		def copy_dir(source, target):
			target.touch()
			for item in source.list():
				child = FilePath((source, item))
				if child.isdir():
					copy_dir(Dir(child), target.subdir(item)) # recur
				else:
					child = File(child)
					child.copyto(target)

		copy_dir(self, dest)
		# TODO - not hooked with FS signals

	def file(self, path):
		'''Get a L{File} object for a path below this folder

		@param path: a (relative) file path as string, tuple or
		L{FilePath} object. When C{path} is a L{File} object already
		this method still enforces it is below this folder.
		So this method can be used as check as well.

		@returns: a L{File} object
		@raises PathLookupError: if the path is not below this folder
		'''
		file = self.resolve_file(path)
		if not file.path.startswith(self.path):
			raise PathLookupError, '%s is not below %s' % (file, self)
		return file

	def resolve_file(self, path):
		'''Get a L{File} object for a path relative to this folder

		Like L{file()} but allows the path to start with "../" as
		well, so can handle any relative path.

		@param path: a (relative) file path as string, tuple or
		L{FilePath} object.
		@returns: a L{File} object
		'''
		assert isinstance(path, (FilePath, basestring, list, tuple))
		if isinstance(path, basestring):
			return File((self.path, path))
		elif isinstance(path, (list, tuple)):
			return File((self.path,) + tuple(path))
		elif isinstance(path, File):
			return path
		elif isinstance(path, FilePath):
			return File(path.path)

	def new_file(self, path):
		'''Get a L{File} object for a new file below this folder.
		Like L{file()} but guarantees the file does not yet exist by
		adding sequential numbers if needed. So the resulting file
		may have a modified name.

		@param path: a (relative) file path as string, tuple or
		L{FilePath} object.

		@returns: a L{File} object
		@raises PathLookupError: if the path is not below this folder
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
		'''Get a L{Dir} object for a path below this folder

		@param path: a (relative) file path as string, tuple or
		L{FilePath} object. When C{path} is a L{Dir} object already
		this method still enforces it is below this folder.
		So this method can be used as check as well.

		@returns: a L{Dir} object
		@raises PathLookupError: if the path is not below this folder

		'''

		dir = self.resolve_dir(path)
		if not dir.path.startswith(self.path):
			raise PathLookupError, '%s is not below %s' % (dir, self)
		return dir

	def resolve_dir(self, path):
		'''Get a L{Dir} object for a path relative to this folder

		Like L{subdir()} but allows the path to start with "../" as
		well, so can handle any relative path.

		@param path: a (relative) file path as string, tuple or
		L{FilePath} object.
		@returns: a L{Dir} object
		'''
		assert isinstance(path, (FilePath, basestring, list, tuple))
		if isinstance(path, basestring):
			return Dir((self.path, path))
		elif isinstance(path, (list, tuple)):
			return Dir((self.path,) + tuple(path))
		elif isinstance(path, Dir):
			return path
		elif isinstance(path, FilePath):
			return Dir(path.path)

	def new_subdir(self, path):
		'''Get a L{Dir} object for a new sub-folder below this folder.
		Like L{subdir()} but guarantees the folder does not yet exist by
		adding sequential numbers if needed. So the resulting folder
		may have a modified name.

		@param path: a (relative) file path as string, tuple or
		L{FilePath} object.

		@returns: a L{Dir} object
		@raises PathLookupError: if the path is not below this folder
		'''
		subdir = self.subdir(path)
		basename = subdir.basename
		i = 0
		while subdir.exists():
			logger.debug('Dir exists "%s" trying increment', subdir)
			i += 1
			newname = basename + '%03i' % i
			subdir = self.subdir(newname)
		return subdir


def _glob_to_regex(glob):
	glob = glob.replace('.', '\\.')
	glob = glob.replace('*', '.*')
	glob = glob.replace('?', '.?')
	return re.compile(glob)


class FilteredDir(Dir):
	'''Class implementing a folder with a filtered listing. Can be
	used to e.g. filter all objects that are also ignored by version
	control.
	'''

	def __init__(self, path):
		'''Constructor

		@param path: an absolute file path, file URL, L{FilePath} object
		or a list of path elements. When a list is given, the first
		element is allowed to be an absolute path, URL or L{FilePath}
		object as well.
		'''
		Dir.__init__(self, path)
		self._ignore = []

	def ignore(self, glob):
		'''Add a file pattern to ignore
		@param glob: a file path pattern (e.g. "*.txt")
		'''
		regex = _glob_to_regex(glob)
		self._ignore.append(regex)

	def filter(self, name):
		for regex in self._ignore:
			if regex.match(name):
				return False
		else:
			return True

	def list(self, includehidden=False, includetmp=False, raw=False):
		files = Dir.list(self, includehidden, includetmp)
		if not raw:
			files = filter(self.filter, files)
		return files


class UnixFile(FilePath):
	'''Class representing a single file.

	This class implements much more complex logic than the default
	python file objects. E.g. on writing we first write to a temporary
	files, then flush and sync and finally replace the file we intended
	to write with the temporary file. This makes it much more difficult
	to loose file contents when something goes wrong during the writing.

	Also it implements logic to check the modification time before
	writing to prevent overwriting a file that was changed on disk in
	between read and write operations. If this mtime check fails MD5
	sums are used to verify before raising an exception (because some
	share drives do not maintain mtime very precisely). However this
	check only works when using L{read()}, L{readlines()}, L{write()}
	or L{writelines()}, but not when calling L{open()} directly.
	Also this logic is not atomic, so your mileage may vary.
	'''

	# For atomic write we first write a tmp file which has the extension
	# .zim-new~ when is was written successfully we replace the actual file
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
		'''Constructor

		@param path: an absolute file path, file URL, L{FilePath} object
		or a list of path elements. When a list is given, the first
		element is allowed to be an absolute path, URL or L{FilePath}
		object as well.

		@param checkoverwrite: when C{True} this object checks the
		modification time before writing to prevent overwriting a file
		that was changed on disk in between read and write operations.

		@param endofline: the line end style used when writing, can be
		one of "unix" ('\\n') or "dos" ('\\r\\n'). Whan C{None} the local
		default is used.
		'''
		FilePath.__init__(self, path)
		self.checkoverwrite = checkoverwrite
		self.endofline = endofline
		self._mtime = None
		self._md5 = None
		self._lock = FS.get_async_lock(self)

	def __getstate__(self):
		# Copy the object's state from self.__dict__
		# But remove the unpicklable entries.
		state = self.__dict__.copy()
		del state['_lock']
		return state

	def __setstate__(self, state):
		# Restore instance attributes
		self.__dict__.update(state)
		self._lock = FS.get_async_lock(self)

	def __eq__(self, other):
		if isinstance(other, File):
			return self.path == other.path
		else:
			return False

	def exists(self):
		return os.path.isfile(self.encodedpath)

	def isimage(self):
		'''Check if this is an image file. Convenience method that
		works even when no real mime-type suport is available.
		If this method returns C{True} it is no guarantee
		this image type is actually supported by gtk.
		@returns: C{True} when this is an image file
		'''

		# Quick shortcut to be able to load images in the gui even if
		# we have no proper mimetype support
		if '.' in self.basename:
			_, ext = self.basename.rsplit('.', 1)
			if ext in IMAGE_EXTENSIONS:
				return True

		return self.get_mimetype().startswith('image/')

	def get_mimetype(self):
		'''Get the mime-type for this file.
		Will use the XDG mimetype system if available, otherwise
		fallsback to the standard library C{mimetypes}.
		@returns: the mimetype as a string, e.g. "text/plain"
		'''
		if xdgmime:
			mimetype = xdgmime.get_type(self.path, name_pri=80)
			return str(mimetype)
		else:
			mimetype, encoding = mimetypes.guess_type(self.path, strict=False)
			if encoding == 'gzip': return 'application/x-gzip'
			elif encoding == 'bzip': return 'application/x-bzip'
			elif encoding == 'compress': return 'application/x-compress'
			else: return mimetype or 'application/octet-stream'

	def get_endofline(self):
		'''Get the end-of-line character(s) used for writing this file.
		@returns: the end-of-line character(s)
		'''
		if self.endofline is None:
			if isinstance(self, WindowsPath): return '\r\n'
			else: return '\n'
		else:
			assert self.endofline in ('unix', 'dos')
			if self.endofline == 'dos': return '\r\n'
			else: return '\n'

	def open(self, mode='r'):
		'''Open an IO object for reading or writing. The stream will
		automatically by encoded or decoded for UTF-8.
		Opening a non-existing file for writing will cause the whole path
		to this file to be created on the fly.

		@param mode: the open mode, either 'r' or 'w' (other modes
		are not supported)

		@returns: a file object
		'''
		# When we open for writing, we actually open the tmp file
		# and return a FileHandle object that will call _on_write()
		# when it is closed. This handler will take care of replacing
		# the actual file with the newly written tmp file.
		assert mode in ('r', 'w')
		if mode == 'w':
			if not self.iswritable():
				raise FileWriteError, _('File is not writable: %s') % self.path # T: Error message
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
		# Handler executed after successful writing the .zim-new~ tmp file
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
		'''Get the raw content without UTF-8 decoding, newline logic,
		etc. Used to read binary data, e.g. when serving files over www.
		Note that this function also does not integrates with checking
		mtime, so intended for read only usage.
		@returns: file content as string
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
		'''Get the file contents as a string. Takes case of decoding
		UTF-8 and fixes line endings.
		@returns: the content as (unicode) string.
		@raises FileNotFoundError: when the file does not exist.
		'''
		with self._lock:
			try:
				file = self.open('r')
				content = file.read()
				self._checkoverwrite(content)
				return content.lstrip(u'\ufeff').replace('\r', '').replace('\x00', '')
					# Strip unicode byte order mark
					# Internally we use Unix line ends - so strip out \r
					# And remove any NULL byte since they screw up parsing
			except IOError:
				raise FileNotFoundError(self)
			except UnicodeDecodeError, error:
				raise FileUnicodeError(self, error)

		return text

	def readlines(self):
		'''Get the file contents as a list of lines. Takes case of
		decoding UTF-8 and fixes line endings.

		@returns: the content as a list of lines.
		@raises FileNotFoundError: when the file does not exist.
		'''
		with self._lock:
			try:
				file = self.open('r')
				lines = file.readlines()
				self._checkoverwrite(lines)
				return [line.lstrip(u'\ufeff').replace('\r', '').replace('\x00', '') for line in lines]
					# Strip unicode byte order mark
					# Internally we use Unix line ends - so strip out \r
					# And remove any NULL byte since they screw up parsing
			except IOError:
				raise FileNotFoundError(self)
			except UnicodeDecodeError, error:
				raise FileUnicodeError(self, error)

		return lines

	def write(self, text):
		'''Write file contents from string. This overwrites the current
		content. Will automatically create all parent folders.
		If writing fails the file will either have the new content or the
		old content, but it should not be possible to have the content
		truncated.
		@param text: new content as (unicode) string
		@emits: path-created if the file did not yet exist
		'''
		with self._lock:
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

		self._check_isnew()

	def _check_isnew(self):
		# Make sure the 'path-created' signal is emitted in the main
		# thread, so do not put this in _write(), but call from write()
		# or from async callback.
		# Also make sur this is called after lock is released to prevent
		# deadlock when event handler tries to access the file.
		if self._isnew:
			FS.emit('path-created', self)

	def writelines(self, lines):
		'''Write file contents from a list of lines.
		Like L{write()} but input is a list instead of a string.
		@param lines: new content as list of lines
		@emits: path-created if the file did not yet exist
		'''
		with self._lock:
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

		self._check_isnew()

	def _checkoverwrite(self, content):
		# Set properties needed by assertoverwrite for the in-memory object
		if self.checkoverwrite:
			self._mtime = self.mtime()
			self._md5 = _md5(content)

	def _assertoverwrite(self):
		# When we read a file and than write it, this method asserts the file
		# did not change in between (e.g. by another process, or another async
		# function of our own process). We use properties of this object instance
		# We check the timestamp, if that does not match we check md5 to be sure.
		# (Sometimes e.g. network filesystems do not maintain timestamps as strict
		# as we would like.)
		#
		# This function should not prohibit writing without reading first.
		# Also we just write the file if it went missing in between
		if self._mtime and self._md5:
			try:
				mtime = self.mtime()
			except OSError:
				if not os.path.isfile(self.encodedpath):
					logger.critical('File missing: %s', self.path)
					return
				else:
					raise

			if not self._mtime == mtime:
				logger.warn('mtime check failed for %s, trying md5', self.path)
				if self._md5 != _md5(self.open('r').read()):
					raise FileWriteError, _('File changed on disk: %s') % self.path
						# T: error message
					# Why are we using MD5 here ?? could just compare content...

	def check_has_changed_on_disk(self):
		'''Returns C{True} when this file has changed on disk'''
		if not (self._mtime and self._md5):
			if os.path.isfile(self.encodedpath):
				return True # may well been just created
			else:
				return False # ??
		elif not os.path.isfile(self.encodedpath):
			return True
		else:
			try:
				self._assertoverwrite()
			except FileWriteError:
				return True
			else:
				return False

	def touch(self):
		'''Create this file and any parent folders if it does not yet
		exist. (Parent folders are also created when writing to a file,
		so you only need to call this method in special cases - e.g.
		when an external program requires the file to exist.)
		'''
		if self.exists():
			return
		else:
			with self._lock:
				io = self.open('w')
				io.write('')
				io.close()

	def remove(self):
		'''Remove (delete) this file and cleanup any related temporary
		files we created. This action can not be un-done.
		Ignores silently if the file did not exist in the first place.
		'''
		logger.info('Remove file: %s', self)
		with self._lock:
			if os.path.isfile(self.encodedpath):
				os.remove(self.encodedpath)

			tmp = self.encodedpath + '.zim-new~'
			if os.path.isfile(tmp):
				os.remove(tmp)

	def cleanup(self):
		'''Remove this file and cleanup any empty parent folder.
		Convenience method calling L{File.remove()} and L{Dir.cleanup()}.
		'''
		self.remove()
		self.dir.cleanup()

	def copyto(self, dest):
		'''Copy this file to another location. Preserves all file
		attributes (by using C{shutil.copy2()})
		@param dest: a L{File} or L{Dir} object for the destination. If the
		destination is a folder, we will copy to a file below that
		folder of the same name
		'''
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
		shutil.copy2(self.encodedpath, dest.encodedpath)
		# TODO - not hooked with FS signals

	def compare(self, other):
		'''Check if file contents are the same. This differs from
		L{isequal()} because files can be different physical locations.
		@param other: another L{File} object
		@returns: C{True} when the files have the same content
		'''
		# TODO: can be more efficient, e.g. by checking stat size first
		# also wonder if MD5 is needed here ... could just compare text
		return _md5(self.read()) == _md5(other.read())


class WindowsFile(UnixFile):
	'''Class representing a single file on windows. See L{UnixFile}
	for API documentation.
	'''

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
		orig = self.encodedpath + '.zim-orig~'
		new = self.encodedpath + '.zim-new~'
		return os.path.isfile(self.encodedpath) or \
			(os.path.isfile(new) and os.path.isfile(orig))
			# if both new and orig exists, we can recover

	def open(self, mode='r'):
		self._recover() # just to be sure
		return UnixFile.open(self, mode)

	def _on_write(self):
		# Handler executed after successful writing the .zim-new~ tmp file
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
	and supports a callback. Used by L{File.open()}.
	'''

	def __init__(self, path, on_close=None, **opts):
		file.__init__(self, path, **opts)
		self.on_close = on_close

	def close(self):
		self.flush()
		os.fsync(self.fileno())
		file.close(self)
		if not self.on_close is None:
			self.on_close()

