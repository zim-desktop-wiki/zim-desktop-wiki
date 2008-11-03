# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import re

from zim.fs import *
from zim.formats import *

meta = {
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
		'''FIXME'''
		assert isinstance(input, (File, Buffer))
		page = Element('page')
		para = SubElement(page, 'p')

		file = input.open('r')
		para.text = file.read()
		file.close()

		return ParseTree(page)


class Dumper(DumperClass):

	def dump(self, tree, output):
		'''FIXME'''
		assert isinstance(tree, ParseTree)
		assert isinstance(output, (File, Buffer))
		file = output.open('w')

		for element in tree.getiterator():
			if not element.text is None:
				file.write(element.text)

		file.close()
