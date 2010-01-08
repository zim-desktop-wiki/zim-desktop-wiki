# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

'''This module contains utilities for parsing strings and text'''

import re


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


_url_encode_re = re.compile(r'[^A-Za-z0-9\-\_\.\!\~\*\'\(\)\/\:]')
	# url encoding - char set from man uri(7), see relevant rfc
	# added '/' and ':' to char set for readability of uris
_url_decode_re = re.compile('%([a-fA-F0-9]{2})')

_unencoded_url_re = re.compile('\s|%(?![a-fA-F0-9]{2})')
	# Not sure if everybody else out there uses the same char set,
	# but whitespace in an url is a sure sign it is not encoded.
	# (Also whitespace is the most problematic for wiki syntax...)
	# Otherwise seeing a "%" without hex behind it also a good sign.

def url_encode(url):
	'''Replaces non-standard characters in urls with hex codes.
	This function uses some heuristics to detect when an url is encoded
	already and avoid double-encoding it.
	'''
	url = url.encode('utf-8') # unicode -> utf-8
	if not ('%' in url and not _unencoded_url_re.search(url)):
		url = _url_encode_re.sub(lambda m: '%%%X' % ord(m.group(0)), url)
	return url


def url_decode(url):
	'''Replace url-encoding hex sequences with their proper characters.
	This function uses some heuristics to detect when an url is not
	encoded in the first place already and avoid double-decoding it.
	'''
	if '%' in url and not _unencoded_url_re.search(url):
		url = _url_decode_re.sub(lambda m: chr(int(m.group(1), 16)), url)
	url = url.decode('utf-8') # utf-8 -> unicode
	return url


_parse_date_re = re.compile(r'(\d{1,4})\D(\d{1,2})(?:\D(\d{1,4}))?')

def parse_date(string):
	'''Returns a tuple of (year, month, day) for a date string or None
	if failed to parse the string. Current supported formats:

		dd?-mm?
		dd?-mm?-yy
		dd?-mm?-yyyy
		yyyy-mm?-dd?

	Where '-' can be replaced by any separator. Any preceding or
	trailing text will be ignored (so we can parse calendar page names
	correctly).

	TODO: Some setting to prefer US dates with mm-dd instead of dd-mm
	TODO: More date formats ?
	'''
	m = _parse_date_re.search(string)
	if m:
		d, m, y = m.groups()
		if len(d) == 4: y, m, d = d, m, y
		if not d:
			return None # yyyy-mm not supported

		if not y:
			# Guess year, based on time delta
			from datetime import date
			today = date.today()
			if today.month - int(m) >= 6:
				y = today.year + 1
			else:
				y = today.year
		else:
			y = int(y)
			if   y < 50:   y += 2000
			elif y < 1000: y += 1900

		return tuple(map(int, (y, m, d)))
	else:
		return None


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

	__slots__ = ('r', 'p', 'm') # regex, pattern and match objects

	def __init__(self, pattern, flags=0):
		'''Constructor takes same arguments as re.compile()'''
		self.r = pattern
		self.p = re.compile(pattern, flags)
		self.m = None

	# We could implement __eq__ here to get more Perlish syntax
	# for matching. However that would make code using this class
	# less readable for Python adepts. Therefore keep using
	# match() and search() and do not go for too much overloading.

	def __str__(self):
		return self.r

	def __repr__(self):
		return '<%s: %s>' % (self.__class__.__name__, self.r)

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
	# scheme "://"
is_email_re = Re('^mailto:|^\S+\@\S+\.\w+$')
	# "mailto:" address
	# name "@" host
is_path_re = Re(r'^(/|\.\.?[/\\]|~.*[/\\]|[A-Z]:\\)')
	# / ~/ ./ ../ ~user/  .\ ..\ ~\ ~user\
	# X:\
is_win32_path_re = Re(r'^[A-Z]:[\\/]')
	# X:\ (or X:/)
is_win32_share_re = Re(r'^(\\\\[^\\]+\\.+|smb://)')
	# \\host\share
	# smb://host/share
is_interwiki_re = Re('^(\w[\w\+\-\.]+)\?(.*)')
	# identifyer "?" path

_classes = {'c': r'[^\s"<>\']'} # limit the character class a bit
url_re = Re(r'''(
	\b \w[\w\+\-\.]+:// %(c)s* \[ %(c)s+ \] (?: %(c)s+ [\w/] )?  |
	\b \w[\w\+\-\.]+:// %(c)s+ [\w/]                             |
	\b mailto: %(c)s+ \@ %(c)s* \[ %(c)s+ \] (?: %(c)s+ [\w/] )? |
	\b mailto: %(c)s+ \@ %(c)s+ [\w/]                            |
	\b %(c)s+ \@ %(c)s+ \. \w+ \b
)''' % _classes, re.X)
	# Full url regex - much more strict then the is_url_re
	# The host name in an uri can be "[hex:hex:..]" for ipv6
	# but we do not want to match "[http://foo.org]"
	# See rfc/3986 for the official -but unpractical- regex

def link_type(link):
	'''Function that retuns a link type for urls and page links'''
	if is_url_re.match(link): type = is_url_re[1]
	elif is_email_re.match(link): type = 'mailto'
	elif is_win32_share_re.match(link): type = 'smb'
	elif is_path_re.match(link): type = 'file'
	elif is_interwiki_re.match(link): type = 'interwiki'
	else: type = 'page'
	return type


class TextBuffer(list):
	'''List of strings. Allows you to append arbitry pieces of text but
	calling get_lines() will recombine or split text into lines. Used by
	parsers that need to output lines but handle smaller pieces of text
	internally.
	'''

	def get_lines(self):
		'''Returns a proper list of lines'''
		lines = ''.join(self).splitlines(True)
		if lines and not lines[-1].endswith('\n'):
			lines[-1] += '\n'
		return lines

	def prefix_lines(self, prefix):
		'''Prefix each line with string 'prefix'.'''
		lines = self.get_lines()
		self[:] = [prefix + line for line in lines]

