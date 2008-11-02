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

try:
	import xml.etree.cElementTree as ETree
	from xml.etree.cElementTree import \
		ElementTree, Element, SubElement, TreeBuilder
except:
	#~ debug("Failed loading cElementTree, fall back to ElementTree")
	import xml.etree.ElementTree as ETree
	from xml.etree.ElementTree import \
		ElementTree, Element, SubElement, TreeBuilder

from zim.fs import Buffer


def get_format(name):
	'''Returns the module object for a specific format.'''
	# __import__ has some quirks, soo the reference manual
	mod = __import__('zim.formats.'+name)
	mod = getattr(mod, 'formats')
	mod = getattr(mod, name)
	return mod

def serialize_tree(tree):
	for element in tree.getiterator('h'):
		element.attrib['level'] = str(element.attrib['level'])
	output = Buffer()
	tree.write(output, 'utf8')
	return output.getvalue()

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
			if isinstance(item, basestring):
				for i, p in enumerate( split_re.split(item) ):
					if i%2:
						l.append( func(p) )
					elif len(p) > 0:
						l.append( p )
					else:
						pass
			else:
				l.append(item)
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
