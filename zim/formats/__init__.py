# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Package with source formats for pages.

For format modules it is safe to import '*' from this module.


Parse trees are build using the (c)ElementTree module (included in
python 2.5 as xml.etree.ElementTree). It is basically a xml structure
supporting a subset of "html like" tags.

Supported tags:

* page root element for grouping paragraphs
* p for paragraphs
* h for heading, level attribute can be 1..6
* pre for verbatim paragraphs (no further parsing in these blocks)
* em for emphasis, rendered italic by default
* strong for strong emphasis, rendered bold by default
* mark for highlighted text, renderd with background color or underlined
* strike for text that is removed, usually renderd as strike through
* code for inline verbatim text
* ul for bullet lists
* .. for checkbox lists
* li for list items
* link for links, attribute href gives the target
* img for images, attributes src, width, height an optionally href
	* any text set on these elements should be rendered as alt
	* class can be used to control plugin functionality, e.g. class=latex-equation

Unless html we respect line breaks and other whitespace as is.
When rendering as html use the "white-space: pre" CSS definition to
get the same effect.

Since elements are based on the functional markup instead of visual
markup it is not allowed to nest elements in arbitrary ways.

TODO: allow links to be nested in other elements
TODO: allow strike to have sub elements
TODO: allow classes to set hints for visual rendering and other interaction
TODO: add HR element
TODO: ol for numbered lists

If a page starts with a h1 this heading is considered the page title,
else we can fall back to the page name as title.


NOTE: To avoid confusion: "headers" refers to meta data, usually in
the form of rfc822 headers at the top of a page. But "heading" refers
to a title or subtitle in the document.
'''

import re

try:
	import xml.etree.cElementTree as ElementTreeModule
	from xml.etree.cElementTree import \
		Element, SubElement, TreeBuilder
except:  # pragma: no cover
	import xml.etree.ElementTree as ElementTreeModule
	from xml.etree.ElementTree import \
		Element, SubElement, TreeBuilder

from zim.fs import Buffer
from zim.utils import ListDict


def get_format(name):
	'''Returns the module object for a specific format.'''
	# __import__ has some quirks, see the reference manual
	mod = __import__('zim.formats.'+name)
	mod = getattr(mod, 'formats')
	mod = getattr(mod, name)
	return mod


class ParseTree(ElementTreeModule.ElementTree):
	'''Wrapper for zim parse trees, derives from ElementTree.'''

	def fromstring(self, string):
		'''Set the contents of this tree from XML representation.'''
		parser = ElementTreeModule.XMLTreeBuilder()
		parser.feed(string)
		root = parser.close()
		self._setroot(root)
		return self # allow ParseTree().fromstring(..)

	def tostring(self):
		'''Serialize the tree to a XML representation.'''

		# Parent dies when we have attributes that are not a string
		for heading in self.getiterator('h'):
			heading.attrib['level'] = str(heading.attrib['level'])

		xml = Buffer()
		xml.write("<?xml version='1.0' encoding='utf-8'?>\n")
		ElementTreeModule.ElementTree.write(self, xml, 'utf-8')
		return xml.getvalue()

	def write(*a):
		'''Writing to file is not implemented, use tostring() instead'''
		raise NotImplementedError

	def parse(*a):
		'''Parsing from file is not implemented, use fromstring() instead'''
		raise NotImplementedError

	def cleanup_headings(self, offset=0, max=6):
		'''Change the heading levels throughout the tree. This makes sure that
		al headings are nested directly under their parent (no gaps in the
		levels of the headings). Also you can set an offset for the top level
		and a max depth.
		'''
		path = []
		for heading in self.getiterator('h'):
			level = int(heading.attrib['level'])
			# find parent header in path using old level
			while path and path[-1][0] >= level:
				path.pop()
			if not path:
				newlevel = offset+1
			else:
				newlevel = path[-1][1] + 1
			if newlevel > max:
				newlevel = max
			heading.attrib['level'] = newlevel
			path.append((level, newlevel))


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
		headers = ListDict()
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
