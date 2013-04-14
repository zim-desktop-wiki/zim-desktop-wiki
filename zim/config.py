# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains utilities to work with config files.

Main classes for storing config items are L{ConfigDictFile} which maps
"ini-style" config files, and L{ListDict} which maintains a dict of
config keys while preserving their order.

The search path for zim config files follows the freedesktop.org (XDG)
Base Dir specification. The functions L{config_file()} and L{data_file()}
are used to locate config and data files, while the functions
L{config_dirs()}, L{data_dir()}, and L{data_dirs()} give access to the
actual search path.

When this module is loaded it will check the environment parameters in
C{os.environ} and try to set proper values for C{HOME} and C{USER} if
they are not set.
'''

import sys
import os
import re
import logging
import types

if sys.version_info >= (2, 6):
	import json # in standard lib since 2.6
else:
	import simplejson as json # extra dependency

from zim.fs import isfile, isdir, File, Dir, FileNotFoundError, ENCODING
from zim.errors import Error
from zim.parsing import TextBuffer, split_quoted_strings


logger = logging.getLogger('zim.config')


def get_environ(param, default=None):
	'''Get a parameter from the environment. Like C{os.environ.get()}
	but does decoding for non-ascii characters.
	@param param: the parameter to get
	@param default: the default if C{param} does not exist
	@returns: a unicode string or C{default}
	'''
	# Do NOT use zim.fs.decode here, we want real decoding on windows,
	# not just convert to unicode
	value = os.environ.get(param)
	if value is None:
		return default
	elif isinstance(value, str):
		return value.decode(ENCODING)
	else:
		return value


def get_environ_list(param, default=None, sep=None):
	'''Get a parameter from the environment and convert to a list.
	@param param: the parameter to get
	@param default: the default if C{param} does not exist
	@param sep: optional seperator, defaults to C{os.pathsep} if not given
	@returns: a list or the default
	'''
	value = get_environ(param, default)
	if isinstance(value, basestring) and value and not value.isspace():
		if sep is None:
			sep = os.pathsep
		return value.split(sep)
	elif isinstance(value, (list, tuple)):
		return value
	else:
		return []


def set_environ(param, value):
	'''Set a parameter in the environment. Like assigning in
	C{os.environ}, but with proper encoding.
	@param param: the parameter to set
	@param value: the value, should be a string
	'''
	if isinstance(value, unicode):
		value = value.encode(ENCODING)
	os.environ[param] = value


### Inialize environment - just to be sure

if os.name == 'nt':
	# Windows specific environment variables
	# os.environ does not support setdefault() ...
	if not 'USER' in os.environ or not os.environ['USER']:
		os.environ['USER'] = os.environ['USERNAME']

	if not 'HOME' in os.environ or not os.environ['HOME']:
		if 'USERPROFILE' in os.environ:
			os.environ['HOME'] = os.environ['USERPROFILE']
		elif 'HOMEDRIVE' in os.environ and 'HOMEPATH' in os.environ:
			home = os.environ['HOMEDRIVE'] + os.environ['HOMEPATH']
			os.environ['HOME'] = home

	if not 'APPDATA' in os.environ or not os.environ['APPDATA']:
		os.environ['APPDATA'] = os.environ['HOME'] + '\\Application Data'

assert isdir(get_environ('HOME')), \
	'ERROR: environment variable $HOME not set correctly'

if not 'USER' in os.environ or not os.environ['USER']:
	# E.g. Maemo doesn't define $USER
	os.environ['USER'] = os.path.basename(os.environ['HOME'])
	logger.info('Environment variable $USER was not set')



## Initialize config paths

ZIM_DATA_DIR = None #: 'data' dir relative to script file (when running from source), L{Dir} or C{None}
XDG_DATA_HOME = None #: L{Dir} for XDG data home
XDG_DATA_DIRS = None #: list of L{Dir} objects for XDG data dirs path
XDG_CONFIG_HOME = None #: L{Dir} for XDG config home
XDG_CONFIG_DIRS = None #: list of L{Dir} objects for XDG config dirs path
XDG_CACHE_HOME = None #: L{Dir} for XDG cache home

def _set_basedirs():
	'''This method sets the global configuration paths for according to the
	freedesktop basedir specification.
	'''
	global ZIM_DATA_DIR
	global XDG_DATA_HOME
	global XDG_DATA_DIRS
	global XDG_CONFIG_HOME
	global XDG_CONFIG_DIRS
	global XDG_CACHE_HOME

	# Detect if we are running from the source dir
	try:
		if isfile('./zim.py'):
			scriptdir = Dir('.') # maybe running module in test / debug
		else:
			encoding = sys.getfilesystemencoding() # not 100% sure this is correct
			path = sys.argv[0].decode(encoding)
			scriptdir = File(path).dir
		zim_data_dir = scriptdir.subdir('data')
		if zim_data_dir.exists():
			ZIM_DATA_DIR = zim_data_dir
		else:
			ZIM_DATA_DIR = None
	except:
		# Catch encoding errors in argv
		logger.exception('Exception locating application data')
		ZIM_DATA_DIR = None

	if os.name == 'nt':
		APPDATA = get_environ('APPDATA')

		XDG_DATA_HOME = Dir(
			get_environ('XDG_DATA_HOME', APPDATA + r'\zim\data'))

		XDG_DATA_DIRS = map(Dir,
			get_environ_list('XDG_DATA_DIRS', '~/.local/share/')) # Backwards compatibility

		XDG_CONFIG_HOME = Dir(
			get_environ('XDG_CONFIG_HOME', APPDATA + r'\zim\config'))

		XDG_CONFIG_DIRS = map(Dir,
			get_environ_list('XDG_CONFIG_DIRS', '~/.config/')) # Backwards compatibility

		try:
			import _winreg as wreg
			wreg_key = wreg.OpenKey(
				wreg.HKEY_CURRENT_USER,
				r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders')
			cache_dir = str(wreg.QueryValueEx(wreg_key, "Cache")[0].replace(u'%USERPROFILE%', get_environ['USERPROFILE']))
			wreg.CloseKey(wreg_key)
		except:
			cache_dir = os.environ['TEMP']

		XDG_CACHE_HOME = Dir(
			get_environ('XDG_CACHE_HOME', cache_dir + r'\zim'))
	else:
		XDG_DATA_HOME = Dir(
			get_environ('XDG_DATA_HOME', '~/.local/share/'))

		XDG_DATA_DIRS = map(Dir,
			get_environ_list('XDG_DATA_DIRS', ('/usr/share/', '/usr/local/share/')))

		XDG_CONFIG_HOME = Dir(
			get_environ('XDG_CONFIG_HOME', '~/.config/'))

		XDG_CONFIG_DIRS = map(Dir,
			get_environ_list('XDG_CONFIG_DIRS', ('/etc/xdg/',)))

		XDG_CACHE_HOME = Dir(
			get_environ('XDG_CACHE_HOME', '~/.cache'))


# Call on module initialization to set defaults
_set_basedirs()


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


def config_file(path):
	'''Alias for constructing a L{ConfigFile} object
	@param path: either basename as string or tuple with relative path
	@returns: a L{ConfigFile}
	'''
	return ConfigFile(path)


def get_config(path):
	'''Convenience method to construct a L{ConfigDictFile} based on a
	C{ConfigFile}.
	@param path: either basename as string or tuple with relative path
	@returns: a L{ConfigDictFile}
	'''
	file = ConfigFile(path)
	return ConfigDictFile(file)


def list_profiles():
	'''Returns a list known preferences profiles.'''
	profiles = []
	for dir in config_dirs():
		for f in dir.subdir('profiles').list():
			if f.endswith('.conf'):
				profiles.append(f[:-5])
	profiles.sort()
	return profiles


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


class ConfigFile(object):
	'''Container object for a config file

	Maps to a "base" file in the home folder, used to write new values,
	and one or more default files, e.g. in C{/usr/share/zim}, which
	are the fallback to get default values

	@ivar file: the underlying file object for the base config file
	in the home folder

	@note: this class implement similar API to the L{File} class but
	is explicitly not a sub-class of L{File} because config files should
	typically not be moved, renamed, etc. It just implements the reading
	and writing methods.
	'''

	def __init__(self, path, file=None):
		'''Constructor
		@param path: either basename as string or tuple with relative path,
		is resolved relative to the default config dir for zim.
		@param file: optional argument for some special case to
		override the base file in the home folder.
		'''
		if isinstance(path, basestring):
			path = (path,)
		self._path = tuple(path)
		if file:
			self.file = file
		else:
			self.file = File((XDG_CONFIG_HOME, 'zim') + self._path)

	def __repr__(self):
		return '<%s: %s>' % (self.__class__.__name__, self.file.path)

	def __eq__(self, other):
		return isinstance(other, ConfigFile) \
		and other._path == self._path \
		and other.file == self.file

	@property
	def basename(self):
		return self.file.basename

	def default_files(self):
		'''Generator that yields default config files (read-only) to
		use instead of the standard file when it is still empty.
		Typically only the first one is used.
		'''
		for dir in config_dirs():
			default = dir.file(self._path)
			if default.exists():
				yield default

	def touch(self):
		'''Ensure the custom file in the home folder exists. Either by
		copying a default config file, or touching an empty file.
		Intended to be called before trying to edit the file with an
		external editor.
		'''
		if not self.file.exists():
			for file in self.default_files():
				file.copyto(self.file)
				break
			else:
				self.file.touch() # create empty file

	def read(self, fail=False):
		'''Read the base file or first default file
		@param fail: if C{True} a L{FileNotFoundError} error is raised
		when neither the base file or a default file are found. If
		C{False} it will return C{''} for a non-existing file.
		@returns: file content as a string
		'''
		try:
			return self.file.read()
		except FileNotFoundError:
			for file in self.default_files():
				return file.read()
			else:
				if fail:
					raise
				else:
					return ''

	def readlines(self, fail=False):
		'''Read the base file or first default file
		@param fail: if C{True} a L{FileNotFoundError} error is raised
		when neither the base file or a default file are found. If
		C{False} it will return C{[]} for a non-existing file.
		@returns: file content as a list of lines
		'''
		try:
			return self.file.readlines()
		except FileNotFoundError:
			for file in self.default_files():
				return file.readlines()
			else:
				if fail:
					raise
				else:
					return []

	# Not implemented: read_async and readlines_async

	def write(self, text):
		'''Write base file, see L{File.write()}'''
		self.file.write(text)

	def writelines(self, lines):
		'''Write base file, see L{File.writelines()}'''
		self.file.writelines(lines)

	def write_async(self, text, callback=None, data=None):
		'''Write base file async, see L{File.write_async()}'''
		return self.file.write_async(text, callback=callback, data=data)

	def writelines_async(self, lines, callback=None, data=None):
		'''Write base file async, see L{File.writelines_async()}'''
		return self.file.writelines_async(lines, callback=callback, data=data)

	def remove(self):
		'''Remove user file, leaves default files in place'''
		if self.file.exists():
			return self.file.remove()


def check_class_allow_empty(value, default):
	'''Check function for L{ListDict.setdefault()} which ensures the
	value is of the same class as the default if it is set, but also
	allows it to be empty (empty string or C{None}). This is
	the same as the default behavior when "C{allow_empty}" is C{True}.
	It will convert C{list} type to C{tuple} automatically if the
	default is a tuple.

	This function can be used in cases where the check is provided
	inderictly and C{allow_empty} can not be passed along, e.g.
	in the definition of plugin preferences.

	@param value: the value in the dict
	@param default: the default that is set
	@returns: the new value to set
	@raises AssertionError: when the value if of the wrong class
	(which will result in C{setdefault()} setting the default value)
	'''
	klass = default.__class__
	if issubclass(klass, basestring):
		klass = basestring

	if value in ('', None) or isinstance(value, klass):
		return value
	elif klass is tuple and isinstance(value, list):
		# Special case because json does not know difference list or tuple
		return tuple(value)
	else:
		raise AssertionError, 'should be of type: %s' % klass


def value_is_coord(value, default):
	'''Check function for L{ListDict.setdefault()} which will check
	whether the value is a coordinate (a tuple of two integers). This
	is e.g. used to store for window coordinates. If the value is a
	list of two integers, it will automatically be converted to a tuple.

	@param value: the value in the dict
	@param default: the default that is set
	@returns: the new value to set
	@raises AssertionError: when the value is not a coordinate tuple
	(which will result in C{setdefault()} setting the default value)
	'''
	if isinstance(value, list):
		value = tuple(value)

	if (
		isinstance(value, tuple)
		and len(value) == 2
		and isinstance(value[0], int)
		and isinstance(value[1], int)
	):
		return value
	else:
		raise AssertionError, 'should be coordinate (tuple of int)'


class ListDict(dict):
	'''Class that behaves like a dict but keeps items in same order.
	This is the base class for all dicts holding config items in zim.
	Most importantly it is used for each section in the L{ConfigDict}.
	Because it remembers the order of the items in the dict, the order
	in which they will be written to a config file is predictable.
	Another important function is to check the config values have
	proper values, this is enforced by L{setdefault()}.

	@ivar modified: C{True} when the values were modified, used to e.g.
	track when a config needs to be written back to file
	'''

	def __init__(self):
		self.order = []
		self._modified = False

	def __repr__(self):
		return '<%s: %s>' % (self.__class__.__name__, dict.__repr__(self))

	def copy(self):
		'''Shallow copy of the items
		@returns: a new object of the same class with the same items
		'''
		new = self.__class__()
		new.update(self)
		return new

	@property
	def modified(self):
		if self._modified:
			return True
		else:
			return any(v.modified for v in self.values()
									if isinstance(v, ListDict))

	def set_modified(self, modified):
		'''Set the modified state. Used to reset modified to C{False}
		after the configuration has been saved to file.
		@param modified: C{True} or C{False}
		'''
		if modified:
			self._modified = True
		else:
			self._modified = False
			for v in self.values():
				if isinstance(v, ListDict):
					v.set_modified(False)

	def update(D, E=None, **F):
		'''Like C{dict.update()}'''
		if E and hasattr(E, 'keys'):
			for k in E: D[k] = E[k]
		elif E:
			for (k, v) in E: D[k] = v
		for k in F: D[k] = F[k]

	def __setitem__(self, k, v):
		dict.__setitem__(self, k, v)
		self._modified = True
		if not k in self.order:
			self.order.append(k)

	def __delitem__(self, k):
		dict.__delitem__(self, k)
		self.order.remove(k)

	def __iter__(self):
		return iter(self.order)

	def pop(self, k):
		'''Like C{dict.pop()}'''
		v = dict.pop(self, k)
		self.order.remove(k)
		return v

	def setdefault(self, key, default, check=None, allow_empty=False):
		'''Set the default value for a configuration item.

		Compatible with C{dict.setdefault()} but extended with
		functionality to check the value that is in the dict, and use
		the default if the value is mal-formed. This is used extensively
		in zim to do a sanity check on values in the configuration
		files. If you initialize the config items with this method you
		can assume them to be safe afterward and avoid a lot of checks
		or bugs later in the code.

		@param key: the dict key
		@param default: the default value for this key

		@param check: the check to do on the values, when the check
		fails the value is considered mal-formed and the default is
		used while a warning is logged.

		If C{check} is C{None} the default behavior will be to compare
		the classes of the set value and the default and enforce them to
		be of the same type. Automatic conversion is done for values of
		type C{list} with defaults of type C{tuple}. And for defaults of
		type C{str} or C{unicode} the C{basestring} type is used as
		check. As a special case when the default is C{None} the check
		is not allowed to be C{None} as well.

		If C{check} is given and it is a class the existing value will be
		checked to be of that class. Same special case for tuples
		and strings applies here.

		If C{check} is given and is a C{set}, C{list} or C{tuple} the
		value will be tested to be in this set or list.

		If the default is an integer and C{check} is a tuple of two
		integers, the check will be that the value is in this range.
		(For compatibility with L{InputForm} extra argument for integer
		spin boxes.)

		If C{check} is given and it is a function it will be used to
		check the value in the dictionary if it exists. The function
		is called as::

			check(value, default)

		Where C{value} is the current value in the dict and C{default}
		is the default value that was provided. The function can not
		only check the value, it can also do on the fly modifications,
		e.g. to coerce it into a specific type. If the value is OK the
		function should return the (modified) value, if not it should
		raise an C{AssertionError}. When this error is raised the
		default is used and the dict is considered being modified.

		( Note that 'assert' statements in the code can be removed
		by code optimization, so explicitly call "C{raise AssertionError}". )

		Examples of functions that can be used as a check are:
		L{check_class_allow_empty} and L{value_is_coord}.

		@param allow_empty: if C{True} the value is allowed to be empty
		(either empty string or C{None}). In this case the default is
		not set to overwrite an empty value, but only for a mal-formed
		value or for a value that doesn't exist yet in the dict.
		'''
		assert not (default is None and check is None), \
			'Bad practice to set default to None without check'

		if not key in self:
			self.__setitem__(key, default)
			return self[key]

		if check is None:
			klass = default.__class__
			if issubclass(klass, basestring):
				klass = basestring
			check = klass

		if default in ('', None):
			allow_empty = True

		if allow_empty and self[key] in ('', None):
			return self[key]

		if isinstance(check, (type, types.ClassType)): # is a class
			klass = check
			if not (allow_empty and default in ('', None)):
				assert isinstance(default, klass), 'Default does not have correct class'

			if not isinstance(self[key], klass):
				if klass is tuple and isinstance(self[key], list):
					# Special case because json does not know difference list or tuple
					modified = self.modified
					self.__setitem__(key, tuple(self[key]))
					self.set_modified(modified) # don't change modified state
				elif hasattr(klass, 'new_from_zim_config'):
					# Class has special contructor
					modified = self.modified
					try:
						self.__setitem__(key, klass.new_from_zim_config(self[key]))
					except:
						logger.exception(
							'Invalid config value for %s: "%s"',
							key, self[key])
					self.set_modified(modified) # don't change modified state
				else:
					logger.warn(
						'Invalid config value for %s: "%s" - should be of type %s',
						key, self[key], klass)
					self.__setitem__(key, default)
			elif self[key] == '':
					# Special case for empty string
					logger.warn(
						'Invalid config value for %s: "%s" - not allowed to be empty',
						key, self[key])
					self.__setitem__(key, default)
			else:
				pass # value is OK
		elif isinstance(check, (set, list)) \
		or (isinstance(check, tuple) and not isinstance(default, int)):
			if not (allow_empty and default in ('', None)):
				# HACK to allow for preferences with "choice" item that has
				# a list of tuples as argumnet
				if all(isinstance(t, tuple) for t in check):
					check = list(check) # copy
					check += [t[0] for t in check]
				assert default in check, 'Default is not within allowed set'

			# HACK to allow the value to be a tuple...
			if all(isinstance(t, tuple) for t in check) \
			and isinstance(self[key], list):
				modified = self.modified
				self.__setitem__(key, tuple(self[key]))
				self.set_modified(modified)

			if not self[key] in check:
				logger.warn(
						'Invalid config value for %s: "%s" - should be one of %s',
						key, self[key], unicode(check))
				self.__setitem__(key, default)
			else:
				pass # value is OK
		elif isinstance(check, tuple) and isinstance(default, int):
			assert len(check) == 2 \
				and isinstance(check[0], int) \
				and isinstance(check[1], int)
			if not isinstance(self[key], int):
				logger.warn(
					'Invalid config value for %s: "%s" - should be integer',
					key, self[key])
				self.__setitem__(key, default)
			elif not check[0] <= self[key] <= check[1]:
				logger.warn(
					'Invalid config value for %s: "%s" - should be between %i and %i',
					key, self[key], check[0], check[1])
				self.__setitem__(key, default)
			else:
				pass # value is OK
		else: # assume callable
			modified = self.modified
			try:
				v = check(self[key], default)
				self.__setitem__(key, v)
				self.set_modified(modified)
			except AssertionError, error:
				logger.warn(
					'Invalid config value for %s: "%s" - %s',
					key, self[key], error.args[0])
				self.__setitem__(key, default)

		return self[key]

	def keys(self):
		'''Like C{dict.keys()}'''
		return self.order[:]

	def items(self):
		'''Like C{dict.items()}'''
		return tuple(map(lambda k: (k, self[k]), self.order))

	def set_order(self, order):
		'''Change the order in which items are listed.

		@param order: a list of keys in a specific order. Items in the
		dict that do not appear in the list will be moved to the end.
		Items in the list that are not in the dict are ignored.
		'''
		order = list(order[:]) # copy and convert
		oldorder = set(self.order)
		neworder = set(order)
		for k in neworder - oldorder: # keys not in the dict
			order.remove(k)
		for k in oldorder - neworder: # keys not in the list
			order.append(k)
		neworder = set(order)
		assert neworder == oldorder
		self.order = order


class ConfigDict(ListDict):
	'''Dict to represent a configuration file in "ini-style". Since the
	ini-file is devided in section this is represented as a dict of
	dicts. This class represents the top-level with a key for each
	section. The values are in turn L{ListDict}s which contain the
	key value pairs in that section.

	A typical file might look like::

	  [Section1]
	  param1=foo
	  param2=bar

	  [Section2]
	  enabled=True
	  data={'foo': 1, 'bar': 2}

	values can either be simple string, number, or one of "True",
	"False" and "None", or a complex data structure encoded with the
	C{json} module.

	Sections are auto-vivicated when a non-existing item is retrieved.

	By default when parsing sections of the same name they will be
	merged and values that appear under the same section name later in
	the file will overwrite values that appeared earlier. As a special
	case we can support sections that repeat under the same section name.
	To do this assign the section name a list before parsing.

	Sections and parameters whose name start with '_' are considered as
	private and are not stored when the config is written to file. This
	can be used for caching values that should not be persistent across
	instances.
	'''

	def __getitem__(self, k):
		if not k in self:
			self[k] = ListDict()
		return dict.__getitem__(self, k)

	def parse(self, text):
		'''Parse an "ini-style" configuration. Fills the dictionary
		with values from this text, wil merge with existing sections and
		overwrite existing values.
		@param text: a string or a list of lines
		'''
		# Note that we explicitly do _not_ support comments on the end
		# of a line. This is because "#" could be a valid character in
		# a config value.
		if isinstance(text, basestring):
			text = text.splitlines(True)
		section = None
		for line in text:
			line = line.strip()
			if not line or line.startswith('#'):
				continue
			elif line.startswith('[') and line.endswith(']'):
				name = line[1:-1].strip()
				section = self[name]
				if isinstance(section, list):
					section.append(ListDict())
					section = section[-1]
			elif '=' in line:
				parameter, rawvalue = line.split('=', 1)
				parameter = str(parameter.rstrip()) # no unicode
				rawvalue = rawvalue.lstrip()
				try:
					value = self._decode_value(parameter, rawvalue)
					section[parameter] = value
				except:
					logger.warn('Failed to parse value for key "%s": %s', parameter, rawvalue)
			else:
				logger.warn('Could not parse line: %s', line)

	# Separated out as this will be slightly different for .desktop files
	# we ignore the key - but DesktopEntryDict uses them
	def _decode_value(self, key, value):
		if len(value) == 0:
			return ''
		if value == 'True': return True
		elif value == 'False': return False
		elif value == 'None': return None
		elif value[0] in ('{', '['):
			return json.loads(value)
		else:
			try:
				value = int(value)
				return value
			except: pass

			try:
				value = float(value)
				return value
			except: pass

			return json.loads('"%s"' % value.replace('"', r'\"')) # force string

	def dump(self):
		'''Serialize the config to a "ini-style" config file.
		@returns: a list of lines with text in "ini-style" formatting
		'''
		lines = []
		def dump_section(name, parameters):
			try:
				lines.append('[%s]\n' % section)
				for param, value in parameters.items():
					if not param.startswith('_'):
						lines.append('%s=%s\n' % (param, self._encode_value(value)))
				lines.append('\n')
			except:
				logger.exception('Dumping section [%s] failed:\n%r', name, parameters)

		for section, parameters in self.items():
			if parameters and not section.startswith('_'):
				if isinstance(parameters, list):
					for param in parameters:
						dump_section(section, param)
				else:
					dump_section(section, parameters)

		return lines

	def _encode_value(self, value):
		if isinstance(value, basestring):
			return json.dumps(value)[1:-1] # get rid of quotes
		elif value is True: return 'True'
		elif value is False: return 'False'
		elif value is None: return 'None'
		elif hasattr(value, 'serialize_zim_config'):
			return value.serialize_zim_config()
		else:
			return json.dumps(value, separators=(',',':'))
				# specify separators for compact encoding


class ConfigFileMixin(ListDict):
	'''Mixin class for reading and writing config to file, can be used
	with any parent class that has a C{parse()}, a C{dump()}, and a
	C{set_modified()} method. See L{ConfigDict} for the documentation
	of these methods.
	'''

	def __init__(self, file):
		'''Constructor
		@param file: a L{File} or L{ConfigFile} object for reading and
		writing the config.
		'''
		ListDict.__init__(self)
		self.file = file
		try:
			self.read()
			self.set_modified(False)
		except FileNotFoundError:
			pass

	def read(self):
		'''Read data from file'''
		# No flush here - this is used by change_file()
		# but may change in the future - so do not depend on it
		logger.debug('Loading config from: %s', self.file)
		self.parse(self.file.readlines())
		# Will fail with FileNotFoundError if file does not exist

	def write(self):
		'''Write data and set C{modified} to C{False}'''
		self.file.writelines(self.dump())
		self.set_modified(False)

	def write_async(self):
		'''Write data asynchronously and set C{modified} to C{False}
		@returns: an L{AsyncOperation} object
		'''
		operation = self.file.writelines_async(self.dump())
		# TODO do we need async error handling here ?
		self.set_modified(False)
		return operation

	def change_file(self, file, merge=True):
		'''Change the underlaying file used to read/write data
		Used to switch to a new config file without breaking existing
		references to config sections.
		@param file: a L{File} or L{ConfigFile} object for the new config
		@param merge: if C{True} the new file will be read (if it exists)
		and values in this dict will be updated.
		'''
		self.file = file
		try:
			self.read()
			self.set_modified(True)
				# This is the correct state because after reading we are
				# merged state, so does not matching file content
		except FileNotFoundError:
			pass


class ConfigDictFile(ConfigFileMixin, ConfigDict):
	pass


class HeaderParsingError(Error):
	'''Error when parsing a L{HeadersDict}'''

	description = '''\
Invalid data was found in a block with headers.
This probably means the header block was corrupted
and can not be read correctly.'''

	def __init__(self, line):
		self.msg = 'Invalid header >>%s<<' % line.strip('\n')


class HeadersDict(ListDict):
	'''This class maps a set of headers in the rfc822 format.
	Can e.g. look like::

		Content-Type: text/x-zim-wiki
		Wiki-Format: zim 0.4
		Creation-Date: 2010-12-14T14:15:09.134955

	Header names are always kept in "title()" format to ensure
	case-insensitivity.
	'''

	_is_header_re = re.compile('^([\w\-]+):\s+(.*)')
	_is_continue_re = re.compile('^(\s+)(?=\S)')

	def __init__(self, text=None):
		'''Constructor

		@param text: the header text, passed on to L{parse()}
		'''
		ListDict.__init__(self)
		if not text is None:
			self.parse(text)

	def __getitem__(self, k):
		return ListDict.__getitem__(self, k.title())

	def __setitem__(self, k, v):
		return ListDict.__setitem__(self, k.title(), v)

	def read(self, lines):
		'''Checks for headers at the start of the list of lines and
		read them into the dict until the first empty line. Will remove
		any lines belonging to the header block from the original list,
		so after this method returns the input does no longer contain
		the header block.
		@param lines: a list of lines
		'''
		self._parse(lines, fatal=False)
		if lines and lines[0].isspace():
			lines.pop(0)

	def parse(self, text):
		'''Adds headers defined in 'text' to the dict.
		Trailing whitespace is ignored.

		@param text: a header block, either as string or as a list of lines.

		@raises HeaderParsingError: when C{text} is not a valid header
		block
		'''
		if isinstance(text, basestring):
			lines = text.rstrip().splitlines(True)
		else:
			lines = text[:] # make copy so we do not destry the original
		self._parse(lines)

	def _parse(self, lines, fatal=True):
		header = None
		while lines:
			is_header = self._is_header_re.match(lines[0])
			if is_header:
				header = is_header.group(1)
				value  = is_header.group(2)
				self[header] = value.strip()
			elif self._is_continue_re.match(lines[0]) and not header is None:
				self[header] += '\n' + lines[0].strip()
			else:
				if fatal:
					raise HeaderParsingError, lines[0]
				else:
					break
			lines.pop(0)

	def dump(self, strict=False):
		'''Serialize the dict to a header block in rfc822 header format.

		@param strict: if C{True} lines will be properly terminated
		with '\\r\\n' instead of '\\n'.

		@returns: the header block as a list of lines
		'''
		buffer = []
		for k, v in self.items():
			v = v.strip().replace('\n', '\n\t')
			buffer.extend((k, ': ', v, '\n'))
		text = ''.join(buffer)

		if strict:
			text = text.replace('\n', '\r\n')

		return text.splitlines(True)


class HierarchicDict(object):
	'''This class implements a data store that behaves as a hierarchig
	dict of dicts. Each key in this object is considered a hierarchic
	path (the path separator is ':' for obvious reasons). The dict for
	each key will "inherit" all values from parent paths. However
	setting a new value will set it specifically for that key, without
	changing the value in the "parents". This is specifically used to store
	namespace properties for zim notebooks. So each child namespace will
	inherit the properties of it's parents unless it was explicitly
	set for that child namespace.

	There is a special member dict stored under the key "__defaults__"
	which has the top-level fallback properties.

	Child dicts are auto-vivicated, so this object only implements
	C{__getitem__()} but no C{__setitem__()}.
	'''
	# Note that all the magic is actually implemented by HierarchicDictFrame

	__slots__ = ('dict',)

	def __init__(self, defaults=None):
		'''Constructor

		@param defaults: dict with the default properties
		'''
		self.dict = {}
		self.dict['__defaults__'] = defaults or {}

	def __getitem__(self, k):
		if not isinstance(k, basestring):
			k = k.name # assume zim path
		return HierarchicDictFrame(self.dict, k)


class HierarchicDictFrame(object):
	'''Object acts as a member dict for L{HierarchicDict}'''

	__slots__ = ('dict', 'key')

	def __init__(self, dict, key):
		'''Constructor

		@param dict: the dict used to store the properties per namespace
		(internal in HierarchicDict)
		@param key: the key for this member dict
		'''
		self.dict = dict
		self.key = key

	def _keys(self):
		yield self.key
		parts = self.key.split(':')
		parts.pop()
		while parts:
			yield ':'.join(parts)
			parts.pop()
		yield '' # top level namespace

	def get(self, k, default=None):
		try:
			v = self.__getitem__(k)
		except KeyError:
			return default
		else:
			return v

	def __getitem__(self, k):
		for key in self._keys():
			if key in self.dict and k in self.dict[key]:
				return self.dict[key][k]
		else:
			if k in self.dict['__defaults__']:
				return self.dict['__defaults__'][k]
			else:
				raise KeyError

	def __setitem__(self, k, v):
		if not self.key in self.dict:
			self.dict[self.key] = {}
		self.dict[self.key][k] = v

	def remove(self, k):
		if self.key in self.dict and k in self.dict[self.key]:
			return self.dict[self.key].pop(k)
		else:
			raise KeyError
