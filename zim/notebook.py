# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''
This package contains the main Notebook class and related classes.

This package defines the public interface towards the
noetbook.  As a backend it uses one of more packages from
the 'stores' namespace.
'''

from __future__ import with_statement

import os
import weakref
import logging

import gobject

import zim.fs
from zim.fs import *
from zim.errors import Error, SignalExceptionContext, SignalRaiseExceptionContext
from zim.config import ConfigDict, ConfigDictFile, TextConfigFile, HierarchicDict, \
	config_file, data_dir, user_dirs
from zim.parsing import Re, is_url_re, is_email_re, is_win32_path_re, link_type, url_encode
import zim.stores


logger = logging.getLogger('zim.notebook')


class NotebookList(TextConfigFile):
	'''This class keeps a list of paths for notebook locations
	plus a attribute 'default' for the default notebook.

	All values are assumed to be (file://) urls.
	'''

	def read(self):
		TextConfigFile.read(self)
		if len(self) > 0:
			if self[0] == '[NotebookList]\n':
				self.parse()
			else:
				self.parse_old_format()

	@staticmethod
	def _filter(line):
		return line and not line.isspace() and not line.startswith('#')

	def parse(self):
		'''Parses the notebook list format after reading it'''
		assert self.pop(0) == '[NotebookList]\n'

		# Parse key for default
		if self[0].startswith('Default='):
			k, v = self.pop(0).strip().split('=', 1)
			self.default = v
		else:
			self.default = None

		# Parse rest of list - assumed to be urls, but we check to be sure
		def map_to_uri(line):
			uri = line.strip()
			if not uri.startswith('file://'):
				uri = File(uri).uri
			return uri

		self[:] = map(map_to_uri, filter(self._filter, self))

	def parse_old_format(self):
		'''Method for backward compatibility'''
		# Old format is name, value pair, separated by whitespace
		# with all other whitespace escaped by a \
		# Default was _default_ which could refer a notebook name..
		import re
		fields_re = re.compile(r'(?:\\.|\S)+') # match escaped char or non-whitespace
		escaped_re = re.compile(r'\\(.)') # match single escaped char
		default = None
		locations = []

		lines = [line.strip() for line in filter(self._filter, self)]
		for line in lines:
			cols = fields_re.findall(line)
			if len(cols) == 2:
				name = escaped_re.sub(r'\1', cols[0])
				path = escaped_re.sub(r'\1', cols[1])
				if name == '_default_':
					default = path
				else:
					path = Dir(path).uri
					locations.append(path)
					if name == default:
						self.default = path

		if not self.default and default:
			self.default = Dir(default).uri

		self[:] = locations

	def write(self):
		lines = self[:] # copy
		lines.insert(0, '[NotebookList]')
		lines.insert(1, 'Default=%s' % (self.default or ''))
		lines = [line + '\n' for line in lines]
		self.file.writelines(lines)

	def get_names(self):
		'''Generator function that yield tuples with the notebook
		name and the notebook path.
		'''
		for path in self:
			name = self.get_name(path)
			if name:
				yield (name, path)

	def get_name(self, uri):
		# TODO support for paths that turn out to be files
		file = Dir(uri).file('notebook.zim')
		if file.exists():
			config = ConfigDictFile(file)
			if 'name' in config['Notebook']:
				return config['Notebook']['name']
		return None

	def get_by_name(self, name):
		for n, path in self.get_names():
			if n.lower() == name.lower():
				return path
		else:
			return None



def get_notebook_list():
	'''Returns a list of known notebooks'''
	# TODO use weakref here
	return config_file('notebooks.list', klass=NotebookList)


def resolve_notebook(string):
	'''Takes either a notebook name or a file or dir path. For a name
	it resolves the path by looking for a notebook of that name in the
	notebook list. For a path it checks if this path points to a
	notebook or to a file in a notebook.

	It returns two values, a path to the notebook directory and an
	optional page path for a file inside a notebook. If the notebook
	was not found both values are None.
	'''
	assert isinstance(string, basestring)

	page = None
	if is_url_re.match(string):
		assert string.startswith('file://')
		if '?' in string:
			filepath, page = string.split('?', 1)
		else:
			filepath = string
	elif os.path.sep in string:
		filepath = string
	else:
		nblist = get_notebook_list()
		filepath = nblist.get_by_name(string)
		if filepath is None:
			return None, None # not found

	file = File(filepath) # Fixme need generic FS Path object here
	if filepath.endswith('notebook.zim'):
		return File(filepath).dir, page
	elif file.exists(): # file exists and really is a file
		parents = list(file)
		parents.reverse()
		for parent in parents:
			if File((parent, 'notebook.zim')).exists():
				page = file.relpath(parent)
				if '.' in page:
					page, _ = page.rsplit('.', 1) # remove extension
				page = Path(page.replace('/', ':'))
				return Dir(parent), page
		else:
			return None, None
	else:
		return Dir(file.path), page

	return notebook, path


def resolve_default_notebook():
	'''Returns a File or Dir object for the default notebook,
	or for the only notebook if there is only a single notebook
	in the list.
	'''
	default = None
	list = get_notebook_list()
	if list.default:
		default = list.default
	elif len(list) == 1:
		default = list[0]

	if default:
		if os.path.isfile(default):
			return File(default)
		else:
			return Dir(default)
	else:
		return None


def get_notebook(path):
	'''Convenience method that constructs a notebook from either a
	File or a Dir object.
	'''
	# TODO this is where the hook goes to automount etc.
	assert isinstance(path, (File, Dir))
	if path.exists():
		if isinstance(path, File):
			return Notebook(file=path)
		else:
			return Notebook(dir=path)
	else:
		return None


def get_default_notebook():
	'''Returns a Notebook object for the default notebook or None'''
	path = resolve_default_notebook()
	if path:
		return get_notebook(path)
	else:
		return None


def init_notebook(path, name=None):
	'''Initialize a new notebook in a directory'''
	assert isinstance(path, Dir)
	path.touch()
	config = ConfigDictFile(path.file('notebook.zim'))
	config['Notebook']['name'] = name or path.basename
	# TODO auto detect if we should enable the slow_fs option
	config.write()


def interwiki_link(link):
	'''Convert an interwiki link into an url'''
	assert isinstance(link, basestring) and '?' in link
	key, page = link.split('?', 1)
	url = None
	for line in config_file('urls.list'):
		if line.startswith(key+' ') or line.startswith(key+'\t'):
			url = line[len(key):].strip()
			break
	else:
		list = get_notebook_list()
		for name, path in list.get_names():
			if name.lower() == key.lower():
				url = path + '?{NAME}'
				break

	if url and is_url_re.match(url):
		if not ('{NAME}' in url or '{URL}' in url):
			url += '{URL}'

		url = url.replace('{NAME}', page)
		url = url.replace('{URL}', url_encode(page))

		return url
	else:
		return None

class PageNameError(Error):

	description = _('''\
The given page name is not valid.
''') # T: error description
	# TODO add to explanation what are validcharacters

	def __init__(self, name):
		self.msg = _('Invalid page name "%s"') % name # T: error message


class LookupError(Error):

	description = '''\
Failed to lookup this page in the notebook storage.
This is likely a glitch in the application.
'''

class IndexBusyError(Error):

	description = '''\
Index is still busy updating while we try to do an
operation that needs the index.
'''


class PageExistsError(Error):
	pass

	# TODO verbose description


class PageReadOnlyError(Error):

	# TODO verbose description

	def __init__(self, page):
		self.msg = _('Can not modify page: %s') % page.name
			# T: error message for read-only pages

class Notebook(gobject.GObject):
	'''Main class to access a notebook. Proxies between backend Store
	and Index objects on the one hand and the gui application on the other

	This class has the following signals:
		* store-page (page)
		* move-page (oldpath, newpath, update_links)
		* delete-page (path)
		* properties-changed ()

	All signals are defined with the SIGNAL_RUN_LAST type, so any
	handler connected normally will run before the actual action.
	Use "connect_after()" to install handlers after storing, moving
	or deleting a page.
	'''

	# TODO add checks for read-only page in much more methods

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'store-page': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'move-page': (gobject.SIGNAL_RUN_LAST, None, (object, object, bool)),
		'delete-page': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'properties-changed': (gobject.SIGNAL_RUN_FIRST, None, ()),
	}

	properties = (
		('name', 'string', _('Name')), # T: label for properties dialog
		('home', 'page', _('Home Page')), # T: label for properties dialog
		('icon', 'image', _('Icon')), # T: label for properties dialog
		('document_root', 'dir', _('Document Root')), # T: label for properties dialog
		('slow_fs', 'bool', _('Slow file system')), # T: label for properties dialog
		#~ ('autosave', 'bool', _('Auto-version when closing the notebook')),
			# T: label for properties dialog
	)

	def __init__(self, dir=None, file=None, config=None, index=None):
		assert not (dir and file), 'BUG: can not provide both dir and file '
		gobject.GObject.__init__(self)
		self._namespaces = []	# list used to resolve stores
		self._stores = {}		# dict mapping namespaces to stores
		self.namespace_properties = HierarchicDict()
		self._page_cache = weakref.WeakValueDictionary()
		self.dir = None
		self.file = None
		self.cache_dir = None
		self.name = None
		self.icon = None
		self.config = config

		if dir:
			assert isinstance(dir, Dir)
			self.dir = dir
			self.readonly = not dir.iswritable()
			self.cache_dir = dir.subdir('.zim')
			if self.readonly or not self.cache_dir.iswritable():
				self.cache_dir = self._cache_dir(dir)
			logger.debug('Cache dir: %s', self.cache_dir)
			if self.config is None:
				self.config = ConfigDictFile(dir.file('notebook.zim'))
			# TODO check if config defined root namespace
			self.add_store(Path(':'), 'files') # set root
			# TODO add other namespaces from config
		elif file:
			assert isinstance(file, File)
			self.file = file
			self.readonly = not file.iswritable()
			assert False, 'TODO: support for single file notebooks'

		if index is None:
			import zim.index # circular import
			self.index = zim.index.Index(notebook=self)
		else:
			self.index = index
			self.index.set_notebook(self)

		if self.config is None:
			self.config = ConfigDict()

		self.config['Notebook'].setdefault('name', None, klass=basestring)
		self.config['Notebook'].setdefault('home', ':Home', klass=basestring)
		self.config['Notebook'].setdefault('icon', None, klass=basestring)
		self.config['Notebook'].setdefault('document_root', None, klass=basestring)
		self.config['Notebook'].setdefault('slow_fs', False)
		self.do_properties_changed()

	@property
	def uri(self):
		'''Returns a file:// uri for this notebook that can be opened by zim'''
		assert self.dir or self.file, 'Notebook does not have a dir or file'
		if self.dir:
			return self.dir.uri
		else:
			return self.file.uri

	def _cache_dir(self, dir):
		from zim.config import XDG_CACHE_HOME
		path = 'notebook-' + dir.path.replace('/', '_').strip('_')
		return XDG_CACHE_HOME.subdir(('zim', path))

	def save_properties(self, **properties):
		# Check if icon is relative
		if 'icon' in properties and properties['icon'] \
		and self.dir and properties['icon'].startswith(self.dir.path):
			i = len(self.dir.path)
			path = './' + properties['icon'][i:].lstrip('/\\')
			# TODO use proper fs routine(s) for this substitution
			properties['icon'] = path

		# Set home page as string
		if 'home' in properties and isinstance(properties['home'], Path):
			properties['home'] = properties['home'].name

		self.config['Notebook'].update(properties)
		self.config.write()
		self.emit('properties-changed')

	def do_properties_changed(self):
		#~ import pprint
		#~ pprint.pprint(self.config)
		config = self.config['Notebook']

		# Set a name for ourselves
		if config['name']: 	self.name = config['name']
		elif self.dir: self.name = self.dir.basename
		elif self.file: self.name = self.file.basename
		else: self.name = 'Unnamed Notebook'

		# We should always have a home
		config.setdefault('home', ':Home')

		# Resolve icon, can be relative
		# TODO proper FS routine to check abs path - also allowed without the "./" - so e.g. icon.png should be resolved as well
		if self.dir and config['icon'] and config['icon'].startswith('.'):
			self.icon = self.dir.file(config['icon']).path
		elif config['icon']:
			self.icon = File(config['icon']).path
		else:
			self.icon = None

		# Set FS property
		if config['slow_fs']: print 'TODO: hook slow_fs property'

	def add_store(self, path, store, **args):
		'''Add a store to the notebook to handle a specific path and all
		it's sub-pages. Needs a Path and a store name, all other args will
		be passed to the store. Alternatively you can pass a store object
		but in that case no arguments are allowed.
		Returns the store object.
		'''
		assert not path.name in self._stores, 'Store for "%s" exists' % path
		if isinstance(store, basestring):
			mod = zim.stores.get_store(store)
			mystore = mod.Store(notebook=self, path=path, **args)
		else:
			assert not args
			mystore = store
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

	def get_stores(self):
		return self._stores.values()

	def resolve_path(self, name, source=None, index=None):
		'''Returns a proper path name for page names given in links
		or from user input. The optional argument 'source' is the
		path for the refering page, if any, or the path of the "current"
		page in the user interface.

		The 'index' argument allows specifying an index object, if
		none is given the default index for this notebook is used.

		If no source path is given or if the page name starts with
		a ':' the name is considered an absolute name and only case is
		resolved. If the page does not exist the last part(s) of the
		name will remain in the case as given.

		If a source path is given and the page name starts with '+'
		it will be resolved as a direct child of the source.

		Else we first look for a match of the first part of the name in the
		source path. If that fails we do a search for the first part of
		the name through all namespaces in the source path, starting with
		pages below the namespace of the source. If no existing page was
		found in this search we default to a new page below this namespace.

		So if we for example look for "baz" with as source ":foo:bar:dus"
		the following pages will be checked in a case insensitive way:

			:foo:bar:baz
			:foo:baz
			:baz

		And if none exist we default to ":foo:bar:baz"

		However if for example we are looking for "bar:bud" with as source
		":foo:bar:baz:dus", we only try to resolve the case for ":foo:bar:bud"
		and default to the given case if it does not yet exist.

		This method will raise a PageNameError if the name resolves
		to an empty string. Since all trailing ":" characters are removed
		there is no way for the name to address the root path in this method -
		and typically user input should not need to able to address this path.
		'''
		assert name, 'BUG: name is empty string'
		startswith = name[0]
		if startswith == '.':
			startswith = '+' # backward compat
		if startswith == '+':
			name = name[1:]
		name = self.cleanup_pathname(name)

		if index is None:
			index = self.index

		if startswith == ':' or source == None:
			return index.resolve_case(name) or Path(name)
		elif startswith == '+':
			if not source:
				raise PageNameError, '+'+name
			return index.resolve_case(source.name+':'+name)  \
						or Path(source.name+':'+name)
			# FIXME use parent as argument
		else:
			# first check if we see an explicit match in the path
			assert isinstance(source, Path)
			anchor = name.split(':')[0].lower()
			path = source.namespace.lower().split(':')
			if anchor in path:
				# ok, so we can shortcut to an absolute path
				path.reverse() # why is there no rindex or rfind ?
				i = path.index(anchor) + 1
				path = path[i:]
				path.reverse()
				path.append( name.lstrip(':') )
				name = ':'.join(path)
				return index.resolve_case(name) or Path(name)
				# FIXME use parentt as argument
				# FIXME use short cut when the result is the parent
			else:
				# no luck, do a search through the whole path - including root
				source = index.lookup_path(source) or source
				for parent in source.parents():
					candidate = index.resolve_case(name, namespace=parent)
					if not candidate is None:
						return candidate
				else:
					# name not found, keep case as is
					return source.parent + name

	def relative_link(self, source, href):
		'''Returns a link for a path 'href' relative to path 'source'.
		More or less the opposite of resolve_path().
		'''
		if href == source:
			return href.basename
		elif href > source:
			return '+' + href.relname(source)
		else:
			parent = source.commonparent(href)
			if parent.isroot:
				return ':' + href.name
			else:
				return parent.basename + ':' + href.relname(parent)

	def register_hook(self, name, handler):
		'''Register a handler method for a specific hook'''
		register = '_register_%s' % name
		if not hasattr(self, register):
			setattr(self, register, [])
		getattr(self, register).append(handler)

	def unregister_hook(self, name, handler):
		'''Remove a handler method for a specific hook'''
		register = '_register_%s' % name
		if hasattr(self, register):
			getattr(self, register).remove(handler)

	def suggest_link(self, source, word):
		'''Suggest a link Path for 'word' or return None if no suggestion is
		found. By default we do not do any suggestion but plugins can
		register handlers to add suggestions. See 'register_hook()' to
		register a handler.
		'''
		if not  hasattr(self, '_register_suggest_link'):
			return None

		for handler in self._register_suggest_link:
			link = handler(source, word)
			if not link is None:
				return link
		else:
			return None

	@staticmethod
	def cleanup_pathname(name):
		'''Returns a safe version of name, used internally by functions like
		resolve_path() to parse user input.
		'''
		orig = name
		name = ':'.join( map(unicode.strip,
				filter(lambda n: len(n)>0, unicode(name).split(':')) ) )

		# Reserved characters are:
		# The ':' is reserrved as seperator
		# The '?' is reserved to encode url style options
		# The '#' is reserved as anchor separator
		# The '/' and '\' are reserved to distinquise file links & urls
		# First character of each part MUST be alphanumeric
		#		(including utf8 letters / numbers)

		# Zim version < 0.42 restricted all special charachters but
		# white listed ".", "-", "_", "(", ")", ":" and "%".

		# TODO check for illegal characters in the name

		if not name or name.isspace():
			raise PageNameError, orig

		return name

	def get_page(self, path):
		'''Returns a Page object. This method uses a weakref dictionary to
		ensure that an unique object is being used for each page that is
		given out.
		'''
		# As a special case, using an invalid page as the argument should
		# return a valid page object.
		assert isinstance(path, Path)
		if path.name in self._page_cache \
		and self._page_cache[path.name].valid:
			return self._page_cache[path.name]
		else:
			store = self.get_store(path)
			page = store.get_page(path)
			# TODO - set haschildren if page maps to a store namespace
			self._page_cache[path.name] = page
			return page

	def flush_page_cache(self, path):
		'''Remove a page from the page cache, calling get_page() after this
		will return a fresh page object. Be aware that the old object
		may still be around but will have its 'valid' attribute set to False.
		This function also removes all child pages of path from the cache.
		'''
		names = [path.name]
		ns = path.name + ':'
		names.extend(k for k in self._page_cache.keys() if k.startswith(ns))
		for name in names:
			if name in self._page_cache:
				page = self._page_cache[name]
				assert not page.modified, 'BUG: Flushing page with unsaved changes'
				page.valid = False
				del self._page_cache[name]

	def get_home_page(self):
		'''Returns a page object for the home page.'''
		path = self.resolve_path(self.config['Notebook']['home'])
		return self.get_page(path)

	def get_pagelist(self, path):
		'''Returns a list of page objects.'''
		store = self.get_store(path)
		return store.get_pagelist(path)
		# TODO: add sub-stores in this namespace if any

	def store_page(self, page):
		'''Store a page permanently. Commits the parse tree from the page
		object to the backend store.
		'''
		assert page.valid, 'BUG: page object no longer valid'
		with SignalExceptionContext(self, 'store-page'):
			self.emit('store-page', page)

	def do_store_page(self, page):
		with SignalRaiseExceptionContext(self, 'store-page'):
			store = self.get_store(page)
			store.store_page(page)

	def revert_page(self, page):
		'''Reloads the parse tree from the store into the page object.
		In a sense the opposite to store_page(). Used in the gui to
		discard changes in a page.
		'''
		# get_page without the cache
		assert page.valid, 'BUG: page object no longer valid'
		store = self.get_store(page)
		storedpage = store.get_page(page)
		page.set_parsetree(storedpage.get_parsetree())
		page.modified = False

	def move_page(self, path, newpath, update_links=True):
		'''Move a page from 'path' to 'newpath'. If 'update_links' is
		True all links from and to the page will be modified as well.
		'''
		if update_links and self.index.updating:
			raise IndexBusyError, 'Index busy'
			# Index need to be complete in order to be 100% sure we
			# know all backlinks, so no way we can update links before.

		page = self.get_page(path)
		if not (page.hascontent or page.haschildren):
			raise LookupError, 'Page does not exist: %s' % path.name
		assert not page.modified, 'BUG: moving a page with uncomitted changes'

		with SignalExceptionContext(self, 'move-page'):
			self.emit('move-page', path, newpath, update_links)

	def do_move_page(self, path, newpath, update_links):
		logger.debug('Move %s to %s (%s)', path, newpath, update_links)

		with SignalRaiseExceptionContext(self, 'move-page'):
			# Collect backlinks
			if update_links:
				from zim.index import LINK_DIR_BACKWARD
				backlinkpages = set(
					l.source for l in
						self.index.list_links(path, LINK_DIR_BACKWARD) )
				for child in self.index.walk(path):
					backlinkpages.update(set(
						l.source for l in
							self.index.list_links(path, LINK_DIR_BACKWARD) ))

			# Do the actual move
			store = self.get_store(path)
			newstore = self.get_store(newpath)
			if newstore == store:
				store.move_page(path, newpath)
			else:
				assert False, 'TODO: move between stores'
				# recursive + move attachments as well

			self.flush_page_cache(path)
			self.flush_page_cache(newpath)

			# Update links in moved pages
			page = self.get_page(newpath)
			if page.hascontent:
				self._update_links_from(page, path)
				store = self.get_store(page)
				store.store_page(page)
				# do not use self.store_page because it emits signals
			for child in self._no_index_walk(newpath):
				if not child.hascontent:
					continue
				oldpath = path + child.relname(newpath)
				self._update_links_from(child, oldpath)
				store = self.get_store(child)
				store.store_page(child)
				# do not use self.store_page because it emits signals

			# Update links to the moved page tree
			if update_links:
				# Need this indexed before we can resolve links to it
				self.index.delete(path)
				self.index.update(newpath)
				#~ print backlinkpages
				for p in backlinkpages:
					if p == path or p > path:
						continue
					page = self.get_page(p)
					self._update_links_in_page(page, path, newpath)
					self.store_page(page)

	def _no_index_walk(self, path):
		'''Walking that can be used when the index is not in sync'''
		# TODO allow this to cross several stores
		store = self.get_store(path)
		for page in store.get_pagelist(path):
			yield page
			for child in self._no_index_walk(page): # recurs
				yield child

	@staticmethod
	def _update_link_tag(tag, newhref):
		newhref = str(newhref)
		haschildren = bool(list(tag.getchildren()))
		if not haschildren and tag.text == tag.attrib['href']:
			tag.text = newhref
		tag.attrib['href'] = newhref

	def _update_links_from(self, page, oldpath):
		logger.debug('Updating links in %s (was %s)', page, oldpath)
		tree = page.get_parsetree()
		if not tree:
			return

		for tag in tree.getiterator('link'):
			href = tag.attrib['href']
			type = link_type(href)
			if type == 'page':
				hrefpath = self.resolve_path(href, source=page)
				oldhrefpath = self.resolve_path(href, source=oldpath)
				#~ print 'LINK', oldhrefpath, '->', hrefpath
				if hrefpath != oldhrefpath:
					if hrefpath >= page and oldhrefpath >= oldpath:
						#~ print '\t.. Ignore'
						pass
					else:
						newhref = self.relative_link(page, oldhrefpath)
						#~ print '\t->', newhref
						self._update_link_tag(tag, newhref)

		page.set_parsetree(tree)

	def _update_links_in_page(self, page, oldpath, newpath):
		# Maybe counter intuitive, but pages below oldpath do not need
		# to exist anymore while we still try to resolve links to these
		# pages. The reason is that all pages that could link _upward_
		# to these pages are below and are moved as well.
		logger.debug('Updating links in %s to %s (was: %s)', page, newpath, oldpath)
		tree = page.get_parsetree()
		if not tree:
			logger.warn('Page turned out to be empty: %s', page)
			return

		for tag in tree.getiterator('link'):
			href = tag.attrib['href']
			type = link_type(href)
			if type == 'page':
				hrefpath = self.resolve_path(href, source=page)
				#~ print 'LINK', hrefpath
				if hrefpath == oldpath:
					newhrefpath = newpath
					#~ print '\t==', oldpath, '->', newhrefpath
				elif hrefpath > oldpath:
					rel = hrefpath.relname(oldpath)
					newhrefpath = newpath + rel
					#~ print '\t>', oldpath, '->', newhrefpath
				else:
					continue

				newhref = self.relative_link(page, newhrefpath)
				self._update_link_tag(tag, newhref)

		page.set_parsetree(tree)

	def rename_page(self, path, newbasename,
						update_heading=True, update_links=True):
		'''Rename page to a page in the same namespace but with a new basename.
		If 'update_heading' is True the first heading in the page will be updated to it's
		new name.  If 'update_links' is True all links from and to the page will be
		modified as well.
		'''
		logger.debug('Rename %s to "%s" (%s, %s)',
			path, newbasename, update_heading, update_links)

		newbasename = self.cleanup_pathname(newbasename)
		newpath = Path(path.namespace + ':' + newbasename)
		if newbasename.lower() != path.basename.lower():
			# allow explicit case-sensitive renaming
			newpath = self.index.resolve_case(
				newbasename, namespace=path.parent) or newpath

		self.move_page(path, newpath, update_links=update_links)
		if update_heading:
			page = self.get_page(newpath)
			tree = page.get_parsetree()
			if not tree is None:
				tree.set_heading(newbasename.title())
				page.set_parsetree(tree)
				self.store_page(page)

		return newpath

	def delete_page(self, path):
		with SignalExceptionContext(self, 'delete-page'):
			self.emit('delete-page', path)

	def do_delete_page(self, path):
		with SignalRaiseExceptionContext(self, 'delete-page'):
			store = self.get_store(path)
			store.delete_page(path)
			self.flush_page_cache(path)

	def resolve_file(self, filename, path):
		'''Resolves a file or directory path relative to a page. Returns a
		File object. However the file does not have to exist.

		File urls and paths that start with '~/' or '~user/' are considered
		absolute paths and are returned unmodified.

		In case the file path starts with '/' the the path is taken relative
		to the document root - this can e.g. be a parent directory of the
		notebook. Defaults to the home dir.

		Other paths are considered attachments and are resolved relative
		to the namespce below the page.

		Because this is used to resolve file links and is supposed to be
		platform independent it tries to convert windows filenames to
		unix equivalents.
		'''
		filename = filename.replace('\\', '/')
		if filename.startswith('~') or filename.startswith('file:/'):
			return File(filename)
		elif filename.startswith('/'):
			dir = self.get_document_root() or Dir('~')
			return dir.file(filename)
		elif is_win32_path_re.match(filename):
			if not filename.startswith('/'):
				filename = '/'+filename
				# make absolute on unix
			return File(filename)
		else:
			# TODO - how to deal with '..' in the middle of the path ?
			filepath = [p for p in filename.split('/') if len(p) and p != '.']
			if not filepath: # filename is e.g. "."
				return self.get_attachments_dir(path)
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
			dir = self.get_attachments_dir(Path(pagename))
			return dir.file(filename)

	def relative_filepath(self, file, path=None):
		'''Returns a filepath relative to either the documents dir (/xxx), the
		attachments dir (if a path is given) (./xxx or ../xxx) or the users
		home dir (~/xxx). Returns None otherwise.

		Intended as the counter part of resolve_file().
		Typically this function is used to present the user with readable paths
		or to shorten the paths inserted in the wiki code. It is advised to
		use file uris for links that can not be made relative.
		'''
		if path:
			root = self.dir
			dir = self.get_attachments_dir(path)
			if file.ischild(dir):
				return './'+file.relpath(dir)
			elif root and file.ischild(root) and dir.ischild(root):
				parent = file.commonparent(dir)
				uppath = dir.relpath(parent)
				downpath = file.relpath(parent)
				up = 1 + uppath.count('/')
				return '../'*up + downpath

		dir = self.get_document_root()
		if dir and file.ischild(dir):
			return '/'+file.relpath(dir)

		dir = Dir('~')
		if file.ischild(dir):
			return '~/'+file.relpath(dir)

		return None

	def get_attachments_dir(self, path):
		'''Returns a Dir object for the attachments directory for 'path'.
		The directory does not need to exist.
		'''
		store = self.get_store(path)
		return store.get_attachments_dir(path)

	def get_document_root(self):
		'''Returns the Dir object for the document root or None'''
		path = self.config['Notebook']['document_root']
		if path: return Dir(path)
		else: return None

	def get_template(self, path):
		'''Returns a template object for path. Typically used to set initial
		content for a new page.
		'''
		from zim.templates import get_template
		template = self.namespace_properties[path].get('template', '_New')
		logger.debug('Found template \'%s\' for %s', template, path)
		return get_template('wiki', template)

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

# Need to register classes defining gobject signals
gobject.type_register(Notebook)


class Path(object):
	'''This is the parent class for the Page class. It contains the name
	of the page and is used instead of the actual page object by methods
	that only know the name of the page. Path objects have no internal state
	and are essentially normalized page names.
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

	def __ne__(self, other):
		return not self.__eq__(other)

	def __lt__(self, other):
		'''`self < other` evaluates True when self is a parent of other'''
		return self.isroot or other.name.startswith(self.name+':')

	def __le__(self, other):
		'''`self <= other` is True if `self == other or self < other`'''
		return self.__eq__(other) or self.__lt__(other)

	def __gt__(self, other):
		'''`self > other` evaluates True when self is a child of other'''
		return other.isroot or self.name.startswith(other.name+':')

	def __ge__(self, other):
		'''`self >= other` is True if `self == other or self > other`'''
		return self.__eq__(other) or self.__gt__(other)

	def __add__(self, name):
		'''"path + name" is an alias for path.child(name)'''
		return self.child(name)

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

	@property
	def parent(self):
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


	def child(self, name):
		'''Returns a child path for 'name' '''
		if len(self.name):
			return Path(self.name+':'+name)
		else: # we are the top level root namespace
			return Path(name)

	def commonparent(self, other):
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


class Page(Path):
	'''Class to represent a single page in the notebook.

	Page objects inherit from Path but have internal state reflecting content
	in the notebook. We try to keep Page objects unique
	by hashing them in notebook.get_page(), Path object on the other hand
	are cheap and can have multiple instances for the same logical path.
	We ask for a path object instead of a name in the constructore to
	encourage the use of Path objects over passsing around page names as
	string. Also this allows some optimalizations by addind index pointers
	to the Path instances.

	You can use a Page object instead of a Path anywhere in the APIs where
	a path is needed as argument etc.

	Page objects have an attribute 'valid' which should evaluate True. If for
	some reason this object is abandoned by the notebook, this attribute will
	be set to False. Once the page object is invalidated you can no longer use
	it's internal state. However in that case the object can still be used as
	a regular Path object to point to the location of a page. The way replace
	an invalid page object is by calling `notebook.get_page(invalid_page)`.
	'''

	def __init__(self, path, haschildren=False, parsetree=None):
		'''Construct Page object. Needs a path object and a boolean to flag
		if the page has children.
		'''
		assert isinstance(path, Path)
		self.name = path.name
		self.haschildren = haschildren
		self.valid = True
		self.modified = False
		self._parsetree = parsetree
		self._ui_object = None
		self.readonly = True # stores need to explicitly set readonly False
		self.properties = {}
		if hasattr(path, '_indexpath'):
			self._indexpath = path._indexpath
			# Keeping this data around will speed things up when this page
			# is used for index lookups

	@property
	def hascontent(self):
		'''Returns whether this page has content'''
		if self._parsetree:
			return self._parsetree.hascontent
		elif self._ui_object:
			return self._ui_object.get_parsetree().hascontent
		else:
			try:
				hascontent = self._source_hascontent()
			except NotImplementedError:
				return False
			else:
				return hascontent

	def get_parsetree(self):
		'''Returns contents as a parsetree or None'''
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
		'''Set the parsetree with content for this page. Set the parsetree
		to None to remove all content.
		'''
		assert self.valid, 'BUG: page object became invalid'

		if self.readonly:
			raise PageReadOnlyError, self

		if self._ui_object:
			self._ui_object.set_parsetree(tree)
		else:
			self._parsetree = tree

		self.modified = True

	def set_ui_object(self, object):
		'''Set a temporary hook to fetch the parse tree. Used by the gtk ui to
		'lock' pages that are being edited. Set to None to break the lock.

		The ui object should in turn have a get_parsetree() and a
		set_parsetree() method which will be called by the page object.
		'''
		if object is None:
			self._parsetree = self._ui_object.get_parsetree()
			self._ui_object = None
		else:
			assert self._ui_object is None, 'BUG: page already being edited by another widget'
			self._parsetree = None
			self._ui_object = object

	def dump(self, format, linker=None):
		'''Convenience method that converts the current parse tree to a
		particular format and returns a list of lines. Format can be either a
		format module or a string which can be passed to formats.get_format().
		'''
		if isinstance(format, basestring):
			import zim.formats
			format = zim.formats.get_format(format)

		if not linker is None:
			linker.set_path(self)

		tree = self.get_parsetree()
		if tree:
			return format.Dumper(linker=linker).dump(tree)
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
		'''Generator for a list of tuples of type, href and attrib for links
		in the parsetree.

		This gives the raw links, if you want nice Link objects use
		index.list_links() instead.
		'''
		tree = self.get_parsetree()
		if tree:
			for tag in tree.getiterator('link'):
				attrib = tag.attrib.copy()
				href = attrib.pop('href')
				type = link_type(href)
				yield type, href, attrib


class IndexPage(Page):
	'''Page displaying a namespace index'''

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
		import zim.formats
		builder = zim.formats.TreeBuilder()

		def add_namespace(path):
			pagelist = self.notebook.index.list_pages(path)
			builder.start('ul')
			for page in pagelist:
				builder.start('li')
				builder.start('link', {'type': 'page', 'href': page.name})
				builder.data(page.basename)
				builder.end('link')
				builder.end('li')
				if page.haschildren and self.index_recurs:
					add_namespace(page) # recurs
			builder.end('ul')

		builder.start('page')
		builder.start('h', {'level':1})
		builder.data('Index of %s' % self.name)
		builder.end('h')
		add_namespace(self)
		builder.end('page')

		return zim.formats.ParseTree(builder.close())


class Link(object):

	__slots__ = ('source', 'href', 'type')

	def __init__(self, source, href, type=None):
		self.source = source
		self.href = href
		self.type = type

	def __repr__(self):
		return '<%s: %s to %s (%s)>' % (self.__class__.__name__, self.source, self.href, self.type)
