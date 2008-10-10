# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Classes and code snippets used by multiple zim modules'''

import re
import sys

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
		dir = os.path.join(dir, *path)
		if os.path.isdir(dir):
			yield Dir(dir)


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
		return len(self.m.groups())

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
