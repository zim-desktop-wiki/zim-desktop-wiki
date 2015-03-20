# -*- coding: utf-8 -*-

# Copyright 2008-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import re

from zim.utils import natural_sort_key
from zim.parsing import link_type

import zim.formats


_pagename_reduce_colon_re = re.compile('::+')
_pagename_invalid_char_re = re.compile(
	'(' +
		'^\W|(?<=:)\W' +
	'|' +
		'[' + re.escape(''.join(
			("?", "#", "/", "\\", "*", '"', "<", ">", "|", "%", "\t", "\n", "\r")
		)) + ']' +
	')',
re.UNICODE)
	# This pattern matches a non-alphanumber at start or after the ':'
	# seperator. It also matches any invalid character.
	# The UNICODE flag is used to make the alphanumber check international.


class Path(object):
	'''Class representing a page name in the notebook

	This is the parent class for the Page class. It contains the name
	of the page and is used instead of the actual page object by methods
	that only need to know the name of the page. Path objects have no
	internal state and are essentially normalized page names. It also
	has a number of methods to compare page names and determing what
	the parent pages are etc.

	@note: There are several subclasses of this class like
	L{index.IndexPath}, L{Page}, and L{stores.files.FileStorePage}.
	In any API call where a path object is needed an instance of any
	of these subclasses can be used instead.

	@ivar name: the full name of the path
	@ivar parts: all the parts of the name (split on ":")
	@ivar basename: the basename of the path (last part of the name)
	@ivar namespace: the name for the parent page or empty string
	@ivar isroot: C{True} when this Path represents the top level namespace
	@ivar parent: the L{Path} object for the parent page


	Valid characters in page names
	==============================

	A number of characters are not valid in page names as used in Zim
	notebooks.

	Reserved characters are:
	  - The ':' is reserved as separator
	  - The '?' is reserved to encode url style options
	  - The '#' is reserved as anchor separator
	  - The '/' and '\' are reserved to distinguish file links & urls
	  - First character of each part MUST be alphanumeric
		(including utf8 letters / numbers)

	For file system filenames we can not use:
	'\', '/', ':', '*', '?', '"', '<', '>', '|'
	(checked both win32 & posix)

	Do not allow '\n' and '\t' for obvious reasons

	Allowing '%' will cause problems with sql wildcards sooner
	or later - also for url decoding ambiguity it is better to
	keep this one reserved.

	All other characters are allowed in page names

	Note that Zim version < 0.42 used different rules that are not
	fully compatible, this is important when upgrading old notebooks.
	See L{Notebook.cleanup_pathname_zim028()}
	'''

	__slots__ = ('name',)

	@staticmethod
	def assertValidPageName(name):
		'''Raises an C{AssertionError} if C{name} does not represent
		a valid page name.
		This is a strict check, most names that fail this test can still
		be cleaned up by the L{makeValidPageName()}.
		@param name: a string
		@raises AssertionError: if the name is not valid
		'''
		assert isinstance(name, basestring)
		if not name.strip(':') \
		or _pagename_reduce_colon_re.search(name) \
		or _pagename_invalid_char_re.search(name):
			raise AssertionError, 'Not a valid page name: %s' % name

	@staticmethod
	def makeValidPageName(name):
		'''Remove any invalid characters from the string and return
		a valid page name. Only string that can not be turned in
		somthing valid is a string that reduces to an empty string
		after removing all invalid characters.
		@param name: a string
		@returns: a string
		@raises ValueError: when the result would be an empty string
		'''
		newname = _pagename_reduce_colon_re.sub(':', name.strip(':'))
		newname = _pagename_invalid_char_re.sub('', newname)
		if newname:
			return newname
		else:
			raise ValueError, 'Not a valid page name: %s' % name

	def __init__(self, name):
		'''Constructor.

		@param name: the absolute page name in the right case as a
		string or as a tuple strings

		The name ":" is used as a special case to construct a path for
		the toplevel namespace in a notebook.

		@note: This constructor does not do any checks for the sanity of
		the path name. Never construct a path directly from user input,
		but use either L{index.lookup_from_user_input()} or first check the
		name with L{makeValidPageName()}
		'''
		if isinstance(name, (list, tuple)):
			self.name = ':'.join(name)
		else:
			self.name = name.strip(':')

		try:
			self.name = unicode(self.name)
		except UnicodeDecodeError:
			raise ValueError, 'BUG: invalid input, page names should be in ascii, or given as unicode'

	@classmethod
	def new_from_zim_config(klass, string):
		'''Returns a new object based on the string representation for
		that path.
		'''
		return klass( klass.makeValidPageName(string) )

	def serialize_zim_config(self):
		'''Returns the name for serializing this path'''
		return self.name

	def __repr__(self):
		return '<%s: %s>' % (self.__class__.__name__, self.name)

	def __hash__(self):
		return self.name.__hash__()

	def __eq__(self, other):
		'''Paths are equal when their names are the same'''
		if isinstance(other, Path):
			return self.name == other.name
		else: # e.g. path == None
			return False

	def __ne__(self, other):
		'''Paths are not equal when their names are not the same'''
		return not self.__eq__(other)

	def __add__(self, name):
		'''C{path + name} is an alias for C{path.child(name)}'''
		return self.child(name)

	@property
	def parts(self):
		'''Get all the parts of the name (split on ":")'''
		return self.name.split(':')

	@property
	def basename(self):
		'''Get the basename of the path (last part of the name)'''
		i = self.name.rfind(':') + 1
		return self.name[i:]

	@property
	def namespace(self):
		'''Gives the name for the parent page.
		Returns an empty string for the top level namespace.
		'''
		i = self.name.rfind(':')
		if i > 0:
			return self.name[:i]
		else:
			return ''

	@property
	def isroot(self):
		'''C{True} when this Path represents the top level namespace'''
		return self.name == ''

	def relname(self, path): # TODO make this use HRef !
		'''Get a part of this path relative to a parent path

		@param path: a parent L{Path}

		Raises an error if C{path} is not a parent

		@returns: the part of the path that is relative to C{path}
		'''
		if path.name == '': # root path
			return self.name
		elif self.name.startswith(path.name + ':'):
			i = len(path.name)+1
			return self.name[i:].strip(':')
		else:
			raise Exception, '"%s" is not below "%s"' % (self, path)

	@property
	def parent(self):
		'''Get the path for the parent page'''
		namespace = self.namespace
		if namespace:
			return Path(namespace)
		elif self.isroot:
			return None
		else:
			return Path(':')

	def parents(self):
		'''Generator function for parent Paths including root'''
		if ':' in self.name:
			path = self.name.split(':')
			path.pop()
			while len(path) > 0:
				namespace = ':'.join(path)
				yield Path(namespace)
				path.pop()
		yield Path(':')

	def child(self, name):
		'''Get a child Path

		@param name: the relative name for the child
		@returns: a new L{Path} object
		'''
		if len(self.name):
			return Path(self.name+':'+name)
		else: # we are the top level root namespace
			return Path(name)

	def ischild(self, parent):
		'''Check of this path is a child of a given path

		@param parent: a L{Path} object
		@returns: True when this path is a (grand-)child of C{parent}
		'''
		return parent.isroot or self.name.startswith(parent.name + ':')

	def commonparent(self, other):
		'''Find a common parent for two Paths

		@param other: another L{Path} object

		@returns: a L{Path} object for the first common parent or C{None}
		'''
		parent = []
		parts = self.parts
		other = other.parts
		if parts[0] != other[0]:
			return Path(':') # root
		else:
			for i in range(min(len(parts), len(other))):
				if parts[i] == other[i]:
					parent.append(parts[i])
				else:
					return Path(':'.join(parent))
			else:
				return Path(':'.join(parent))


HREF_REL_ABSOLUTE = 0
HREF_REL_FLOATING = 1
HREF_REL_RELATIVE = 2

class HRef(object):

	__slots__ = ('rel', 'names', 'sortkeys')

	@classmethod
	def new_from_wiki_link(klass, href):
		'''Constructor that constructs a L{HRef} object for a link as
		writen in zim's wiki syntax.
		@param href: a string for the link
		@returns: a L{HRef} object
		@raises ValueError: when the string could not be parsed
		(see L{Path.makeValidPageName()})

		@note: This mehtod HRef class assumes the logic of our wiki links
		for other formats, a separate constructor may be needed
		'''

		if href.startswith(':'):
			rel = HREF_REL_ABSOLUTE
		elif href.startswith('+'):
			rel = HREF_REL_RELATIVE
		else:
			rel = HREF_REL_FLOATING

		names = Path.makeValidPageName(href.lstrip('+'))
			# Can raise ValueError if link would reduce to empty string

		sortkeys = ':'.join(natural_sort_key(n) for n in names.split(':'))
		assert names.count(':') == sortkeys.count(':'), 'BUG: conflict in usage of the ":" character'

		return klass(rel, names, sortkeys)

	def __init__(self, rel, names, sortkeys):
		self.rel = rel
		self.names = names
		self.sortkeys = sortkeys

	def __str__(self):
		rel = {HREF_REL_ABSOLUTE: 'abs', HREF_REL_FLOATING: 'float', HREF_REL_RELATIVE: 'rel'}[self.rel]
		return '<%s: %s %s>' % (self.__class__.__name__, rel, self.names)

	def parts(self):
		return zip(
			self.names.split(':'),
			self.sortkeys.split(':')
		)

	def anchor_key(self):
		'''Returns the first part of C{sortkeys}, this is used to anchor
		the "floating" link type by looking for matching of this part
		in the path.
		'''
		if ':' in self.sortkeys:
			return self.sortkeys.split(':', 1)[0]
		else:
			return self.sortkeys


class Page(Path):
	'''Class to represent a single page in the notebook.

	Page objects inherit from L{Path} but have internal state reflecting
	content in the notebook. We try to keep Page objects unique
	by hashing them in L{Notebook.get_page()}, Path object on the other
	hand are cheap and can have multiple instances for the same logical path.
	We ask for a path object instead of a name in the constructor to
	encourage the use of Path objects over passing around page names as
	string.

	You can use a Page object instead of a Path anywhere in the APIs where
	a path is needed as argument etc.

	@ivar name: full page name (inherited from L{Path})
	@ivar hascontent: C{True} if the page has content
	@ivar haschildren: C{True} if the page has sub-pages
	@ivar modified: C{True} if the page was modified since the last
	store. Will be reset by L{Notebook.store_page()}
	@ivar readonly: C{True} when the page is read-only
	@ivar properties: dict with page properties
	@ivar valid: C{True} when this object is 'fresh' but C{False} e.g.
	after flushing the notebook cache. Invalid Page objects can still
	be used anywhere in the API where a L{Path} is needed, but not
	for any function that actually requires a L{Page} object.
	The way replace an invalid page object is by calling
	C{notebook.get_page(invalid_page)}.
	'''

	def __init__(self, path, haschildren=False, parsetree=None):
		'''Construct Page object. Needs a path object and a boolean to flag
		if the page has children.
		'''
		assert isinstance(path, Path)
		self.name = path.name
		self.haschildren = haschildren
			# Note: this attribute is updated by the owning notebook
			# when a child page is stored
		self.valid = True
		self.modified = False
		self._parsetree = parsetree
		self._ui_object = None
		self.readonly = True # stores need to explicitly set readonly False
		self.properties = {}

	@property
	def hascontent(self):
		'''Returns whether this page has content'''
		if self._parsetree:
			return self._parsetree.hascontent
		elif self._ui_object:
			tree = self._ui_object.get_parsetree()
			if tree:
				return tree.hascontent
			else:
				return False
		else:
			try:
				hascontent = self._source_hascontent()
			except NotImplementedError:
				return False
			else:
				return hascontent

	def exists(self):
		'''C{True} when the page has either content or children'''
		return self.haschildren or self.hascontent

	def isequal(self, other):
		'''Check equality of pages
		This method is intended to deal with case-insensitive storage
		backends (e.g. case insensitive file system) where the method
		is supposed to check equality of the resource.
		Note that this may be the case even when the page objects differ
		and can have a different name (so L{__cmp__} will not show
		them to be equal). However default falls back to L{__cmp__}.
		@returns: C{True} of both page objects point to the same resource
		@implementation: can be implementated by subclasses
		'''
		return self == other

	def get_parsetree(self):
		'''Returns the contents of the page

		@returns: a L{zim.formats.ParseTree} object or C{None}
		'''
		assert self.valid, 'BUG: page object became invalid'

		if self._parsetree:
			return self._parsetree
		elif self._ui_object:
			return self._ui_object.get_parsetree()
		else:
			try:
				self._parsetree = self._fetch_parsetree()
			except NotImplementedError:
				return None
			else:
				return self._parsetree

	def _source_hascontent(self):
		'''Method to be overloaded in sub-classes.
		Should return a parsetree True if _fetch_parsetree() returns content.
		'''
		raise NotImplementedError

	def _fetch_parsetree(self):
		'''Method to be overloaded in sub-classes.
		Should return a parsetree or None.
		'''
		raise NotImplementedError

	def set_parsetree(self, tree):
		'''Set the parsetree with content for this page

		@param tree: a L{zim.formats.ParseTree} object with content
		or C{None} to remove all content from the page

		@note: after setting new content in the Page object it still
		needs to be stored in the notebook to save this content
		permanently. See L{Notebook.store_page()}.
		'''
		assert self.valid, 'BUG: page object became invalid'

		if self.readonly:
			raise PageReadOnlyError, self

		if self._ui_object:
			self._ui_object.set_parsetree(tree)
		else:
			self._parsetree = tree

		self.modified = True

	def append_parsetree(self, tree):
		'''Append content

		@param tree: a L{zim.formats.ParseTree} object with content
		'''
		ourtree = self.get_parsetree()
		if ourtree:
			self.set_parsetree(ourtree + tree)
		else:
			self.set_parsetree(tree)

	def set_ui_object(self, object):
		'''Lock the page to an interface widget

		Setting a "ui object" locks the page and turns it into a proxy
		for that widget - typically a L{zim.gui.pageview.PageView}.
		The "ui object" should in turn have a C{get_parsetree()} and a
		C{set_parsetree()} method which will be called by the page object.

		@param object: a widget or similar object or C{None} to unlock
		'''
		if object is None:
			if self._ui_object:
				self._parsetree = self._ui_object.get_parsetree()
				self._ui_object = None
		else:
			assert self._ui_object is None, 'BUG: page already being edited by another widget'
			self._parsetree = None
			self._ui_object = object

	def dump(self, format, linker=None):
		'''Get content in a specific format

		Convenience method that converts the current parse tree to a
		particular format first.

		@param format: either a format module or a string
		that is understood by L{zim.formats.get_format()}.

		@param linker: a linker object (see e.g. L{BaseLinker})

		@returns: text as a list of lines or an empty list
		'''
		if isinstance(format, basestring):
			format = zim.formats.get_format(format)

		if not linker is None:
			linker.set_path(self)

		tree = self.get_parsetree()
		if tree:
			return format.Dumper(linker=linker).dump(tree)
		else:
			return []

	def parse(self, format, text, append=False):
		'''Store formatted text in the page

		Convenience method that parses text and sets the parse tree
		accordingly.

		@param format: either a format module or a string
		that is understood by L{zim.formats.get_format()}.
		@param text: text as a string or as a list of lines
		@param append: if C{True} the text is appended instead of
		replacing current content.
		'''
		if isinstance(format, basestring):
			format = zim.formats.get_format(format)

		if append:
			self.append_parsetree(format.Parser().parse(text))
		else:
			self.set_parsetree(format.Parser().parse(text))

	def iter_page_href(self):
		'''Generator for page links in the text

		This method gives the raw links from the content, which are used
		by the indexer. If you want nice L{Link} objects use
		L{index.links.list_links()} instead.

		@returns: yields a list of unique L{HRef} objects
		'''
		# FIXME optimize with a ParseTree.get_links that does not
		#       use Node

		def my_href_iter(tree):
			for elt in tree.findall(zim.formats.LINK):
				href = elt.attrib.pop('href')
				yield href

			for elt in tree.findall(zim.formats.IMAGE):
				if 'href' in elt.attrib:
					yield elt.attrib.pop('href')

		tree = self.get_parsetree()
		if tree:
			seen = set()
			for href in my_href_iter(tree):
				if href not in seen \
				and link_type(href) == 'page':
					seen.add(href)
					try:
						yield HRef.new_from_wiki_link(href)
					except ValueError:
						pass

	def get_tags(self):
		'''Generator for tags in the page content

		@returns: yields an unordered list of unique 2-tuples
		C{(name, attrib)} for tags in the parsetree.
		'''
		# FIXME optimize with a ParseTree.get_links that does not
		#       use Node
		tree = self.get_parsetree()
		if tree:
			seen = set()
			for elt in tree.findall(zim.formats.TAG):
				name = elt.gettext()
				if not name in seen:
					seen.add(name)
					yield name.lstrip('@'), elt.attrib

	def get_title(self):
		tree = self.get_parsetree()
		if tree:
			return tree.get_heading() or self.basename
		else:
			return self.basename

	def heading_matches_pagename(self):
		'''Returns whether the heading matches the page name.
		Used to determine whether the page should have its heading
		auto-changed on rename/move.
		@returns: C{True} when the heading can be auto-changed.
		'''
		tree = self.get_parsetree()
		if tree:
			return tree.get_heading() == self.basename
		else:
			return False


class IndexPage(Page):
	'''Class implementing a special page for displaying a namespace index'''

	def __init__(self, notebook, path=None, recurs=True):
		'''Constructor takes a namespace path'''
		if path is None:
			path = Path(':')
		Page.__init__(self, path, haschildren=True)
		self.index_recurs = recurs
		self.notebook = notebook
		self.properties['type'] = 'namespace-index'

	@property
	def hascontent(self): return True

	def get_parsetree(self):
		if self._parsetree is None:
			self._parsetree = self._generate_parsetree()
		return self._parsetree

	def _generate_parsetree(self):
		builder = zim.formats.ParseTreeBuilder()

		def add_namespace(path):
			pagelist = self.notebook.pages.list_pages(path)
			builder.start(zim.formats.BULLETLIST)
			for page in pagelist:
				builder.start(zim.formats.LISTITEM)
				builder.append(zim.formats.LINK,
					{'type': 'page', 'href': page.name},
					page.basename)
				builder.end(zim.formats.LISTITEM)
				if page.haschildren and self.index_recurs:
					add_namespace(page) # recurs
			builder.end(zim.formats.BULLETLIST)

		builder.start(zim.formats.FORMATTEDTEXT)
		builder.append(zim.formats.HEADING, {'level':1},
			'Index of %s\n' % self.name)
		add_namespace(self)
		builder.end(zim.formats.FORMATTEDTEXT)

		tree = builder.get_parsetree()
		#~ print "!!!", tree.tostring()
		return tree

