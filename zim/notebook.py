# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''
This package contains the main Notebook class together
with basic classed like Page and Namespace.

This package defines the public interface towards the
noetbook.  As a backend it uses one of more packages from
the 'stores' namespace.
'''

import weakref

from zim.fs import *
from zim.config import ConfigList, config_file, data_dir
from zim.parsing import Re, is_url_re, is_email_re
import zim.stores
import zim.history

def get_notebook(notebook):
	'''Takes a path or name and returns a notebook object'''
	if not isinstance(notebook, Dir):
		# We are not sure if it is a name or a path, try lookup
		name = notebook
		table = get_notebook_table()
		notebook = unicode(notebook)
		if notebook in table:
			if notebook == '_default_' and table['_default_'] in table:
				# default is not set to a path, but to another notebook name
				notebook = table[table[notebook]]
			else:
				notebook = table[notebook]
			notebook = Dir(notebook)
		elif notebook == '_manual_':
			notebook = data_dir('manual')
		else:
			notebook = Dir(notebook) # maybe it's a path after all
	else:
		name = notebook.path

	if notebook.exists():
		return Notebook(path=notebook, name=name)
	else:
		raise Exception, 'no such notebook: %s' % notebook


notebook_table_ref = lambda: None

def get_notebook_table():
	'''FIXME'''
	table = notebook_table_ref()
	if table is None:
		table = ConfigList('notebooks.list')
		_notebook_table_ref = weakref.ref(table)
	return table


def set_notebooks_dict(notebooks):
	'''FIXME'''
	assert isinstance(notebooks, ConfigList)
	file = config_file('notebooks.list')
	notebooks.write(file)


class PageNameError(Exception):
	pass


class LookupError(Exception):
	pass


class Notebook(object):
	'''FIXME'''

	def __init__(self, path=None, name=None, config=None):
		'''FIXME'''
		self.namespaces = []
		self.stores = {}
		self.page_cache = weakref.WeakValueDictionary()
		self.dir = None
		self.name = name
		self._history_ref = lambda: None

		if isinstance(path, Dir):
			self.dir = path
			if config is None:
				pass # TODO: load config file from dir
			# TODO check if config defined root namespace
			self.add_store('', 'files') # set root
			# TODO add other namespaces from config
		elif isinstance(path, File):
			assert False, 'TODO: support for single file notebooks'
		elif not path is None:
			assert False, 'path should be either File or Dir'

	def add_store(self, namespace, store, **args):
		'''Add a store to the notebook under a specific namespace.
		All other args will be passed to the store.
		Returns the store object.
		'''
		mod = zim.stores.get_store(store)
		mystore = mod.Store(
			notebook=self,
			namespace=namespace,
			**args
		)
		self.stores[namespace] = mystore
		self.namespaces.append(namespace)

		# keep order correct for lookup
		self.namespaces.sort()
		self.namespaces.reverse()

		return mystore

	def get_store(self, name, resolve=False):
		'''Returns the store object to handle a page or namespace.'''
		for namespace in self.namespaces:
			# longest match first because of reverse sorting
			if name.startswith(namespace):
				return self.stores[namespace]
		raise LookupError, 'Could not find store for: %s' % name

	def resolve_store(self, name):
		'''Case insensitive version of get_store()'''
		lname = name.lower()
		for namespace in self.namespaces:
			# longest match first because of reverse sorting
			if lname.startswith( namespace.lower() ):
				return self.stores[namespace]
		raise LookupError, 'Could not find store for: %s' % name

	def get_stores(self, name):
		'''Returns a list of (path, store) for all stores in
		the path to a specific page. The 'path' item in the result is
		the maximum part of the path handled by that store.
		'''
		stores = []
		path = name
		for namespace in self.namespaces:
			# longest match first because of reverse sorting
			if name.startswith(namespace):
				store = self.stores[namespace]
				stores.append( (path, store) )
				# set path for next match to namespace part
				# which is not covered by this store
				i = store.namespace.rfind(':')
				path = store.namespace[:i]
		return stores

	def get_history(self):
		history = self._history_ref()
		if history is None:
			history = zim.history.History(self)
			self._history_ref = weakref.ref(history)
		return history

	def normalize_name(self, name):
		'''Normalizes a page name to a valid form.
		Raises a PageNameError if name is empty.
		'''
		name = name.strip(':')
		if not name:
			raise PageNameError, 'Empty page name'
		parts = [p for p in name.split(':') if p]
		return ':'.join(parts)

	def normalize_namespace(self, name):
		'''Normalizes a namespace name to a valid form.'''
		name = name.strip(':')
		# TODO remove / encode chars that are not allowed
		if not name:
			return ''
		parts = [p for p in name.split(':') if p]
		return ':'.join(parts)

	def resolve_name(self, name, namespace=''):
		'''Returns a proper page name from links or user input.

		'namespace' is the namespace of the refering page, if any.

		If namespace is empty or if the page name starts with a ':'
		the name is considered an absolute name and only case is
		resolved. If the page does not exist the last part(s) of the
		name will remain in the case as given.

		If the name is relative to namespace we first look for a match
		of the first part of the name in the path. If that fails we
		do a search for the first part of the name through all
		namespaces in the path. If no match was found we default to
		the name relative to 'namespace'.
		'''
		isabs = name.startswith(':') or not namespace
		name = self.normalize_name(name)

		# If I'm not mistaken each call to this method will
		# result in exactly one call to the corresponding method
		# for a specific store (but potentially for multiple stores).

		def resolve_abs(name):
			# only resolve case for absolute name
			# keep case as is when not found
			store = self.resolve_store(name)
			n = store.resolve_name(name)
			return n or name

		if isabs:
			return resolve_abs(name)
		else:
			# first check if we see an explicit match in the path
			anchor = name.split(':')[0].lower()
			path = namespace.lower().split(':')[1:]
			if anchor in path:
				# ok, so we can shortcut to an absolute path
				path.reverse() # why is there no rindex or rfind ?
				i = path.index(anchor) + 1
				path = path[i:]
				path.reverse()
				path.append( name.lstrip(':') )
				name = ':'.join(path)
				return resolve_abs(name)
			else:
				# no luck, do a search through the whole path
				stores = self.get_stores(namespace)
				for path, store in stores:
					n = store.resolve_name(name, namespace=path)
					if not n is None: return n

				# name not found, keep case as is
				return namespace+name

	def get_page(self, name):
		'''Returns a Page object'''
		name = self.normalize_name(name)
		if name in self.page_cache:
			return self.page_cache[name]
		else:
			store = self.get_store(name)
			page = store.get_page(name)
			self.page_cache[name] = page
			return page

	def get_home_page(self):
		'''Returns a page object for the home page.'''
		return self.get_page(':Home') # TODO: make this configable

	def get_root(self):
		'''Returns a Namespace object for root namespace.'''
		return self.stores[''].get_root()

	def get_namespace(self, namespace):
		'''Returns a Namespace object for 'namespace'.'''
		namespace = self.normalize_namespace(namespace)
		store = self.get_store(namespace)
		return store.get_namespace(namespace)

	def get_previous(self, page):
		'''Like Namespace.get_previous(page), but crosses namespace bounds'''

	def get_next(self, page):
		'''Like Namespace.get_next(page), but crosses namespace bounds'''

	#~ def move_page(self, name, newname):
		#~ '''FIXME'''

	#~ def copy_page(self, name, newname):
		#~ '''FIXME'''

	#~ def del_page(self, name):
		#~ '''FIXME'''

	#~ def search(self):
		#~ '''FIXME'''
		#~ pass # TODO search code

	def resolve_file(file, page):
		'''Resolves a file or directory path relative to a page and returns.

		File urls and paths that start with '~/' or '~user/' are considered
		absolute paths and are returned unmodified.

		In case the file path starts with '/' the the path is taken relative
		to the document root of the notebook is used. This can be the dir
		where pages are stored, or some other dir.

		Other paths are considered attachments and are resolved relative
		to the page.
		'''
		# TODO security argument for www interface
		#	- turn everything outside notebook into file:// urls
		#	- do not leak info on existence of files etc.
		# TODO should we handle smb:// URLs here ?

		if file.startswith('~') or file.startswith('file://'):
			return file
		elif file.startswith('/'):
			pass # TODO get_document_dir
		else:
			filepath = [p for p in path.split('/') if len(p)]
			pagepath = page.name.split(':')
			filename = filepath.pop()
			for part in filepath[:]:
				if part == '.':
					filepath.pop(0)
				elif part == '..':
					# TODO if not pagepath -> document root ??
					filepath.pop(0)
					pagepath.pop(0)
				else:
					break
			pagename = ':'+':'.join(pagepath, filepath)
			if pagename == page.name:
				store = page.store
			else:
				store = self.get_store(pagename)
			dir = store.get_attachments_dir(pagename)
			return dir.file(filename)

class Page(object):
	'''FIXME'''

	# Page objects should never need to access self.store.notebook,
	# they are purely intended as references to data in the store.

	def __init__(self, name, store, source=None, format=None):
		'''Construct Page object.
		Needs at least a name and a store object.
		The source object and format module are optional but go together.
		'''
		assert len(name), 'Page needs a name' # FIXME assert name is valid
		assert not (source and format is None) # these should come as a pair
		self.name     = name
		self.store    = store
		self.children = None
		self.source   = source
		self.format   = format
		self._tree    = None
		self.properties = {}

	def __repr__(self):
		return '<%s: %s>' % (self.__class__.__name__, self.name)

	@property
	def namespace(self):
		'''Gives the namespace name for the parent namespace.
		Gives empty string for the top level namespace.
		Use 'notebook.get_namespace(page.namespace)' to get a namespace object.
		'''
		i = self.name.rfind(':')
		if i > 0:
			return self.name[:i]
		else:
			return ''

	@property
	def basename(self):
		i = self.name.rfind(':') + 1
		return self.name[i:]

	def isempty(self):
		'''Returns True if this page has no content'''
		if self.source:
			return not self.source.exists()
		else:
			return not self._tree

	def get_parsetree(self):
		'''Returns contents as a parse tree or None'''
		if self.source:
			if self.isempty():
				return None
			parser = self.format.Parser(self)
			tree = parser.parse(self.source)
			return tree
		else:
			return self._tree

	def set_parsetree(self, tree):
		'''Save a parse tree to page source'''
		if 'readonly' in self.properties and self.properties['readonly']:
			raise Exception, 'Can not store data in a read-only Page'

		if self.source:
			dumper = self.format.Dumper(self)
			dumper.dump(tree, self.source)
		else:
			self._tree = tree

	def get_text(self, format):
		'''Returns contents as string'''
		tree = self.get_parsetree()
		if tree:
			import zim.formats
			dumper = zim.formats.get_format(format).Dumper(self)
			return dumper.tostring(tree)
		else:
			return ''

	def set_text(self, format, text):
		'''Convenience method that parses 'text' and sets the parse tree
		for this page.
		'''
		import zim.formats
		parser = zim.formats.get_format(format).Parser(self)
		self.set_parsetree(parser.fromstring(text))

	def path(self):
		'''Generator function for parent namespaces
		can be used like:

			for namespace in page.path():
				if namespace.page('foo').exists:
					# ...
		'''
		path = self.name.split(':')
		path.pop(-1)
		while len(path) > 0:
			namespace = path.join(':')
			yield Namespace(namespace, self.store)


class Namespace(object):
	'''Iterable object for namespaces, which functions as a wrapper for the
	result of store.list_pages(). The advantage being that list_pages()
	does not actually is called untill you start iterating the namespace
	object, which prevents a lot of objects to be created prematurely.
	By setting a Namespace object or not the store tells users of the Page
	object whether the page has children or not, but testing this property
	does not necesitate actually constructing objects, this is delayed untill
	iteration.
	'''

	def __init__(self, namespace, store):
		'''Constructor needs a namespace and a store object'''
		self.name = namespace
		self.store = store

	def __repr__(self):
		return '<%s: %s>' % (self.__class__.__name__, self.name)

	def __iter__(self):
		'''Calls the store.listpages generator function'''
		return self.store.list_pages( self.name )

	def __getitem__(self, item):
		# TODO: optimize querying a specific page in a namespace
		i = 0
		for page in self:
			if i == item:
				return page
			else:
				i += 1

	def walk(self):
		'''Generator to walk page tree recursively'''
		for page in self:
			yield page
			if page.children:
				for page in page.children.walk(): # recurs
					yield page

	def get_previous(self, page):
		'''FIXME'''

	def get_next(self, page):
		'''FIXME'''
