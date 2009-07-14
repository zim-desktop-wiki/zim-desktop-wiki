# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''This module handles parsing and dumping input in plain text'''

import re

from zim.formats import *
from zim.parsing import TextBuffer

info = {
	'name':  'Plain text',
	'mime':  'text/plain',
	'read':	  True,
	'write':  True,
	'import': True,
	'export': True,
}


class Parser(ParserClass):

	# TODO parse constructs like *bold* and /italic/ same as in email,
	# but do not remove the "*" and "/", just display text 1:1
	# idem for linking urls etc.

	def parse(self, input):
		if isinstance(input, basestring):
			input = input.splitlines(True)

		page = Element('page')
		para = SubElement(page, 'p')
		para.text = ''.join(input)

		return ParseTree(page)


class Dumper(DumperClass):

	def dump(self, tree):
		assert isinstance(tree, ParseTree)

		output = TextBuffer()
		for element in tree.getiterator():
			if not element.text is None:
				output.append(element.text)

		return output.get_lines()
