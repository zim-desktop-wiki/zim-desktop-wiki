# -*- coding: utf-8 -*-

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

Unlike html we respect line breaks and other whitespace as is.
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
import logging

from zim.fs import Dir
from zim.parsing import link_type, is_url_re, url_encode, url_decode
from zim.config import data_file


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
	from xml.etree.cElementTree import \
		Element, SubElement, TreeBuilder
except:  # pragma: no cover
	logger.warn('Could not load cElementTree, defaulting to ElementTree')
	import xml.etree.ElementTree as ElementTreeModule
	from xml.etree.ElementTree import \
		Element, SubElement, TreeBuilder


EXPORT_FORMAT = 1
IMPORT_FORMAT = 2
NATIVE_FORMAT = 4

UNCHECKED_BOX = 'unchecked-box'
CHECKED_BOX = 'checked-box'
XCHECKED_BOX = 'xchecked-box'
BULLET = '*'


def list_formats(type):
	if type == EXPORT_FORMAT:
		return ['HTML']
	else:
		assert False, 'TODO'


def get_format(name):
	'''Returns the module object for a specific format.'''
	# __import__ has some quirks, see the reference manual
	name = name.lower()
	mod = __import__('zim.formats.'+name)
	mod = getattr(mod, 'formats')
	mod = getattr(mod, name)
	return mod


class ParseTree(ElementTreeModule.ElementTree):
	'''Wrapper for zim parse trees, derives from ElementTree.'''

	@property
	def hascontent(self):
		'''Returns True if the tree contains any content at all.'''
		root = self.getroot()
		return bool(root.getchildren() or root.text)

	def fromstring(self, string):
		'''Set the contents of this tree from XML representation.'''
		parser = ElementTreeModule.XMLTreeBuilder()
		parser.feed(string)
		root = parser.close()
		self._setroot(root)
		return self # allow ParseTree().fromstring(..)

	def tostring(self):
		'''Serialize the tree to a XML representation.'''
		from cStringIO import StringIO

		# Parent dies when we have attributes that are not a string
		for element in self.getiterator('*'):
			for key in element.attrib.keys():
				element.attrib[key] = str(element.attrib[key])

		xml = StringIO()
		xml.write("<?xml version='1.0' encoding='utf-8'?>\n")
		ElementTreeModule.ElementTree.write(self, xml, 'utf-8')
		return xml.getvalue()

	def write(*a):
		'''Writing to file is not implemented, use tostring() instead'''
		raise NotImplementedError

	def parse(*a):
		'''Parsing from file is not implemented, use fromstring() instead'''
		raise NotImplementedError

	def set_heading(self, text, level=1):
		'''Set the first heading of the parse tree to 'text'. If the tree
		already has a heading of the specified level or higher it will be
		replaced. Otherwise the new heading will be prepended.
		'''
		root = self.getroot()
		children = root.getchildren()
		if children:
			first = children[0]
			if first.tag == 'h' and first.attrib['level'] >= level:
				root.remove(first)
		heading = Element('h', {'level': level})
		heading.text = text
		heading.tail = "\n"
		root.insert(0, heading)

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

	def resolve_images(self, notebook, path):
		'''Resolves the source files for all images relative to a page path	and
		adds a '_src_file' attribute to the elements with the full file path.
		'''
		for element in self.getiterator('img'):
			filepath = element.attrib['src']
			element.attrib['_src_file'] = notebook.resolve_file(element.attrib['src'], path)

	def encode_urls(self):
		'''Calls encode_url() on all links that contain urls'''
		for link in self.getiterator('link'):
			href = link.attrib['href']
			if is_url_re.match(href):
				link.attrib['href'] = url_encode(href)
				if link.text == href:
					link.text = link.attrib['href']

	def decode_urls(self):
		'''Calls decode_url() on all links that contain urls'''
		for link in self.getiterator('link'):
			href = link.attrib['href']
			if is_url_re.match(href):
				link.attrib['href'] = url_decode(href)
				if link.text == href:
					link.text = link.attrib['href']

	def count(self, text):
		'''Returns the number of occurences of 'text' in this tree.'''
		count = 0
		for element in self.getiterator():
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
		for element in self.getiterator():
			if element.text:
				newstring, n = regex.subn('', element.text)
				count += n
			if element.tail:
				newstring, n = regex.subn('', element.tail)
				count += n

		return count


count_eol_re = re.compile(r'\n+\Z')
split_para_re = re.compile(r'((?:^[ \t]*\n){2,})', re.M)


class ParseTreeBuilder(object):
	'''This class supplies an alternative for xml.etree.ElementTree.TreeBuilder
	which cleans up the tree on the fly while building it. The main use
	is to normalize the tree that is produced by the editor widget, but it can
	also be used on other "dirty" interfaces.

	This builder takes care of the following issues:
	* Inline tags ('emphasis', 'strong', 'h', etc.) can not span multiple lines
	* Tags can not contain only whitespace
	* Tags can not be empty (with the exception of the 'img' tag)
	* There should be an empty line before each 'h', 'p' or 'pre'
	  (with the exception of the first tag in the tree)
	* The 'p' and 'pre' elements should always end with a newline ('\n')
	* Each 'p', 'pre' and 'h' should be postfixed with a newline ('\n')
	  (as a results 'p' and 'pre' are followed by an empty line, the
	   'h' does not end in a newline itself, so it is different)
	* Newlines ('\n') after a <li> alement are removed (optional)
	* The element '_ignore_' is silently ignored
	'''

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
		elif tag in ('h', 'p', 'pre'):
			self._flush(need_eol=2)
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
			self._last = Element(tag, attrib)
		else:
			self._last = Element(tag)

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

		if len(self._stack) > 1 and not (tag == 'img'
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
		if self._tail and self._last.tag in ('h', 'p', 'pre') \
		and not text.startswith('\n'):
			if text:
				text = '\n' + text
			else:
				text = '\n'
				self._seen_eol = 1
		if self._tail and self._last.tag == 'li' \
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
						self._last = Element(self._last.tag, attrib)
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

				k, v = option.split('=')
				if k in ('width', 'height', 'type'):
					if len(v) > 0:
						attrib[str(k)] = v # str to avoid unicode key
				else:
					logger.warn('Unknown attribute "%s" in "%s"', k, url)
			return attrib
		else:
			return {'src': url}


class DumperClass(object):
	'''Base class for dumper classes.

	Each format that can be used natively should define a class
	'Dumper' which inherits from this base class.
	'''

	def __init__(self, linker=None):
		self.linker = linker

	def dump(self, tree):
		'''ABSTRACT METHOD needs to be overloaded by sub-classes.

		This method takes a ParseTree object and returns a list of
		lines of text.
		'''
		raise NotImplementedError

	def isrtl(self, element):
		'''Returns True if the parse tree below element starts with
		characters in a RTL script. This is e.g. needed to produce correct
		HTML output. Returns None if direction is not determined.
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

		if element.text:
			dir = pango.find_base_dir(element.text, len(element.text))
			if not dir == pango.DIRECTION_NEUTRAL:
				return dir == pango.DIRECTION_RTL
		for child in element.getchildren():
			rtl = self.isrtl(child)
			if not rtl is None:
				return rtl
		if element.tail:
			dir = pango.find_base_dir(element.tail, len(element.tail))
			if not dir == pango.DIRECTION_NEUTRAL:
				return dir == pango.DIRECTION_RTL

		return None


class BaseLinker(object):
	'''Base class for linker objects. Linker object translate links in zim pages
	to either paths or urls. Paths should be interpreted relative to the
	document in the way this is done in html.
	'''

	def __init__(self):
		self._icons = {}
		self.path = None
		self.usebase = False
		self.base = None

	def set_path(self, path):
		'''Set the page path for resolving links'''
		self.path = path

	def set_base(self, dir):
		'''Set a path to use a base for linking files'''
		assert isinstance(dir, Dir)
		self.base = dir

	def set_usebase(self, usebase):
		'''Set whether the format supports relative files links or not'''
		self.usebase = usebase

	def link(self, link):
		'''Returns a path or url for 'link' '''
		# TODO optimize by hashing links seen (reset per page)
		assert not self.path is None
		type = link_type(link)
		if type == 'page':
			return self.page(link)
		elif type == 'file':
			return self.file(link)
		elif type == 'mailto':
			if link.startswith('mailto:'):
				return link
			else:
				return 'mailto:' + link
		else:
			# I dunno, some url ?
			return link

	def img(self, src):
		'''Returns a path or url for image file 'src' '''
		return self.file(src)

	def icon(self, name):
		'''Returns a path or url for an icon'''
		if not name in self._icons:
			self._icons[name] = data_file('pixmaps/%s.png' % name).uri
		return self._icons[name]

	def page(self, link):
		'''To be overloaded'''
		raise NotImplementedError

	def file(self, path):
		'''To be overloaded'''
		raise NotImplementedError

