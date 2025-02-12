
# Copyright 2015-2016 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Module which contains all classes to deal with the filesystem'''

import sys
import os
import logging

logger = logging.getLogger('zim.newfs')


FS_CASE_SENSITIVE = not (os.name == 'nt' or sys.platform == 'darwin') #: file system case-sensitive yes or no
	# Both windows and macOS have by default case in-sensitive file systems

FS_SUPPORT_NON_LOCAL_FILE_SHARES = (os.name == 'nt') #: Support \\host\share paths yes or no


from .base import *
from .base import SEP, _EOL, _HOME
from .local import *
from .helpers import *


# NOTE: key design principle in this module is that we never take relative
# paths implicitely. Relative paths should always be explicit with the
# reference path being provided as an object. One reason is that this makes
# the code more robust and secure by being explicit. Secondly it allows
# test cases without touching real files, which is in general faster.

# Functions
# - (relative) pathname manipulation - specifically for links
# - file/folder info - iswritable, mtime, ctime, exists
# - file info - mimetype, size, (thumbnail)
# - file access - read, write, touch, remove (clear)
# - folder access - list, touch, remove, file, folder, child
# - tree operations - move, copy
# - signal changes (internal) - specifically for version control
# - monitor changes (external) - specifically to pick up changes in open page

# OS dependent
# - pathname should support all variants, cross platform
# - path encoding for low level functions
# - atomic rename for writing

# Classes
# - FilePath - pathname manipulation
# - File - base class for files
# - Folder - base class for folders

# local file system:
# - LocalFSObjectBase - file / folder info
# - LocalFile - file info + file access + tree operations
# - LocalFolder - folder access + tree operation

# helpers:
# - FolderMask - wraps a Folder and exposes part of children, disables all but list()
# - FSObjectMonitor - monitor single file or folder for external changes
#	- ObjectMonitorFallback - at least report internal changes
# - FSTreeMonitor - monitor internal changes, passes itself as "logger" to children


def localFileOrFolder(path, pwd=None):
	'''Convenience method that resolves a local C{File} or C{Folder} object

	If the path is a string and ends with either "/" or "\\" it is interpreted
	as user input and a C{LocalFolder} object will be returned. Else the function
	will try to sort out whether the path is a file or a folder by checking on
	disk. This requires the object to exist.

	NOTE: for consistency, this function only returns objects for existing files
	or folders, else it raises C{FileNotFoundError}

	@param path: file path as a string, L{FilePath} object, or list of path elements
	@param pwd: working directory as a string, needed to allow relative paths
	'''
	if pwd:
		filepath = FilePath(pwd).get_abspath(path)
	else:
		filepath = FilePath(path)

	if isinstance(path, str) and path and path[-1] in ('/', '\\'):
		folder = LocalFolder(filepath)
		if folder.exists():
			return folder
		else:
			raise FileNotFoundError(filepath)
	else:
		try:
			return LocalFolder(filepath.dirname).child(filepath.basename)
		except:
			raise FileNotFoundError(filepath) # translate parent not found error


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
