# -*- coding: utf-8 -*-

# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>


'''PageSelection objects wrap the list of pages to be exported'''


class PageSelection(object):
	'''Base class defining the public API'''

	notebook = None #: The L{Notebook} object
	prefix = None #: optional L{Path} object with common prefix of pages in the selection, or C{None}
	name = None #: name used in export template
	title = None # name used in export template

	def __iter__(self):
		'''Iterate page obejcts
		@implementation: must be implemented by subclases
		'''
		raise NotImplemented


	# TODO add alternative method to walk names for ToC
	# TODO add __len__ that gives total pages for progress
	# TODO Use collections subclass to make interface complete ?


class AllPages(PageSelection):
	'''Selection of all pages in a notebook'''

	def __init__(self, notebook):
		self.notebook = notebook
		self.name = notebook.name
		self.title = notebook.name # XXX implement notebook.title

	def __iter__(self):
		return self.notebook.walk()


class SinglePage(PageSelection):
	'''Selection of one specific page without subpages'''

	def __init__(self, notebook, page):
		self.notebook = notebook
		self.page = page
		self.name = self.page.name
		self.title = self.page.name # XXX implement page.title (use heading)
		self.prefix = page

	def __iter__(self):
		yield self.notebook.get_page(self.page)


class SubPages(SinglePage):
	'''Selection of pages in sub-tree of a notebook'''

	def __iter__(self):
		yield self.notebook.get_page(self.page)
		for page in self.notebook.walk(self.page):
			yield page




