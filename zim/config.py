# -*- coding: utf8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import sys
import os
import re
import logging

from zim.fs import *
from zim.parsing import TextBuffer, ParsingError

logger = logging.getLogger('zim.config')

# add "data" dir if it is in the same dir as zim.py
# this allows running zim without installation
_data_dirs = []
_scriptdir = os.path.dirname(sys.argv[0])
_data_dir = os.path.join(_scriptdir, 'data')
if os.path.isdir(_data_dir):
	_data_dirs.append(_data_dir)


def data_dirs(*path):
	'''Generator for existings dirs matching path in the zim data dirs.'''
	# TODO prepend XDG data home - env or default
	# TODO append XDG data dirs - check env or use default
	for dir in _data_dirs:
		if path:
			dir = os.path.join(dir, *path)
		if os.path.isdir(dir):
			yield Dir(dir)

def data_file(filename):
	for dir in data_dirs():
		path = os.path.join(dir.path, filename)
		if os.path.isfile(path):
			return File(path)

def data_dir(filename):
	for dir in data_dirs():
		path = os.path.join(dir.path, filename)
		if os.path.isdir(path):
			return Dir(path)

def config_file(filename):
	# TODO XDG logic
	#~ return File([os.environ['HOME'], '.config', 'zim', filename])
	return File([sys.path[0], 'config', filename])


class ListDict(dict):
	'''Class that behaves like a dict but keeps items in same order.
	Used as base class for e.g. for config objects were writing should be
	in a predictable order.
	'''

	def __init__(self):
		self.order = []

	def __setitem__(self, k, v):
		dict.__setitem__(self, k, v)
		if not k in self.order:
			self.order.append(k)

	def items(self):
		for k in self.order:
			yield (k, self[k])

	def set_order(self, order):
		'''Change the order in which items are listed by setting a list
		of keys. Keys not in the list are moved to the end. Keys that are in
		the list but not in the dict will be ignored.
		'''
		oldorder = set(self.order)
		neworder = set(order)
		for k in neworder - oldorder: # keys not in the dict
			order.remove(k)
		for k in oldorder - neworder: # keys not in the list
			order.append(k)
		neworder = set(order)
		assert neworder == oldorder
		self.order = order


class ConfigList(ListDict):
	'''This class supports config files that exist of two columns separated
	by whitespace. It inherits from ListDict to ensure the list remain in
	the same order when it is written to file again. When a file path is set
	for this object it will be used to try reading from any from the config
	and data directories while using the config home directory for writing.
	'''

	fields_re = re.compile(r'(?:\\.|\S)+') # match escaped char or non-whitespace
	escaped_re = re.compile(r'\\(.)') # match single escaped char
	escape_re = re.compile(r'([\s\\])') # match chars to escape

	def __init__(self, path=None, read_all=False):
		'''Constructor calls read() directly if 'path' is given'''
		ListDict.__init__(self)
		if not path is None:
			assert read_all is False, 'TODO'
			self.path = path
			self.read()

	def read(self, file=None):
		'''FIXME'''
		if file is None and self.path:
			# TODO - include data dirs for default config
			# TODO - support read_all options
			file = config_file(self.path)
			if not file.exists():
				return
		self.parse(file.readlines())

	def parse(self, text):
		'''FIXME'''
		if isinstance(text, basestring):
			text = text.splitlines(True)
		
		for line in text:
			line = line.strip()
			if line.isspace() or line.startswith('#'):
				continue
			cols = self.fields_re.findall(line)
			if len(cols) == 1:
				cols[1] = None # empty string in second column
			else:
				assert len(cols) >= 2
				if len(cols) > 2 and not cols[2].startswith('#'):
					logger.warn('trailing data') # FIXME better warning
			for i in range(0, 2):
				cols[i] = self.escaped_re.sub(r'\1', cols[i])
			self[cols[0]] = cols[1]

	def write(self, file=None):
		'''FIXME'''
		if file is None and self.path:
			file = config_file(self.path)
		file.writelines(self.dump())

	def dump(self):
		'''FIXME'''
		text = TextBuffer()
		for k, v in self.items():
			k = self.escape_re.sub(r'\\\1', k)
			v = self.escape_re.sub(r'\\\1', v)
			text.append("%s\t%s\n" % (k, v))
		return text.get_lines()


class ConfigDict(ListDict):
	'''Config object which wraps a dict of dicts.
	These are represented as INI files.
	'''

	def read(self, file):
		'''FIXME'''
		# TODO parse INI style config

	def write(self, file):
		'''FIXME'''
		# TODO write INI style config


class HeadersDict(ListDict):
	'''This class maps a set of headers in the rfc822 format.

	Header names are always kept in "title()" format to ensure
	case-insensitivity.
	'''

	_is_header_re = re.compile('^([\w\-]+):\s+(.*)')
	_is_continue_re = re.compile('^(\s+)')

	def __init__(self, text=None):
		ListDict.__init__(self)
		if not text is None:
			self.append(text)

	def __getitem__(self, k):
		return ListDict.__getitem__(self, k.title())

	def __setitem__(self, k, v):
		return ListDict.__setitem__(self, k.title(), v)

	def append(self, text):
		'''Adds headers defined in 'text' to the dict.

		Raises a ParsingError when 'text' is not a valid header block.
		Trailing whitespace is ignored.
		'''
		header = None
		for line in text.rstrip().splitlines():
			is_header = self._is_header_re.match(line)
			if is_header:
				header = is_header.group(1)
				value  = is_header.group(2)
				self[header] = value.strip()
			elif self._is_continue_re.match(line) and not header is None:
				self[header] += '\n' + line.strip()
			else:
				raise ParsingError, 'Not a valid rfc822 header block'

	def tostring(self, strict=False):
		'''Returns the dict as a rfc822 header block.

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

		return text
