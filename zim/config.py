# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains utilities to work with config files. It also supports looking up
files according to the Freedesktop.org (XDG) Base Dir specification.
'''

# TODO: remove all mention of ConfigList if it is not being used anymore

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


ZIM_DATA_DIR = None
XDG_DATA_HOME = None
XDG_DATA_DIRS = None
XDG_CONFIG_HOME = None
XDG_CONFIG_DIRS = None
XDG_CACHE_HOME = None

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
	'''Put the basedirs in use into logging'''
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
	'''Generator for paths that contain zim data files. These will be the
	equivalent of e.g. /usr/share/zim, /usr/local/share/zim etc..
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
	'''Takes a path relative to the zim data dir and returns the first subdir
	found doing a lookup over all data dirs.
	'''
	for dir in data_dirs(path):
		if dir.exists():
			return dir
	else:
		return None

def data_file(path):
	'''Takes a path relative to the zim data dir and returns the first file
	found doing a lookup over all data dirs.
	'''
	for dir in data_dirs():
		file = dir.file(path)
		if file.exists():
			return file
	else:
		return None

def config_dirs():
	'''Generator that first yields the equivalent of ~/.config/zim and
	/etc/xdg/zim and then continous with the data dirs. Zim is not strictly
	XDG conformant by installing default config files in /usr/share/zim instead
	of in /etc/xdg/zim. Therefore this function yields both.
	'''
	yield XDG_CONFIG_HOME.subdir(('zim'))
	for dir in XDG_CONFIG_DIRS:
		yield dir.subdir(('zim'))
	for dir in data_dirs():
		yield dir

def config_file(path, klass=None):
	'''Takes a path relative to the zim config dir and returns a file equivalent
	to ~/.config/zim/path . Based on the file extension a ConfigDictFile object,
	a ConfigListFile object or a normal File object is returned. In the case a
	ConfigDictFile is returned the default is also set when needed.
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
	'''Returns a dict with directories for the xdg user dirs'''
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
	'''Check function for setdefault() which ensures the value is of
	the same class as the default but allows it to be empty. THis is
	the same as the default behavior when "allow_empty" is True.

	Only reason to use this function is for places where setdefault()
	is called indirectly, e.g. with arguments from plugin preferences.
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
	'''Check function for setdefault() which enforces a coordinate
	(a tuple or list of 2 ints).
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
	Used as base class for e.g. for config objects were writing should be
	in a predictable order.
	'''

	def __init__(self):
		self.order = []
		self._modified = False

	def copy(self):
		'''Shallow copy'''
		new = self.__class__()
		new.update(self)
		return new

	@property
	def modified(self):
		'''Recursive property'''
		if self._modified:
			return True
		else:
			return any(v.modified for v in self.values()
									if isinstance(v, ListDict))

	def set_modified(self, modified):
		if modified:
			self._modified = True
		else:
			self._modified = False
			for v in self.values():
				if isinstance(v, ListDict):
					v.set_modified(False)

	def update(D, E=None, **F):
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
		v = dict.pop(self, k)
		self.order.remove(k)
		return v

	# Would expect that setdefault() triggers __setitem__
	# but this seems not to be the case in the standard implementation
	# And we added some extra functionality here
	def setdefault(self, key, default, check=None, allow_empty=False):
		'''Like dict.setdefault() but with some extra restriction
		because we assume un-safe user input. If no extra arguments
		are given it will compare the classes of the set value and the
		default to ensure we get what we expect. An exception is made
		when value is None, in that case it is good practise to always
		specify a class or check function. When the default is a string
		we check the value to be an instance of basestring (ignoring
		difference between str and unicode). Another special case is when
		the default is a tuple and the value is a list, in this case the
		value will be cast to a tuple.

		If 'check' is given and is a class the existing value will be
		checked to be of that class and reset to default if it is not.
		Same spacial case for tuples applies here.

		If 'check' is given and it is a function it will be used to
		check the value in the dictionary if it exists. The check
		function gets the current value and the default value as
		arguments. The function should raise an AssertionError when the
		value is not ok. The return value of the function is used to
		replace the current value, so the check function can coerce
		values into the proper form (but don't use this to return a
		default!).
		( Note that 'assert' statements in the code can be removed
		by code optimization, so explicitly call 'raise' to raise the
		AssertionError. )

		If 'check' is given and is a set the value will be tested
		against this set. If 'check' is a list or a tuple and the
		default is not an int it is also considered a set.

		If the default is an integer and 'check' is a tuple of two
		integers, the check will be that the value is in this range.
		(For compatibility with InputForm.add_inputs arguments.)

		If 'allow_empty' is True values are also allowed to be empty
		string or None. This is used for optional parameters in the
		config. By default 'allow_empty' is False but it is set to
		True implicitely when the default value is None or ''.
		'''
		if not key in self:
			self.__setitem__(key, default)
			return self[key]

		if check is None:
			assert not default is None, 'Bad practise to set default to None without check'
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
		return self.order[:]

	def items(self):
		return tuple(map(lambda k: (k, self[k]), self.order))

	def set_order(self, order):
		'''Change the order in which items are listed by setting a list
		of keys. Keys not in the list are moved to the end. Keys that are in
		the list but not in the dict will be ignored.
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
	'''Config object which wraps a dict of dicts.
	These are represented as INI files where each sub-dict is a section.
	Sections are auto-vivicated when getting a non-existing key.
	Each section is in turn a ListDict.

	By default sections will be merged if they have the same name.
	Values that appear under the same section name later in the file
	will overwrite values that appeared earlier.

	As a special case we can support sections that repeat under the
	same section name. To do this assign the section name a list
	before parsing.
	'''

	def __getitem__(self, k):
		if not k in self:
			self[k] = ListDict()
		return dict.__getitem__(self, k)

	def parse(self, text):
		'''Parse 'text' and set values based on this input
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

	# Seperated out as this will be slightly different for .desktop files
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
		'''Returns a list of lines with text representation of the
		dict. Used to write as a config file.
		'''
		lines = []
		def dump_section(name, parameters):
			lines.append('[%s]\n' % section)
			for param, value in parameters.items():
				lines.append('%s=%s\n' % (param, self._encode_value(value)))
			lines.append('\n')

		for section, parameters in self.items():
			if parameters:
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
	'''Base class for ConfigDictFile and ConfigListFile, can not be
	instantiated on its own.
	'''

	def __init__(self, file, default=None):
		ListDict.__init__(self)
		self.file = file
		self.default = default
		try:
			self.read()
			self.set_modified(False)
		except FileNotFoundError:
			pass

	def read(self):
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
		self.file.writelines(self.dump())
		self.set_modified(False)

	def write_async(self):
		operation = self.file.writelines_async(self.dump())
		# TODO do we need async error handling here ?
		self.set_modified(False)
		return operation


class ConfigDictFile(ConfigFile, ConfigDict):
	pass


class TextConfigFile(list):
	'''Like ConfigFile, but just represents a list of lines'''

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

	description = '''\
Invalid data was found in a block with headers.
This probably means the header block was corrupted
and can not be read correctly.'''

	def __init__(self, line):
		self.msg = 'Invalid header >>%s<<' % line.strip('\n')


class HeadersDict(ListDict):
	'''This class maps a set of headers in the rfc822 format.

	Header names are always kept in "title()" format to ensure
	case-insensitivity.
	'''

	_is_header_re = re.compile('^([\w\-]+):\s+(.*)')
	_is_continue_re = re.compile('^(\s+)(?=\S)')

	def __init__(self, text=None):
		ListDict.__init__(self)
		if not text is None:
			self.parse(text)

	def __getitem__(self, k):
		return ListDict.__getitem__(self, k.title())

	def __setitem__(self, k, v):
		return ListDict.__setitem__(self, k.title(), v)

	def read(self, lines):
		'''Checks for headers at the start of the list of lines and if any
		reads them into the dict until the first empty line. Will shift any
		lines belonging to the header block, so after this method returns the
		input does no longer contain the header block.
		'''
		self._parse(lines, fatal=False)
		if lines and lines[0].isspace():
			lines.pop(0)

	def parse(self, text):
		'''Adds headers defined in 'text' to the dict. Text can either be
		a string or a list of lines.

		Raises a HeaderParsingError when 'text' is not a valid header block.
		Trailing whitespace is ignored.
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
		'''Returns the dict as a list of lines defining a rfc822 header block.

		If 'strict' is set to True lines will be properly terminated
		with '\r\n' instead of '\n'.
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
	'''Dict which considers keys to be hierarchic (separator is ':' for
	obvious reasons). Each key gives a dict which shows shadows of all
	parents in the hierarchy. This is specifically used to store
	namespace properties for zim notebooks.
	'''

	__slots__ = ('dict')

	def __init__(self, defaults=None):
		self.dict = {}
		self.dict['__defaults__'] = defaults or {}

	def __getitem__(self, k):
		if not isinstance(k, basestring):
			k = k.name # assume zim path
		return HierarchicDictFrame(self.dict, k)


class HierarchicDictFrame(object):

	__slots__ = ('dict', 'key')

	def __init__(self, dict, key):
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
