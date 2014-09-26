# -*- coding: utf-8 -*-

# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>


'''This module defines the ExportTemplateContext, which is a dictionary
used to set the template parameters when exporting.

Export template parameters supported::

  generator
 	.name	-- "Zim x.xx"
 	.user

  title

  navigation	- links to other export pages (if not included here)
 	home
 	up
  	prev			-- prev export file or None
  	next			-- next export file or None

  links			-- links to other export pages (index & plugins / ...) - sorted dict to have Index, Home first followed by plugins

 	link
 		.name
 		.basename

  pages			-- iter over special + content
 	.special	-- iter special pages to be included (index / plugins / ...) - support get() as well here
 	.content	-- iter pages being exported

 		page
 			.title		-- heading or basename
 			.name / .section / .basename
 			.heading
 			.body		-- full body minus first heading
 			.content	-- heading + body
 			.headings(max_level) 	-- iter over headings

 				headingsection
					.level
 					.heading
 					.body
 					.content

 			.properties
 			.links
 			.backlinks
 			.attachments

 				file
 					.basename
 					.mtime
 					.size

  options		-- dict with template options (for format)

  toc([page])			-- iter of headings in this page or all of pages
  index([section])	-- index of full export job, not just in this page
  uri(link|file)
  resource(file)
  anchor(page|section)

From template base::

  range() / len() / sorted() / reversed()
  strftime()
  strfcal()

Test in a template for single page export use: "IF loop.first and loop.last"
'''

import logging

logger = logging.getLogger('zim.export')


from zim import __version__ as ZIM_VERSION

import zim.datetimetz as datetime

from zim.utils import OrderedDict
from zim.fs import format_file_size
from zim.environ import environ

from zim.index import LINK_DIR_BACKWARD, LINK_DIR_FORWARD
from zim.notebook import Path

from zim.formats import ParseTree, ParseTreeBuilder, Visitor, \
	FORMATTEDTEXT, BULLETLIST, LISTITEM, STRONG, LINK, HEADING

from zim.templates import TemplateContextDict
from zim.templates.functions import ExpressionFunction


class ExportTemplateContext(dict):
	# No need to inherit from TemplateContextDict here, the template
	# will do a copy first anyway to protect changing content in this
	# object. This means functions and proxies can assume this dict is
	# save, and only "options" is un-save input.
	#
	# This object is not intended for re-use -- just instantiate a
	# new one for each export page

	def __init__(self, notebook, linker_factory, dumper_factory,
		title, content, special=None,
		home=None, up=None, prevpage=None, nextpage=None,
		links=None,
		index_generator=None, index_page=None,
	):
		'''Constructor

		When exporting one notebook page per export page ("multi file"),
		'C{content}' is a list of one page everytime. Even for exporting
		special pages, they go into 'C{content}' one at a time.
		The special pages are linked in 'C{links}' so the template can
		refer to them.

		When exporting multiple notebook pages to a single export page
		("single file"), 'C{content}' is a list of all notebook pages a
		nd 'C{special}' a list.

		@param notebook: L{Notebook} object
		@param linker_factory: function producing L{ExportLinker} objects
		@param dumper_factory: function producing L{DumperClass} objects
		@param title: the export page title
		@param content: list of notebook pages to be exported
		@param special: list of special notebook pages to be exported if any
		@param home: link to home page if any
		@param up: link to parent export page if any
		@param prevpage: link to previous export page if any
		@param nextpage: link to next export page if any
		@param links: list of links to special pages if any, links are
		given as a 2-tuple of a key and a target (either a L{Path} or
		a L{NotebookPathProxy})
		@param index_generator: a generator function or that
		provides L{IndexPath} or L{Page} objects to be used for the
		the C{index()} function. This method should take a single
		argument for the root namespace to show.
		See the definition of L{Index.walk()} or L{PageSelection.index()}.
		@param index_page: the current page to show in the index if any
		'''
		# TODO get rid of need of notebook here!
		self._content = content
		self._linker_factory = linker_factory
		self._dumper_factory = dumper_factory
		self._index_generator = index_generator or content
		self._index_page = index_page

		self.linker = linker_factory()

		def _link(l):
			if isinstance(l, basestring):
				return UriProxy(l)
			elif isinstance(l, Path):
				return NotebookPathProxy(l)
			else:
				assert l is None or isinstance(l, (NotebookPathProxy, FileProxy))
				return l

		if special:
			pages = ExportTemplatePageIter(
				special=PageListProxy(notebook, special, self.dumper_factory),
				content=PageListProxy(notebook, content, self.dumper_factory)
			)
		else:
			pages = ExportTemplatePageIter(
				content=PageListProxy(notebook, content, self.dumper_factory)
			)

		self.update({
			# Parameters
			'generator': {
					'name': 'Zim %s' % ZIM_VERSION,
					'user': environ['USER'], # TODO allow user name in prefs ?
			},
			'title': title,
			'navigation': {
				'home': _link(home),
				'up': _link(up),
				'prev': _link(prevpage),
				'next': _link(nextpage),
			},
			'links': OrderedDict(), # keep order of links for iteration
			'pages': pages,

			# Template settings
			'options': TemplateContextDict({}), # can be modified by template

			# Functions
			#~ 'toc': self.toc_function,
			'index': self.index_function,
			'pageindex': self.index_function, # backward compatibility
			'uri': self.uri_function,
			'anchor': self.anchor_function,
			'resource': self.resource_function,
		})

		if links:
			for k, l in links.items():
				l = _link(l)
				self['links'][k] = l

	def dumper_factory(self, page):
		'''Returns a L{DumperClass} instance for source page C{page}

		Only template options defined before this method is called are
		included, so only construct the "dumper" when you are about to
		use it
		'''
		linker = self._linker_factory(source=page)
		return self._dumper_factory(
			linker=linker,
			template_options=self['options']
		)

	#~ @ExpressionFunction
	#~ def toc_function(self):
		#~ # TODO
		#~ #       needs way to link heading achors in exported code (html)
		#~ #       pass these anchors through the parse tree
		#~
		#~ builder = ParseTreeBuilder()
		#~ builder.start(FORMATTEDTEXT)
		#~ builder.start(BULLETLIST)

		#~ for page in self._content:
			#~ current = 1
			#~ for level, heading in ...:
				#~ if level > current:
					#~ for range(current, level):
						#~ builder.start(BULLETLIST)
					#~ current = level
				#~ elif level < current:
					#~ for range(level, current):
						#~ builder.end(BULLETLIST)
					#~ current = level

				#~ builder.start(LISTITEM)
				#~ builder.append(LINK, {'href': ...}, anchor)
				#~ builder.end(LISTITEM)

			#~ for range(1, current):
				#~ builder.end(BULLETLIST)
			#~
		#~ builder.end(BULLETLIST)
		#~ builder.end(FORMATTEDTEXT)

		#~ tree = builder.get_parsetree()
		#~ if not tree:
			#~ return ''

		#~ print "!!!", tree.tostring()
		#~ dumper = self.dumper_factory(None)
		#~ return ''.join(dumper.dump(tree))

	@ExpressionFunction
	def index_function(self, namespace=None, collapse=True, ignore_empty=True):
		'''Index function for export template
		@param namespace: the namespace to include
		@param collapse: if C{True} only the branch of the current page
		is shown, if C{False} the whole index is shown
		@param ignore_empty: if C{True} empty pages (placeholders) are
		not shown in the index
		'''
		if not self._index_generator:
			return ''

		builder = ParseTreeBuilder()
		builder.start(FORMATTEDTEXT)
		builder.start(BULLETLIST)
		if self._index_page:
			expanded = [self._index_page] + list(self._index_page.parents())
		else:
			expanded = []
		stack = []

		for path in self._index_generator(namespace):
			if self._index_page and collapse \
			and not path.parent in expanded:
				continue # skip since it is not part of current path
			elif ignore_empty and not (path.hascontent or path.haschildren):
				continue # skip since page is empty

			if not stack:
				stack.append(path.parent)
			elif stack[-1] != path.parent:
				if path.ischild(stack[-1]):
					builder.start(BULLETLIST)
					stack.append(path.parent)
				else:
					while stack and stack[-1] != path.parent:
						builder.end(BULLETLIST)
						stack.pop()

			builder.start(LISTITEM)
			if path == self._index_page:
				# Current page is marked with the strong style
				builder.append(STRONG, text=path.basename)
			else:
				# links to other pages
				builder.append(LINK,
					{'type': 'page', 'href': ':'+path.name},
					path.basename)
			builder.end(LISTITEM)

		for p in stack:
			builder.end(BULLETLIST)
		builder.end(FORMATTEDTEXT)

		tree = builder.get_parsetree()
		if not tree:
			return ''

		#~ print "!!!", tree.tostring()
		dumper = self.dumper_factory(None)
		return ''.join(dumper.dump(tree))

	@ExpressionFunction
	def uri_function(self, link):
		if isinstance(link, UriProxy):
			return link.uri
		elif isinstance(link, NotebookPathProxy):
			return self.linker.page_object(link._path)
		elif isinstance(link, FilePathProxy):
			return self.linker.file_object(link._file)
		elif isinstance(link, basestring):
			return self.linker.link(link)
		else:
			return None

	@ExpressionFunction
	def anchor_function(self, page):
		# TODO remove prefix from anchors?
		if isinstance(page, (PageProxy, NotebookPathProxy)):
			return page.name
		else:
			return page

	@ExpressionFunction
	def resource_function(self, link):
		return self.linker.resource(link)


class ExportTemplatePageIter(object):

	def __init__(self, special=None, content=None):
		self.special = special or []
		self.content = content or []

	def __iter__(self):
		for p in self.special:
			yield p
		for p in self.content:
			yield p


class HeadingSplitter(Visitor):

	def __init__(self, max_level=None):
		self.max_level = max_level or 999
		self._builder = ParseTreeBuilder()
		self.headings = []

	def _split(self):
		self._builder.end(FORMATTEDTEXT)
		tree = self._builder.get_parsetree()
		if tree.hascontent:
			self.headings.append(tree)
		self._builder = ParseTreeBuilder()
		self._builder.start(FORMATTEDTEXT)

	def _close(self):
		tree = self._builder.get_parsetree()
		if tree.hascontent:
			self.headings.append(tree)

	def start(self, tag, attrib=None):
		if tag is HEADING and int(attrib['level']) <= self.max_level:
			self._split()
		self._builder.start(tag, attrib)

	def end(self, tag):
		self._builder.end(tag)
		if tag == FORMATTEDTEXT:
			self._close()

	def text(self, text):
		self._builder.text(text)

	def append(self, tag, attrib=None, text=None):
		if tag is HEADING and int(attrib['level']) <= self.max_level:
			self._split()
		self._builder.append(tag, attrib, text)


class PageListProxy(object):

	def __init__(self, notebook, iterable, dumper_factory):
		self._notebook = notebook
		self._iterable = iterable
		self._dumper_factory = dumper_factory

	def __iter__(self):
		for page in self._iterable:
			dumper = self._dumper_factory(page)
			yield PageProxy(self._notebook, page, dumper)


class ParseTreeProxy(object):

	@property
	def heading(self):
		head, body = self._split_head()
		return head

	@property
	def body(self):
		try:
			head, body = self._split_head()
			if body:
				lines = self._dumper.dump(body)
				return u''.join(lines)
			else:
				return ''
		except:
			logger.exception('Exception exporting page: %s', self._page.name)
			raise # will result in a "no such parameter" kind of error

	@property
	def content(self):
		try:
			if self._tree:
				lines = self._dumper.dump(self._tree)
				return u''.join(lines)
			else:
				return ''
		except:
			logger.exception('Exception exporting page: %s', self._page.name)
			raise # will result in a "no such parameter" kind of error

	def _split_head(self):
		if not hasattr(self, '_severed_head'):
			if self._tree:
				tree = self._tree.copy()
				head, level = tree.pop_heading()
				self._severed_head = (head, tree) # head can be None here
			else:
				self._severed_head = (None, None)

		return self._severed_head


class PageProxy(ParseTreeProxy):

	def __init__(self, notebook, page, dumper):
		self._notebook = notebook
		self._page = page
		self._tree = page.get_parsetree()
		self._dumper = dumper

		self.name = self._page.name
		self.section = self._page.namespace
		self.namespace = self._page.namespace # backward compat
		self.basename = self._page.basename
		self.properties = self._page.properties

	@property
	def title(self):
		return self.heading or self.basename

	@ExpressionFunction
	def headings(self, max_level=None):
		if self._tree and self._tree.hascontent:
			splitter = HeadingSplitter(max_level)
			self._tree.visit(splitter)
			for subtree in splitter.headings:
				yield HeadingProxy(self._page, subtree, self._dumper)

	@property
	def links(self):
		links = self._notebook.index.list_links(self._page, LINK_DIR_FORWARD)
		for link in links:
			yield NotebookPathProxy(link.target)

	@property
	def backlinks(self):
		links = self._notebook.index.list_links(self._page, LINK_DIR_BACKWARD)
		for link in links:
			yield NotebookPathProxy(link.source)

	@property
	def attachments(self):
		dir = self._notebook.get_attachments_dir(self._page)
		for basename in dir.list():
			file = dir.file(basename)
			if file.exists(): # is file
				yield FileProxy(file, './'+basename)


class HeadingProxy(ParseTreeProxy):

	def __init__(self, page, tree, dumper):
		self._page = page
		self._tree = tree
		self._dumper = dumper
		self.level = tree.get_heading_level() or 1


class FilePathProxy(object):

	def __init__(self, file, relpath=None):
		self._file = file
		self.name = relpath or file.basename
		self.basename = file.basename


class FileProxy(FilePathProxy):

	@property
	def mtime(self):
		return datetime.datetime.fromtimestamp(float(self._file.mtime()))

	@property
	def size(self):
		return format_file_size(self._file.size())


class NotebookPathProxy(object):

	def __init__(self, path):
		self._path = path
		self.name = path.name
		self.basename = path.basename
		self.section = path.namespace
		self.namespace = path.namespace # backward compat


class UriProxy(object):

	def __init__(self, uri):
		self.uri = uri

	def __str__(self):
		return self.uri

