
# Copyright 2015-2016 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Module which contains all classes to deal with the filesystem'''

import sys
import os
import logging

logger = logging.getLogger('zim.newfs')


FS_CASE_SENSITIVE = (os.name != 'nt') #: file system case-sensitive yes or no

FS_SUPPORT_NON_LOCAL_FILE_SHARES = (os.name == 'nt') #: Support \\host\share paths yes or no


from .base import *
from .base import SEP, _EOL, _HOME
from .local import *
from .helpers import *


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


# Key is that we always use objects to signal file vs folder,
# get rid of all uses of "isdir" because it shows a constructor issue.
# Instead use "folder.child(path)" to get either file or folder.
# Also no common FS object, just construct the parent folder first
#
# When instatiating you need to use specific LocalFolder or LocalFile
# this will alert you to the non-mockable nature of the code
#
# This also means that folder provide access to children, not parents
# if a object needs access to larger file system, a root folder
# should be passed as a requirement to the constructor; else you can
# not mock the function for testing.

# TODO
# - test on FAT file system - e.g. USB stick ?

# TODO - put in helper modules:
# - trash - optional, only support for local file - separate gui object
# - monitor with gio - separate gui object
# - thumbnailer - separate gui object

# TODO - don't do
# - lock for fs operations --> checkin / checkout mechanism in notebook, use notebook lock

# With respect to page interface:
# Page.source is used for:
# - StubLinker - export with links to real source
# - cusomt tools to get commandline arg
# - edit source command
# - versioncontrol & zeitgeist logger plugins
#   --> these are also only one interested in FS signals
# --> very limitted access needed

# Re checkin//checkout --> only needed for interface editing page
# implement by setting callbacks that can be called by the notebook
# before any operation.
# notebook.checkout(page, callback)
# notebook.checkin(page)
# notebook.update_checked_pages()
#   called automatically by most methods, call explicitly from export
#
# by calling all callbacks *before* any action we allow for error dialogs
# etc before modification - no surprises once running
# --> Make it a context manager lock to block checkout during operation etc.






def localFileOrFolder(path):
	'''Convenience method that resolves a local C{File} or C{Folder} object'''
	path = FilePath(path)
	try:
		return LocalFolder(path.dirname).child(path.basename)
	except FileNotFoundError:
		raise FileNotFoundError(path)


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
