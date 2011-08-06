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

from zim.fs import isfile, isdir, File, Dir, FileNotFoundError
from zim.errors import Error
from zim.parsing import TextBuffer, split_quoted_strings


logger = logging.getLogger('zim.config')


if os.name == 'nt':
	# Windows specific environment variables
	# os.environ does not support setdefault() ...
	if not 'USER' in os.environ or not os.environ['USER']:
		os.environ['USER'] =  os.environ['USERNAME']

	if not 'HOME' in os.environ or not os.environ['HOME']:
		if 'USERPROFILE' in os.environ:
			os.environ['HOME'] = os.environ['USERPROFILE']
		elif 'HOMEDRIVE' in os.environ and 'HOMEPATH' in os.environ:
			home = os.environ['HOMEDRIVE'] + os.environ['HOMEPATH']
			os.environ['HOME'] = home

assert isdir(os.environ['HOME']), \
	'ERROR: environment variable $HOME not set correctly'

if not 'USER' in os.environ or not os.environ['USER']:
	# E.g. Maemo doesn't define $USER
	os.environ['USER'] = os.path.basename(os.environ['HOME'])
	logger.info('Environment variable $USER was not set')


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
	if isfile('./zim.py'):
		scriptdir = '.' # maybe running module in test / debug
	else:
		scriptdir = os.path.dirname(os.path.abspath(sys.argv[0]))
	zim_data_dir = Dir(scriptdir + '/data')
	if zim_data_dir.exists():
		ZIM_DATA_DIR = zim_data_dir
	else:
		ZIM_DATA_DIR = None

	if 'XDG_DATA_HOME' in os.environ:
		XDG_DATA_HOME = Dir(os.environ['XDG_DATA_HOME'])
	else:
		XDG_DATA_HOME = Dir('~/.local/share/')

	if 'XDG_DATA_DIRS' in os.environ:
		XDG_DATA_DIRS = map(Dir, os.environ['XDG_DATA_DIRS'].split(':'))
	else:
		XDG_DATA_DIRS = map(Dir, ('/usr/share/', '/usr/local/share/'))

	if 'XDG_CONFIG_HOME' in os.environ:
		XDG_CONFIG_HOME = Dir(os.environ['XDG_CONFIG_HOME'])
	else:
		XDG_CONFIG_HOME = Dir('~/.config/')

	if 'XDG_CONFIG_DIRS' in os.environ:
		XDG_CONFIG_DIRS = map(Dir, os.environ['XDG_CONFIG_DIRS'].split(':'))
	else:
		XDG_CONFIG_DIRS = [Dir('/etc/xdg/')]

	if 'XDG_CACHE_HOME' in os.environ:
		XDG_CACHE_HOME = Dir(os.environ['XDG_CACHE_HOME'])
	else:
		XDG_CACHE_HOME = Dir('~/.cache')

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

def config_file(path, klass=None):
	'''Get a zim config file.

	Use this as the main function to find config files.

	@param path: the relative file path of the config file,
	e.g. "preferences.conf"

	@param klass: a class object to use for the returned config file,
	defaults to L{ConfigDictFile} for files ending with ".conf", and
	L{TextConfigFile} for all other files. Constructor of this class
	should take the same arguments as L{ConfigDictFile}.

	@returns: a config file object of the class specified, even if no
	config file of this name exists (yet). Typically this object will
	read values of any installed default, but write new values to the
	config home.
	'''
	if isinstance(path, basestring):
		path = [path]
	zimpath = ['zim'] + list(path)
	file = XDG_CONFIG_HOME.file(zimpath)

	if not file.exists():
		for dir in config_dirs():
			default = dir.file(path)
			if default.exists():
				break
		else:
			default = None
	else:
		default = None

	if klass:
		return klass(file, default=default)
	elif path[-1].endswith('.conf'):
		return ConfigDictFile(file, default=default)
	else:
		return TextConfigFile(file, default=default)

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
				assert default in check, 'Default is not within allows set'

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
				parameter, value = line.split('=', 1)
				parameter = str(parameter.rstrip()) # no unicode
				try:
					value = self._decode_value(value.lstrip())
					section[parameter] = value
				except:
					logger.warn('Failed to parse value for: %s', parameter)
			else:
				logger.warn('Could not parse line: %s', line)

	# Separated out as this will be slightly different for .desktop files
	def _decode_value(self, value):
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

			return json.loads('"%s"' % value.replace('"', '\\"')) # force string

	def dump(self):
		'''Serialize the config to a "ini-style" config file.
		@returns: a list of lines with text in "ini-style" formatting
		'''
		lines = []
		def dump_section(name, parameters):
			lines.append('[%s]\n' % section)
			for param, value in parameters.items():
				if not param.startswith('_'):
					lines.append('%s=%s\n' % (param, self._encode_value(value)))
			lines.append('\n')

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


class ConfigFile(ListDict):
	'''Mixin class for reading and writing config to file'''

	def __init__(self, file, default=None):
		'''Constructor

		Typically C{file} is the file in the home dir that the user can
		always write to. While C{default} is the default file in e.g.
		"/usr/share" which the user can read but not write. When the
		file in the home folder does not exist, the default is read,
		but when we write it after modifications we write to the home
		folder file.

		@param file: a L{File} object for reading and writing the config
		@param default: optional default L{File} object, only used for
		reading when C{file} does not exist.
		'''
		ListDict.__init__(self)
		self.file = file
		self.default = default
		try:
			self.read()
			self.set_modified(False)
		except FileNotFoundError:
			pass

	def read(self):
		'''Read data'''
		# TODO: flush dict first ?
		try:
			logger.debug('Loading %s', self.file.path)
			self.parse(self.file.readlines())
		except FileNotFoundError:
			if self.default:
				logger.debug('File not found, loading %s', self.default.path)
				self.parse(self.default.readlines())
			else:
				raise

	def write(self):
		'''Write data and set C{modified} to C{False}
		'''
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


class ConfigDictFile(ConfigFile, ConfigDict):
	pass


class TextConfigFile(list):
	'''Like L{ConfigFile}, but just represents a list of lines'''

	# TODO think of a way of uniting this class with ConfigFile

	def __init__(self, file, default=None):
		self.file = file
		self.default = default
		try:
			self.read()
		except FileNotFoundError:
			pass

	def read(self):
		# TODO: flush list first ?
		try:
			self[:] = self.file.readlines()
		except FileNotFoundError:
			if self.default:
				self[:] = self.default.readlines()
			else:
				raise

	def write(self):
		self.file.writelines(self)


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
