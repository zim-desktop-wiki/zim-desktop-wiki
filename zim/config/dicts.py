# -*- coding: utf-8 -*-

# Copyright 2009-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains base classes to map config files.

Main classes for storing config items are L{ConfigDictFile} which maps
"ini-style" config files, and L{ListDict} which maintains a dict of
config keys while preserving their order.
'''

import sys
import re
import logging
import types

if sys.version_info >= (2, 6):
	import json # in standard lib since 2.6
else:
	import simplejson as json # extra dependency


from zim.fs import File, FileNotFoundError
from zim.errors import Error

from .basedirs import XDG_CONFIG_HOME


logger = logging.getLogger('zim.config')


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

	def __init__(self, mapping=None):
		self.order = []
		if mapping:
			self.update(mapping)
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
