#!/usr/bin/python

'''Base classes for parsers and parse trees

For format modules it is safe to import '*' from this module.

NOTE: To avoid confusion: "headers" refers to meta data, usually in the
form of rfc822 headers at the top of a page. But "heading" refers to a title
or subtitle in the document.
'''

import re

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


class Node(object):
	'''Base class for all parse tree nodes

	Currently empty, but used for instance checking
	'''
	pass



class NodeList(list, Node):
	'''Base for groups of parse tree nodes

	This class masks a list of parse tree nodes, used e.g. to represent
	paragraphs.
	'''

	def dump(self, level=0):
		'''Dump contents to stdout, used for debugging parse trees'''
		print "\t"*level, '('
		for item in self:
			item.dump(level=level+1)
		print "\t"*level, ')'



class NodeTree(NodeList):
	'''Top level element of a parse tree

	This is also a list of parse nodes like NodeList, but adds meta
	data that applies to the whole tree.
	'''

	def __init__(self):
		self.headers = {}

	def dump(self, level=0):
		'''Dump contents to stdout, used for debugging parse trees'''
		print "\t"*level, '>>> NodeTree'
		print "\t"*level, 'Headers:'
		for k, v in self.headers.iteritems():
			print "\t"*(level+1), k, '=', v
		NodeList.dump(self, level=level) # parent class
		print "\t"*level, '<<<'



class TextNode(Node):
	'''Parse tree node containing atomical piece of text'''

	def __init__(self, string, style=None):
		'''Constructor needs at least a piece of text'''
		self.string = string
		self.style = style

	def dump(self, level=0):
		'''Dump contents to stdout, used for debugging parse trees'''
		style = self.style or 'normal'
		print "\t"*level, style, ':', self.string



class LinkNode(TextNode):
	'''Class for link objects'''

	def __init__(self, string, link=None):
		'''Constructor needs at leas a piece of text'''
		self.string = string
		self.link = link

	def dump(self, level=0):
		'''Dump contents to stdout, used for debugging parse trees'''
		pass

class ImageNode(Node):
	'''Class for image objects'''
	pass



class ParserError(Exception):
	'''Exception thrown when the parser chucks up.
	When this exception is raised it will be considered a bug in the parser.
	'''

	# TODO: do something meaningfull in this class

	def __init__(self, block, message):
		self.block = block
		self.message = message

	def __str__(self):
		return '>>>\n'+self.block+'<<<\n'+self.message



class SyntaxError(Exception):
	'''Exception thrown when the parser can not handle the input'''
	pass



class ParserClass(object):
	'''Base class for parsers

	Each format that can be used natively should define a class
	'Parser' which inherits from this base class.
	'''

	def parse_file(self, path):
		'''returns a tree of contents read from path'''
		file = open(path, 'r')
		tree = self.parse(file)
		file.close()
		return tree

	def parse_string(self, string):
		'''parse from string'''
		file = StringIO(string)
		tree = self.parse(file)
		return tree

	header_re = re.compile('^([\w\-]+):\s+(.*)')
	not_headers_re = re.compile('^(?!\Z|\s+|[\w\-]+:\s+)', re.M)

	def matches_headers(self, text):
		"""Checks if 'text' is a rfc822 stle header block.
		If this returns True, 'text' can be parsed by parse_headers().
		"""
		if not self.header_re.match(text):
			# first line is not a header
			return False
		elif self.not_headers_re.search(text):
			# some line is not a header or a continuation of a header
			return False
		else:
			return True

	def parse_headers(self, text):
		'''Returns a dictonary with the headers defined in 'text'.
		Uses rfc822 style header syntax including continuation lines.
		All headers are made case insesitive using string.title().
		'''
		headers = {}
		header = None
		if not self.matches_headers(text):
			raise ParserError(text, 'is not a header block')
		for line in text.splitlines():
			if line.isspace(): break
			is_header = self.header_re.match(line)
			if is_header:
				header = is_header.group(1).title()
					# using title() to make header names case insensitive
				value  = is_header.group(2).strip()
				headers[header] = value
			else:
				headers[header] += line.strip()
		return headers

	def walk_list(self, list, split_re, func):
		'''Convenience function to process a list of strings and Node
		objects.  Node objects will be ignored, but strings are
		splitted using regex 'split_re'.  Each part matched by the
		regex is than replaced by the results of 'func(match)'.
		The list is expanded this way into more strings and objects
		and returned.  This function can be called multiple times to
		match exclusive pieces of formatting.
		'''
		l = []
		for item in list:
			if isinstance(item, Node):
				l.append(item)
				continue

			# item is still a string
			for i, p in enumerate( split_re.split(item) ):
				if i%2:
					l.append( func(p) )
				elif len(p) > 0:
					l.append( p )
				else:
					pass
		return l



class DumperClass(object):
	'''Base class for dumper classes.

	Each format that can be used natively should define a class
	'Dumper' which inherits from this base class.
	'''

	def dump_file(self, tree, path):
		'''Dump to file'''
		file = open(path, 'w')
		self.dump(tree, file)
		file.close()

	def dump_string(self, tree):
		'''Returns string with dump of tree'''
		file = StringIO()
		self.dump(tree, file)
		return file.getvalue()

# vim: tabstop=4
