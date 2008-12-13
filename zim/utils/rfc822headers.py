# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''This module contians functions to handle headers in the rfc822 format.
It is used both to store meta data in wiki files as for the WWW HTTP interface.

* These routines support rfc822 style header syntax including continuation lines.
* All headers are made case insesitive using string.title().
* The ListDict class is used to store headers to guarantee that reading and
  writing a block preserves the order of the headers.
'''

import re

from zim.utils import ListDict

_is_header_re = re.compile('^([\w\-]+):\s+(.*)')
_not_headers_re = re.compile('^(?!\Z|\s+|[\w\-]+:\s+)', re.M)

def match(text):
	'''Checks if 'text' is a rfc822 stle header block, returns boolean'''
	if not _is_header_re.match(text):
		# first line is not a header
		return False
	elif _not_headers_re.search(text):
		# some line is not a header or a continuation of a header
		return False
	else:
		return True

def parse(text):
	'''Returns a dict (ListDict) with the headers defined in a text block'''
	headers = ListDict()
	header = None
	for line in text.splitlines():
		if line.isspace(): break
		is_header = _is_header_re.match(line)
		if is_header:
			header = is_header.group(1).title()
			value  = is_header.group(2).strip()
			headers[header] = value
		elif not header is None:
			headers[header] += '\n' + line.strip()
	return headers

def format(headers, strict=False):
	'''Takes a dict and returns a block with rfc822 header.

	If strict is set to True lines will be properly terminated with '\r\n'
	isntead of '\n'.
	'''
	buffer = []
	for k, v in headers.items():
		v = v.strip().replace('\n', '\n\t')
		buffer.extend((k, ': ', v, '\n'))
	text = ''.join(buffer)
	if strict:
		text = text.replace('\n', '\r\n')
	return text
