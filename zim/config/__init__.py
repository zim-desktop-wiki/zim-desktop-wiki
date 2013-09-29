# -*- coding: utf-8 -*-

# Copyright 2009-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from .basedirs import *
from .dicts import *
from .manager import *




# FIXME - when XDG variables in basedirs.py change, they don't change
# in this module ...
# should they move to their own module ?

# TODO - decide which of these functions should be handled by the
# config manager. E.g. keep function for loading resources (icons,
# images, templates, ..) but load all config files through the manager


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


def config_dirs():
	'''Generator listing paths for zim config files. These will be the
	equivalent of e.g. "~/.config/zim", "/etc/xdg/zim" etc.

	Zim is not strictly XDG conformant by installing default config
	files in "/usr/share/zim" instead of in "/etc/xdg/zim". Therefore
	this function yields both.

	@returns: yields L{Dir} objects for all config and data dirs
	'''
	yield XDG_CONFIG_HOME.subdir(('zim'))
	for dir in XDG_CONFIG_DIRS:
		yield dir.subdir(('zim'))
	for dir in data_dirs():
		yield dir


#~ def config_file(path):
	#~ '''Alias for constructing a L{ConfigFile} object
	#~ @param path: either basename as string or tuple with relative path
	#~ @returns: a L{ConfigFile}
	#~ '''
	#~ return ConfigFile(path)


#~ def get_config(path):
	#~ '''Convenience method to construct a L{ConfigDictFile} based on a
	#~ C{ConfigFile}.
	#~ @param path: either basename as string or tuple with relative path
	#~ @returns: a L{ConfigDictFile}
	#~ '''
	#~ file = ConfigFile(path)
	#~ return ConfigDictFile(file)


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

