# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains functions for encoding/decoding strings and URLs'''

import re


def _escape(match):
	char = match.group(0)
	if char == '\n':
		return '\\n'
	if char == '\r':
		return '\\r'
	elif char == '\t':
		return '\\t'
	else:
		return '\\' + char


def escape_string(string, chars=''):
	'''Escape special characters with a backslash
	Escapes newline, tab, backslash itself and any characters in C{chars}
	'''
	return re.sub('[\n\r\t\\\\%s]' % chars, _escape, string)


def _unescape(match):
	char = match.group(0)[-1]
	if char == 'n':
		return '\n'
	elif char == 't':
		return '\t'
	else:
		return char


def unescape_string(string):
	'''Unescape backslash escapes in string
	Recognizes C{\\n} and C{\\t} for newline and tab respectively,
	otherwise keeps the literal character
	'''
	return re.sub('\\\\.', _unescape, string)


def split_escaped_string(string, char):
	'''Split string on C{char} while respecting backslash escapes'''
	parts = []
	trailing_backslash = False
	for piece in string.split(char):
		if trailing_backslash:
			parts[-1] = parts[-1] + char + piece
		else:
			parts.append(piece)
		m = re.search('\\\\+$', piece)
		trailing_backslash = m and len(m.group(0)) % 2 # uneven number of backslashes
	return parts


_word_re = re.compile(r'''
	(	'(\\'|[^'])*' |  # single quoted word
		"(\\"|[^"])*" |  # double quoted word
		[^\s'"]+         # word without spaces or quotes
	)''', re.X)


def split_quoted_strings(string: str) -> list[str]:
	'''Split a word list respecting quotes, does not remove the quotes

	Allow both double and single quotes

	This function always expect full words to be quoted, even if quotes
	appear in the middle of a word, they are considered word
	boundries.
	'''
	string = string.strip()
	words = []
	m = _word_re.match(string)
	while m:
		words.append(m.group(0))
		i = m.end()
		string = string[i:].lstrip()
		m = _word_re.match(string)

	if string:
		words += string.split() # unmatched quote ?

	return [w for w in words if w]


def unescape_quoted_string(string: str) -> str:
	'''Removes quotes from a string and unescapes embedded quotes'''
	if not string:
		return string
	elif string[0] in ('"', "'") and string[-1] == string[0]:
		string = string[1:-1]
	return unescape_string(string)


def encode_xml_text(text: str|None) -> str:
	'''Encode text such that it can be used in xml or html attributes
	Encodes the following characters: `& < >`
	'''
	return text.replace('&', '&amp;').replace('>', '&gt;').replace('<', '&lt;') if text else ''


def encode_xml_attrib(text: str|None) -> str:
	'''Encode text such that it can be used in xml or html attributes
	Encodes the following characters: `& < > " '`
	'''
	return text.replace('&', '&amp;').replace('>', '&gt;').replace('<', '&lt;').replace('"', '&quot;').replace("'", '&apos;') if text else ''


_xml_chars = {'amp': '&', 'gt': '>', 'lt': '<', 'quot': '"', 'apos': "'"}
_xml_decode_func = lambda m: _xml_chars[m.group(1)]
_xml_decode_re = re.compile(r'&(\w+);')

def decode_xml(xml: str) -> str:
	'''Decode xml or html quoted text
	NOTE: Does not a full decoding, only undoes the effect of C{encode_html_text()} or C{encode_html_attrib()}
	'''
	return _xml_decode_re.sub(_xml_decode_func, xml)


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

import codecs

URL_ENCODE_DATA = 0 # all
URL_ENCODE_PATH = 1	# all except '/'
URL_ENCODE_READABLE = 2 # only space and utf-8

_url_encode_re = re.compile(r'[^A-Za-z0-9\-_.~]') # unreserved (see rfc3986)
_url_encode_path_re = re.compile(r'[^A-Za-z0-9\-_.~/]') # unreserved + /


def _url_encode_on_error(error):
	# Note we (implicitly) support encoding and decoding here..
	data = error.object[error.start:error.end]
	if isinstance(data, str):
		data = data.encode('UTF-8')
	replace = ''.join('%%%02X' % b for b in data)
	return replace, error.end

codecs.register_error('urlencode', _url_encode_on_error)

def _url_encode(match):
	data = bytes(match.group(0), 'UTF-8')
	return ''.join('%%%02X' % b for b in data)

def _url_encode_readable(match):
	i = ord(match.group(0))
	if i == 32 or i > 127: # space or utf-8
		return _url_encode(match)
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

	The encoded URL is a string containing only ASCII characters
	'''
	assert isinstance(url, str)
	if mode == URL_ENCODE_DATA:
		return _url_encode_re.sub(_url_encode, url)
	elif mode == URL_ENCODE_PATH:
		return _url_encode_path_re.sub(_url_encode, url)
	elif mode == URL_ENCODE_READABLE:
		return _url_encode_re.sub(_url_encode_readable, url)
	else:
		assert False, 'BUG: Unknown url encoding mode'


# All ASCII codes <= 127 start with %0 .. %7
_url_bytes_decode_re = re.compile('(%[a-fA-F0-9]{2})+')
_url_decode_ascii_re = re.compile('(%[0-7][a-fA-F0-9])+')
_url_decode_unicode_bytes_re = re.compile(b'(%[a-fA-F89][a-fA-F0-9])+')

def _url_decode(match):
	hexstring = match.group()
	ords = [int(hexstring[i + 1:i + 3], 16) for i in range(0, len(hexstring), 3)]
	return bytes(ords).decode('UTF-8')

def _url_decode_bytes(match):
	hexstring = match.group()
	ords = [int(hexstring[i + 1:i + 3], 16) for i in range(0, len(hexstring), 3)]
	return bytes(ords)

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

	This method will only decode non-ascii byte codes when the _whole_ byte
	equivalent of the URL is in valid UTF-8 decoding. Else it is assumed the
	encoding was done in another format and the decoding fails silently
	for these byte sequences.
	'''
	assert isinstance(url, str)
	# First pass on ascii bytes
	if mode == URL_ENCODE_READABLE:
		url = url.replace('%20', ' ')
	else:
		url = _url_decode_ascii_re.sub(_url_decode, url)

	# Then try UTF-8 bytes
	try:
		data = _url_decode_unicode_bytes_re.sub(_url_decode_bytes, url.encode('UTF-8'))
		url = data.decode('UTF-8')
	except UnicodeDecodeError:
		pass

	return url
