# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import re

from zim.fs import *
from zim.formats import *

__format__ = 'plain'


class Parser(ParserClass):

	# TODO parse constructs like *bold* and /italic/ same as in email,
	# but do not remove the "*" and "/", just display text 1:1

	def parse(self, input):
		'''FIXME'''
		assert isinstance(input, (File, Buffer))
		file = input.open('r')

		text = file.read()
		tree = NodeTree()
		tree.append( TextNode(text) )

		file.close()
		return tree


class Dumper(DumperClass):

	def dump(self, tree, output):
		'''FIXME'''
		assert isinstance(tree, NodeTree)
		assert isinstance(output, (File, Buffer))
		file = output.open('w')

		for node in tree.walk():
			assert isinstance(node, TextNode)
			file.write(node.string)

		file.close()
