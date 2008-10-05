# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Package with source formats for pages.

For format modules it is safe to import '*' from this module.

NOTE: To avoid confusion: "headers" refers to meta data, usually in
the form of rfc822 headers at the top of a page. But "heading" refers
to a title or subtitle in the document.

----
Top level parse tree must be of type NodeTree. Each Item in NodeTree
can be either a NodeList to group a paragraph, a TextNode containing
whitespace between the paragraphs, a HeaderNode or an ImageNode.

Each nodelist should exists of one or more TextNode, LinkNode or
ImageNode items. HeaderNodes are not allowed here, also no nested
ListNodes.

Each TextNode has exactly one style property.
'''

import re

from zim.fs import Buffer


def get_format(name):
	'''Returns the module object for a specific format.'''
	# __import__ has some quirks, soo the reference manual
	mod = __import__('zim.formats.'+name)
	mod = getattr(mod, 'formats')
	mod = getattr(mod, name)
	assert mod.__format__ == name
	return mod


class Node(object):
	'''Base class for all parse tree nodes

	Currently empty, but used for instance checking
	'''

	# set empty slot list here, else optimising slots in
	# cild classes is useless
	__slots__ = []


class NodeList(list, Node):
	'''Base for groups of parse tree nodes

	This class masks a list of parse tree nodes, used e.g. to
	represent paragraphs.
	'''

	def __str__(self):
		txt = u'<para>\n'
		for item in self:
			txt += item.__str__()
		txt += u'</para>\n'
		return txt

	def walk(self):
		'''Generator to walk node tree recursively.
		Flattens the tree and only iterates the end nodes.
		'''
		for node in self:
			if isinstance(node, NodeList):
				for n in node.walk(): # recurs
					yield n
			else:
				yield node


class NodeTree(NodeList):
	'''Top level element of a parse tree

	This is also a list of parse nodes like NodeList, but adds
	meta data that applies to the whole tree.
	'''

	def __init__(self, list=None):
		if not list is None:
			self.extend(list)
		self.headers = {}

	def __str__(self):
		txt = u'<page>\n'
		for k, v in self.headers.iteritems():
			txt += u'<meta name="%s">%s</meta>' % (k, v)
		for item in self:
			txt += item.__str__()
		txt += u'</page>\n'
		return txt


class TextNode(Node):
	'''Parse tree node containing atomical piece of text'''

	__slots__ = ('string', 'style')

	def __init__(self, string, style=None):
		'''Constructor needs at least a piece of text'''
		self.string = string
		self.style = style

	def __str__(self, level=0):
		if self.style:
			return u'<text style="%s">%s</text>\n' % (self.style, self.string)
		else:
			return u'<text>%s</text>\n' % self.string


class HeadingNode(TextNode):
	'''FIXME'''

	__slots__ = ('level',)

	def __init__(self, level, string):
		'''FIXME'''
		assert 1 <= level <= 5
		self.string = string
		self.level = level

	def __str__(self):
		return u'<head lvl="%i">%s</head>\n' % (self.level, self.string)


class LinkNode(TextNode):
	'''Class for link objects'''

	__slots__ = ('link',)

	def __init__(self, text=None, link=None):
		'''FIXME'''
		self.string = text or link
		if link:
			self.link = link
		else:
			self.link = text

	def __str__(self):
		return u'<link href="%s">%s</link>\n' % (self.link, self.string)


class ImageNode(LinkNode):
	'''Class for image objects'''

	__slots__ = ('src',)

	def __init__(self, src, text='', link=None):
		'''FIXME'''
		self.src = src
		self.string = text
		self.link = link   # no default link like in LinkNode

	def __str__(self):
		return u'<img href="%s">%s</img>\n' % (self.link, self.string)


class ParserClass(object):
	'''Base class for parsers

	Each format that can be used natively should define a class
	'Parser' which inherits from this base class.
	'''

	def __init__(self, page):
		'''FIXME'''
		self.page = page

	def parse(self, file):
		'''FIXME'''
		raise NotImplementedError

	header_re = re.compile('^([\w\-]+):\s+(.*)')
	not_headers_re = re.compile('^(?!\Z|\s+|[\w\-]+:\s+)', re.M)

	def matches_rfc822_headers(self, text):
		'''Checks if 'text' is a rfc822 stle header block. If this
		returns True, 'text' can be parsed by parse_rfc822_headers().
		'''
		if not self.header_re.match(text):
			# first line is not a header
			return False
		elif self.not_headers_re.search(text):
			# some line is not a header or a continuation of a header
			return False
		else:
			return True

	def parse_rfc822_headers(self, text):
		'''Returns a dictonary with the headers defined in 'text'.
		Uses rfc822 style header syntax including continuation lines.
		All headers are made case insesitive using string.title().
		'''
		headers = {}
		header = None
		assert self.matches_rfc822_headers(text), 'Not a header block'
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

	def __init__(self, page):
		'''FIXME'''
		self.page = page

	def dump(self, tree, file):
		'''FIXME'''
		raise NotImplementedError

	def dump_rfc822_headers(self, headers):
		'''FIXME'''
		assert isinstance(headers, dict)
		# TODO figure out how to keep headers in proper order
		text = u''
		for k, v in headers.items():
			v = v.strip()
			v = '\n\t'.join( v.split('\n') )
			text += k+': '+v+'\n'
		if text:
			text += '\n' # empty line at end of headers
		return text

# vim: tabstop=4
