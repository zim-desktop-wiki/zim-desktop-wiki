
# Copyright 2008-2022 Jaap Karssenberg <jaap.karssenberg@gmail.com>

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
	- mark for highlighted text, rendered with background color or underlined
	- strike for text that is removed, usually rendered as strike through
	- code for inline verbatim text
	- ul for bullet and checkbox lists
	- ol for numbered lists
	- li for list items
	- link for links, attribute href gives the target
	- img for images, attributes src, width, height an optionally href and alt
		- type can be used to control plugin functionality, e.g. type=equation
	- table for tables, attributes
			* aligns - comma separated values: right,left,center
			* wraps - 0 for not wrapped, 1 for auto-wrapped line display
		- thead for table header row
			- th for table header cell
		- trow for table row
			- td for table data cell

Nesting rules:

	- paragraphs, list items, table cells & headings can contain all inline elements
	- inline formats can contain other inline formats as well as links and tags
	- code and pre cannot contain any other elements

Unlike html we respect line breaks and other whitespace as is.
When rendering as html use the "white-space: pre" CSS definition to
get the same effect.

Text blocks (paragraphs, listitems, headings, vertabim blocks) must end with a
newline. Only the last block of the sequence can omit the newline. This case
will be interpreted as a text snippet and affect copy-paste behavior.

Tables and other objects that are not inline are implicitly handled as ending in
a newline.

As a result the newlines outsides blocks represent the number of empty lines
between the blocks and newline ending the block is contained in the block.

If a page starts with a h1 this heading is considered the page title,
else we can fall back to the page name as title.


NOTE: To avoid confusion: "headers" refers to meta data, usually in
the form of rfc822 headers at the top of a page. But "heading" refers
to a title or subtitle in the document.
'''

import re
import itertools
import logging
import collections

from functools import reduce

logger = logging.getLogger('zim.formats')


from zim.parse.encode import url_decode, url_encode, URL_ENCODE_READABLE, URL_ENCODE_DATA
from zim.parse.links import link_type, is_url_re, is_www_link_re
from zim.parse.tokenlist import TokenParser, topLevelLists, collect_until_end_token
from zim.parse.builder import Builder

from zim.config import ConfigDict
from zim.plugins import PluginManager

import zim.plugins

# Needed to determine RTL, but may not be available
# if gtk bindings are not installed
try:
	from gi.repository import Pango
except:
	Pango = None
	logger.warning('Could not load pango - RTL scripts may look bad')

import xml.etree.ElementTree # needed to compile with cElementTree
try:
	import xml.etree.cElementTree as ElementTreeModule
except:  #pragma: no cover
	import xml.etree.ElementTree as ElementTreeModule


EXPORT_FORMAT = 1
IMPORT_FORMAT = 2
NATIVE_FORMAT = 4
TEXT_FORMAT = 8 # Used for "Copy As" menu - these all prove "text/plain" mimetype

UNCHECKED_BOX = 'unchecked-box'
CHECKED_BOX = 'checked-box'
XCHECKED_BOX = 'xchecked-box'
MIGRATED_BOX = 'migrated-box'
TRANSMIGRATED_BOX = "transmigrated-box"
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

BLOCK_LEVEL = (PARAGRAPH, HEADING, VERBATIM_BLOCK, BLOCK, LISTITEM) # Top levels with nested text

EMPHASIS = 'emphasis' # TODO change to "em" to be in line with html
STRONG = 'strong'
MARK = 'mark'
VERBATIM = 'code'
STRIKE = 'strike'
SUBSCRIPT = 'sub'
SUPERSCRIPT = 'sup'

INLINE_STYLE_TAGS = (EMPHASIS, STRONG, MARK, VERBATIM, STRIKE, SUBSCRIPT, SUPERSCRIPT) # Inline tags without additional semantics


LINK = 'link'
TAG = 'tag'
ANCHOR = 'anchor'

TABLE = 'table'
HEADROW = 'thead'
HEADDATA = 'th'
TABLEROW = 'trow'
TABLEDATA = 'td'

LINE = 'line'
OBJECT_LIKE = (OBJECT, TABLE, LINE) # Do not include trailing newline


# Tokens
TEXT = 'T'
END = '/'


_letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

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
			i = _letters.index(listiter)
			return _letters[i + 1]
		except ValueError: # listiter is not a letter
			return None
		except IndexError: # wrap to start of list
			return _letters[0]


def convert_list_iter_letter_to_number(listiter):
	'''Convert a "letter" numbered list to a digit numbered list
	Usefull for export to formats that do not support letter lists.
	Both "A." and "a." convert to "1." assumption is that this function
	is used for start iter only, not whole list
	'''
	try:
		i = int(listiter)
		return listiter
	except ValueError:
		try:
			i = _letters.index(listiter) + 1
			i = i if i <= 26 else i % 26
			return str(i)
		except ValueError: # listiter is not a letter
			return None


def encode_xml(text):
	'''Encode text such that it can be used in xml
	@param text: label text as string
	@returns: encoded text
	'''
	return text.replace('&', '&amp;').replace('>', '&gt;').replace('<', '&lt;').replace('"', '&quot;').replace("'", '&apos;')


def list_formats(type):
	if type == EXPORT_FORMAT:
		return ['HTML', 'LaTeX', 'Markdown (pandoc)', 'RST (sphinx)']
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
	if name == 'text':
		return 'plain'
	else:
		return name


_aliases = {
	'zim-wiki': 'wiki',
}

def get_format(name):
	'''Returns the module object for a specific format.'''
	# If this method is removes, class names in formats/*.py can be made more explicit
	#~ print('DEPRECATED: get_format() is deprecated in favor if get_parser() and get_dumper()')
	return get_format_module(name)


def get_format_module(name):
	'''Returns the module object for a specific format

	@param name: the format name
	@returns: a module object
	'''
	name = _aliases.get(name, name)
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


def heading_to_anchor(name):
	"""Derive an anchor name from a heading"""
	name = re.sub(r'\s', '-', name.strip().lower())
	return re.sub(r'[^\w\-_]', '', name)


TokenListElement = collections.namedtuple('TokenListElement', ('tag', 'attrib', 'content'))


class ParseTree(object):
	'''Wrapper for zim parse trees.'''

	def __init__(self, *arg, **kwarg):
		self._etree = ElementTreeModule.ElementTree(*arg, **kwarg)
		self._object_cache = {}
		self.meta = LastDefinedOrderedDict()
		assert not (self._etree.getroot() and self._etree.getroot().attrib.get('raw', False)), 'Deprecated "raw" attribute'

	@classmethod
	def new_from_tokens(klass, tokens):
		tokens = list(tokens) # TODO: allow efficient use of generator here ?
		assert tokens
		if tokens[0][0] != FORMATTEDTEXT:
			tokens.insert(0, (FORMATTEDTEXT, None))
			tokens.append((END, FORMATTEDTEXT))

		builder = ParseTreeBuilder()
		parser = TokenParser(builder)
		parser.parse(tokens)
		return builder.get_parsetree()

	@property
	def hascontent(self):
		'''Returns True if the tree contains any content at all.'''
		root = self._etree.getroot()
		return root is not None and (
			bool(list(root)) or (root.text and not root.text.isspace())
		)

	def _set_root_attrib(self, key, value):
		self._etree.getroot().attrib[key] = value

	def _get_root_attrib(self, key, default=None):
		return self._etree.getroot().attrib.get(key, default)

	def _pop_root_attrib(self, key, default=None):
		return self._etree.getroot().attrib.pop(key, default)

	def extend(self, tree):
		# Do we need a deepcopy here ?
		myroot = self._etree.getroot()
		otherroot = tree._etree.getroot()
		if otherroot.text:
			children = list(myroot)
			if children:
				last = children[-1]
				last.tail = (last.tail or '') + otherroot.text
			else:
				myroot.text = (myroot.text or '') + otherroot.text

		for element in iter(otherroot):
			myroot.append(element)

		return self

	__add__ = extend

	def fromstring(self, string):
		'''Set the contents of this tree from XML representation.'''
		parser = ElementTreeModule.XMLParser()
		parser.feed(string)
		root = parser.close()
		self._etree._setroot(root)
		return self # allow ParseTree().fromstring(..)

	def tostring(self):
		'''Serialize the tree to a XML representation'''
		from io import StringIO

		# HACK: Force sorting of attrib - else change in python3.8 breaks test cases
		# Ensure all attrib are string, else ElementTree fails
		for element in self._etree.iter('*'):
			myattrib = element.attrib.copy()
			element.attrib.clear()
			for key in sorted(myattrib.keys()):
				element.attrib[key] = str(myattrib[key])

		xml = StringIO()
		xml.write("<?xml version='1.0' encoding='utf-8'?>\n")
		ElementTreeModule.ElementTree.write(self._etree, xml, 'unicode')
		return xml.getvalue()

	def copy(self):
		#return self.__class__.new_from_tokens(list(self.iter_tokens()))
		return ParseTree().fromstring(self.tostring())

	def iter_tokens(self):
		return iter(topLevelLists(self._get_tokens(self._etree.getroot())))

	def _get_tokens(self, node):
		tokens = [(node.tag, node.attrib.copy())]

		if node.text:
			for t in node.text.splitlines(True):
				tokens.append((TEXT, t))

		for child in node:
			tokens.extend(self._get_tokens(child)) # recurs
			if child.tail:
				for t in child.tail.splitlines(True):
					tokens.append((TEXT, t))

		tokens.append((END, node.tag))
		return tokens

	def iter_href(self, include_page_local_links=False, include_anchors=False):
		'''Generator for links in the text
		@param include_anchors: if C{False} remove the target location from the
		link and only yield unique links to pages
		@returns: yields a list of unique L{HRef} objects
		'''
		from zim.notebook.page import HRef # XXX

		seen = set()
		for elt in itertools.chain(
			self._etree.iter(LINK),
			self._etree.iter(IMAGE)
		):
			href = elt.attrib.get('href')
			if not href or link_type(href) != 'page':
				continue

			try:
				href_obj = HRef.new_from_wiki_link(href)
			except ValueError:
				continue

			if not include_anchors:
				if not href_obj.names:
					continue # internal link within same page
				elif href_obj.anchor:
					href_obj.anchor = None
					href = href_obj.to_wiki_link()

			if href in seen:
				continue
			seen.add(href)
			yield href_obj

	def iter_tag_names(self):
		'''Generator for tags in the page content
		@returns: yields an unordered list of tag names
		'''
		seen = set()
		for elt in self._etree.iter(TAG):
			name = elt.text
			if not name in seen:
				seen.add(name)
				yield name.lstrip('@')

	def _get_heading_element(self, level=1):
		root = self._etree.getroot()
		children = list(root)
		if root.text and not root.text.isspace():
			return None

		if children:
			first = children[0]
			if first.tag == 'h' and int(first.attrib['level']) >= level:
				return first
		return None

	def get_heading_level(self):
		heading_elem = self._get_heading_element()
		if heading_elem is not None:
			return int(heading_elem.attrib['level'])
		else:
			return None

	def _elt_to_text(self, elt):
		strings = [elt.text]
		for e in elt:
			strings.append(self._elt_to_text(e)) # recurs
			strings.append(e.tail)
		return ''.join(s for s in strings if s) # remove possible None values

	def get_heading_text(self, level=1):
		heading_elem = self._get_heading_element(level)
		if heading_elem is not None:
			return self._elt_to_text(heading_elem).strip()
		else:
			return ""

	def set_heading_text(self, text, level=1):
		'''Set the first heading of the parse tree to 'text'. If the tree
		already has a heading of the specified level or higher it will be
		replaced. Otherwise the new heading will be prepended.
		'''
		text = text.rstrip() + '\n'
		heading = self._get_heading_element(level)
		if heading is not None:
			heading.text = text
			for e in heading:
				heading.remove(e)
		else:
			root = self._etree.getroot()
			heading = ElementTreeModule.Element('h', {'level': level})
			heading.text = text
			heading.tail = '\n' + (root.text or '')
			root.text = None
			root.insert(0, heading)

	def cleanup_headings(self, offset=0, max=6):
		'''Change the heading levels throughout the tree. This makes sure that
		al headings are nested directly under their parent (no gaps in the
		levels of the headings). Also you can set an offset for the top level
		and a max depth.
		'''
		path = []
		for heading in self._etree.iter('h'):
			level = int(heading.attrib['level'])
			# find parent header in path using old level
			while path and path[-1][0] >= level:
				path.pop()
			if not path:
				newlevel = offset + 1
			else:
				newlevel = path[-1][1] + 1
			if newlevel > max:
				newlevel = max
			heading.attrib['level'] = newlevel
			path.append((level, newlevel))

	def encode_urls(self, mode=URL_ENCODE_READABLE):
		'''Calls encode_url() on all links that contain urls.
		See zim.parse.links for details. Modifies the parse tree.
		'''
		for link in self._etree.iter('link'):
			href = link.attrib['href']
			if href and is_url_re.match(href) or is_www_link_re.match(href):
				link.attrib['href'] = url_encode(href, mode=mode)
				if link.text == href:
					link.text = link.attrib['href']

	def decode_urls(self, mode=URL_ENCODE_READABLE):
		'''Calls decode_url() on all links that contain urls.
		See zim.parse.links for details. Modifies the parse tree.
		'''
		for link in self._etree.iter('link'):
			href = link.attrib['href']
			if href and is_url_re.match(href) or is_www_link_re.match(href):
				link.attrib['href'] = url_decode(href, mode=mode)
				if link.text == href:
					link.text = link.attrib['href']

	def count(self, text):
		'''Returns the number of occurences of 'text' in this tree.'''
		count = 0
		for element in self._etree.iter():
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
		for element in self._etree.iter():
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
				children = list(element)
				if children:
					return self._get_element_ends_with_newline(children[-1]) # recurs
				elif element.text:
					return element.text.endswith('\n')
				else:
					return False # empty element like image

	def find_element(self, tag):
		'''Helper function to find the first occurence of C{tag}, returns a L{TokenListElement} or C{None}'''
		for e in self.iter_elements(tag):
			return e # return first
		else:
			return None

	def iter_elements(self, tag):
		'''Helper function to find all occurences of C{tag}, yields L{TokenListElement}s'''
		token_iter = self.iter_tokens()
		for t in token_iter:
			if t[0] == tag:
				content = collect_until_end_token(token_iter, tag)
				yield TokenListElement(t[0], t[1], content)

	def substitute_elements(self, tags, func):
		'''Helper function to create a copy while substituting certain elements

		@param tags: list of tags to match
		@param func: function that determines the substitution

		The C{func} will get a L{TokenListElement} for each token that matches
		C{tags}. The return value of C{func} can be C{None} to remove the element,
		the same or a modified L{TokenListElement} or a list of tokens.
		'''
		tokens = []
		token_iter = self.iter_tokens()
		for t in token_iter:
			if t[0] in tags:
				content = collect_until_end_token(token_iter, t[0])
				replacement = func(TokenListElement(t[0], t[1], content))
				if replacement is None:
					pass # remove these tokens
				elif isinstance(replacement, TokenListElement):
					tokens.append((replacement.tag, replacement.attrib))
					tokens.extend(replacement.content)
					tokens.append((END, replacement.tag))
				else:
					tokens.extend(replacement)
			else:
				tokens.append(t)

		return ParseTree.new_from_tokens(tokens)


def split_heading_from_parsetree(parsetree, keep_head_token=True):
	'''Helper function to split the header from a L{ParseTree}
	Looks for a header at the start of a page and strips empty lines after it.
	Returns two L{ParseTree} objects: one for the header and one for the main
	body of the content - both can be C{None} if they are empty.
	'''
	token_iter = parsetree.iter_tokens()
	heading = []
	body = []
	for t in token_iter:
		if t[0] == FORMATTEDTEXT:
			pass
		elif t[0] == HEADING:
			heading.append(t)
			heading.extend(collect_until_end_token(token_iter, HEADING))
			heading.append((END, HEADING))
			break
		elif t[0] == TEXT and t[1].isspace():
			pass
		else:
			body.append(t)
			break

	if not body:
		for t in token_iter:
			if t[0] == TEXT and t[1].isspace():
				pass
			else:
				body.append(t)
				break

	body.extend(list(token_iter))
	if body[-1] == (END, FORMATTEDTEXT):
		body.pop()

	if heading and not keep_head_token:
		heading = heading[1:-1]
		if heading[-1][0] == TEXT:
			if heading[-1][1] == '\n':
				heading.pop()
			elif heading[-1][1].endswith('\n'):
				heading[-1] = (TEXT, heading[-1][1][:-1])

	heading_tree = ParseTree.new_from_tokens(heading) if heading else None
	body_tree = ParseTree.new_from_tokens(body) if body else None
	return heading_tree, body_tree


class ParseTreeBuilder(Builder):
	'''Builder object that builds a L{ParseTree}'''

	def __init__(self):
		self._b = ElementTreeModule.TreeBuilder()
		self.stack = [] #: keeps track of current open elements
		self._last_char = None

	def get_parsetree(self):
		'''Returns the constructed L{ParseTree} object.
		Can only be called once, after calling this method the object
		can not be re-used.
		'''
		root = self._b.close()
		return zim.formats.ParseTree(root)

	def start(self, tag, attrib=None):
		attrib = attrib.copy() if attrib is not None else {}
		self._b.start(tag, attrib)
		self.stack.append(tag)
		if tag in BLOCK_LEVEL:
			if self._last_char and self._last_char != '\n':
				logger.warning('Missing "\\n" before new block (%s)' % tag)
			self._last_char = None

	def text(self, text):
		self._last_char = text[-1]
		self._b.data(text)

	def end(self, tag):
		assert tag == self.stack[-1], 'Unmatched tag closed: %s' % tag
		self._b.end(tag)
		self.stack.pop()
		if tag in OBJECT_LIKE:
			self._last_char = '\n' # Special case - implicit newline in object

	def append(self, tag, attrib=None, text=None):
		attrib = attrib.copy() if attrib is not None else {}

		self._b.start(tag, attrib)
		if text:
			self._last_char = text[-1]
			self._b.data(text)
		if tag in OBJECT_LIKE:
			self._last_char = '\n' # Special case - implicit newline in object
		self._b.end(tag)

		if tag in OBJECT_LIKE:
			self._last_char = '\n' # Special case - implicit newline in object
		else:
			self._last_char = text[-1] if text else None


class BackwardParseTreeBuilderWithCleanup(object):
	'''Adaptor for the pageview compatible with the old builder interface'''

	# NOTE: Processing tokens here without "topLevelLists()" logic

	# TODO: Adaptor breaks text at newline - move to real pageview tokenizer, combine
	# with breaking inline tags at newline - or handle both in token filter function

	# TODO: clean up of empty link & heading tags is a bit of a cludge, might be
	# better resolved directly in tokenizer

	def __init__(self):
		self._tokens = []

	def start(self, tag, attrib=None):
		if tag != '_ignore_':
			self._tokens.append((tag, attrib))

	def data(self, text):
		for t in text.splitlines(True):
			if t:
				self._tokens.append((TEXT, t))

	def end(self, tag):
		if tag != '_ignore_':
			self._tokens.append((END, tag))

	def close(self):
		_pop_empty_head_and_linke(self._tokens)
		tokens = list(strip_whitespace(iter(self._tokens)))

		builder = ParseTreeBuilder()
		for t in tokens:
			if t[0] == END:
				builder.end(t[1])
			elif t[0] == TEXT:
				builder.text(t[1])
			else:
				builder.start(*t)

		return builder._b.close() # XXX


def _pop_empty_head_and_linke(tokens):
	# Filter needed to pass testIllegalHeadingWithListItem and testIllegalDoubleLink tests
	i = len(tokens)-1
	while i > 0:
		if tokens[i][0] == END and tokens[i][1] in (HEADING, LINK) \
			and tokens[i-1][0] == tokens[i][1]:
				# Empty tag
				tokens.pop(i)
				tokens.pop(i-1)
				i -= 2
		else:
			i -= 1


def strip_whitespace(token_iter):
	'''Gererator that filters a token stream to sanitize whitespace around
	inline formatting and remove empty tags
	'''
	# <b><i><space>foo</i></b> --> <space><b><i>foo</i></b>
	# <b><space><i>foo</i></b> --> <space><b><i>foo</i></b>
	# <b><i>foo<space></i></b> --> <b><i>foo</i></b><space>
	# <b><i>foo</i><space></b> --> <b><i>foo</i></b><space>
	# <b><i><space></i></b> --> <space>
	# <b><i></i></b> -->  None
	# <b><i><space><img /></i></b> --> <space><b><i><img /></i></b>
	for t in token_iter:
		if t[0] in INLINE_STYLE_TAGS:
			for t in _strip_whitespace_inner(t, token_iter):
				yield t
		else:
			yield t

def _strip_whitespace_inner(start_tag, token_iter):
	end_tag = (END, start_tag[0])
	content = []
	for t in token_iter:
		if t == end_tag:
			break
		elif t[0] in INLINE_STYLE_TAGS:
			content.extend(_strip_whitespace_inner(t, token_iter)) # recurs
		else:
			content.append(t)

	# lstrip
	prefix = None
	if content and content[0][0] == TEXT:
		text = content[0][1]
		if text.isspace():
			prefix = content.pop(0)
		else:
			stripped_text = text.lstrip()
			i = len(text) - len(stripped_text)
			if i > 0:
				prefix = (TEXT, text[:i])
				content[0] = (TEXT, text[i:])

	# rstrip
	postfix = None
	if content and content[-1][0] == TEXT:
		text = content[-1][1]
		if text.isspace():
			postfix = content.pop()
		else:
			stripped_text = text.rstrip()
			i = len(text) - len(stripped_text)
			if i > 0:
				postfix = (TEXT, text[-i:])
				content[-1] = (TEXT, text[:-i])

	# put it together
	if content:
		content.insert(0, start_tag)
		if prefix:
			content.insert(0, prefix)

		content.append(end_tag)
		if postfix:
			content.append(postfix)
	elif prefix:
		# ignore empty tag, just keep prefix if any
		# cannot have postfix without content
		content = [prefix]
	else:
		pass

	return content


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
			for option in url[i + 1:].split('&'):
				if option.find('=') == -1:
					logger.warning('Mal-formed options in "%s"', url)
					break

				k, v = option.split('=', 1)
				if k in ('id', 'width', 'height', 'type', 'href'):
					if len(v) > 0:
						value = url_decode(v, mode=URL_ENCODE_DATA)
						attrib[str(k)] = value # str to avoid unicode key
				else:
					logger.warning('Unknown attribute "%s" in "%s"', k, url)
			return attrib
		else:
			return {'src': url}


DumperContextElement = collections.namedtuple('DumperContextElement', ('tag', 'attrib', 'text'))


class DumperClass(object):
	'''Base class for dumper classes. Dumper classes serialize the content
	of a parse tree back to a text representation of the page content.

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

	NOTE: content that is serialized from a C{PageView} contains some
	"illegal" shortcuts for which a Dumper of a native format (used to read/write
	pages - not just export) should be robust:

	  - paragraph tags are missing
	  - list tags are missing, instead list items have an "indent" attribute


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
		'''Format a parsetree to text
		@param tree: a C{ParseTree} object
		@returns: a list of lines
		'''
		# FIXME - issue here is that we need to reset state - should be in __init__
		self._text = []
		self.context = [DumperContextElement(None, None, self._text)]
		self._dump(tree.iter_tokens())
		if len(self.context) != 1:
			raise AssertionError('Unclosed tags on tree: %s' % self.context[-1].tag)
		#~ import pprint; pprint.pprint(self._text)
		return self.get_lines() # FIXME - maybe just return text ?

	def get_lines(self):
		'''Return the dumped content as a list of lines
		Should only be called after closing the top level element
		'''
		return ''.join(self._text).splitlines(1)

	def _dump(self, token_iter):
		for t in token_iter:
			if t[0] == TEXT:
				text = t[1]
				if self.context[-1].tag != OBJECT:
					text = self.encode_text(self.context[-1].tag, text)
				self.context[-1].text.append(text)
			elif t[0] == END:
				assert t[1] == self.context[-1].tag, 'Unexpected tag closed: %s - stack: %r' % (t[1], [c.tag for c in self.context])
				tag, attrib, strings = self.context.pop()

				if tag in self.TAGS:
					if strings:
						start, end = self.TAGS[tag]
						strings.insert(0, start)
						strings.append(end)
					else:
						pass # Skip empty tags silently
				elif tag == FORMATTEDTEXT:
					pass
				else:
					try:
						method = getattr(self, 'dump_' + tag)
					except AttributeError:
						raise AssertionError('BUG: Unknown tag: %s' % tag)

					strings = method(tag, attrib, strings)

				if strings is not None:
					self.context[-1].text.extend(strings)
			else: # START
				attrib = t[1].copy() if t[1] else {} # Ensure dumping does not change tree
				self.context.append(DumperContextElement(t[0], attrib, []))

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
		lines = ''.join(strings).splitlines(1)
		return [prefix + l for l in lines]

	def dump_object(self, tag, attrib, strings=[]):
		'''Dumps objects defined by L{InsertedObjectType}'''
		format = str(self.__class__.__module__).split('.')[-1]
		try:
			obj = PluginManager.insertedobjects[attrib['type']]
		except KeyError:
			pass
		else:
			try:
				output = obj.format(format, self, attrib, ''.join(strings))
			except ValueError:
				pass
			else:
				assert isinstance(output, (list, tuple)), "Invalid output: %r" % output
				return output

		if attrib['type'].startswith('image+'):
			# Fallback for backward compatibility of image generators < zim 0.70
			attrib = attrib.copy()
			attrib['type'] = attrib['type'][6:]
			return self.dump_img(IMAGE, attrib, None)
		else:
			return self.dump_object_fallback(tag, attrib, strings)

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
		if Pango is None:
			return None

		# It seems the find_base_dir() function is not documented in the
		# python language bindings. The Gtk C code shows the signature:
		#
		#     Pango.find_base_dir(text, length)
		#
		# It either returns a direction, or NEUTRAL if e.g. text only
		# contains punctuation but no real characters.

		dir = Pango.find_base_dir(text, len(text))
		if dir == Pango.Direction.NEUTRAL:
			return None
		else:
			return dir == Pango.Direction.RTL


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


class TableParser():
	'''Common functions for converting a table from its' xml structure to another format'''

	@staticmethod
	def width2dim(lines):
		'''
		Calculates the characters on each column and return list of widths
		:param lines: 2-dim multiline rows
		:return: the number of characters of the longest cell-value by column
		'''
		widths = [max(list(map(len, line))) for line in zip(*lines)]
		return widths

	@staticmethod
	def width3dim(lines):
		'''
		Calculates the characters on each column and return list of widths
		:param lines: 3-dim multiline rows
		:return: the number of characters of the longest cell-value by column
		'''
		lines = reduce(lambda x, y: x + y, lines)
		widths = [max(list(map(len, line))) for line in zip(*lines)]
		return widths

	@staticmethod
	def convert_to_multiline_cells(rows):
		'''
		Each cell in a list of rows is split by "\n" and a 3-dimensional list is returned,
		whereas each tuple represents a line and multiple lines represents a row and multiple rows represents the table
		c11a = Cell in Row 1 in Column 1 in first = a line
		:param rows: format like (('c11a \n c11b', 'c12a \n c12b'), ('c21', 'c22a \n 22b'))
		:return: format like (((c11a, c12a), (c11b, c12b)), ((c21, c22a), ('', c22b)))
		'''
		multi_rows = [[cell.split("\n") for cell in row] for row in rows]

		# grouping by line, not by row
		strings = [list(map(lambda *line: [val if val is not None else '' for val in line], *row)) for row in multi_rows]
		return strings

	@staticmethod
	def get_options(attrib):
		'''
		Lists the attributes as tuple
		:param attrib:
		:return: tuple of attributes
		'''
		aligns = attrib['aligns'].split(',')
		wraps = list(map(int, attrib['wraps'].split(',')))

		return aligns, wraps

	@staticmethod
	def rowsep(maxwidths, x='+', y='-'):
		'''
		Displays a row separator
		example: rowsep((3,0), '-', '+') -> +-----+--+
		:param maxwidths: list of column lengths
		:param x: point-separator
		:param y: line-separator
		:return: a textline
		'''
		return x + x.join([(width + 2) * y for width in maxwidths]) + x

	@staticmethod
	def headsep(maxwidths, aligns, x='|', y='-'):
		'''
		Displays a header separation with alignment infos
		example: rowsep((3,0), '-', '+') -> +-----+--+
		:param maxwidths: list of column lengths
		:param aligns:  list of alignments
		:param x: point-separator
		:param y: line-separator
		:return: a text line
		'''
		cells = []
		for width, align in zip(maxwidths, aligns):
			line = width * y
			if align == 'left':
				cell = ':' + line + y
			elif align == 'right':
				cell = y + line + ':'
			elif align == 'center':
				cell = ':' + line + ':'
			else:
				cell = y + line + y
			cells.append(cell)
		return x + x.join(cells) + x

	@staticmethod
	def headline(row, maxwidths, aligns, wraps, x='|', y=' '):
		'''
		Displays a headerline line in text format
		:param row: tuple of cells
		:param maxwidths: list of column length
		:param aligns:  list of alignments
		:param wraps: 0 for not wrapped, 1 for auto-wrapped line display
		:param x:  point-separator
		:param y: space-separator
		:return: a textline
		'''
		row = TableParser.alignrow(row, maxwidths, aligns, y)
		cells = []
		for val, wrap in zip(row, wraps):
			if wrap == 1:
				val = val[:-1] + '<'
			cells.append(val)
		return x + x.join(cells) + x

	@staticmethod
	def rowline(row, maxwidths, aligns, x='|', y=' '):
		'''
		Displays a normal column line in text format
		example: rowline((3,0), (left, left), '+','-') -> +-aa--+--+
		:param row: tuple of cells
		:param maxwidths: list of column length
		:param aligns:  list of alignments
		:param x:  point-separator
		:param y: space-separator
		:return: a textline
		'''
		cells = TableParser.alignrow(row, maxwidths, aligns, y)
		return x + x.join(cells) + x

	@staticmethod
	def alignrow(row, maxwidths, aligns, y=' '):
		'''
		Formats a row with the right alignments
		:param row: tuple of cells
		:param maxwidths: list of column length
		:param aligns:  list of alignments
		:param y: space-separator
		:return: a textline
		'''
		cells = []
		for val, align, maxwidth in zip(row, aligns, maxwidths):
			if align == 'left':
				(lspace, rspace) = (1, maxwidth - len(val) + 1)
			elif align == 'right':
				(lspace, rspace) = (maxwidth - len(val) + 1, 1)
			elif align == 'center':
				lspace = (maxwidth - len(val)) // 2 + 1
				rspace = (maxwidth - lspace - len(val) + 2)
			else:
				(lspace, rspace) = (1, maxwidth - len(val) + 1)
			cells.append(lspace * y + val + rspace * y)
		return cells


from zim.base import LastDefinedOrderedDict

_is_header_re = re.compile(r'^([\w\-]+):\s+(.*?)\n', re.M)
_is_continue_re = re.compile(r'^([^\S\n]+)(.+?)\n', re.M)

def parse_header_lines(text):
	'''Read header lines in the rfc822 format.
	Can e.g. look like::

		Content-Type: text/x-zim-wiki
		Wiki-Format: zim 0.4
		Creation-Date: 2010-12-14T14:15:09.134955

	@returns: the text minus the headers and a dict with the headers
	'''
	assert isinstance(text, str)
	meta = LastDefinedOrderedDict()
	match = _is_header_re.match(text)
	pos = 0
	while match:
		header = match.group(1)
		value = match.group(2)
		pos = match.end()

		meta[header] = value.strip()
		match = _is_continue_re.match(text, pos)
		while match:
			cont = match.group(2)
			meta[header] += '\n' + cont.strip()
			pos = match.end()
			match = _is_continue_re.match(text, pos)

		match = _is_header_re.match(text, pos)
	else:
		if pos > 0:
			try:
				if text[pos] == '\n':
					pos += 1
			except IndexError:
				pass
			text = text[pos:]

	return text, meta


def dump_header_lines(*headers):
	'''Return text representation of header dict'''
	text = []
	append = lambda k, v: text.extend((k, ': ', v.strip().replace('\n', '\n\t'), '\n'))

	for h in headers:
		if hasattr(h, 'items'):
			for k, v in list(h.items()):
				append(k, v)
		else:
			for k, v in h:
				append(k, v)
	return ''.join(text)
