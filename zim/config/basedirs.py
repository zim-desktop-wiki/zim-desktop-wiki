# -*- coding: utf-8 -*-

# Copyright 2009-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module defines the search path for zim config files following
the freedesktop.org (XDG) Base Dir specification.
'''

import os
import logging

from zim.fs import File, Dir
from zim.environ import environ


logger = logging.getLogger('zim.config')



## Initialize config paths

ZIM_DATA_DIR = None #: 'data' dir relative to script file (when running from source), L{Dir} or C{None}
XDG_DATA_HOME = None #: L{Dir} for XDG data home
XDG_DATA_DIRS = None #: list of L{Dir} objects for XDG data dirs path
XDG_CONFIG_HOME = None #: L{Dir} for XDG config home
XDG_CONFIG_DIRS = None #: list of L{Dir} objects for XDG config dirs path
XDG_CACHE_HOME = None #: L{Dir} for XDG cache home

def set_basedirs():
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
	zim_data_dir = File(zim.ZIM_EXECUTABLE).dir.subdir('data')
	if zim_data_dir.exists():
		ZIM_DATA_DIR = zim_data_dir

	if os.name == 'nt':
		APPDATA = environ['APPDATA']

		XDG_DATA_HOME = Dir(
			environ.get('XDG_DATA_HOME', APPDATA + r'\zim\data'))

		XDG_DATA_DIRS = map(Dir,
			environ.get_list('XDG_DATA_DIRS', '~/.local/share/')) # Backwards compatibility

		XDG_CONFIG_HOME = Dir(
			environ.get('XDG_CONFIG_HOME', APPDATA + r'\zim\config'))

		XDG_CONFIG_DIRS = map(Dir,
			environ.get_list('XDG_CONFIG_DIRS', '~/.config/')) # Backwards compatibility

		try:
			import _winreg as wreg
			wreg_key = wreg.OpenKey(
				wreg.HKEY_CURRENT_USER,
				r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders')
			cache_dir = str(wreg.QueryValueEx(wreg_key, "Cache")[0].replace(u'%USERPROFILE%', environ['USERPROFILE']))
			wreg.CloseKey(wreg_key)
		except:
			cache_dir = APPDATA + r'\zim\cache'
			# Not using TMP here because it is cleaned too often

		XDG_CACHE_HOME = Dir(
			environ.get('XDG_CACHE_HOME', cache_dir + r'\zim'))
	else:
		XDG_DATA_HOME = Dir(
			environ.get('XDG_DATA_HOME', '~/.local/share/'))

		XDG_DATA_DIRS = map(Dir,
			environ.get_list('XDG_DATA_DIRS', ('/usr/share/', '/usr/local/share/')))

		XDG_CONFIG_HOME = Dir(
			environ.get('XDG_CONFIG_HOME', '~/.config/'))

		XDG_CONFIG_DIRS = map(Dir,
			environ.get_list('XDG_CONFIG_DIRS', ('/etc/xdg/',)))

		XDG_CACHE_HOME = Dir(
			environ.get('XDG_CACHE_HOME', '~/.cache'))


# Call on module initialization to set defaults
set_basedirs()


def log_basedirs():
	'''Write the search paths used to the logger, used to generate
	debug output
	'''
	if ZIM_DATA_DIR:
		logger.debug('Running from a source dir: %s', ZIM_DATA_DIR.dir)
	else:
		logger.debug('Not running from a source dir')
	logger.debug('Set XDG_DATA_HOME to %s', XDG_DATA_HOME)
	logger.debug('Set XDG_DATA_DIRS to %s', XDG_DATA_DIRS)
	logger.debug('Set XDG_CONFIG_HOME to %s', XDG_CONFIG_HOME)
	logger.debug('Set XDG_CONFIG_DIRS to %s', XDG_CONFIG_DIRS)
	logger.debug('Set XDG_CACHE_HOME to %s', XDG_CACHE_HOME)

