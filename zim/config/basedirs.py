
# Copyright 2009-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module defines the search path for zim config files following
the freedesktop.org (XDG) Base Dir specification.
'''

import os
import logging

from zim.newfs import LocalFile, LocalFolder


logger = logging.getLogger('zim.config')


def _split_environ_dir_list(value, default=()):
	value = value.strip() if isinstance(value, str) else value
	if value:
		paths = value.split(os.pathsep)
	else:
		paths = default
	return [LocalFolder(p) for p in paths]


## Initialize config paths

ZIM_DATA_DIR = None #: 'data' dir relative to script file (when running from source), L{LocalFolder} or C{None}
XDG_DATA_HOME = None #: L{LocalFolder} for XDG data home
XDG_DATA_DIRS = None #: list of L{LocalFolder} objects for XDG data dirs path
XDG_CONFIG_HOME = None #: L{LocalFolder} for XDG config home
XDG_CONFIG_DIRS = None #: list of L{LocalFolder} objects for XDG config dirs path
XDG_CACHE_HOME = None #: L{LocalFolder} for XDG cache home

def set_basedirs(_ignore_test=False):
	'''This method sets the global configuration paths for according to the
	freedesktop basedir specification.
	Called automatically when module is first loaded, should be
	called explicitly only when environment has changed.
	'''
	global ZIM_DATA_DIR
	global XDG_DATA_HOME
	global XDG_DATA_DIRS
	global XDG_CONFIG_HOME
	global XDG_CONFIG_DIRS
	global XDG_CACHE_HOME

	# Cast string to folder
	import zim
	zim_data_dir = LocalFile(zim.ZIM_EXECUTABLE).parent().folder('data')
	if zim_data_dir.exists():
		ZIM_DATA_DIR = zim_data_dir

	if os.name == 'nt':
		APPDATA = os.environ['APPDATA']

		XDG_DATA_HOME = LocalFolder(
			os.environ.get('XDG_DATA_HOME', APPDATA + r'\zim\data').strip())

		XDG_DATA_DIRS = \
			_split_environ_dir_list(os.environ.get('XDG_DATA_DIRS'), ('~/.local/share/',)) # Backwards compatibility

		XDG_CONFIG_HOME = LocalFolder(
			os.environ.get('XDG_CONFIG_HOME', APPDATA + r'\zim\config').strip())

		XDG_CONFIG_DIRS = \
			_split_environ_dir_list(os.environ.get('XDG_CONFIG_DIRS'), ('~/.config/',)) # Backwards compatibility

		XDG_CACHE_HOME = LocalFolder(
			os.environ.get('XDG_CACHE_HOME', APPDATA + r'\zim\cache').strip())
	else:
		XDG_DATA_HOME = LocalFolder(
			os.environ.get('XDG_DATA_HOME', '~/.local/share/').strip())

		XDG_DATA_DIRS = \
			_split_environ_dir_list(os.environ.get('XDG_DATA_DIRS'), ('/usr/share/', '/usr/local/share/'))

		XDG_CONFIG_HOME = LocalFolder(
			os.environ.get('XDG_CONFIG_HOME', '~/.config/').strip())

		XDG_CONFIG_DIRS = \
			_split_environ_dir_list(os.environ.get('XDG_CONFIG_DIRS'), ('/etc/xdg/',))

		XDG_CACHE_HOME = LocalFolder(
			os.environ.get('XDG_CACHE_HOME', '~/.cache').strip())

		if os.environ.get('ZIM_TEST_RUNNING') and not _ignore_test:
			# See tests/__init__.py, we load more folders then we really want
			# because the needs of Gtk, but want to restrict it here for all
			# zim internal use
			XDG_DATA_DIRS = [LocalFolder(os.environ['TEST_XDG_DATA_DIRS'])]

# Call on module initialization to set defaults
set_basedirs()


def log_basedirs():
	'''Write the search paths used to the logger, used to generate
	debug output
	'''
	if ZIM_DATA_DIR:
		logger.debug('Running from a source dir: %s', ZIM_DATA_DIR.parent())
	else:
		logger.debug('Not running from a source dir')
	logger.debug('Set XDG_DATA_HOME to %s', XDG_DATA_HOME)
	logger.debug('Set XDG_DATA_DIRS to %s', XDG_DATA_DIRS)
	logger.debug('Set XDG_CONFIG_HOME to %s', XDG_CONFIG_HOME)
	logger.debug('Set XDG_CONFIG_DIRS to %s', XDG_CONFIG_DIRS)
	logger.debug('Set XDG_CACHE_HOME to %s', XDG_CACHE_HOME)
