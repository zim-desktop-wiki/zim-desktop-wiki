
# Copyright 2008-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import re
import logging
import itertools

from typing import Generator, Generic, List, Optional, Union

logger = logging.getLogger('zim.notebook')


from zim.parsing import link_type
from zim.errors import Error

import zim.formats
import zim.newfs

from zim.signals import SignalEmitter, SIGNAL_NORMAL

import zim.datetimetz as datetime


_pagename_reduce_colon_re = re.compile('::+')
_pagename_invalid_char_re = re.compile(
	'(' +
		r'^[_\W]+|(?<=:)[_\W]+' +
	'|' +
		'[' + re.escape(''.join(
			("?", "#", "/", "\\", "*", '"', "<", ">", "|", "%", "\t", "\n", "\r")
		)) + ']' +
	')',
re.UNICODE)
	# This pattern matches a non-alphanumber at start or after the ':'
	# separator. It also matches any invalid character.
	# The UNICODE flag is used to make the alphanumber check international.


def shortest_unique_names(paths: List['Path']) -> List[str]:
	'''Returns the shortest unique name for each path in paths
	@param paths: list of L{Path} objects
	@returns: list of strings
	'''
	by_basename = {}
	for path in paths:
		basename = path.basename
		mylist = by_basename.setdefault(basename, [])
		mylist.append(path)

	result = []
	for path in paths:
		basename = path.basename
		conflicts = by_basename[basename]
		if len(conflicts) == 1:
			result.append(path.basename)
		else:
			conflicts.remove(path)
			conflicts.insert(0, path) # shuffle path of interest to front
			reverse_paths = [reversed(p.name.split(':')) for p in conflicts]
			names = []
			for parts in itertools.zip_longest(*reverse_paths):
				if parts[0] is None:
					break
				elif parts[0] not in parts[1:]:
					names.append(parts[0])
					break
				else:
					names.append(parts[0])

			result.append(':'.join(reversed(names)))

	return result


class Path():
	'''Class representing a page name in the notebook

	This is the parent class for the Page class. It contains the name
	of the page and is used instead of the actual page object by methods
	that only need to know the name of the page. Path objects have no
	internal state and are essentially normalized page names. It also
	has a number of methods to compare page names and determining what
	the parent pages are etc.

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
	def assertValidPageName(name: str) -> None:
		'''Raises an C{AssertionError} if C{name} does not represent
		a valid page name.
		This is a strict check, most names that fail this test can still
		be cleaned up by the L{makeValidPageName()}.
		@raises AssertionError: if the name is not valid
		'''
		assert isinstance(name, str)
		if not name.strip(':') \
		or _pagename_reduce_colon_re.search(name) \
		or _pagename_invalid_char_re.search(name):
			raise AssertionError('Not a valid page name: %s' % name)

	@staticmethod
	def makeValidPageName(name: str) -> str:
		'''Remove any invalid characters from the string and return
		a valid page name. Only string that can not be turned in
		somthing valid is a string that reduces to an empty string
		after removing all invalid characters.
		@raises ValueError: when the result would be an empty string
		'''
		newname = _pagename_reduce_colon_re.sub(':', name.strip(':'))
		newname = _pagename_invalid_char_re.sub('', newname)
		newname = newname.replace('_', ' ')
		try:
			Path.assertValidPageName(newname)
		except AssertionError:
			raise ValueError('Not a valid page name: %s (was: %s)' % (newname, name))
		return newname

	def __init__(self, name: Union[str, tuple]):
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
			self.name = str(self.name)
		except UnicodeDecodeError:
			raise ValueError('BUG: invalid input, page names should be in ascii, or given as unicode')

	@classmethod
	def new_from_zim_config(klass, string: str) -> 'Path':
		'''Returns a new object based on the string representation for
		that path.
		'''
		return klass(klass.makeValidPageName(string))

	def serialize_zim_config(self) -> str:
		'''Returns the name for serializing this path'''
		return self.name

	def __repr__(self):
		return '<%s: %s>' % (self.__class__.__name__, self.name)

	def __str__(self):
		return self.name

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
	def parts(self) -> List[str]:
		'''Get all the parts of the name (split on ":")'''
		return self.name.split(':')

	@property
	def basename(self) -> str:
		'''Get the basename of the path (last part of the name)'''
		i = self.name.rfind(':') + 1
		return self.name[i:]

	@property
	def namespace(self) -> str:
		'''Gives the name for the parent page.
		Returns an empty string for the top level namespace.
		'''
		i = self.name.rfind(':')
		if i > 0:
			return self.name[:i]
		else:
			return ''

	@property
	def isroot(self) -> bool:
		'''C{True} when this Path represents the top level namespace'''
		return self.name == ''

	def relname(self, path: 'Path') -> str: # TODO make this use HRef !
		'''Get a part of this path relative to a parent path

		@param path: a parent L{Path}

		@raises ValueError: if C{path} is not a parent

		@returns: the part of the path that is relative to C{path}
		'''
		if path.name == '': # root path
			return self.name
		elif self.name.startswith(path.name + ':'):
			i = len(path.name) + 1
			return self.name[i:].strip(':')
		else:
			raise ValueError('"%s" is not below "%s"' % (self, path))

	@property
	def parent(self) -> 'Path':
		'''Get the path for the parent page'''
		namespace = self.namespace
		if namespace:
			return Path(namespace)
		elif self.isroot:
			return None
		else:
			return Path(':')

	def parents(self) -> Generator['Path', None, None]:
		'''Generator function for parent Paths including root'''
		if ':' in self.name:
			path = self.name.split(':')
			path.pop()
			while len(path) > 0:
				namespace = ':'.join(path)
				yield Path(namespace)
				path.pop()
		yield Path(':')

	def child(self, basename: str) -> 'Path':
		'''Get a child Path

		@param basename: the relative name for the child
		@returns: a new L{Path} object
		'''
		return Path(self.name + ':' + basename)

	def ischild(self, parent: 'Path') -> bool:
		'''Check whether this path is a child of a given path
		@param parent: a L{Path} object
		@returns: True when this path is a (grand-)child of C{parent}
		'''
		return parent.isroot or self.name.startswith(parent.name + ':')

	def match_namespace(self, namespace: 'Path') -> bool:
		'''Check whether this path is in a specific section of the notebook
		@param namespace: a L{Path} object
		@returns: True when this path is equal to C{namespace} or is a (grand-)child of C{namespace}
		'''
		return namespace.isroot or self.name == namespace.name or self.name.startswith(namespace.name + ':')

	def commonparent(self, other: 'Path') -> 'Path':
		'''Find a common parent for two Paths

		@param other: another L{Path} object

		@returns: a L{Path} object for the first common parent
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


HRef_rel_flavor = int
HREF_REL_ABSOLUTE = 0
HREF_REL_FLOATING = 1
HREF_REL_RELATIVE = 2

class HRef():
	'''Represents a link as it appears in the wiki source.
	Contains semantic information about the link type, but
	does not contain an end point.

	Introduced to help preserve link type when moving content.

	@note: To create the shortest link between two pages,
	use L{Notebook.pages.create_link}

	@note: To resolve a link into a L{Path}, create a L{HRef}
	and pass it to L{Notebook.pages.resolve_link}.
	'''

	__slots__ = ('rel', 'names', 'anchor')

	@classmethod
	def makeValidHRefString(klass, href: str) -> str:
		return klass.new_from_wiki_link(href).to_wiki_link()

	@classmethod
	def new_from_wiki_link(klass, href: str) -> 'Href':
		'''Constructor that constructs a L{HRef} object for a link as
		written in zim's wiki syntax.
		@param href: a string for the link
		@raises ValueError: when the string could not be parsed
		(see L{Path.makeValidPageName()})

		@note: This method HRef class assumes the logic of our wiki links.
		For other formats, a separate constructor may be needed.
		'''
		href = href.strip()

		if href.startswith(':'):
			rel = HREF_REL_ABSOLUTE
		elif href.startswith('+'):
			rel = HREF_REL_RELATIVE
		else:
			rel = HREF_REL_FLOATING

		anchor = None
		if '#' in href:
			href, anchor = href.split('#', 1)
			anchor = zim.formats.heading_to_anchor(anchor) # make valid achor string

		names = Path.makeValidPageName(href.lstrip('+')) if href else ""

		return klass(rel, names, anchor)

	def __init__(self, rel: HRef_rel_flavor, names: str, anchor: Optional[str] = None):
		self.rel = rel
		self.names = names
		self.anchor = anchor

	def __str__(self):
		rel = {HREF_REL_ABSOLUTE: 'abs', HREF_REL_FLOATING: 'float', HREF_REL_RELATIVE: 'rel'}[self.rel]
		return '<%s: %s %s %s>' % (self.__class__.__name__, rel, self.names, self.anchor)

	def __eq__(self, other):
		return (self.__class__ is other.__class__) and (str(self) == str(other))

	def parts(self) -> Union[List, List[str]]:
		return self.names.split(':') if self.names else []

	def short_name(self) -> str:
		" Returns the last name part and/or anchor if any. "
		name = self.parts()[-1] if self.names else ""
		return name + "#" + self.anchor if self.anchor else name

	def to_wiki_link(self) -> str:
		'''Returns href as text for wiki link'''
		if self.rel == HREF_REL_ABSOLUTE:
			link = ":" + self.names.strip(':')
		elif self.rel == HREF_REL_RELATIVE:
			link = "+" + self.names
		else:
			link = self.names

		if self.anchor:
			link += "#" + self.anchor

		return link


class PageError(Error):

	def __init__(self, path):
		self.path = path
		self.msg = self._msg % path.name


class PageReadOnlyError(PageError):
	_msg = _('Can not modify page: %s') # T: error message for read-only pages


class Page(Path, SignalEmitter):
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
	@ivar readonly: C{True} when the page is read-only or belongs to a readonly notebook

	@signal: C{storage-changed (changed-on-disk)}: signal emitted on page
	change. The argument "changed-on-disk" is C{True} when an external
	edit was detected. For internal edits it is C{False}.
	@signal: C{modified-changed ()}: emitted when the page is edited
	'''

	__signals__ = {
		'storage-changed': (SIGNAL_NORMAL, None, (bool,)),
		'modified-changed': (SIGNAL_NORMAL, None, ()),
	}

	def __init__(self, path, haschildren, file, folder, format):
		assert isinstance(path, Path)
		self.name = path.name
		self.haschildren = haschildren
			# Note: this attribute is updated by the owning notebook
			# when a child page is stored
		self._modified = False
		self._change_counter = 0
		self._parsetree = None
		self._textbuffer = None
		self._meta = None

		self._readonly = None
		self._last_etag = None
		if isinstance(format, str):
			self.format = zim.formats.get_format(format)
		else:
			self.format = format
		self.source_file = file
		self.attachments_folder = folder

	@property
	def readonly(self):
		if self._readonly is None:
			self._readonly = not self.source_file.iswritable()
		return self._readonly

	@property
	def mtime(self):
		return self.source_file.mtime() if self.source_file.exists() else None

	@property
	def ctime(self):
		return self.source_file.ctime() if self.source_file.exists() else None

	@property
	def hascontent(self):
		'''Returns whether this page has content'''
		if self._textbuffer:
			return self._textbuffer.hascontent
		elif self._parsetree:
			return self._parsetree.hascontent
		else:
			return self.source_file.exists()

	@property
	def modified(self):
		return self._modified

	def set_modified(self, modified):
		if modified:
			# HACK: by setting page.modified to a number rather than a
			# bool we can use this number to check against race conditions
			# in notebook.store_page_async post handler
			self._change_counter = max(1, (self._change_counter + 1) % 1000)
			self._modified = self._change_counter
			assert bool(self._modified) is True, 'BUG in counter'
		else:
			self._modified = False
		self.emit('modified-changed')

	def on_buffer_modified_changed(self, buffer):
		# one-way traffic, set page modified after modifying the buffer
		# but do not set page.modified False again when buffer goes
		# back to un-modified. Reason is that we use the buffer modified
		# state to track if we already requested the parse tree (see
		# get_parsetree()) while page modified is used to track need
		# for saving and is reset after save was done
		if buffer.get_modified():
			if self.readonly:
				logger.warning('Buffer edited while page read-only - potential bug')
			self.set_modified(True)

	def _store(self):
		tree = self.get_parsetree()
		self._store_tree(tree)

	def _store_tree(self, tree):
		if tree and tree.hascontent:
			if self._meta is not None:
				tree.meta.update(self._meta) # Preserver headers
			elif self.source_file.exists():
				# Try getting headers from file
				try:
					text = self.source_file.read()
				except zim.newfs.FileNotFoundError:
					return None
				else:
					parser = self.format.Parser()
					tree = parser.parse(text)
					self._meta = tree.meta
					tree.meta.update(self._meta) # Preserver headers
			else: # not self.source_file.exists()
				now = datetime.now()
				tree.meta['Creation-Date'] = now.isoformat()

			lines = self.format.Dumper().dump(tree, file_output=True)
			self._last_etag = self.source_file.writelines_with_etag(lines, self._last_etag)
			self._meta = tree.meta
		else:
			self.source_file.remove()
			self._last_etag = None
			self._meta = None
		self.emit('storage-changed', False)

	def check_source_changed(self):
		'''Checks for changes in the source file and load it if needed

		If the page has a C{textbuffer} and it contains unsaved changes, this
		method will not overwrite them and you'll get an error on next attempt
		to save. To force overwrite see L{reload_textbuffer()}
		'''
		if (
			self._last_etag
			and not (self.source_file.exists() and self.source_file.verify_etag(self._last_etag))
		) or (
			not self._last_etag
			and self.source_file.exists()
		):
			logger.info('Page changed on disk: %s', self.name)
			self._last_etag = None
			self._meta = None
			if self._textbuffer and not self._textbuffer.get_modified():
				self.reload_textbuffer()
			else:
				self._parsetree = None

			self.emit('storage-changed', True)
			return True
		else:
			return False

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
		if self is other or self == other:
			return True
		elif self.source_file.exists():
			return self.source_file.isequal(other.source_file)
		else:
			return False

	def get_parsetree(self):
		'''Returns the contents of the page

		@returns: a L{zim.formats.ParseTree} object or C{None}
		'''
		if self._textbuffer:
			if self._textbuffer.get_modified() or self._parsetree is None:
				self._parsetree = self._textbuffer.get_parsetree()
				self._textbuffer.set_modified(False)
			#~ print self._parsetree.tostring()
			return self._parsetree
		elif self._parsetree:
			return self._parsetree
		else:
			try:
				text, self._last_etag = self.source_file.read_with_etag()
			except zim.newfs.FileNotFoundError:
				return None
			else:
				parser = self.format.Parser()
				self._parsetree = parser.parse(text, file_input=True)
				self._meta = self._parsetree.meta
				assert self._meta is not None
				return self._parsetree

	def set_parsetree(self, tree):
		'''Set the parsetree with content for this page

		@param tree: a L{zim.formats.ParseTree} object with content
		or C{None} to remove all content from the page

		@note: after setting new content in the Page object it still
		needs to be stored in the notebook to save this content
		permanently. See L{Notebook.store_page()}.
		'''
		if self.readonly:
			raise PageReadOnlyError(self)
		self._set_parsetree(tree)

	def _set_parsetree(self, tree):
		self._parsetree = tree
		if self._textbuffer:
			assert not self._textbuffer.get_modified(), 'BUG: changing parsetree while buffer was changed as well'
			try:
				if tree is None:
					self._textbuffer.clear()
				else:
					self._textbuffer.set_parsetree(tree)
			except:
				# Prevent auto-save to kick in at any cost
				self._textbuffer.set_modified(False)
				raise
			else:
				self._textbuffer.set_modified(False)

		self.set_modified(True)

	def append_parsetree(self, tree):
		'''Append content

		@param tree: a L{zim.formats.ParseTree} object with content
		'''
		if self._textbuffer:
			self._textbuffer.append_parsetree(tree)
		else:
			ourtree = self.get_parsetree()
			if ourtree:
				self.set_parsetree(ourtree + tree)
			else:
				self.set_parsetree(tree)

	def get_textbuffer(self, constructor=None):
		'''Get a C{Gtk.TextBuffer} for the page

		Will either return an existing buffer or construct a new one and return
		it. A C{Gtk.TextBuffer} can be shared between multiple C{Gtk.TextView}s.
		The page object owns the textbuffer to allow multiple views on the same
		page.

		Once a buffer is set, also methods like L{get_parsetree()} and
		L{get_parsetree()} will interact with this buffer.

		@param constructor: if not buffer was set previously, this function
		is called to construct the buffer.

		@returns: a C{TextBuffer} object or C{None} if no buffer is set and
		no constructor is provided.
		'''
		if self._textbuffer is None:
			if constructor is None:
				return None

			tree = self.get_parsetree()
			self._textbuffer = constructor(parsetree=tree)
			self._textbuffer.connect('modified-changed', self.on_buffer_modified_changed)

		return self._textbuffer

	def reload_textbuffer(self):
		'''Reload page content from source file and update the textbuffer if set

			NOTE: this method overwrites any changes in the C{textbuffer} or
			C{parsetree} that have not been saved to file !
		'''
		buffer = self._textbuffer
		self._textbuffer = None
		self._parsetree = None
		if buffer is not None:
			tree = self.get_parsetree()
			self._textbuffer = buffer
			buffer.set_modified(False)
			self._set_parsetree(tree)
				# load new tree in buffer, undo-able in 1 step
				# private method circumvents readonly check !
			self.set_modified(False)
		# else do nothing - source will be read with next call to `get_parsetree()`

	def dump(self, format, linker=None):
		'''Get content in a specific format

		Convenience method that converts the current parse tree to a
		particular format first.

		@param format: either a format module or a string
		that is understood by L{zim.formats.get_format()}.

		@param linker: a linker object (see e.g. L{BaseLinker})

		@returns: text as a list of lines or an empty list
		'''
		if isinstance(format, str):
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
		if isinstance(format, str):
			format = zim.formats.get_format(format)

		if append:
			self.append_parsetree(format.Parser().parse(text))
		else:
			self.set_parsetree(format.Parser().parse(text))

	def get_title(self):
		tree = self.get_parsetree()
		if tree:
			return tree.get_heading_text() or self.basename
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
			return tree.get_heading_text() == self.basename
		else:
			return False
