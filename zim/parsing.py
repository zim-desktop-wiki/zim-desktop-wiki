# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains utilities for parsing strings and text'''

import re


def split_quoted_strings(string, unescape=True, strict=True):
	'''Split a word list respecting quotes

	This function always expect full words to be quoted, even if quotes
	appear in the middle of a word, they are considered word
	boundries.

	( XDG Desktop Entry spec says full words must be quoted and
	quotes in a word escaped, but doesn't specifify what to do with
	loose quotes in a string. )

	Also a comma "," is handled specially and is always considered a
	word on it's own.

	@param string: string to split in words
	@param unescape: if C{True} quotes are removed, else they are
	left in place
	@param strict: if C{True} unmatched quotes will cause a C{ValueError}
	to be raised, if C{False} unmatched quotes are ignored.
	@returns: list of strings
	'''
	word_re = Re(r'''
		(	'(\\'|[^'])*' |  # single quoted word
			"(\\"|[^"])*" |  # double quoted word
			[^\s,'"]+     |  # word without spaces and commas
			,                # comma - (allow "words,word"<<)
		)''', re.X)
	string = string.strip()
	words = []
	while word_re.match(string):
		words.append(word_re[0])
		i = word_re.m.end()
		string = string[i:].lstrip()

	if string and strict:
		raise ValueError, 'Unmatched quote'
	elif string:
		words += string.split()

	if unescape:
		words = [unescape_quoted_string(w) for w in words]
	return words


def unescape_quoted_string(string):
	'''Removes quotes from a string and unescapes embedded quotes
	@returns: string
	'''
	escape_re = re.compile(r'(\\(\\)|\\([\'\"]))')
	def replace(m):
		return m.group(2) or m.group(3)
	if (string.startswith('"') or string.startswith("'")) \
	and string[-1] == string[0]:
		string = string[1:-1]
		string = escape_re.sub(replace, string)
	return string

# URL encoding / decoding is a bit more tricky than it seems:
#
# === From man 7 url ===
# Reserved chars:   ; / ? : @ & = + $ ,
# Unreserved chars: A-Z a-z 0-9 - _ . ! ~ * ' ( )
# although heuristics could have a problem with . ! or ' at end of url
# All other chars are not allowed and need escaping
# Unicode chars need to be encoded as utf-8 and then as several escapes
#
# === Usage ===
# Encode all - encode all chars
#   e.g. for encoding parts of a file:// uri
#   for encoding data for mailto:?subject=...
#	return ascii
# Encode path - encode all except /
#   convenience method for file paths
#	return ascii
# Encode readable - encode space & utf-8, keep other escapes
#	for pageview -> external (e.g. clipboard)
#	assume reserved is (still) encoded properly
#	return ascii
# Decode all - decode all chars
#   e.g. for decoding file:// uris
#	return unicode
# Decode readable - decode space, utf-8, keep other escapes
#   for source / external (e.g. clipboard) -> pageview
#	assume it is encoded properly to start with
#	return unicode
#
# space is really just ' ', other whitespace characters like tab or
# newline should not appear in the first place - so do not facilitate
# them.
#
# In wiki source we use fully escaped URLs. In theory we could allow
# for utf-8 characters, but this adds complexity. Also it could break
# external usage of the text files.
#
# === From man 7 utf-8 ===
# * The classic US-ASCII characters are encoded simply as bytes 0x00 to 0x7f
# * All UCS characters > 0x7f are encoded as a multi-byte sequence
#   consisting only of bytes in the range 0x80 to 0xfd, so no ASCII byte
#   can appear as part of another character
# * The bytes 0xfe and 0xff are never used in the UTF-8 encoding.
#
# So checking ranges makes sure utf-8 is really outside of ascii set,
# and does not e.g. include "%".

URL_ENCODE_DATA = 0 # all
URL_ENCODE_PATH = 1	# all except '/'
URL_ENCODE_READABLE = 2 # only space and utf-8

_url_encode_re = re.compile(r'[^A-Za-z0-9\-_\.!~*\'\(\)]') # unreserved
_url_encode_path_re = re.compile(r'[^A-Za-z0-9\-_\.!~*\'\(\)/]') # unreserved + /

def _url_encode(match):
	return '%%%02X' % ord(match.group(0))

def _url_encode_readable(match):
	i = ord(match.group(0))
	if i == 32 or i > 127: # space or utf-8
		return '%%%02X' % i
	else: # do not encode
		return match.group(0)

def url_encode(url, mode=URL_ENCODE_PATH):
	'''Replaces non-standard characters in urls with hex codes.

	Mode can be:
		- C{URL_ENCODE_DATA}: encode all un-safe chars
		- C{URL_ENCODE_PATH}: encode all un-safe chars except '/'
		- C{URL_ENCODE_READABLE}: encode whitespace and all unicode characters

	The mode URL_ENCODE_READABLE can be applied to urls that are already
	encoded because it does not touch the "%" character. The modes
	URL_ENCODE_DATA and URL_ENCODE_PATH can only be applied to strings
	that are known not to be encoded.

	The encoded URL is returned as an ASCII string.
	'''
	url = url.encode('utf-8') # unicode -> utf-8, so encode one byte at a time

	if mode == URL_ENCODE_DATA:
		return _url_encode_re.sub(_url_encode, url)
	elif mode == URL_ENCODE_PATH:
		return _url_encode_path_re.sub(_url_encode, url)
	elif mode == URL_ENCODE_READABLE:
		return _url_encode_re.sub(_url_encode_readable, url)
	else:
		assert False, 'BUG: Unknown url encoding mode'


_url_decode_re = re.compile('%([a-fA-F0-9]{2})')

def _url_decode(match):
	return chr(int(match.group(1), 16))

def _url_decode_readable(match):
	i = int(match.group(1), 16)
	if i == 32 or i > 127: # space or utf-8
		return chr(i)
	else: # do not decode
		return match.group(0)

def url_decode(url, mode=URL_ENCODE_PATH):
	'''Replace url-encoding hex sequences with their proper characters.

	Mode can be:
		- C{URL_ENCODE_DATA}: decode all chars
		- C{URL_ENCODE_PATH}: same as URL_ENCODE_DATA
		- C{URL_ENCODE_READABLE}: decode only whitespace and unicode characters

	The mode C{URL_ENCODE_READABLE} will not decode any other characters,
	so urls decoded with these modes can still contain escape sequences.
	They are safe to use within zim, but should be re-encoded with
	C{URL_ENCODE_READABLE} before handing them to an external program.

	The result is returned as a unicode string.
	'''
	url = url.encode('utf-8') # in case url is already unicode
	try:
		if mode in (URL_ENCODE_DATA, URL_ENCODE_PATH):
			return _url_decode_re.sub(_url_decode, url).decode('utf-8')
		elif mode == URL_ENCODE_READABLE:
			return _url_decode_re.sub(_url_decode_readable, url).decode('utf-8')
		else:
			assert False, 'BUG: Unknown url encoding mode'
	except UnicodeDecodeError:
		# Someone did not exactly follow the recommendations in the spec...
		if mode in (URL_ENCODE_DATA, URL_ENCODE_PATH):
			return _url_decode_re.sub(_url_decode, url)
		elif mode == URL_ENCODE_READABLE:
			return url.replace('%20', ' ')

_parse_date_re = re.compile(r'(\d{1,4})\D(\d{1,2})(?:\D(\d{1,4}))?')

def parse_date(string):
	'''Returns a tuple of (year, month, day) for a date string or None
	if failed to parse the string. Current supported formats:

		- C{dd?-mm?}
		- C{dd?-mm?-yy}
		- C{dd?-mm?-yyyy}
		- C{yyyy-mm?-dd?}

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

	Usage::

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

	def start(self,group=0):
		'''Return the indices of the start of the substring matched by group;
		group defaults to zero (meaning the whole matched substring). Return -1 if
		group exists but did not contribute to the match. See re.matchobject for
		details'''
		return self.m.start(group)

	def end(self,group=0):
		'''Return the indices of the end of the substring matched by group;
		group defaults to zero (meaning the whole matched substring). Return -1 if
		group exists but did not contribute to the match. See re.matchobject for
		details'''
		return self.m.end(group)

# Some often used regexes
is_uri_re = Re('^(\w[\w\+\-\.]*):')
	# "scheme:"
is_url_re = Re('^(\w[\w\+\-\.]*)://')
	# "scheme://"
is_email_re = Re('^(mailto:\S+|[^\s:]+)\@\S+\.\w+$', re.U)
	# "mailto:" address
	# name "@" host
	# but exclude other uris like mid: and cid:
is_path_re = Re(r'^(/|\.\.?[/\\]|~.*[/\\]|[A-Za-z]:\\)')
	# / ~/ ./ ../ ~user/  .\ ..\ ~\ ~user\
	# X:\
is_win32_path_re = Re(r'^[A-Za-z]:[\\/]')
	# X:\ (or X:/)
is_win32_share_re = Re(r'^(\\\\[^\\]+\\.+|smb://)')
	# \\host\share
	# smb://host/share
is_interwiki_re = Re('^(\w[\w\+\-\.]*)\?(.*)', re.U)
	# identifier "?" path
is_interwiki_keyword_re = re.compile('^\w[\w\+\-\.]*$', re.U)


_classes = {'c': r'[^\s"<>\']'} # limit the character class a bit
url_re = Re(r'''(
	\b \w[\w\+\-\.]+:// %(c)s* \[ %(c)s+ \] (?: %(c)s+ [\w/] )?  |
	\b \w[\w\+\-\.]+:// %(c)s+ [\w/]                             |
	\b mailto: %(c)s+ \@ %(c)s* \[ %(c)s+ \] (?: %(c)s+ [\w/] )? |
	\b mailto: %(c)s+ \@ %(c)s+ [\w/]                            |
	\b %(c)s+ \@ %(c)s+ \. \w+ \b
)''' % _classes, re.X | re.U)
	# Full url regex - much more strict then the is_url_re
	# The host name in an uri can be "[hex:hex:..]" for ipv6
	# but we do not want to match "[http://foo.org]"
	# See rfc/3986 for the official -but unpractical- regex


def uri_scheme(link):
	'''Function that returns a scheme for URIs, URLs and email addresses'''
	if is_email_re.match(link):
		return 'mailto'
	elif is_uri_re.match(link):
		# Includes URLs, but also URIs like "mid:", "cid:"
		return is_uri_re[1]
	else:
		return None


def link_type(link):
	'''Function that returns a link type for urls and page links'''
	# More strict than uri_scheme() because page links conflict with
	# URIs without "//" or without "@"
	if is_url_re.match(link):
		if link.startswith('zim+'): type = 'notebook'
		else: type = is_url_re[1]
	elif is_email_re.match(link): type = 'mailto'
	elif '@' in link and (
		link.startswith('mid:') or
		link.startswith('cid:')
	):
		return link[:3]
		# email message uris, see RFC 2392
	elif is_win32_share_re.match(link): type = 'smb'
	elif is_path_re.match(link): type = 'file'
	elif is_interwiki_re.match(link): type = 'interwiki'
	else: type = 'page'
	return type


class TextBuffer(list):
	'''List of strings. Allows you to append arbitrary pieces of text but
	calling get_lines() will recombine or split text into lines. Used by
	parsers that need to output lines but handle smaller pieces of text
	internally.
	'''

	def get_lines(self, end_with_newline=True):
		'''Returns a proper list of lines'''
		lines = ''.join(self).splitlines(True)
		if end_with_newline and lines and not lines[-1].endswith('\n'):
			lines[-1] += '\n'
		return lines

	def prefix_lines(self, prefix):
		'''Prefix each line with string 'prefix'.'''
		lines = self.get_lines(end_with_newline=False)
			# allowing end_with_newline here modifies content
		self[:] = [prefix + line for line in lines]
