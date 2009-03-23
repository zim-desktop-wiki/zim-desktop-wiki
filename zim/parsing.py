# -*- coding: utf8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import re

class ParsingError(Exception):
	pass


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

	# TODO, mimic complete interface for regex object including
	#       split, findall, finditer, etc.

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

	def sublist(self, repl, list):
		'''This method is similar to "sub()" in that it substitutes regex
		matches with the result of calling the argument "repl" with the
		Re object as argument. The difference is that this function takes a
		list as argument and executes the substitution for all strings in the
		list while ignoring any non-string items. Also it does not substitute
		the results in the string, but expands to a list where each part is
		either a piece of the original string or the result of calling "repl".
		This method is useful to build a tokenizer. The method "repl" can
		return token objects and the resulting list of strings and tokens can
		be fed through this method several times for different regexes.
		'''
		result = []
		for item in list:
			if isinstance(item, basestring):
				pos = 0
				for m in self.p.finditer(item):
					start, end = m.span()
					if start > pos:
						result.append(item[pos:start])
					pos = end
					self.m = m
					result.append(repl(self))
				if pos < len(item):
					result.append(item[pos:])
			else:
				result.append(item)
		return result

# Some often used regexes
is_url_re = Re('^(\w[\w\+\-\.]+)://')
is_email_re = Re('^mailto:|^\S+\@\S+\.\w+$')
is_path_re = Re('.*/') # FIXME - any better check ?
is_interwiki_re = Re('^(\w[\w\+\-\.]+)\?(.*)')

def link_type(link):
	'''Function that retuns a link type for urls and page links'''
	if is_url_re.match(link): type = is_url_re[1]
	elif is_email_re.match(link): type = 'mailto'
	elif is_path_re.match(link): type = 'file'
	else: type = 'page'
	# TODO interwiki
	return type
