# -*- coding: utf-8 -*-

# Copyright 2009-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains base classes to map config files to dicts

The main classes are L{ConfigDict} and L{INIConfigFile}. The
L{ConfigDict} defines a dictionary of config keys. To add a key in this
dictionary it must first be defined using one of the sub-classes of
L{ConfigDefinition}. This definition takes care of validating the
value of the config keys and (de-)serializing the values from and to
text representation used in the config files. The L{INIConfigFile} maps
to a INI-style config file that defines multiple sections with config
keys. It is represented as a dictionary where each key maps a to a
L{ConfigDict}.

Both derive from L{ControlledDict} which defines the C{changed} signal
which can be used to track changes in the configuration.

Typically these classes are not instantiated directly, but by the
L{ConfigManager} defined in Lzim.config.manager}.
'''

from __future__ import with_statement


import sys
import re
import logging
import types
import collections
import ast


if sys.version_info >= (2, 6):
	import json # in standard lib since 2.6
else: #pragma: no cover
	import simplejson as json # extra dependency


from zim.signals import SignalEmitter, ConnectorMixin
from zim.utils import OrderedDict, FunctionThread
from zim.fs import File, FileNotFoundError
from zim.errors import Error

from .basedirs import XDG_CONFIG_HOME


logger = logging.getLogger('zim.config')


class ControlledDict(OrderedDict, SignalEmitter, ConnectorMixin):
	'''Sub-class of C{OrderedDict} that tracks modified state.
	This modified state is recursive for nested C{ControlledDict}s.

	Used as base class for L{SectionedConfigDict}, L{ConfigDict}
	and L{HeadersDict}.

	@signal: C{changed ()}: emitted when content of this dict changed,
	or a nested C{ControlledDict} changed
	'''

	def __init__(self, E=None, **F):
		OrderedDict.__init__(self, E, **F)
		self._modified = False

	# Note that OrderedDict optimizes __getitem__, cannot overload it

	def __setitem__(self, k, v):
		OrderedDict.__setitem__(self, k, v)
		if isinstance(v, ControlledDict):
			self.connectto(v, 'changed', self.on_child_changed)
		self.emit('changed')

	def __delitem__(self, k):
		v = OrderedDict.__delitem__(self, k)
		if isinstance(v, OrderedDict):
			self.disconnect_from(v)
		self.emit('changed')

	def update(self, E=(), **F):
		# Only emit changed once here
		with self.blocked_signals('changed'):
			OrderedDict.update(self, E, **F)
		self.emit('changed')

	def changed(self):
		self.emit('changed')

	def on_child_changed(self, v):
		self.emit('changed')

	def do_changed(self):
		self._modified = True

	@property
	def modified(self):
		'''C{True} when the values were modified, used to e.g.
		track when a config needs to be written back to file
		'''
		return self._modified

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
				if isinstance(v, ControlledDict):
					v.set_modified(False)


class ConfigDefinition(object):
	'''Definition for a key in a L{ConfigDict}'''

	__slots__ = ('default', 'allow_empty')

	def __init__(self, default, allow_empty=False):
		self.default = default
		if default is None:
			allow_empty = True
		self.allow_empty = allow_empty

		self.check(default) # ensure that default follows check

	def __eq__(self, other):
		return self.__class__ == other.__class__ \
			and self.allow_empty == other.allow_empty

	def __ne__(self, other):
		return not self.__eq__(other)

	def _check_allow_empty(self, value):
		if value in ('', None, 'None', 'null'):
			if self.allow_empty:
				return True
			else:
				raise ValueError, 'Value not allowed to be empty'
		else:
			return False

	def _eval_string(self, value):
		if not value:
			return value
		elif value[0] in ('{', '['):
			# Backward compatibility
			try:
				value = json.loads(value)
			except:
				pass
		else:
			try:
				value = ast.literal_eval(value)
			except:
				pass

		return value

	def check(self, value):
		'''Check C{value} to be a valid value for this key
		@raises ValueError: if value is invalid and can not
		be converted
		@returns: (converted) value if valid
		'''
		raise NotImplementedError

	def tostring(self, value):
		return str(value)


class ConfigDefinitionByClass(ConfigDefinition):
	'''Definition that enforces the value has to have a certain class

	Classes that have a C{new_from_zim_config()} method can convert
	values to the desired class.
	'''
	# TODO fully get rid of this class and replace by specialized classes

	__slots__= ('klass',)

	def __init__(self, default, klass=None, allow_empty=False):
		if klass is None:
			klass = default.__class__

		if issubclass(klass, basestring):
			self.klass = basestring
		else:
			self.klass = klass

		ConfigDefinition.__init__(self, default, allow_empty)

	def __eq__(self, other):
		return ConfigDefinition.__eq__(self, other) \
			and self.klass == other.klass

	def check(self, value):
		if self._check_allow_empty(value):
			return None
		elif isinstance(value, basestring) \
		and not self.klass is basestring:
			value = self._eval_string(value)

		if isinstance(value, self.klass):
			return value
		elif self.klass is tuple and isinstance(value, list):
			# Special case because json does not know difference list or tuple
			return tuple(value)
		elif hasattr(self.klass, 'new_from_zim_config'):
			# Class has special contructor (which can also raise ValueError)
			try:
				return self.klass.new_from_zim_config(value)
			except:
				logger.debug('Error while converting %s to %s', value, self.klass, exc_info=1)
				raise ValueError, 'Can not convert %s to %s' % (value, self.klass)
		else:
			raise ValueError, 'Value should be of type: %s' % self.klass.__name__

	def tostring(self, value):
		if hasattr(value, 'serialize_zim_config'):
			return value.serialize_zim_config()
		else:
			return json.dumps(value, separators=(',',':'))
				# specify separators for compact encoding


class Boolean(ConfigDefinition):
	'''This class defines a config key that maps to a boolean'''

	def check(self, value):
		if self._check_allow_empty(value):
			return None
		elif isinstance(value, bool):
			return value
		elif value in ('True', 'true', 'False', 'false'):
			return value in ('True', 'true')
		else:
			raise ValueError, 'Must be True or False'


class String(ConfigDefinition):
	'''This class defines a config key that maps to a string'''

	# TODO support esacpe codes \s \t \n \r (see desktop / json spec)

	def __init__(self, default, allow_empty=False):
		if default == '':
			default = None
		ConfigDefinition.__init__(self, default, allow_empty)

	def check(self, value):
		if self._check_allow_empty(value):
			return None
		elif isinstance(value, basestring):
			return value
		elif hasattr(value, 'serialize_zim_config'):
			return value.serialize_zim_config()
		else:
			raise ValueError, 'Must be string'

	def tostring(self, value):
		if value is None:
			return ''
		else:
			return value


class StringAllowEmpty(String):
	'''Like C{String} but defaults to C{allow_empty=True}'''

	# XXX needed by TaskList - remove when prefs are ported to use defs directly

	def __init__(self, default, allow_empty=True):
		String.__init__(self, default, allow_empty=True)


class Integer(ConfigDefinition):
	'''This class defines a config key that maps to an integer value'''

	def check(self, value):
		if self._check_allow_empty(value):
			return None
		elif isinstance(value, int):
			return value
		else:
			try:
				return int(value)
			except:
				raise ValueError, 'Must be integer'


class Float(ConfigDefinition):
	'''This class defines a config key that maps to a float'''

	def check(self, value):
		if self._check_allow_empty(value):
			return None
		elif isinstance(value, float):
			return value
		else:
			try:
				return float(value)
			except:
				raise ValueError, 'Must be integer'


class Choice(ConfigDefinition):
	'''Definition that allows selecting a value from a given set
	Will be presented in the gui as a dropdown with a list of choices
	'''

	__slots__ = ('choices',)

	# TODO - this class needs a type for the choices
	#        could be simply commen type of list items, but we get
	#        bitten because we allow tuples as needed for preferences
	#        with label --> make that a dedicated feature

	def __init__(self, default, choices, allow_empty=False):
		self.choices = choices
		ConfigDefinition.__init__(self, default, allow_empty)

	def __eq__(self, other):
		return ConfigDefinition.__eq__(self, other) \
			and self.choices == other.choices

	def check(self, value):
		if self._check_allow_empty(value):
			return None
		else:
			# Allow options that are not strings (e.g. tuples of strings)
			if isinstance(value, basestring) \
			and not all(isinstance(t, basestring) for t in self.choices):
				value = self._eval_string(value)

			# HACK to allow for preferences with "choice" item that has
			# a list of tuples as argumnet
			if all(isinstance(t, tuple) for t in self.choices):
				choices = list(self.choices) + [t[0] for t in self.choices]
			else:
				choices = self.choices

			# convert json list to tuple
			if all(isinstance(t, tuple) for t in self.choices) \
			and isinstance(value, list):
				value = tuple(value)

			if value in choices:
				return value
			elif isinstance(value, basestring) and value.lower() in choices:
				return value.lower()
			else:
				raise ValueError, 'Value should be one of %s' % unicode(choices)


class Range(Integer):
	'''Definition that defines an integer value in a certain range'''

	__slots__ = ('min', 'max')

	def __init__(self, default, min, max):
		self.min = min
		self.max = max
		ConfigDefinition.__init__(self, default)


	def __eq__(self, other):
		return ConfigDefinition.__eq__(self, other) \
			and (self.min, self.max) == (other.min, other.max)


	def check(self, value):
		value = Integer.check(self, value)
		if self._check_allow_empty(value):
			return None
		elif self.min <= value <= self.max:
			return value
		else:
			raise ValueError, 'Value should be between %i and %i' % (self.min, self.max)


class Coordinate(ConfigDefinition):
	'''Class defining a config value that is a coordinate
	(i.e. a tuple of two integers). This is e.g. used to store for
	window coordinates. If the value is a list of two integers,
	it will automatically be converted to a tuple.
	'''

	def __init__(self, default, allow_empty=False):
		if default == (None, None):
			allow_empty=True
		ConfigDefinition.__init__(self, default, allow_empty)

	def check(self, value):
		if isinstance(value, basestring):
			value = self._eval_string(value)

		if self._check_allow_empty(value) \
		or value == (None, None) and self.allow_empty:
			return None
		else:
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
				raise ValueError, 'Value should be a coordinate (tuple of 2 integers)'

value_is_coord = Coordinate # XXX for backward compatibility


_definition_classes = {
	str: String,
	unicode: String,
	basestring: String,
	int: Integer,
	float: Float,
	bool: Boolean,
}


def build_config_definition(default=None, check=None, allow_empty=False):
	'''Convenience method to construct a L{ConfigDefinition} object
	based on a default value an/or a check.
	'''
	if default is None and check is None:
		raise AssertionError, 'At least provide either a default or a check'
	elif check is None:
		check = default.__class__

	if isinstance(check, (type, types.ClassType)): # is a class
		if issubclass(check, ConfigDefinition):
			return check(default, allow_empty=allow_empty)
		elif check in _definition_classes:
			return _definition_classes[check](default, allow_empty)
		else:
			return ConfigDefinitionByClass(default, check, allow_empty)
	elif isinstance(check, (set, list)) \
	or (isinstance(check, tuple) and not isinstance(default, int)):
		return Choice(default, check, allow_empty)
	elif isinstance(check, tuple) and isinstance(default, int):
		assert len(check) == 2 \
			and isinstance(check[0], int) \
			and isinstance(check[1], int)
		return Range(default, check[0], check[1])
	else:
		raise ValueError, 'Unrecognized check type'



class ConfigDict(ControlledDict):
	'''The class defines a dictionary of config keys.

	To add a key in this dictionary it must first be defined using one
	of the sub-classes of L{ConfigDefinition}. This definition takes
	care of validating the value of the config keys and
	(de-)serializing the values from and to text representation used
	in the config files.

	Both getting and setting a value will raise a C{KeyError} when the
	key has not been defined first. An C{ValueError} is raised when the
	value does not conform to the definition.

	THis class derives from L{ControlledDict} which in turn derives
	from L{OrderedDict} so changes to the config can be tracked by the
	C{changed} signal, and values are kept in the same order so the order
	in which items are written to the config file is predictable.
	'''

	def __init__(self, E=None, **F):
		assert not (E and F)
		ControlledDict.__init__(self)
		self.definitions = OrderedDict()
		if E:
			self._input = dict(E)
		else:
			self._input = F

	def copy(self):
		'''Shallow copy of the items
		@returns: a new object of the same class with the same items
		'''
		new = self.__class__()
		new.update(self)
		new._input.update(self._input)
		return new

	def update(self, E=None, **F):
		'''Like C{dict.update()}, copying values from C{E} or C{F}.
		However if C{E} is also a C{ConfigDict}, also the definitions
		are copied along.
		Do use C{update()} when setting multiple values at once since it
		results in emitting C{changed} only once.
		'''
		if E and isinstance(E, ConfigDict):
			self.define(
				(k, E.definitions[k]) for k in E if not k in self
			)
		ControlledDict.update(self, E, **F)

	# Note that OrderedDict optimizes __getitem__, cannot overload it

	def __setitem__(self, k, v):
		if k in self.definitions:
			try:
				v = self.definitions[k].check(v)
			except ValueError, error:
				raise ValueError, 'Invalid config value for %s: "%s" - %s' % (k, v, error.args[0])
			else:
				ControlledDict.__setitem__(self, k, v)
		else:
			raise KeyError('Config key "%s" has not been defined' % k)

	def input(self, E=None, **F):
		'''Like C{update()} but won't raise on failures.
		Values for undefined keys are stored and validated once the
		key is defined. Invalid values only cause a logged error
		message but do not cause errors to be raised.
		'''
		assert not (E and F)
		update = E or F
		if isinstance(update, collections.Mapping):
			items = update.items()
		else:
			items = update

		for key, value in items:
			if key in self.definitions:
				self._set_input(key, value)
			else:
				self._input[key] = value # validated later

	def define(self, E=None, **F):
		'''Set one or more defintions for this config dict
		Can cause error log when values prior given to C{input()} do
		not match the definition.
		'''
		assert not (E and F)
		update = E or F
		if isinstance(update, collections.Mapping):
			items = update.items()
		else:
			items = update

		for key, definition in items:
			if key in self.definitions:
				if definition != self.definitions[key]:
					raise AssertionError, \
						'Key is already defined with different definition: %s\n%s != %s' \
						% (key, definition, self.definitions[key])
				else:
					continue

			self.definitions[key] = definition
			if key in self._input:
				value = self._input.pop(key)
				self._set_input(key, value)
			else:
				with self.blocked_signals('changed'):
					OrderedDict.__setitem__(self, key, definition.default)

	def _set_input(self, key, value):
		try:
			value = self.definitions[key].check(value)
		except ValueError, error:
			logger.warn(
				'Invalid config value for %s: "%s" - %s',
					key, value, error.args[0]
			)
			value = self.definitions[key].default

		with self.blocked_signals('changed'):
			OrderedDict.__setitem__(self, key, value)

	def setdefault(self, key, default, check=None, allow_empty=False):
		'''Set the default value for a configuration item.

		@note: Usage of this method with keyword arguments is
		depreciated, use L{define()} instead.

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
		if key in self.definitions \
		and check is None \
		and allow_empty is False:
			# Real setdefault
			return ControlledDict.setdefault(self, key, default)
		else:
			# Define
			definition = build_config_definition(default, check, allow_empty)
			self.define({key: definition})
			return self.__getitem__(key)


class SectionedConfigDict(ControlledDict):
	'''Dict with multiple sections of config values
	Sections are auto-vivicated when a non-existing item is retrieved.
	'''

	def __setitem__(self, k, v):
		assert isinstance(v, (ControlledDict, list)) # FIXME shouldn't we get rid of the list option here ?
		ControlledDict.__setitem__(self, k, v)

	def __getitem__(self, k):
		try:
			return ControlledDict.__getitem__(self, k)
		except KeyError:
			with self.blocked_signals('changed'):
				ControlledDict.__setitem__(self, k, ConfigDict())
			return ControlledDict.__getitem__(self, k)


class INIConfigFile(SectionedConfigDict):
	'''Dict to represent a configuration file in "ini-style". Since the
	ini-file is devided in section this is represented as a dict of
	dicts. This class represents the top-level with a key for each
	section. The values are in turn L{ConfigDict}s which contain the
	key value pairs in that section.

	A typical file might look like::

	  [Section1]
	  param1=foo
	  param2=bar

	  [Section2]
	  enabled=True
	  data={'foo': 1, 'bar': 2}

	(The values are parsed by the L{ConfigDefinition} for each key)

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

	# TODO get rid of the read() and write() methods here
	#      separate the dict object from the file object
	#      let parse() and dump() take a file-like object

	def __init__(self, file, monitor=False):
		'''Constructor
		@param file: a L{File} or L{ConfigFile} object for reading and
		writing the config.
		@param monitor: if C{True} will listen to the C{changed} signal
		of the file object and update the dict accordingly. Leave
		C{False} for objects with a short life span.
		'''
		SectionedConfigDict.__init__(self)
		self.file = file
		try:
			with self.blocked_signals('changed'):
				self.read()
			self.set_modified(False)
		except FileNotFoundError:
			pass

		if monitor:
			self.connectto(self.file, 'changed', self.on_file_changed)

	def on_file_changed(self, *a):
		if self.file.check_has_changed_on_disk():
			try:
				with self.blocked_signals('changed'):
					self.read()
			except FileNotFoundError:
				pass
			else:
				# First emit top level to allow general changes
				self.emit('changed')
				with self.blocked_signals('changed'):
					for section in self.values():
						section.emit('changed')
				self.set_modified(False)

	def read(self):
		'''Read data from file'''
		assert not self.modified, 'dict has unsaved changes'
		logger.debug('Loading config from: %s', self.file)
		self.parse(self.file.readlines())
		# Will fail with FileNotFoundError if file does not exist

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
		values = []

		for line in text:
			line = line.strip()
			if not line or line.startswith('#'):
				continue
			elif line.startswith('[') and line.endswith(']'):
				if values:
					section.input(values)
					values = []

				name = line[1:-1].strip()
				section = self[name]
			elif '=' in line:
				if section is None:
					logger.warn('Parameter outside section: %s', line)
				else:
					key, string = line.split('=', 1)
					values.append((str(key.rstrip()), string.lstrip())) # key is not unicode
			else:
				logger.warn('Could not parse line: %s', line)
		else:
			if values:
				section.input(values)

	def write(self):
		'''Write data and set C{modified} to C{False}'''
		self.file.writelines(self.dump())
		self.set_modified(False)

	def write_async(self):
		'''Write data asynchronously and set C{modified} to C{False}
		@returns: an L{FunctionThread} object
		'''
		func = FunctionThread(
			self.file,
			self.file.writelines,
			self.dump())
		func.start()
		self.set_modified(False)
		return func

	def dump(self):
		'''Serialize the config to a "ini-style" config file.
		@returns: a list of lines with text in "ini-style" formatting
		'''
		lines = []
		def dump_section(name, section):
			try:
				lines.append('[%s]\n' % name)
				for key, value in section.items():
					if not key.startswith('_'):
						lines.append('%s=%s\n' % (key, section.definitions[key].tostring(value)))
				lines.append('\n')
			except:
				logger.exception('Dumping section [%s] failed:\n%r', name, section)

		for name, section in self.items():
			if section and not name.startswith('_'):
				if isinstance(section, list):
					for s in section:
						dump_section(name, s)
				else:
					dump_section(name, section)

		return lines


class HeaderParsingError(Error):
	'''Error when parsing a L{HeadersDict}'''

	description = '''\
Invalid data was found in a block with headers.
This probably means the header block was corrupted
and can not be read correctly.'''

	def __init__(self, line):
		self.msg = 'Invalid header >>%s<<' % line.strip('\n')


class HeadersDict(ControlledDict):
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
		OrderedDict.__init__(self)
		if not text is None:
			self.parse(text)

	def __getitem__(self, k):
		return OrderedDict.__getitem__(self, k.title())

	def __setitem__(self, k, v):
		return OrderedDict.__setitem__(self, k.title(), v)

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
