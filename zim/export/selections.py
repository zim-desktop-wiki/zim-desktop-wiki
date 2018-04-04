
# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>


'''PageSelection objects wrap the list of pages to be exported'''


from zim.notebook import PageNotFoundError


class PageSelection(object):
	'''Base class defining the public API'''

	notebook = None #: The L{Notebook} object
	prefix = None #: optional L{Path} object with common prefix of pages in the selection, or C{None}
	name = None #: name used in export template
	title = None # name used in export template

	def __iter__(self):
		'''Iterate page objects
		@implementation: must be implemented by subclases
		'''
		raise NotImplemented

	def index(self, namespace=None):
		'''Iterate path objects for template C{index()} function, depth first
		@param namespace: the sub namespace to iterate or None to iterate
		toplevel
		'''
		raise NotImplemented

	# TODO add __len__ that gives total pages for progress
	# TODO Use collections subclass to make interface complete ?


class AllPages(PageSelection):
	'''Selection of all pages in a notebook'''

	def __init__(self, notebook):
		self.notebook = notebook
		self.name = notebook.name
		self.title = notebook.name # XXX implement notebook.title

	def __iter__(self):
		for path in self.notebook.pages.walk():
			try:
				yield self.notebook.get_page(path)
			except PageNotFoundError:
				pass

	def index(self, namespace=None):
		return self.notebook.pages.walk(namespace)


class SinglePage(PageSelection):
	'''Selection of one specific page without subpages'''

	def __init__(self, notebook, page):
		self.notebook = notebook
		self.page = page
		self.name = self.page.name
		self.title = self.page.name # XXX implement page.title (use heading)
		self.prefix = page

	def __iter__(self):
		try:
			yield self.notebook.get_page(self.page)
		except PageNotFoundError:
			pass

	def index(self, namespace=None):
		if namespace is None or self.page.ischild(namespace):
			yield self.page
		else:
			pass


class SubPages(SinglePage):
	'''Selection of pages in sub-tree of a notebook'''

	def __iter__(self):
		yield self.notebook.get_page(self.page)
		for path in self.notebook.pages.walk(self.page):
			yield self.notebook.get_page(path)

	def index(self, namespace=None):
		if namespace is None or namespace.name == self.page.name:
			yield self.page
			for page in self.notebook.pages.walk(self.page):
				yield page
		elif namespace.ischild(self.page):
			for page in self.notebook.pages.walk(namespace):
				yield page
		else:
			pass
