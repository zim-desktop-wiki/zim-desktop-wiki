# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Classes and code snippets used by multiple zim modules'''

import re
import sys
import os

from zim.fs import *

# scan python module path for dirs called "data"
# FIXME limit to zim specific part of the path ?
_data_dirs = []
for dir in sys.path:
	dir = os.path.join(dir, 'data')
	if os.path.isdir(dir):
		_data_dirs.append(dir)


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
		file = os.path.join(dir.path, filename)
		if os.path.isfile(file):
			return File(file)

def config_file(filename):
	# TODO XDG logic
	return File([os.environ['HOME'], '.config', 'zim', filename])

def split_quoted_strings(string, unescape=True):
	'''Split a word list respecting quotes.'''
	word_re = Re(r'''
		(	'(\\'|[^'])*' |  # single quoted word
			"(\\"|[^"])*" |  # double quoted word
			\S+              # word without spaces
		)''', re.X)
	string = string.strip()
	words = []
	while word_re.match(string):
		words.append(word_re[1])
		i = word_re.m.end()
		string = string[i:].lstrip()
	assert not string
	if unescape:
		words = map(unescape_quoted_string, words)
	return words


def unescape_quoted_string(string):
	'''Removes quotes from a string and unescapes embedded quotes.'''
	escape_re = re.compile(r'(\\(\\)|\\([\'\"]))')
	def replace(m):
		return m.group(2) or m.group(3)
	if string.startswith('"') or string.startswith("'"):
		string = string[1:-1]
		string = escape_re.sub(replace, string)
	return string


class Re(object):
	'''Wrapper around regex pattern objects which memorizes the
	last match object and gives list access to it's capturing groups.
	See module re for regex docs.

	Usage:

		my_re = Re('^(\w[\w\+\-\.]+)\?(.*)')

		if my_re.match(string):
			print my_re[1], my_re[2]
	'''

	__slots__ = ('p', 'm') # pattern and match objects

	def __init__(self, pattern, flags=0):
		'''Constructor takes same arguments as re.compile()'''
		self.p = re.compile(pattern, flags)
		self.m = None

	# We could implement __eq__ here to get more Perlish syntax
	# for matching. However that would make code using this class
	# less readable for Python adepts. Therefore keep using
	# match() and search() and do not go for to much overloading.

	def __len__(self):
		if self.m is None:
			return 0
		return len(self.m.groups())+1

	def __getitem__(self, i):
		if self.m is None:
			raise IndexError
		return self.m.group(i)

	def match(self, string):
		'''Same as re.match()'''
		self.m = self.p.match(string)
		return self.m

	def search(self, string):
		'''Same as re.search()'''
		self.m = self.p.search(string)
		return self.m

# Some often used regexes
is_url_re   = Re('^(\w[\w\+\-\.]+)://')
is_email_re = Re('^mailto:|^\S+\@\S+\.\w+$')

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
		assert isinstance(file, (File, Buffer))

		fh = file.open('r')
		for line in fh:
			line = line.strip()
			if line.isspace() or line.startswith('#'):
				continue
			cols = self.fields_re.findall(line)
			if len(cols) == 1:
				cols[1] = None # empty string in second column
			else:
				assert len(cols) >= 2
				if len(cols) > 2 and not cols[2].startswith('#'):
					print 'WARNING: trailing data' # FIXME better warning
			for i in range(0, 2):
				cols[i] = self.escaped_re.sub(r'\1', cols[i])
			self[cols[0]] = cols[1]
		fh.close()

	def write(self, file=None):
		'''FIXME'''
		if file is None and self.path:
			file = config_file(self.path)
		assert isinstance(file, (File, Buffer))

		fh = file.open('w')
		for k, v in self.items():
			k = self.escape_re.sub(r'\\\1', k)
			v = self.escape_re.sub(r'\\\1', v)
			fh.write("%s\t%s\n" % (k, v))
		fh.close()


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
