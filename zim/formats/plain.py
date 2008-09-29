# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import re

from zim.formats import *

__format__ = 'plain'


class Parser(ParserClass):

	# TODO parse constructs like *bold* and /italic/ same as in email,
	# but do not remove the "*" and "/", just display text 1:1

	def parse(self, file):
		'''FIXME'''
		text = file.read()
		tree = NodeTree()
		tree.append( TextNode(text) )
		return tree


class Dumper(DumperClass):

	def dump(self, tree, file):
		'''FIXME'''
		for node in tree.walk():
			assert isinstance(node, TextNode)
			file.write(node.string)
