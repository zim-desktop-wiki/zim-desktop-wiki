# -*- coding: utf-8 -*-

# Copyright 2009-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from .basedirs import *
from .dicts import *
from .manager import *


'''This module defines all functions and objects related to the
application config.

The sub module L{zim.config.manager} contains that L{ConfigManager}
object, which is the main object to access configuration files. In
L{zim.config.dicts} a number of classes are defined that represent
configuration files as dictionaries. And classes to define the config
options that are used and how to validate those.

The file system paths where to search for config files are defined
in L{zim.config.basedirs}.
'''


# FIXME - when XDG variables in basedirs.py change, they don't change
# in this module ...
# should they move to their own module ?

# TODO: Define a ResourceManager for loading resources (icons,
# images, templates, ..)
# Singleton class
# Avoid using basedirs directly elsewhere in the code

# TODO: resources like icons etc can be managed by a Singleton ResourceManager



def data_dirs(path=None):
	'''Generator listing paths that contain zim data files in the order
	that they should be searched. These will be the equivalent of
	e.g. "~/.local/share/zim", "/usr/share/zim", etc.
	@param path: a file path relative to to the data dir, including this
	will list sub-folders with this relative path.
	@returns: yields L{Dir} objects for the data dirs
	'''
	zimpath = ['zim']
	if path:
		if isinstance(path, basestring):
			path = [path]
		assert not path[0] == 'zim'
		zimpath.extend(path)

	yield XDG_DATA_HOME.subdir(zimpath)

	if ZIM_DATA_DIR:
		if path:
			yield ZIM_DATA_DIR.subdir(path)
		else:
			yield ZIM_DATA_DIR

	for dir in XDG_DATA_DIRS:
		yield dir.subdir(zimpath)


def data_dir(path):
	'''Get an data dir sub-folder.  Will look up C{path} relative
	to all data dirs and return the first one that exists. Use this
	function to find any folders from the "data/" folder in the source
	package.
	@param path:  a file path relative to to the data dir
	@returns: a L{Dir} object or C{None}
	'''
	for dir in data_dirs(path):
		if dir.exists():
			return dir
	else:
		return None


def data_file(path):
	'''Get a data file. Will look up C{path} relative to all data dirs
	and return the first one that exists. Use this function to find
	any files from the "data/" folder in the source package.
	@param path:  a file path relative to to the data dir (e.g. "zim.png")
	@returns: a L{File} object or C{None}
	'''
	for dir in data_dirs():
		file = dir.file(path)
		if file.exists():
			return file
	else:
		return None


def user_dirs():
	'''Get the XDG user dirs.
	@returns: a dict with directories for the XDG user dirs. These are
	typically defined in "~/.config/user-dirs.dirs". Common user dirs
	are: "XDG_DESKTOP_DIR", "XDG_DOWNLOAD_DIR", etc. If no definition
	is found an empty dict will be returned.
	'''
	dirs = {}
	file = XDG_CONFIG_HOME.file('user-dirs.dirs')
	try:
		for line in file.readlines():
			line = line.strip()
			if line.isspace() or line.startswith('#'):
				continue
			else:
				try:
					assert '=' in line
					key, value = line.split('=', 1)
					value = os.path.expandvars(value.strip('"'))
					dirs[key] = Dir(value)
				except:
					logger.exception('Exception while parsing %s', file)
	except FileNotFoundError:
		pass
	return dirs

