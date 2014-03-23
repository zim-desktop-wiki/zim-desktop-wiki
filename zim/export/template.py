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
 			.name / .namespace / .basename
 			.heading
 			.body		-- full body minus first heading
 			.content	-- heading + body
 			.sections 	-- iter over sections (headings) -- TODO later

 				section -- TODO
 					.heading
 					.body
 					.level

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
  index([namespace])	-- index of full export job, not just in this page
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

		@param format: the export format
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
		'''
		# TODO get rid of need of noetbook here!
		self.notebook = notebook
		self._linker_factory = linker_factory
		self._dumper_factory = dumper_factory

		self.linker = linker_factory()

		def _link(l):
			if isinstance(l, Path):
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
			'toc': self.toc_function,
			'index': self.index_function,
			'uri': self.uri_function,
			'anchor': self.anchor_function,
			'resource': self.resource_function,
		})

		if links:
			for k, l in links:
				l = _link(l)
				self['links'][k] = l

	def dumper_factory(self, page):
		'''Returns a L{DumperClass} instance for source page C{page}'''
		linker = self._linker_factory(source=page)
		return self._dumper_factory(
			linker=linker,
			template_options=self['options']
		)

	@ExpressionFunction
	def toc_function(self):
		pass # TODO

	@ExpressionFunction
	def index_function(self):
		# TODO some caching for the index when generating many similar pages ?
		pass # TODO

	@ExpressionFunction
	def uri_function(self, link):
		if isinstance(link, NotebookPathProxy):
			return self.linker.page_object(link._path)
		elif isinstance(link, FilePathProxy):
			return self.linker.file_object(link._file)
		else:
			return self.linker.link(link)

	@ExpressionFunction
	def anchor_function(self, page):
		# TODO remove prefix from anchors?
		if isinstance(page, (PageProxy, NotebookPathProxy)):
			return "#" + page.name
		else:
			return "#" + page

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


class PageListProxy(object):

	def __init__(self, notebook, iterable, dumper_factory):
		self._notebook = notebook
		self._iterable = iterable
		self._dumper_factory = dumper_factory

	def __iter__(self):
		for page in self._iterable:
			dumper = self._dumper_factory(page)
			yield PageProxy(self._notebook, page, dumper)


class PageProxy(object):

	def __init__(self, notebook, page, dumper):
		self._notebook = notebook
		self._page = page
		self._dumper = dumper

		self.name = self._page.name
		self.namespace = self._page.namespace
		self.basename = self._page.basename
		self.properties = self._page.properties

	@property
	def title(self):
		return self.heading or self.basename

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
			tree = self._page.get_parsetree()
			if tree:
				lines = self._dumper.dump(tree)
				return u''.join(lines)
			else:
				return ''
		except:
			logger.exception('Exception exporting page: %s', self._page.name)
			raise # will result in a "no such parameter" kind of error

	def _split_head(self):
		if not hasattr(self, '_severed_head'):
			tree = self._page.get_parsetree()
			if tree:
				tree = tree.copy()
				head, level = tree.pop_heading()
				self._severed_head = (head, tree) # head can be None here
			else:
				self._severed_head = (None, None)

		return self._severed_head

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



#~ class PageSectionProxy(object):
	#~ #					.heading
	#~ #					.body
	#~ #					.level
	#~ pass


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
		self.namespace = path.namespace

