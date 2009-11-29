# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''This module handles parsing and dumping input in plain text'''

import re

from zim.formats import *
from zim.parsing import TextBuffer, url_re

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

	def parse(self, input):
		if isinstance(input, basestring):
			input = input.splitlines(True)

		input = url_re.sublist(
			lambda match: ('link', {'href':match[1]}, match[1]) , input)


		builder = TreeBuilder()
		builder.start('zim-tree')

		for item in input:
			if isinstance(item, tuple):
				tag, attrib, text = item
				builder.start(tag, attrib)
				builder.data(text)
				builder.end(tag)
			else:
				builder.data(item)

		builder.end('zim-tree')
		return ParseTree(builder.close())


class Dumper(DumperClass):

	def dump(self, tree):
		assert isinstance(tree, ParseTree)

		output = TextBuffer()
		for element in tree.getiterator():
			if not element.text is None:
				output.append(element.text)
			if not element.tail is None:
				output.append(element.tail)

		return output.get_lines()
