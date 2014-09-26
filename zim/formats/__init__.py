# -*- coding: utf-8 -*-

# Copyright 2008-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Package with source formats for pages.

Each module in zim.formats should contains exactly one subclass of
DumperClass and exactly one subclass of ParserClass
(optional for export formats). These can be loaded by L{get_parser()}
and L{get_dumper()} respectively. The requirement to have exactly one
subclass per module means you can not import other classes that derive
from these base classes directly into the module.

For format modules it is safe to import '*' from this module.

Parse tree structure
====================

Parse trees are build using the (c)ElementTree module (included in
python 2.5 as xml.etree.ElementTree). It is basically a xml structure
supporting a subset of "html like" tags.

Supported tags:

	- page root element for grouping paragraphs
	- p for paragraphs
	- h for heading, level attribute can be 1..6
	- pre for verbatim paragraphs (no further parsing in these blocks)
	- em for emphasis, rendered italic by default
	- strong for strong emphasis, rendered bold by default
	- mark for highlighted text, renderd with background color or underlined
	- strike for text that is removed, usually renderd as strike through
	- code for inline verbatim text
	- ul for bullet and checkbox lists
	- ol for numbered lists
	- li for list items
	- link for links, attribute href gives the target
	- img for images, attributes src, width, height an optionally href and alt
		- type can be used to control plugin functionality, e.g. type=equation

Unlike html we respect line breaks and other whitespace as is.
When rendering as html use the "white-space: pre" CSS definition to
get the same effect.

Since elements are based on the functional markup instead of visual
markup it is not allowed to nest elements in arbitrary ways.

TODO: allow links to be nested in other elements
TODO: allow strike to have sub elements
TODO: add HR element

If a page starts with a h1 this heading is considered the page title,
else we can fall back to the page name as title.


NOTE: To avoid confusion: "headers" refers to meta data, usually in
the form of rfc822 headers at the top of a page. But "heading" refers
to a title or subtitle in the document.
'''

import re
import string
import logging

import types

from zim.fs import Dir, File
from zim.parsing import link_type, is_url_re, \
	url_encode, url_decode, URL_ENCODE_READABLE, URL_ENCODE_DATA
from zim.parser import Builder
from zim.config import data_file, ConfigDict
from zim.objectmanager import ObjectManager

import zim.plugins


logger = logging.getLogger('zim.formats')

# Needed to determine RTL, but may not be available
# if gtk bindings are not installed
try:
	import pango
except:
	pango = None
	logger.warn('Could not load pango - RTL scripts may look bad')

try:
	import xml.etree.cElementTree as ElementTreeModule
except:  #pragma: no cover
	logger.warn('Could not load cElementTree, defaulting to ElementTree')
	import xml.etree.ElementTree as ElementTreeModule


EXPORT_FORMAT = 1
IMPORT_FORMAT = 2
NATIVE_FORMAT = 4
TEXT_FORMAT = 8 # Used for "Copy As" menu - these all prove "text/plain" mimetype

UNCHECKED_BOX = 'unchecked-box'
CHECKED_BOX = 'checked-box'
XCHECKED_BOX = 'xchecked-box'
BULLET = '*' # FIXME make this 'bullet'

FORMATTEDTEXT = 'zim-tree'
FRAGMENT = 'zim-tree'

HEADING = 'h'
PARAGRAPH = 'p'
VERBATIM_BLOCK = 'pre' # should be same as verbatim
BLOCK = 'div'

IMAGE = 'img'
OBJECT = 'object'

BULLETLIST = 'ul'
NUMBEREDLIST = 'ol'
LISTITEM = 'li'

EMPHASIS = 'emphasis' # TODO change to "em" to be in line with html
STRONG = 'strong'
MARK = 'mark'
VERBATIM = 'code'
STRIKE = 'strike'
SUBSCRIPT = 'sub'
SUPERSCRIPT = 'sup'

LINK = 'link'
TAG = 'tag'
ANCHOR = 'anchor'

BLOCK_LEVEL = (PARAGRAPH, HEADING, VERBATIM_BLOCK, BLOCK, OBJECT, IMAGE, LISTITEM)


def increase_list_iter(listiter):
	'''Get the next item in a list for a numbered list
	E.g if C{listiter} is C{"1"} this function returns C{"2"}, if it
	is C{"a"} it returns C{"b"}.
	@param listiter: the current item, either an integer number or
	single letter
	@returns: the next item, or C{None}
	'''
	try:
		i = int(listiter)
		return str(i + 1)
	except ValueError:
		try:
			i = string.letters.index(listiter)
			return string.letters[i+1]
		except ValueError: # listiter is not a letter
			return None
		except IndexError: # wrap to start of list
			return string.letters[0]

def encode_xml(text):
	'''Encode text such that it can be used in xml
	@param text: label text as string
	@returns: encoded text
	'''
	return text.replace('&', '&amp;').replace('>', '&gt;').replace('<', '&lt;').replace('"', '&quot;').replace("'", '&apos;')


def list_formats(type):
	if type == EXPORT_FORMAT:
		return ['HTML','LaTeX', 'Markdown (pandoc)', 'RST (sphinx)']
	elif type == TEXT_FORMAT:
		return ['Text', 'Wiki', 'Markdown (pandoc)', 'RST (sphinx)']
	else:
		assert False, 'TODO'


def canonical_name(name):
	# "HTML" -> html
	# "Markdown (pandoc)" -> "markdown"
	# "Text" -> "plain"
	name = name.lower()
	if ' ' in name:
		name, _ = name.split(' ', 1)
	if name == 'text': return 'plain'
	else: return name


def get_format(name):
	'''Returns the module object for a specific format.'''
	# If this method is removes, class names in formats/*.py can be made more explicit
	#~ print 'DEPRECATED: get_format() is deprecated in favor if get_parser() and get_dumper()'
	return get_format_module(name)


def get_format_module(name):
	'''Returns the module object for a specific format

	@param name: the format name
	@returns: a module object
	'''
	return zim.plugins.get_module('zim.formats.' + canonical_name(name))


def get_parser(name, *arg, **kwarg):
	'''Returns a parser object instance for a specific format

	@param name: format name
	@param arg: arguments to pass to the parser object
	@param kwarg: keyword arguments to pass to the parser object

	@returns: parser object instance (subclass of L{ParserClass})
	'''
	module = get_format_module(name)
	klass = zim.plugins.lookup_subclass(module, ParserClass)
	return klass(*arg, **kwarg)


def get_dumper(name, *arg, **kwarg):
	'''Returns a dumper object instance for a specific format

	@param name: format name
	@param arg: arguments to pass to the dumper object
	@param kwarg: keyword arguments to pass to the dumper object

	@returns: dumper object instance (subclass of L{DumperClass})
	'''
	module = get_format_module(name)
	klass = zim.plugins.lookup_subclass(module, DumperClass)
	return klass(*arg, **kwarg)


class ParseTree(object):
	'''Wrapper for zim parse trees.'''

	# No longer derives from ElementTree, internals are not private

	# TODO, also remove etree args from init
	# TODO, rename to FormattedText

	def __init__(self, *arg, **kwarg):
		self._etree = ElementTreeModule.ElementTree(*arg, **kwarg)
		self._object_cache = {}

	@property
	def hascontent(self):
		'''Returns True if the tree contains any content at all.'''
		root = self._etree.getroot()
		return bool(root.getchildren()) or (root.text and not root.text.isspace())

	@property
	def ispartial(self):
		'''Returns True when this tree is a segment of a page
		(like a copy-paste buffer).
		'''
		return self._etree.getroot().attrib.get('partial', False)

	@property
	def israw(self):
		'''Returns True when this is a raw tree (which is representation
		of TextBuffer, but not really valid).
		'''
		return self._etree.getroot().attrib.get('raw', False)

	def extend(self, tree):
		# Do we need a deepcopy here ?
		myroot = self._etree.getroot()
		otherroot = tree._etree.getroot()
		if otherroot.text:
			children = myroot.getchildren()
			if children:
				last = children[-1]
				last.tail = (last.tail or '') + otherroot.text
			else:
				myroot.text = (myroot.text or '') + otherroot.text

		for element in otherroot.getchildren():
			myroot.append(element)

		return self

	__add__ = extend

	def fromstring(self, string):
		'''Set the contents of this tree from XML representation.'''
		parser = ElementTreeModule.XMLTreeBuilder()
		parser.feed(string)
		root = parser.close()
		self._etree._setroot(root)
		return self # allow ParseTree().fromstring(..)

	def tostring(self):
		'''Serialize the tree to a XML representation'''
		from cStringIO import StringIO

		# Parent dies when we have attributes that are not a string
		for element in self._etree.getiterator('*'):
			for key in element.attrib.keys():
				element.attrib[key] = str(element.attrib[key])

		xml = StringIO()
		xml.write("<?xml version='1.0' encoding='utf-8'?>\n")
		ElementTreeModule.ElementTree.write(self._etree, xml, 'utf-8')
		return xml.getvalue()

	def copy(self):
		# By using serialization we are absolutely sure all refs are new
		xml = self.tostring()
		try:
			return ParseTree().fromstring(xml)
		except:
			print ">>>", xml, "<<<"
			raise

	def _get_heading_element(self, level=1):
		root = self._etree.getroot()
		children = root.getchildren()
		if root.text and not root.text.isspace():
			return None

		if children:
			first = children[0]
			if first.tag == 'h' and first.attrib['level'] >= level:
				return first
		return None

	def get_heading_level(self):
		heading_elem = self._get_heading_element()
		if heading_elem is not None:
			return int(heading_elem.attrib['level'])
		else:
			return None

	def get_heading(self, level=1):
		heading_elem = self._get_heading_element(level)
		if heading_elem is not None:
			return heading_elem.text
		else:
			return ""

	def set_heading(self, text, level=1):
		'''Set the first heading of the parse tree to 'text'. If the tree
		already has a heading of the specified level or higher it will be
		replaced. Otherwise the new heading will be prepended.
		'''
		heading = self._get_heading_element(level)
		if heading is not None:
			heading.text = text
		else:
			root = self._etree.getroot()
			heading = ElementTreeModule.Element('h', {'level': level})
			heading.text = text
			heading.tail = root.text
			root.text = None
			root.insert(0, heading)

	def pop_heading(self, level=-1):
		'''If the tree starts with a heading, remove it and any trailing
		whitespace.
		Will modify the tree.
		@returns: a 2-tuple of text and heading level or C{(None, None)}
		'''
		root = self._etree.getroot()
		children = root.getchildren()
		if root.text and not root.text.isspace():
			return None, None

		if children:
			first = children[0]
			if first.tag == 'h':
				mylevel = int(first.attrib['level'])
				if level == -1 or mylevel <= level:
					root.remove(first)
					if first.tail and not first.tail.isspace():
						root.text = first.tail # Keep trailing text
					return first.text, mylevel
				else:
					return None, None
			else:
				return None, None
		else:
			return None, None

	def cleanup_headings(self, offset=0, max=6):
		'''Change the heading levels throughout the tree. This makes sure that
		al headings are nested directly under their parent (no gaps in the
		levels of the headings). Also you can set an offset for the top level
		and a max depth.
		'''
		path = []
		for heading in self._etree.getiterator('h'):
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

	def resolve_images(self, notebook=None, path=None):
		'''Resolves the source files for all images relative to a page path	and
		adds a '_src_file' attribute to the elements with the full file path.
		'''
		if notebook is None:
			for element in self._etree.getiterator('img'):
				filepath = element.attrib['src']
				element.attrib['_src_file'] = File(filepath)
		else:
			for element in self._etree.getiterator('img'):
				filepath = element.attrib['src']
				element.attrib['_src_file'] = notebook.resolve_file(element.attrib['src'], path)

	def unresolve_images(self):
		'''Undo effect of L{resolve_images()}, mainly intended for
		testing.
		'''
		for element in self._etree.getiterator('img'):
			if '_src_file' in element.attrib:
				element.attrib.pop('_src_file')

	def encode_urls(self, mode=URL_ENCODE_READABLE):
		'''Calls encode_url() on all links that contain urls.
		See zim.parsing for details. Modifies the parse tree.
		'''
		for link in self._etree.getiterator('link'):
			href = link.attrib['href']
			if is_url_re.match(href):
				link.attrib['href'] = url_encode(href, mode=mode)
				if link.text == href:
					link.text = link.attrib['href']

	def decode_urls(self, mode=URL_ENCODE_READABLE):
		'''Calls decode_url() on all links that contain urls.
		See zim.parsing for details. Modifies the parse tree.
		'''
		for link in self._etree.getiterator('link'):
			href = link.attrib['href']
			if is_url_re.match(href):
				link.attrib['href'] = url_decode(href, mode=mode)
				if link.text == href:
					link.text = link.attrib['href']

	def count(self, text):
		'''Returns the number of occurences of 'text' in this tree.'''
		count = 0
		for element in self._etree.getiterator():
			if element.text:
				count += element.text.count(text)
			if element.tail:
				count += element.tail.count(text)

		return count

	def countre(self, regex):
		'''Returns the number of matches for a regular expression
		in this tree.
		'''
		count = 0
		for element in self._etree.getiterator():
			if element.text:
				newstring, n = regex.subn('', element.text)
				count += n
			if element.tail:
				newstring, n = regex.subn('', element.tail)
				count += n

		return count

	def get_ends_with_newline(self):
		'''Checks whether this tree ends in a newline or not'''
		return self._get_element_ends_with_newline(self._etree.getroot())

	def _get_element_ends_with_newline(self, element):
			if element.tail:
				return element.tail.endswith('\n')
			elif element.tag in ('li', 'h'):
				return True # implicit newline
			else:
				children = element.getchildren()
				if children:
					return self._get_element_ends_with_newline(children[-1]) # recurs
				elif element.text:
					return element.text.endswith('\n')
				else:
					return False # empty element like image

	def visit(self, visitor):
		'''Visit all nodes of this tree

		@note: If the visitor modifies the attrib dict on nodes, this
		will modify the tree.

		@param visitor: a L{Visitor} or L{Builder} object
		'''
		try:
			self._visit(visitor, self._etree.getroot())
		except VisitorStop:
			pass

	def _visit(self, visitor, node):
		try:
			if len(node): # Has children
				visitor.start(node.tag, node.attrib)
				if node.text:
					visitor.text(node.text)
				for child in node:
					self._visit(visitor, child) # recurs
					if child.tail:
						visitor.text(child.tail)
				visitor.end(node.tag)
			else:
				visitor.append(node.tag, node.attrib, node.text)
		except VisitorSkip:
			pass

	def find(self, tag):
		'''Find first occurence of C{tag} in the tree
		@returns: a L{Node} object or C{None}
		'''
		for elt in self.findall(tag):
			return elt # return first
		else:
			return None

	def findall(self, tag):
		'''Find all occurences of C{tag} in the tree
		@param tag: tag name
		@returns: yields L{Node} objects
		'''
		for elt in self._etree.getiterator(tag):
			yield Element.new_from_etree(elt)

	def replace(self, tag, func):
		'''Modify the tree by replacing all occurences of C{tag}
		by the return value of C{func}.

		@param tag: tag name
		@param func: function to generate replacement values.
		Function will be called as::

			func(node)

		Where C{node} is a L{Node} object representing the subtree.
		If the function returns another L{Node} object or modifies
		C{node} and returns it, the subtree will be replaced by this
		new node.
		If the function raises L{VisitorSkip} the replace is skipped.
		If the function raises L{VisitorStop} the replacement of all
		nodes will stop.
		'''
		try:
			self._replace(self._etree.getroot(), tag, func)
		except VisitorStop:
			pass

	def _replace(self, elt, tag, func):
		# Two-step replace in order to do items in order
		# of appearance.
		replacements = []
		for i, child in enumerate(elt):
			if child.tag == tag:
				try:
					replacement = func(Element.new_from_etree(child))
				except VisitorSkip:
					pass
				else:
					replacements.append((i, child, replacement))
			elif len(child):
				self._replace(child, tag, func) # recurs
			else:
				pass


		if replacements:
			self._do_replace(elt, replacements)

	def _do_replace(self, elt, replacements):
		offset = 0 # offset due to replacements
		for i, child, node in replacements:
			i += offset
			if node is None or len(node) == 0:
				# Remove element
				tail = child.tail
				elt.remove(child)
				if tail:
					self._insert_text(elt, i, tail)
				offset -= 1
			elif isinstance(node, Element):
				# Just replace elements
				newchild = self._node_to_etree(node)
				newchild.tail = child.tail
				elt[i] = newchild
			elif isinstance(node, DocumentFragment):
				# Insert list of elements and text
				tail = child.tail
				elt.remove(child)
				offset -= 1
				for item in node:
					if isinstance(item, basestring):
						self._insert_text(elt, i, item)
					else:
						assert isinstance(item, Element)
						elt.insert(i, self._node_to_etree(item))
						i += 1
						offset += 1
				if tail:
					self._insert_text(elt, i, tail)
			else:
				raise TypeError, 'BUG: invalid replacement result'

	@staticmethod
	def _node_to_etree(node):
		builder = ParseTreeBuilder()
		node.visit(builder)
		return builder._b.close()

	def _insert_text(self, elt, i, text):
		if i == 0:
			if elt.text:
				elt.text += text
			else:
				elt.text = text
		else:
			prev = elt[i-1]
			if prev.tail:
				prev.tail += text
			else:
				prev.tail = text

	def get_objects(self, type=None):
		'''Generator that yields all custom objects in the tree,
		or all objects of a certain type.
		@param type: object type to return or C{None} to get all
		@returns: yields objects (as provided by L{ObjectManager})
		'''
		for elt in self._etree.getiterator(OBJECT):
			if type and elt.attrib.get('type') != type:
				pass
			else:
				obj = self._get_object(elt)
				if obj is not None:
					yield obj

	def _get_object(self, elt):
		## TODO optimize using self._object_cache or new API for
		## passing on objects in the tree
		type = elt.attrib.get('type')
		if elt.tag == OBJECT and type:
			return ObjectManager.get_object(type, elt.attrib, elt.text)
		else:
			return None


class VisitorStop(Exception):
	'''Exception to be raised to cancel a visitor action'''
	pass


class VisitorSkip(Exception):
	'''Exception to be raised when the visitor should skip a leaf node
	and not decent into it.
	'''
	pass


class Visitor(object):
	'''Conceptual opposite of a builder, but with same API.
	Used to walk nodes in a parsetree and call callbacks for each node.
	See e.g. L{ParseTree.visit()}.
	'''

	def start(self, tag, attrib=None):
		'''Start formatted region

		Visitor objects can raise two exceptions in this method
		to influence the tree traversal:

		  1. L{VisitorStop} will cancel the current parsing, but without
			 raising an error. So code implementing a visit method should
			 catch this.
		  2. L{VisitorSkip} can be raised when the visitor wants to skip
			 a node, and should prevent the implementation from further
			 decending into this node

		@note: If the visitor modifies the attrib dict on nodes, this
		will modify the tree. If this is not intended, the implementation
		needs to take care to copy the attrib to break the reference.

		@param tag: the tag name
		@param attrib: optional dict with attributes
		@implementation: optional for subclasses
		'''
		pass

	def text(self, text):
		'''Append text
		@param text: text to be appended as string
		@implementation: optional for subclasses
		'''
		pass

	def end(self, tag):
		'''End formatted region
		@param tag: the tag name
		@raises AssertionError: when tag does not match current state
		@implementation: optional for subclasses
		'''
		pass

	def append(self, tag, attrib=None, text=None):
		'''Convenience function to open a tag, append text and close
		it immediatly.

		Can raise L{VisitorStop} or L{VisitorSkip}, see C{start()}
		for the conditions.

		@param tag: the tag name
		@param attrib: optional dict with attributes
		@param text: formatted text
		@implementation: optional for subclasses, default implementation
		calls L{start()}, L{text()}, and L{end()}
		'''
		self.start(tag, attrib)
		if text is not None:
			self.text(text)
		self.end(tag)


class ParseTreeBuilder(Builder):
	'''Builder object that builds a L{ParseTree}'''

	def __init__(self, partial=False):
		self.partial = partial
		self._b = ElementTreeModule.TreeBuilder()
		self.stack = [] #: keeps track of current open elements
		self._last_char = None

	def get_parsetree(self):
		'''Returns the constructed L{ParseTree} object.
		Can only be called once, after calling this method the object
		can not be re-used.
		'''
		root = self._b.close()
		if self.partial:
			root.attrib['partial'] = True
		return zim.formats.ParseTree(root)

	def start(self, tag, attrib=None):
		self._b.start(tag, attrib)
		self.stack.append(tag)
		if tag in BLOCK_LEVEL:
			self._last_char = None

	def text(self, text):
		self._last_char = text[-1]

		# FIXME hack for backward compat
		if self.stack and self.stack[-1] in (HEADING, LISTITEM):
			text = text.strip('\n')

		self._b.data(text)

	def end(self, tag):
		if tag != self.stack[-1]:
			raise AssertionError, 'Unmatched tag closed: %s' % tag

		if tag in BLOCK_LEVEL:
			if self._last_char is not None and not self.partial:
				#~ assert self._last_char == '\n', 'Block level text needs to end with newline'
				if self._last_char != '\n' and tag not in (HEADING, LISTITEM):
					self._b.data('\n')
					# FIXME check for HEADING LISTITME for backward compat

			# TODO if partial only allow missing \n at end of tree,
			# delay message and trigger if not followed by get_parsetree ?

		self._b.end(tag)
		self.stack.pop()

		# FIXME hack for backward compat
		if tag == HEADING:
			self._b.data('\n')

		self._last_char = None

	def append(self, tag, attrib=None, text=None):
		if tag in BLOCK_LEVEL:
			if text and not text.endswith('\n'):
				text += '\n'

		# FIXME hack for backward compat
		if text and tag in (HEADING, LISTITEM):
			text = text.strip('\n')

		self._b.start(tag, attrib)
		if text:
			self._b.data(text)
		self._b.end(tag)

		# FIXME hack for backward compat
		if tag == HEADING:
			self._b.data('\n')

		self._last_char = None


count_eol_re = re.compile(r'\n+\Z')
split_para_re = re.compile(r'((?:^[ \t]*\n){2,})', re.M)


class OldParseTreeBuilder(object):
	'''This class supplies an alternative for xml.etree.ElementTree.TreeBuilder
	which cleans up the tree on the fly while building it. The main use
	is to normalize the tree that is produced by the editor widget, but it can
	also be used on other "dirty" interfaces.

	This builder takes care of the following issues:
		- Inline tags ('emphasis', 'strong', 'h', etc.) can not span multiple lines
		- Tags can not contain only whitespace
		- Tags can not be empty (with the exception of the 'img' tag)
		- There should be an empty line before each 'h', 'p' or 'pre'
		  (with the exception of the first tag in the tree)
		- The 'p' and 'pre' elements should always end with a newline ('\\n')
		- Each 'p', 'pre' and 'h' should be postfixed with a newline ('\\n')
		  (as a results 'p' and 'pre' are followed by an empty line, the
		  'h' does not end in a newline itself, so it is different)
		- Newlines ('\\n') after a <li> alement are removed (optional)
		- The element '_ignore_' is silently ignored
	'''

	## TODO TODO this also needs to be based on Builder ##

	def __init__(self, remove_newlines_after_li=True):
		assert remove_newlines_after_li, 'TODO'
		self._stack = [] # stack of elements for open tags
		self._last = None # last element opened or closed
		self._data = [] # buffer with data
		self._tail = False # True if we are after an end tag
		self._seen_eol = 2 # track line ends on flushed data
			# starts with "2" so check is ok for first top level element

	def start(self, tag, attrib=None):
		if tag == '_ignore_':
			return self._last
		elif tag == 'h':
			self._flush(need_eol=2)
		elif tag in ('p', 'pre'):
			self._flush(need_eol=1)
		else:
			self._flush()
		#~ print 'START', tag

		if tag == 'h':
			if not (attrib and 'level' in attrib):
				logger.warn('Missing "level" attribute for heading')
				attrib = attrib or {}
				attrib['level'] = 1
		elif tag == 'link':
			if not (attrib and 'href' in attrib):
				logger.warn('Missing "href" attribute for link')
				attrib = attrib or {}
				attrib['href'] = "404"
		# TODO check other mandatory properties !

		if attrib:
			self._last = ElementTreeModule.Element(tag, attrib)
		else:
			self._last = ElementTreeModule.Element(tag)

		if self._stack:
			self._stack[-1].append(self._last)
		else:
			assert tag == 'zim-tree', 'root element needs to be "zim-tree"'
		self._stack.append(self._last)

		self._tail = False
		return self._last

	def end(self, tag):
		if tag == '_ignore_':
			return None
		elif tag in ('p', 'pre'):
			self._flush(need_eol=1)
		else:
			self._flush()
		#~ print 'END', tag

		self._last = self._stack[-1]
		assert self._last.tag == tag, \
			"end tag mismatch (expected %s, got %s)" % (self._last.tag, tag)
		self._tail = True

		if len(self._stack) > 1 and not (tag == 'img' or tag == 'object'
		or (self._last.text and not self._last.text.isspace())
		or self._last.getchildren() ):
			# purge empty tags
			if self._last.text and self._last.text.isspace():
				self._append_to_previous(self._last.text)

			empty = self._stack.pop()
			self._stack[-1].remove(empty)
			children = self._stack[-1].getchildren()
			if children:
				self._last = children[-1]
				if not self._last.tail is None:
					self._data = [self._last.tail]
					self._last.tail = None
			else:
				self._last = self._stack[-1]
				self._tail = False
				if not self._last.text is None:
					self._data = [self._last.text]
					self._last.text = None

			return empty

		else:
			return self._stack.pop()

	def data(self, text):
		assert isinstance(text, basestring)
		self._data.append(text)

	def _flush(self, need_eol=0):
		# need_eol makes sure previous data ends with \n

		#~ print 'DATA:', self._data
		text = ''.join(self._data)

		# Fix trailing newlines
		if text:
			m = count_eol_re.search(text)
			if m: self._seen_eol = len(m.group(0))
			else: self._seen_eol = 0

		if need_eol > self._seen_eol:
			text += '\n' * (need_eol - self._seen_eol)
			self._seen_eol = need_eol

		# Fix prefix newlines
		if self._tail and self._last.tag in ('h', 'p') \
		and not text.startswith('\n'):
			if text:
				text = '\n' + text
			else:
				text = '\n'
				self._seen_eol = 1
		elif self._tail and self._last.tag == 'li' \
		and text.startswith('\n'):
			text = text[1:]
			if not text.strip('\n'):
				self._seen_eol -=1

		if text:
			assert not self._last is None, 'data seen before root element'
			self._data = []

			# Tags that are not allowed to have newlines
			if not self._tail and self._last.tag in (
			'h', 'emphasis', 'strong', 'mark', 'strike', 'code'):
				# assume no nested tags in these types ...
				if self._seen_eol:
					text = text.rstrip('\n')
					self._data.append('\n' * self._seen_eol)
					self._seen_eol = 0
				lines = text.split('\n')

				for line in lines[:-1]:
					assert self._last.text is None, "internal error (text)"
					assert self._last.tail is None, "internal error (tail)"
					if line and not line.isspace():
						self._last.text = line
						self._last.tail = '\n'
						attrib = self._last.attrib.copy()
						self._last = ElementTreeModule.Element(self._last.tag, attrib)
						self._stack[-2].append(self._last)
						self._stack[-1] = self._last
					else:
						self._append_to_previous(line + '\n')

				assert self._last.text is None, "internal error (text)"
				self._last.text = lines[-1]
			else:
				# TODO split paragraphs

				if self._tail:
					assert self._last.tail is None, "internal error (tail)"
					self._last.tail = text
				else:
					assert self._last.text is None, "internal error (text)"
					self._last.text = text
		else:
			self._data = []


	def close(self):
		assert len(self._stack) == 0, 'missing end tags'
		assert not self._last is None and self._last.tag == 'zim-tree', 'missing root element'
		return self._last

	def _append_to_previous(self, text):
		'''Add text before current element'''
		parent = self._stack[-2]
		children = parent.getchildren()[:-1]
		if children:
			if children[-1].tail:
				children[-1].tail = children[-1].tail + text
			else:
				children[-1].tail = text
		else:
			if parent.text:
				parent.text = parent.text + text
			else:
				parent.text = text


class ParserClass(object):
	'''Base class for parsers

	Each format that can be used natively should define a class
	'Parser' which inherits from this base class.
	'''

	def parse(self, input):
		'''ABSTRACT METHOD: needs to be overloaded by sub-classes.

		This method takes a text or an iterable with lines and returns
		a ParseTree object.
		'''
		raise NotImplementedError

	@classmethod
	def parse_image_url(self, url):
		'''Parse urls style options for images like "foo.png?width=500" and
		returns a dict with the options. The base url will be in the dict
		as 'src'.
		'''
		i = url.find('?')
		if i > 0:
			attrib = {'src': url[:i]}
			for option in url[i+1:].split('&'):
				if option.find('=') == -1:
					logger.warn('Mal-formed options in "%s"' , url)
					break

				k, v = option.split('=', 1)
				if k in ('width', 'height', 'type', 'href'):
					if len(v) > 0:
						value = url_decode(v, mode=URL_ENCODE_DATA)
						attrib[str(k)] = value # str to avoid unicode key
				else:
					logger.warn('Unknown attribute "%s" in "%s"', k, url)
			return attrib
		else:
			return {'src': url}



import collections

DumperContextElement = collections.namedtuple('DumperContextElement', ('tag', 'attrib', 'text'))
	# FIXME unify this class with a generic Element class (?)


class DumperClass(Visitor):
	'''Base class for dumper classes. Dumper classes serialize the content
	of a parse tree back to a text representation of the page content.
	Therefore this class implements the visitor API, so it can be
	used with any parse tree implementation or parser object that supports
	this API.

	To implement a dumper class, you need to define handlers for all
	tags that can appear in a page. Tags that are represented by a simple
	prefix and postfix string can be defined in the dictionary C{TAGS}.
	For example to define the italic tag in html output the dictionary
	should contain a definition like: C{EMPHASIS: ('<i>', '</i>')}.

	For tags that require more complex logic you can define a method to
	format the tag. Typical usage is to format link attributes in such
	a method. The method name should be C{dump_} + the name of the tag,
	e.g. C{dump_link()} for links (see the constants with tag names for
	the other tags). Such a sump method will get 3 arguments: the tag
	name itself, a dictionary with the tag attributes and a list of
	strings that form the tag content. The method should return a list
	of strings that represents the formatted text.

	This base class takes care of a stack of nested formatting tags and
	when a tag is closed either picks the appropriate prefix and postfix
	from C{TAGS} or calls the corresponding C{dump_} method. As a result
	tags are serialized depth-first.

	@ivar linker: the (optional) L{Linker} object, used to resolve links
	@ivar template_options: a L{ConfigDict} with options that may be set
	in a template (so inherently not safe !) to control the output style.
	Formats using this need to define the supported keys in the dict
	C{TEMPLATE_OPTIONS}.
	@ivar context: the stack of open tags maintained by this class. Can
	be used in C{dump_} methods to inspect the parent scope of the
	format. Elements on this stack have "tag", "attrib" and "text"
	attributes. Keep in mind that the parent scope is not yet complete
	when a tag is serialized.
	'''

	TAGS = {} #: dict mapping formatting tags to 2-tuples of a prefix and a postfix string

	TEMPLATE_OPTIONS = {} #: dict mapping ConfigDefinitions for template options

	def __init__(self, linker=None, template_options=None):
		self.linker = linker
		self.template_options = ConfigDict(template_options)
		self.template_options.define(self.TEMPLATE_OPTIONS)
		self.context = []
		self._text = []

	def dump(self, tree):
		'''Convenience methods to dump a given tree.
		@param tree: a parse tree object that supports a C{visit()} method
		'''
		# FIXME - issue here is that we need to reset state - should be in __init__
		self._text = []
		self.context = [DumperContextElement(None, None, self._text)]
		tree.visit(self)
		if len(self.context) != 1:
			raise AssertionError, 'Unclosed tags on tree: %s' % self.context[-1].tag
		#~ import pprint; pprint.pprint(self._text)
		return self.get_lines() # FIXME - maybe just return text ?

	def get_lines(self):
		'''Return the dumped content as a list of lines
		Should only be called after closing the top level element
		'''
		return u''.join(self._text).splitlines(1)

	def start(self, tag, attrib=None):
		if attrib:
			attrib = attrib.copy() # Ensure dumping does not change tree
		self.context.append(DumperContextElement(tag, attrib, []))

	def text(self, text):
		assert not text is None
		if self.context[-1].tag != OBJECT:
			text = self.encode_text(self.context[-1].tag, text)
		self.context[-1].text.append(text)

	def end(self, tag):
		if not tag or tag != self.context[-1].tag:
			raise AssertionError, 'Unexpected tag closed: %s' % tag
		_, attrib, strings = self.context.pop()
		if tag in self.TAGS:
			assert strings, 'Can not append empty %s element' % tag
			start, end = self.TAGS[tag]
			strings.insert(0, start)
			strings.append(end)
		elif tag in FORMATTEDTEXT:
			pass
		else:
			try:
				method = getattr(self, 'dump_'+tag)
			except AttributeError:
				raise AssertionError, 'BUG: Unknown tag: %s' % tag

			strings = method(tag, attrib, strings)
			#~ try:
				#~ u''.join(strings)
			#~ except:
				#~ print "BUG: %s returned %s" % ('dump_'+tag, strings)

		if strings is not None:
			self.context[-1].text.extend(strings)

	def append(self, tag, attrib=None, text=None):
		strings = None
		if tag in self.TAGS:
			assert text is not None, 'Can not append empty %s element' % tag
			start, end = self.TAGS[tag]
			text = self.encode_text(tag, text)
			strings = [start, text, end]
		elif tag == FORMATTEDTEXT:
			if text is not None:
				strings = [self.encode_text(tag, text)]
		else:
			if attrib:
				attrib = attrib.copy() # Ensure dumping does not change tree

			try:
				method = getattr(self, 'dump_'+tag)
			except AttributeError:
				raise AssertionError, 'BUG: Unknown tag: %s' % tag

			if text is None:
				strings = method(tag, attrib, None)
			elif tag == OBJECT:
				strings = method(tag, attrib, [text])
			else:
				strings = method(tag, attrib, [self.encode_text(tag, text)])

		if strings is not None:
			self.context[-1].text.extend(strings)

	def encode_text(self, tag, text):
		'''Optional method to encode text elements in the output

		@note: Do not apply text encoding in the C{dump_} methods, the
		list of strings given there may contain prefix and postfix
		formatting of nested tags.

		@param tag: formatting tag
		@param text: text to be encoded
		@returns: encoded text
		@implementation: optional, default just returns unmodified input
		'''
		return text

	def prefix_lines(self, prefix, strings):
		'''Convenience method to wrap a number of lines with e.g. an
		indenting sequence.
		@param prefix: a string to prefix each line
		@param strings: a list of pieces of text
		@returns: a new list of lines, each starting with prefix
		'''
		lines = u''.join(strings).splitlines(1)
		return [prefix + l for l in lines]

	def dump_object(self, tag, attrib, strings=None):
		'''Dumps object using proper ObjectManager'''
		format = str(self.__class__.__module__).split('.')[-1]
		if 'type' in attrib:
			obj = ObjectManager.get_object(attrib['type'], attrib, u''.join(strings))
			output = obj.dump(format, self, self.linker)
			if isinstance(output, basestring):
				return [output]
			elif output is not None:
				return output

		return self.dump_object_fallback(tag, attrib, strings)

		# TODO put content in attrib, use text for caption (with full recursion)
		# See img

	def dump_object_fallback(self, tag, attrib, strings=None):
		'''Method to serialize objects that do not have their own
		handler for this format.
		@implementation: must be implemented in sub-classes
		'''
		raise NotImplementedError

	def isrtl(self, text):
		'''Check for Right To Left script
		@param text: the text to check
		@returns: C{True} if C{text} starts with characters in a
		RTL script, or C{None} if direction is not determined.
		'''
		if pango is None:
			return None

		# It seems the find_base_dir() function is not documented in the
		# python language bindings. The Gtk C code shows the signature:
		#
		#     pango.find_base_dir(text, length)
		#
		# It either returns a direction, or NEUTRAL if e.g. text only
		# contains punctuation but no real characters.

		dir = pango.find_base_dir(text, len(text))
		if dir == pango.DIRECTION_NEUTRAL:
			return None
		else:
			return dir == pango.DIRECTION_RTL


class BaseLinker(object):
	'''Base class for linker objects
	Linker object translate links in zim pages to (relative) URLs.
	This is used when exporting data to resolve links.
	Relative URLs start with "./" or "../" and should be interpreted
	in the same way as in HTML. Both URLs and relative URLs are
	already URL encoded.
	'''

	def link(self, link):
		'''Returns an url for a link in a zim page
		This method is used to translate links of any type.

		@param link: link to be translated
		@returns: url, uri, or relative path
		context of this linker
		@implementation: must be implemented by child classes
		'''
		raise NotImplementedError

	def img(self, src):
		'''Returns an url for image file 'src'
		@implementation: must be implemented by child classes
		'''
		raise NotImplementedError

	#~ def icon(self, name):
		#~ '''Returns an url for an icon
		#~ @implementation: must be implemented by child classes
		#~ '''
		#~ raise NotImplementedError

	def resource(self, path):
		'''Return an url for template resources
		@implementation: must be implemented by child classes
		'''
		raise NotImplementedError

	def resolve_source_file(self, link):
		'''Find the source file for an attachment
		Used e.g. by the latex format to find files for equations to
		be inlined. Do not use this method to resolve links, the file
		given here might be temporary and is not guaranteed to be
		available after the export.
		@returns: a L{File} object or C{None} if no file was found
		@implementation: must be implemented by child classes
		'''
		raise NotImplementedError

	def page_object(self, path):
		'''Turn a L{Path} object in a relative link or URI'''
		raise NotImplementedError

	def file_object(self, file):
		'''Turn a L{File} object in a relative link or URI
		@implementation: must be implemented by child classes
		'''
		raise NotImplementedError


class StubLinker(BaseLinker):
	'''Linker used for testing - just gives back the link as it was
	parsed. DO NOT USE outside of testing.
	'''

	def __init__(self, source_dir=None):
		self.source_dir = source_dir

	def link(self, link):
		type = link_type(link)
		if type == 'mailto' and not link.startswith('mailto:'):
			return 'mailto:' + link
		elif type == 'interwiki':
			return 'interwiki:' + link
		else:
			return link

	def img(self, src):
		return src

	#~ def icon(self, name):
		#~ return 'icon:' + name

	def resource(self, path):
		return path

	def resolve_source_file(self, link):
		if self.source_dir:
			return self.source_dir.file(link)
		else:
			return None

	def page_object(self, path):
		return path.name

	def file_object(self, file):
		return file.name



class Node(list):
	'''Base class for DOM-like access to the document structure.
	@note: This class is not optimized for keeping large structures
	in memory.

	@ivar tag: tag name
	@ivar attrib: dict with attributes
	'''

	__slots__ = ('tag', 'attrib')

	def __init__(self, tag, attrib=None, *content):
		self.tag = tag
		self.attrib = attrib
		if content:
			self.extend(content)

	@classmethod
	def new_from_etree(klass, elt):
		obj = klass(elt.tag, dict(elt.attrib))
		if elt.text:
			obj.append(elt.text)
		for child in elt:
			subnode = klass.new_from_etree(child) # recurs
			obj.append(subnode)
			if child.tail:
				obj.append(child.tail)
		return obj

	def get(self, key, default=None):
		if self.attrib:
			return self.attrib.get(key, default)
		else:
			return default

	def set(self, key, value):
		if not self.attrib:
			self.attrib = {}
		self.attrib[key] = value

	def append(self, item):
		if isinstance(item, DocumentFragment):
			list.extend(self, item)
		else:
			list.append(self, item)

	def gettext(self):
		'''Get text as string
		Ignores any markup and attributes and simply returns textual
		content.
		@note: do _not_ use as replacement for exporting to plain text
		@returns: string
		'''
		strings = self._gettext()
		return u''.join(strings)

	def _gettext(self):
		strings = []
		for item in self:
			if isinstance(item, basestring):
				strings.append(item)
			else:
				strings.extend(item._gettext())
		return strings

	def toxml(self):
		strings = self._toxml()
		return u''.join(strings)

	def _toxml(self):
		strings = []
		if self.attrib:
			strings.append('<%s' % self.tag)
			for key in sorted(self.attrib):
				strings.append(' %s="%s"' % (key, encode_xml(self.attrib[key])))
			strings.append('>')
		else:
			strings.append("<%s>" % self.tag)

		for item in self:
			if isinstance(item, basestring):
				strings.append(encode_xml(item))
			else:
				strings.extend(item._toxml())

		strings.append("</%s>" % self.tag)
		return strings

	__repr__ = toxml

	def visit(self, visitor):
		if len(self) == 1 and isinstance(self[0], basestring):
			visitor.append(self.tag, self.attrib, self[0])
		else:
			visitor.start(self.tag, self.attrib)
			for item in self:
				if isinstance(item, basestring):
					visitor.text(item)
				else:
					item.visit(visitor)
			visitor.end(self.tag)


class Element(Node):
	'''Element class for DOM-like access'''
	pass


class DocumentFragment(Node):
	'''Document fragment class for DOM-like access'''

	def __init__(self, *content):
		self.tag = FRAGMENT
		self.attrib = None
		if content:
			self.extend(content)
