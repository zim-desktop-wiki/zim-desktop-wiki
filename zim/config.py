# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

'''This module contains utilities to work with config files. It also supports looking up
files according to the Freedesktop.org (XDG) Base Dir specification.
'''

# TODO: remove all mention of ConfigList if it is not being used anymore

import sys
import os
import re
import logging

try:
	import json # in standard lib since 2.6
except:
	import simplejson as json # extra dependency

from zim.fs import *
from zim.errors import Error
from zim.parsing import TextBuffer, split_quoted_strings


logger = logging.getLogger('zim.config')


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
	if os.path.isfile('./zim.py'):
		scriptdir = '.' # maybe running module in test / debug
	else:
		scriptdir = os.path.dirname(sys.argv[0])
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
	#~ elif path[-1].endswith('.list'):
		#~ return ConfigListFile(file, default=default)
	else:
		return TextConfigFile(file, default=default)

def user_dirs():
	'''Returns a dict with directories for the xdg user dirs'''
	dirs = {}
	file = XDG_CONFIG_HOME.file('user-dirs.dirs')
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
	return dirs


class ConfigPathError(Error):

	description = '''\
A config file was not found and did not have a default either.
This ould mean that the paths for locating config files are
not set correctly.
'''

	def __init__(self, file):
		self.file = file
		self.msg = 'No default config found for %s' % file

class ListDict(dict):
	'''Class that behaves like a dict but keeps items in same order.
	Used as base class for e.g. for config objects were writing should be
	in a predictable order.
	'''

	def __init__(self):
		self.order = []
		self._modified = False

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

	def __setitem__(self, k, v):
		dict.__setitem__(self, k, v)
		self._modified = True
		if not k in self.order:
			self.order.append(k)

	def __delitem__(self, k):
		dict.__delitem__(self, k)
		self.order.remove(k)

	def pop(self, k):
		v = dict.pop(self, k)
		self.order.remove(k)

	# Would expect that setdefault() triggers __setitem__
	# but this seems not to be the case in the standard implementation
	# And we added some extra functionality here
	def setdefault(self, k, v=None, klass=None, check=None):
		'''Like dict.setdefault() but with some extra restriction because we
		assume un-safe user input. If 'klass' is given the existing value
		will be checked to be of that class and reset to default if it is not.
		Alternatively 'check' can be a function that needs to return True
		in order to keep the existing value. If no class and no function
		is given is it will compare the classes of the set value and the
		default to ensure we get what we expect. (An exception is made when
		value is None, in that case it is good practise to always specify
		a class or check function.)
		'''
		if not k in self:
			self.__setitem__(k, v)
		elif check is None:
			klass = klass or v.__class__
			if issubclass(klass, basestring):
				klass = basestring
			if not self[k] is None and not v is None \
			and not isinstance(self[k], klass):
				logger.warn(
					'Invalid config value for %s: "%s" - should be of type %s',
					k, self[k], klass)
				self.__setitem__(k, v)
		else:
			if not check(self[k]):
				logger.warn(
					'Invalid config value for %s: "%s"', k, self[k])
				self.__setitem__(k, v)
		return self[k]

	def items(self):
		return map(lambda k: (k, self[k]), self.order)

	def set_order(self, order):
		'''Change the order in which items are listed by setting a list
		of keys. Keys not in the list are moved to the end. Keys that are in
		the list but not in the dict will be ignored.
		'''
		order = order[:] # copy
		oldorder = set(self.order)
		neworder = set(order)
		for k in neworder - oldorder: # keys not in the dict
			order.remove(k)
		for k in oldorder - neworder: # keys not in the list
			order.append(k)
		neworder = set(order)
		assert neworder == oldorder
		self.order = order

	def check_is_int(self, key, default):
		'''Asserts that the value for 'key' is an int. If this is not
		the case or when no value is set at all for 'key'.
		'''
		if not key in self:
			self[key] = default
		elif not isinstance(self[key], int):
			logger.warn('Invalid config value for %s: "%s" - should be an integer')
			self[key] = default

	def check_is_float(self, key, default):
		'''Asserts that the value for 'key' is a float. If this is not
		the case or when no value is set at all for 'key'.
		'''
		if not key in self:
			self[key] = default
		elif not isinstance(self[key], float):
			logger.warn('Invalid config value for %s: "%s" - should be a decimal number')
			self[key] = default

	@staticmethod
	def is_coord(value):
		'''Returns True if value is a coordinate (a tuple or list of 2 ints).
		Can be used in combination with setdefault() to enforce data types.
		'''
		return (isinstance(value, (tuple, list))
				and len(value) == 2
				and isinstance(value[0], int)
				and isinstance(value[1], int)  )


#~ class ConfigList(ListDict):
	#~ '''This class supports config files that exist of two columns separated
	#~ by whitespace. It inherits from ListDict to ensure the list remain in
	#~ the same order when it is written to file again. When a file path is set
	#~ for this object it will be used to try reading from any from the config
	#~ and data directories while using the config home directory for writing.
	#~ '''
#~
	#~ _fields_re = re.compile(r'(?:\\.|\S)+') # match escaped char or non-whitespace
	#~ _escaped_re = re.compile(r'\\(.)') # match single escaped char
	#~ _escape_re = re.compile(r'([\s\\])') # match chars to escape
#~
	#~ def parse(self, text):
		#~ if isinstance(text, basestring):
			#~ text = text.splitlines(True)
#~
		#~ for line in text:
			#~ line = line.strip()
			#~ if line.isspace() or line.startswith('#'):
				#~ continue
			#~ cols = self._fields_re.findall(line)
			#~ if len(cols) == 1:
				#~ cols.append(None) # empty string in second column
				#~ cols[0] = self._escaped_re.sub(r'\1', cols[0])
			#~ else:
				#~ assert len(cols) >= 2
				#~ if len(cols) > 2 and not cols[2].startswith('#'):
					#~ logger.warn('trailing data') # FIXME better warning
				#~ cols[0] = self._escaped_re.sub(r'\1', cols[0])
				#~ cols[1] = self._escaped_re.sub(r'\1', cols[1])
			#~ self[cols[0]] = cols[1]
#~
	#~ def dump(self):
		#~ text = TextBuffer()
		#~ for k, v in self.items():
			#~ k = self._escape_re.sub(r'\\\1', k)
			#~ if v is None:
				#~ v = ''
			#~ else:
				#~ v = self._escape_re.sub(r'\\\1', v)
			#~ text.append("%s\t%s\n" % (k, v))
		#~ return text.get_lines()


class ConfigDict(ListDict):
	'''Config object which wraps a dict of dicts.
	These are represented as INI files where each sub-dict is a section.
	Sections are auto-vivicated when getting a non-existing key.
	Each section is in turn a ListDict.
	'''

	def __getitem__(self, k):
		if not k in self:
			self[k] = ListDict()
		return dict.__getitem__(self, k)

	def parse(self, text):
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
			elif '=' in line:
				parameter, value = line.split('=', 1)
				parameter = parameter.rstrip()
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
		lines = []
		for section, parameters in self.items():
			if parameters:
				lines.append('[%s]\n' % section)
				for param, value in parameters.items():
					lines.append('%s=%s\n' % (param, self._encode_value(value)))
				lines.append('\n')
		return lines

	def _encode_value(self, value):
		if isinstance(value, basestring):
			return json.dumps(value)[1:-1] # get rid of quotes
		elif value is True: return 'True'
		elif value is False: return 'False'
		elif value is None: return 'None'
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
		except ConfigPathError:
			pass

	def read(self):
		# TODO: flush dict first ?
		if self.file.exists():
			self.parse(self.file.readlines())
		elif self.default:
			self.parse(self.default.readlines())
		else:
			raise ConfigPathError, self.file

	def write(self):
		self.file.writelines(self.dump())
		self.set_modified(False)


class ConfigDictFile(ConfigFile, ConfigDict):
	pass


#~ class ConfigListFile(ConfigFile, ConfigList):
	#~ pass


class TextConfigFile(list):
	'''Like ConfigFile, but just represents a list of lines'''

	# TODO think of a way of uniting this class with ConfigFile

	def __init__(self, file, default=None):
		self.file = file
		self.default = default
		try:
			self.read()
		except ConfigPathError:
			pass

	def read(self):
		# TODO: flush list first ?
		if self.file.exists():
			self[:] = self.file.readlines()
		elif self.default:
			self[:] = self.default.readlines()
		else:
			raise ConfigPathError, self.file

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
		reads them into the dict untill the first empty line. Will shift any
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

	def __init__(self):
		self.dict = {}

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
