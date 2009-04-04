# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''
This package contains the main Notebook class and related classes.

This package defines the public interface towards the
noetbook.  As a backend it uses one of more packages from
the 'stores' namespace.
'''

import os
import weakref
import logging

from zim.fs import *
from zim.config import ConfigList, config_file, data_dir
from zim.parsing import Re, is_url_re, is_email_re
import zim.stores


logger = logging.getLogger('zim.notebook')


def get_notebook(notebook):
	'''Takes a path or name and returns a notebook object'''
	if isinstance(notebook, basestring):
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
		else:
			pass # maybe it's a path after all

		if notebook == '_manual_':
			notebook = data_dir('manual')
		elif os.path.isfile(notebook):
			notebook = File(notebook)
		else:
			notebook = Dir(notebook)

	if isinstance(notebook, File) and notebook.basename == 'notebook.zim':
		notebook = notebook.dir
		name = notebook.path # FIXME get name from the file
	else:
		name = notebook.path

	if notebook.exists():
		return Notebook(path=notebook, name=name)
	else:
		raise Exception, 'No such notebook: %s' % notebook


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

	def __init__(self, path=None, name=None, config=None, index=None):
		'''FIXME'''
		self._namespaces = []	# list used to resolve stores
		self._stores = {}		# dict mapping namespaces to stores
		self._page_cache = weakref.WeakValueDictionary()
		self.dir = None
		self.cache_dir = None
		self.name = name

		if isinstance(path, Dir):
			self.dir = path
			self.cache_dir = path.subdir('.zim')
			logger.debug('Cache dir: %s', self.cache_dir)
			if config is None:
				pass # TODO: load config file from dir
			# TODO check if config defined root namespace
			self.add_store(Path(':'), 'files') # set root
			# TODO add other namespaces from config
		elif isinstance(path, File):
			assert False, 'TODO: support for single file notebooks'
		elif not path is None:
			assert False, 'path should be either File or Dir'

		if index is None:
			import zim.index # circular import
			self.index = zim.index.Index(notebook=self)
		else:
			self.index = index
			self.index.set_notebook(self)


	def add_store(self, path, store, **args):
		'''Add a store to the notebook to handle a specific path and all
		it's sub-pages. Needs a Path and a store name, all other args will
		be passed to the store. Returns the store object.
		'''
		mod = zim.stores.get_store(store)
		assert not path.name in self._stores, 'Store for "%s" exists' % path
		mystore = mod.Store(notebook=self, path=path, **args)
		self._stores[path.name] = mystore
		self._namespaces.append(path.name)

		# keep order correct for lookup
		self._namespaces.sort(reverse=True)

		return mystore

	def get_store(self, path):
		'''Returns the store object to handle a page or namespace.'''
		for namespace in self._namespaces:
			# longest match first because of reverse sorting
			if namespace == ''			\
			or page.name == namespace	\
			or page.name.startswith(namespace+':'):
				return self._stores[namespace]
		else:
			raise LookupError, 'Could not find store for: %s' % name

	def resolve_path(self, name, namespace=None, index=None):
		'''Returns a proper path name for page names given in links
		or from user input. The optional argument 'namespace' is the
		path for the parent namespace of the refering page, if any.
		Or the path of the "current" namespace in the user interface.

		The 'index' argument allows specifying an index object, if
		none is given the default index for this notebook is used.

		If no namespace path is given or if the page name starts with
		a ':' the name is considered an absolute name and only case is
		resolved. If the page does not exist the last part(s) of the
		name will remain in the case as given.

		If the name is relative to the namespace path we first look for a
		match of the first part of the name in the path. If that fails
		we do a search for the first part of the name through all
		namespaces in the path, starting with pages below the namespace
		itself. If no existing page was found in this search we default to
		a new page below this namespace.

		So if we for exampel look for "baz" with as namespace ":foo:bar"
		the following pages will be checked in a case insensitive way:

			:foo:bar:baz
			:foo:baz
			:baz

		And if none exist we default to ":foo:bar:baz"

		However if for example we are looking for "bar:bud" with as namespace
		":foo:bar:baz", we only try to resolve the case for ":foo:bar:bud"
		and default to the given case if it does not yet exist.

		This method will raise a PageNameError if the name resolves
		to an empty string. Since all trailing ":" characters are removed
		there is no way for the name to address the root path in this method -
		and typically user input should not need to able to address this path.
		'''
		isabs = name.startswith(':') or namespace == None
		# normalize name
		# TODO check for illegal characters in the name
		name = ':'.join( map(unicode.strip,
				filter(lambda n: len(n)>0, unicode(name).split(':')) ) )
		if not name or name.isspace():
			raise PageNameError

		if index is None:
			index = self.index

		if isabs:
			return index.resolve_case(name) or Path(name)
		else:
			# first check if we see an explicit match in the path
			assert isinstance(namespace, Path)
			anchor = name.split(':')[0].lower()
			path = namespace.name.lower().split(':')
			if anchor in path:
				# ok, so we can shortcut to an absolute path
				path.reverse() # why is there no rindex or rfind ?
				i = path.index(anchor) + 1
				path = path[i:]
				path.reverse()
				path.append( name.lstrip(':') )
				name = ':'.join(path)
				return index.resolve_case(name) or Path(name)
				# FIXME use parent
				# FIXME use short cut when the result is the parent
			else:
				# no luck, do a search through the whole path - including root
				namespace = index.lookup_path(namespace) or namespace
				for parent in namespace.parents():
					candidate = index.resolve_case(name, namespace=parent)
					if not candidate is None:
						return candidate
				else:
					# name not found, keep case as is
					return namespace+name

	def get_page(self, path):
		'''Returns a Page object'''
		assert isinstance(path, Path)
		if path.name in self._page_cache:
			return self._page_cache[path.name]
		else:
			store = self.get_store(path)
			page = store.get_page(path)
			# TODO - set haschildren if page maps to a store namespace
			self._page_cache[path.name] = page
			return page

	def get_home_page(self):
		'''Returns a page object for the home page.'''
		return self.get_page(Path('Home')) # TODO: make this configable

	def get_pagelist(self, path):
		'''Returns a list of page objects.'''
		store = self.get_store(path)
		return store.get_pagelist(path)
		# TODO: add sub-stores in this namespace if any

	#~ def move_page(self, name, newname):
		#~ '''FIXME'''

	#~ def copy_page(self, name, newname):
		#~ '''FIXME'''

	#~ def del_page(self, name):
		#~ '''FIXME'''

	#~ def search(self):
		#~ '''FIXME'''
		#~ pass # TODO search code

	def resolve_file(self, file, path):
		'''Resolves a file or directory path relative to a page. Returns a
		File object. However the file does not have to exist.

		File urls and paths that start with '~/' or '~user/' are considered
		absolute paths and are returned unmodified.

		In case the file path starts with '/' the the path is taken relative
		to the document root - this can be the dir where pages are stored,
		or some other dir.

		Other paths are considered attachments and are resolved relative
		to the namespce below the page.
		'''
		if file.startswith('~') or file.startswith('file:/'):
			return File(file)
		elif file.startswith('/'):
			print 'TODO: document_root - no compat to file root !'
			return File('/TODO')
		else:
			# TODO - how to deal with '..' in the middle of the path ?
			filepath = [p for p in file.split('/') if len(p) and p != '.']
			pagepath = path.name.split(':')
			filename = filepath.pop()
			while filepath and filepath[0] == '..':
				if not pagepath:
					print 'TODO: handle paths relative to notebook but outside notebook dir'
					return File('/TODO')
				else:
					filepath.pop(0)
					pagepath.pop()
			pagename = ':'+':'.join(pagepath + filepath)
			store = self.get_store(pagename)
			dir = store.get_attachments_dir(Path(pagename))
			return dir.file(filename)

	def walk(self, path=None):
		'''Generator function which iterates through all pages, depth first.
		If a path is given, only iterates through sub-pages of that path.

		If you are only interested in the paths using Index.walk() will be
		more efficient.
		'''
		if path == None:
			path = Path(':')
		for p in self.index.walk(path):
			page = self.get_page(p)
			yield page

	def get_pagelist_indexkey(self, path):
		store = self.get_store(path)
		return store.get_pagelist_indexkey(path)

	def get_page_indexkey(self, path):
		store = self.get_store(path)
		return store.get_page_indexkey(path)

class Path(object):
	'''This is the parent class for the Page class. It contains the name
	of the page and is used instead of the actual page object by methods
	that only know the name of the page.
	'''

	__slots__ = ('name',)

	def __init__(self, name):
		'''Constructor. Takes an absolute page name in the right case.
		The name ":" is used as a special case to construct a path for
		the toplevel namespace in a notebook.

		Note: This class does not do any checks for the sanity of the path
		name. Never construct a path directly from user input, but always use
		"Notebook.resolve_path()" for that.
		'''
		if isinstance(name, (list, tuple)):
			name = ':'.join(name)

		if name == ':': # root namespace
			self.name = ''
		else:
			self.name = name.strip(':')

	def __repr__(self):
		return '<%s: %s>' % (self.__class__.__name__, self.name)

	def __eq__(self, other):
		'''Paths are equal when their names are the same'''
		if isinstance(other, Path):
			return self.name == other.name
		else: # e.g. path == None
			return False

	def __add__(self, name):
		'''"path + name" returns a child path'''
		if len(self.name):
			return Path(self.name+':'+name)
		else: # we are the top level root namespace
			return Path(name)

	@property
	def parts(self):
		return self.name.split(':')

	@property
	def basename(self):
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
		return self.name == ''

	def relname(self, path):
		'''Returns a relative name for this path compared to the reference.
		Raises an error if this page is not below the given path.
		'''
		if path.name == '': # root path
			return self.name
		elif self.name.startswith(path.name + ':'):
			i = len(path.name)+1
			return self.name[i:]
		else:
			raise Exception, '"%s" is not below "%s"' % (self, path)

	def get_parent(self):
		'''Returns the path for the parent page'''
		namespace = self.namespace
		if namespace:
			return Path(namespace)
		elif self.isroot:
			return None
		else:
			return Path(':')

	def parents(self):
		'''Generator function for parent namespace paths including root'''
		if ':' in self.name:
			path = self.name.split(':')
			path.pop()
			while len(path) > 0:
				namespace = ':'.join(path)
				yield Path(namespace)
				path.pop()
		yield Path(':')


class Page(Path):
	'''FIXME

	Page objects inherit from Path but contain store specific data about
	how/where to get the page content. We try to keep Page objects unique
	by hashing them in notebook.get_page(), Path object on the other hand
	are cheap and can have multiple instances for the same logical path.
	We ask for a path object instead of a name in the constructore to
	encourage the use of Path objects over passsing around page names as
	string. Also this allows some optimalizations by addind index pointers
	to the Path instances.
	'''

	# define signals we want to use - (closure type, return type and arg types)
	#~ __gsignals__ = {
		#~ 'request-parsetree': (gobject.SIGNAL_RUN_LAST, None, ()),
		#~ 'changed': (gobject.SIGNAL_RUN_LAST, None, ())
	#~ }

	def __init__(self, path, haschildren=False, parsetree=None):
		'''Construct Page object. Needs a path object and a boolean to flag
		if the page has children.
		'''
		assert isinstance(path, Path)
		#~ gobject.GObject.__init__(self)
		self.name = path.name
		self.haschildren = haschildren
		self._parsetree = parsetree
		self.properties = {}
		self._on_changed = None
		self._on_request_parsetree = None
		if hasattr(path, '_indexpath'):
			self._indexpath = path._indexpath
			# Keeping this data around will speed things up when this page
			# is used for index lookups

	@property
	def hascontent(self):
		'''Returns whether this page has content'''
		return bool(self._parsetree)

	def get_parsetree(self):
		'''Returns contents as a parse tree or None'''
		#~ self.emit('request-parsetree')
		return self._parsetree

	def set_parsetree(self, tree):
		'''Set the parsetree with content for this page. Set the parsetree
		to None to remove all content.
		'''
		if 'readonly' in self.properties and self.properties['readonly']:
			raise Exception, 'Can not store data in a read-only Page'
		self._parsetree = tree
		#~ self.emit('changed')

	def dump(self, format):
		'''Convenience method that converts the current parse tree to a
		particular format and returns a list of lines. Format can be either a
		format module or a string which can be passed to formats.get_format().
		'''
		if isinstance(format, basestring):
			import zim.formats
			format = zim.formats.get_format(format)

		tree = self.get_parsetree()
		if tree:
			return format.Dumper().dump(tree)
		else:
			return []

	def parse(self, format, text):
		'''Convenience method that parses text and sets the parse tree
		for this page. Format can be either a format module or a string which
		can be passed to formats.get_format(). Text can be either a string or
		a list or iterable of lines.
		'''
		if isinstance(format, basestring):
			import zim.formats
			format = zim.formats.get_format(format)

		self.set_parsetree(format.Parser().parse(text))

	def get_links(self):
		tree = self.get_parsetree()
		if tree:
			for tag in tree.getiterator('link'):
				#~ if is_url_re.match(link): type = is_url_re[1]
				#~ elif is_email_re.match(link): type = 'mailto'
				#~ elif is_path_re.match(link): type = 'file'
				#~ else: type = 'page'
				yield Link(self, **tag.attrib)


class Link(object):

	__slots__ = ('source', 'href', 'type')

	def __init__(self, source, href, type=None):
		self.source = source
		self.href = href
		self.type = type

	def __repr__(self):
		return '<%s: %s -> %s (%s)>' % (self.__class__.__name__, self.source, self.href, self.type)
