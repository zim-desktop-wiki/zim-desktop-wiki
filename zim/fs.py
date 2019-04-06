
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

import os
import re
import sys
import shutil
import errno
import logging


from zim.errors import Error
from zim.parsing import url_encode, url_decode, URL_ENCODE_READABLE
from zim.signals import SignalEmitter, SIGNAL_AFTER

logger = logging.getLogger('zim.fs')


from zim.newfs.base import _os_expanduser, SEP
from zim.newfs.local import AtomicWriteContext


def adapt_from_newfs(file):
	from zim.newfs import LocalFile, LocalFolder

	if isinstance(file, LocalFile):
		return File(file.path)
	elif isinstance(file, LocalFolder):
		return Dir(file.path)
	else:
		return file


try:
	from gi.repository import Gio
except ImportError:
	Gio = None

if not Gio:
	logger.info('No file monitor support - changes will go undetected')


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


def isabs(path):
	'''Wrapper for C{os.path.isabs}.
	@param path: a file system path as string
	@returns: C{True} when the path is absolute instead of a relative path
	'''
	return path.startswith('file:/') \
	or path.startswith('~') \
	or os.path.isabs(path)


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
	root = tempfile.gettempdir()
	user = url_encode(os.environ['USER'], URL_ENCODE_READABLE)
	dir = Dir((root, 'zim-%s' % user))

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
	if isinstance(content, str):
		m.update(content.encode('UTF-8'))
	else:
		for l in content:
			m.update(l.encode('UTF-8'))
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
		self.description += '\n\n' + _('Details') + ':\n' + str(error)
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
	__signals__ = {
		'path-created': (SIGNAL_AFTER, None, (object,)),
		'path-moved': (SIGNAL_AFTER, None, (object, object)),
		'path-deleted': (SIGNAL_AFTER, None, (object,)),
	}


#: Singleton object for the system filesystem - see L{FSSingletonClass}
FS = FSSingletonClass()


class UnixPath(object):
	'''Base class for Dir and File objects, represents a file path

	@ivar path: the absolute file path as string
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
			return

		try:
			if isinstance(path, (list, tuple)):
				path = list(map(str, path))
					# Flatten objects - strings should be unicode or ascii already
				path = SEP.join(path)
					# os.path.join is too intelligent for it's own good
					# just join with the path separator.
			else:
				path = str(path) # make sure we can decode
		except UnicodeDecodeError:
			raise Error('BUG: invalid input, file names should be in ascii, or given as unicode')

		if path.startswith('file:/'):
			path = self._parse_uri(path)
		elif path.startswith('~'):
			path = _os_expanduser(path)

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
		if uri.startswith('file:///'):
			uri = uri[7:]
		elif uri.startswith('file://localhost/'):
			uri = uri[16:]
		elif uri.startswith('file://'):
			assert False, 'Can not handle non-local file uris'
		elif uri.startswith('file:/'):
			uri = uri[5:]
		else:
			assert False, 'Not a file uri: %s' % uri
		return url_decode(uri)

	def _set_path(self, path):
		self.path = os.path.abspath(path)

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

	def monitor(self):
		'''Creates a L{FSObjectMonitor} for this path'''
		return FSObjectMonitor(self)

	def exists(self):
		'''Check if a file or folder exists.
		@returns: C{True} if the file or folder exists
		@implementation: must be implemented by sub classes in order
		that they enforce the type of the resource as well
		'''
		return os.path.exists(self.path)

	def iswritable(self):
		'''Check if a file or folder is writable. Uses permissions of
		parent folder if the file or folder does not (yet) exist.
		@returns: C{True} if the file or folder is writable
		'''
		if self.exists():
			return os.access(self.path, os.W_OK)
		else:
			return self.dir.iswritable() # recurs

	def mtime(self):
		'''Get the modification time of the file path.
		@returns: the mtime timestamp
		'''
		return os.stat(self.path).st_mtime

	def ctime(self):
		'''Get the creation time of the file path.
		@returns: the mtime timestamp
		'''
		return os.stat(self.path).st_ctime

	def size(self):
		'''Get file size in bytes
		See L{format_file_size()} to get a human readable label
		@returns: file size in bytes
		'''
		return os.stat(self.path).st_size

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
			stat_result = os.stat(self.path)
			other_stat_result = os.stat(other.path)
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
		parts[0] = drive + SEP + parts[0]
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
		sep = SEP # '/' or '\'
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
				raise AssertionError('Not a parent folder')
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
		path = path.replace(os.path.sep, SEP) # msys can have '/' as seperator
		i = path.rfind(SEP) # win32 save...
		if i >= 0:
			return Dir(path[:i + 1])
		else:
			# different drive ?
			return None

	def ischild(self, parent):
		'''Check if this path is a child path of a folder
		@returns: C{True} if this path is a child path of C{parent}
		'''
		return self.path.startswith(parent.path + SEP)

	def isdir(self):
		'''Check if this path is a folder or not. Used to detect if
		e.g. a L{File} object should have really been a L{Dir} object.
		@returns: C{True} when this path is a folder
		'''
		return os.path.isdir(self.path)

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
		newpath = adapt_from_newfs(newpath)
		if self.path == newpath.path:
			raise AssertionError('Renaming %s to itself !?' % self.path)

		if newpath.isdir():
			if self.isequal(newpath):
				# We checked name above, so must be case insensitive file system
				# but we still want to be able to rename to other case, so need to
				# do some moving around
				tmpdir = self.dir.new_subdir(self.basename)
				shutil.move(self.path, tmpdir.path)
				shutil.move(tmpdir.path, newpath.path)
			else:
				# Needed because shutil.move() has different behavior for this case
				raise AssertionError('Folder already exists: %s' % newpath.path)
		else:
			# normal case
			newpath.dir.touch()
			shutil.move(self.path, newpath.path)

		FS.emit('path-moved', self, newpath)
		self.dir.cleanup()


class WindowsPath(UnixPath):
	'''Base class for Dir and File objects, represents a file path
	on windows.
	'''

	def _set_path(self, path):
		# Strip leading / for absolute paths
		if re.match(r'^[/\\]+[A-Za-z]:[/\\]', path):
			path = path.lstrip('/').lstrip('\\')
		self.path = os.path.abspath(path).replace('/', SEP) # msys can use '/' instead of '\\'

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
		return os.path.isdir(self.path)

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
		files = self._list(includehidden, includetmp)

		if glob:
			expr = _glob_to_regex(glob)
			files = list(filter(expr.match, files))

		files.sort()
		return files

	def _list(self, includehidden, includetmp):
		if self.exists():
			files = []
			for file in os.listdir(self.path):
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
			path = self.path + SEP + name
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
				os.makedirs(self.path, mode=mode)
			else:
				os.makedirs(self.path)
		except OSError as e:
			if e.errno != errno.EEXIST:
				raise

	def remove(self):
		'''Remove this folder, fails if it is not empty.'''
		logger.info('Remove dir: %s', self)
		lrmdir(self.path)
		FS.emit('path-deleted', self)

	def cleanup(self):
		'''Remove this foldder and any empty parent folders. If the
		folder does not exist, still check for empty parent folders.
		Fails silently if the folder is not empty.
		@returns: C{True} when successfull (so C{False} means it still exists).
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
		'''Recursively remove everything below this folder .

		B{WARNING:} This is quite powerful and can do a lot of damage
		when executed for the wrong folder, so pleae make sure to double
		check the dir is actually what you think it is before calling this.
		'''
		assert self.path and self.path != '/'
		logger.info('Remove file tree: %s', self)
		for root, dirs, files in os.walk(self.path, topdown=False):
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
			raise PathLookupError('%s is not below %s' % (file, self))
		return file

	def resolve_file(self, path):
		'''Get a L{File} object for a path relative to this folder

		Like L{file()} but allows the path to start with "../" as
		well, so can handle any relative path.

		@param path: a (relative) file path as string, tuple or
		L{FilePath} object.
		@returns: a L{File} object
		'''
		assert isinstance(path, (FilePath, str, list, tuple))
		if isinstance(path, str):
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
			raise PathLookupError('%s is not below %s' % (dir, self))
		return dir

	def resolve_dir(self, path):
		'''Get a L{Dir} object for a path relative to this folder

		Like L{subdir()} but allows the path to start with "../" as
		well, so can handle any relative path.

		@param path: a (relative) file path as string, tuple or
		L{FilePath} object.
		@returns: a L{Dir} object
		'''
		assert isinstance(path, (FilePath, str, list, tuple))
		if isinstance(path, str):
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
			files = list(filter(self.filter, files))
		return files


class File(FilePath):
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
	share drives do not maintain mtime very precisely).
	This logic is not atomic, so your mileage may vary.
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

	def __eq__(self, other):
		if isinstance(other, File):
			return self.path == other.path
		else:
			return False

	def exists(self):
		return os.path.isfile(self.path)

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
			if encoding == 'gzip':
				return 'application/x-gzip'
			elif encoding == 'bzip':
				return 'application/x-bzip'
			elif encoding == 'compress':
				return 'application/x-compress'
			else:
				return mimetype or 'application/octet-stream'

	def get_endofline(self):
		'''Get the end-of-line character(s) used for writing this file.
		@returns: the end-of-line character(s)
		'''
		if self.endofline is None:
			if isinstance(self, WindowsPath):
				return '\r\n'
			else:
				return '\n'
		else:
			assert self.endofline in ('unix', 'dos')
			if self.endofline == 'dos':
				return '\r\n'
			else:
				return '\n'

	def raw(self):
		'''Get the raw content without UTF-8 decoding, newline logic,
		etc. Used to read binary data, e.g. when serving files over www.
		Note that this function also does not integrates with checking
		mtime, so intended for read only usage.
		@returns: file content as string
		'''
		try:
			fh = open(self.path, mode='rb')
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
		try:
			content = self._read()
			self._checkoverwrite(content)
			return content.lstrip('\ufeff').replace('\x00', '')
				# Strip unicode byte order mark
				# And remove any NULL byte since they screw up parsing
		except IOError:
			raise FileNotFoundError(self)
		except UnicodeDecodeError as error:
			raise FileUnicodeError(self, error)

		return text

	def _read(self):
		with open(self.path, encoding='UTF-8') as fh:
			return fh.read()

	def readlines(self):
		'''Get the file contents as a list of lines. Takes case of
		decoding UTF-8 and fixes line endings.

		@returns: the content as a list of lines.
		@raises FileNotFoundError: when the file does not exist.
		'''
		try:
			file = open(self.path, encoding='UTF-8')
			lines = file.readlines()
			self._checkoverwrite(lines)
			return [line.lstrip('\ufeff').replace('\x00', '') for line in lines]
				# Strip unicode byte order mark
				# And remove any NULL byte since they screw up parsing
		except IOError:
			raise FileNotFoundError(self)
		except UnicodeDecodeError as error:
			raise FileUnicodeError(self, error)

		return lines

	def _write_check(self):
		if not self.iswritable():
			raise FileWriteError(_('File is not writable: %s') % self.path) # T: Error message
		elif not self.exists():
			self.dir.touch()
		else:
			pass # exists and writable

	def write(self, text):
		'''Write file contents from string. This overwrites the current
		content. Will automatically create all parent folders.
		If writing fails the file will either have the new content or the
		old content, but it should not be possible to have the content
		truncated.
		@param text: new content as (unicode) string
		@emits: path-created if the file did not yet exist
		'''
		self._assertoverwrite()
		isnew = not os.path.isfile(self.path)
		newline = self.get_endofline()
		self._write_check()
		with AtomicWriteContext(self, newline=newline) as fh:
			fh.write(text)

		self._checkoverwrite(text)
		if isnew:
			FS.emit('path-created', self)

	def writelines(self, lines):
		'''Write file contents from a list of lines.
		Like L{write()} but input is a list instead of a string.
		@param lines: new content as list of lines
		@emits: path-created if the file did not yet exist
		'''
		self._assertoverwrite()
		isnew = not os.path.isfile(self.path)
		newline = self.get_endofline()
		self._write_check()
		with AtomicWriteContext(self, newline=newline) as fh:
			fh.writelines(lines)

		self._checkoverwrite(lines)
		if isnew:
			FS.emit('path-created', self)

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
				if not os.path.isfile(self.path):
					logger.critical('File missing: %s', self.path)
					return
				else:
					raise

			if not self._mtime == mtime:
				logger.warn('mtime check failed for %s, trying md5', self.path)
				if self._md5 != _md5(self._read()):
					raise FileWriteError(_('File changed on disk: %s') % self.path)
						# T: error message
					# Why are we using MD5 here ?? could just compare content...

	def check_has_changed_on_disk(self):
		'''Returns C{True} when this file has changed on disk'''
		if not (self._mtime and self._md5):
			if os.path.isfile(self.path):
				return True # may well been just created
			else:
				return False # ??
		elif not os.path.isfile(self.path):
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
			self.write('')

	def remove(self):
		'''Remove (delete) this file and cleanup any related temporary
		files we created. This action can not be un-done.
		Ignores silently if the file did not exist in the first place.
		'''
		logger.info('Remove file: %s', self)
		if os.path.isfile(self.path):
			os.remove(self.path)

		tmp = self.path + '.zim-new~'
		if os.path.isfile(tmp):
			os.remove(tmp)

		FS.emit('path-deleted', self)

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
		dest = adapt_from_newfs(dest)
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
		shutil.copy2(self.path, dest.path)
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


### TODO filter Dir.list directly for hidden files
if os.name != 'nt':
	def is_hidden_file(file):
			return file.basename.startswith('.')

else:
	import ctypes

	def is_hidden_file(file):
		INVALID_FILE_ATTRIBUTES = -1
		FILE_ATTRIBUTE_HIDDEN = 2

		try:
			attrs = ctypes.windll.kernel32.GetFileAttributesW(file.path)
				# note: GetFileAttributesW is unicode version of GetFileAttributes
		except AttributeError:
			return False
		else:
			if attrs == INVALID_FILE_ATTRIBUTES:
				return False
			else:
				return bool(attrs & FILE_ATTRIBUTE_HIDDEN)
###


class FSObjectMonitor(SignalEmitter):

	__signals__ = {
		'changed': (None, None, (None, None)),
	}

	def __init__(self, path):
		self.path = path
		self._gio_file_monitor = None

	def _setup_signal(self, signal):
		if signal == 'changed' \
		and self._gio_file_monitor is None \
		and Gio:
			try:
				file = Gio.File.new_for_uri(self.path.uri)
				self._gio_file_monitor = file.monitor()
				self._gio_file_monitor.connect('changed', self._on_changed)
			except:
				logger.exception('Error while setting up file monitor')

	def _teardown_signal(self, signal):
		if signal == 'changed' \
		and self._gio_file_monitor:
			try:
				self._gio_file_monitor.cancel()
			except:
				logger.exception('Error while tearing down file monitor')
			finally:
				self._gio_file_monitor = None

	def _on_changed(self, filemonitor, file, other_file, event_type):
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

		#~ print('MONITOR:', self, event_type)
		if event_type in (
			Gio.FileMonitorEvent.CREATED,
			Gio.FileMonitorEvent.CHANGES_DONE_HINT,
			Gio.FileMonitorEvent.DELETED,
			Gio.FileMonitorEvent.MOVED,
		):
			self.emit('changed', None, None) # TODO translate otherfile and eventtype
