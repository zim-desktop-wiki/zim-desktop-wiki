# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''
This package contains the main Notebook class and related classes.

This package defines the public interface towards the
noetbook.  As a backend it uses one of more packages from
the 'stores' namespace.
'''

from __future__ import with_statement

import os
import re
import weakref
import logging

import gobject

import zim.fs
from zim.fs import *
from zim.errors import Error, TrashNotSupportedError
from zim.config import ConfigDict, ConfigDictFile, TextConfigFile, HierarchicDict, \
	config_file, data_dir, user_dirs
from zim.parsing import Re, is_url_re, is_email_re, is_win32_path_re, link_type, url_encode
from zim.async import AsyncLock
import zim.stores


logger = logging.getLogger('zim.notebook')

DATA_FORMAT_VERSION = (0, 4)


class NotebookInfo(object):
	'''This class keeps the info for a notebook

	@ivar uri: The location of the notebook
	@ivar name: The notebook name (or the basename of the uri)
	@ivar icon: The file uri for the notebook icon
	@ivar mtime: The mtime of the config file this info was read from (if any)
	@ivar active: The attribute is used to signal whether the notebook
	is already open or not, used in the daemon context, C{None} if this
	is not used, C{True} or C{False} otherwise
	'''

	def __init__(self, uri, name=None, icon=None, mtime=None, **a):
		'''Constructor'''
		# **a is added to be future proof of unknown values in the cache
		f = File(uri)
		self.uri = f.uri
		self.name = name or f.basename
		self.icon = icon
		self.mtime = mtime
		self.active = None

	def __eq__(self, other):
		# objects describe the same notebook when the uri is the same
		return self.uri == other.uri

	def __repr__(self):
		return '<%s: %s>' % (self.__class__.__name__, self.uri)

	def update(self):
		'''Check if info is still up to date and update this object

		This method will check the X{notebook.zim} file for notebook
		folders and read it if it changed.

		@returns: C{True} when data was updated, C{False} otherwise
		'''
		# TODO support for paths that turn out to be files
		dir = Dir(self.uri)
		file = dir.file('notebook.zim')
		if file.exists() and file.mtime() != self.mtime:
			config = ConfigDictFile(file)

			if 'name' in config['Notebook']:
				self.name = config['Notebook']['name'] or dir.basename

			icon, document_root = _resolve_relative_config(dir, config['Notebook'])
			if icon:
				self.icon = icon.uri
			else:
				self.icon = None

			self.mtime = file.mtime()
			return True
		else:
			return False


class NotebookInfoList(list):
	'''This class keeps a list of L{NotebookInfo} objects

	It maps to a X{notebooks.list} config file that keeps a list of
	notebook locations and cached attributes from the various
	X{notebook.zim} config files

	@ivar default: L{NotebookInfo} object for the default
	'''

	def __init__(self, file, default=None):
		'''Constructor

		Signature is compatible to use this class with
		L{zim.config.config_file()}.

		@param file: file object for notebooks.list
		@param default: file object for the default notebooks.list in
		case 'file' does not exists
		'''
		self._file = file
		self._defaultfile = default # default config file
		self.default = None # default notebook
		self.read()
		try:
			self.update()
		except:
			logger.exception('Exception while loading notebook list:')

	def read(self):
		'''Read the config and cache and populate the list'''
		if self._file.exists():
			file = self._file
		elif self._defaultfile:
			file = self._defaultfile
		else:
			return

		lines = file.readlines()
		if len(lines) > 0:
			if lines[0].startswith('[NotebookList]'):
				self.parse(lines)
			else:
				self.parse_old_format(lines)

	def parse(self, text):
		'''Parses the config and cache and populates the list

		Format is::

		  [Notebooklist]
		  default=uri1
		  uri1
		  uri2

		  [Notebook]
		  name=Foo
		  uri=uri1

		Then followed by more "[Notebook]" sections that are cache data

		@param text: a string or a list of lines
		'''
		if isinstance(text, basestring):
			text = text.splitlines(True)

		assert text.pop(0).strip() == '[NotebookList]'

		# Parse key for default
		if text[0].startswith('Default='):
			k, v = text.pop(0).strip().split('=', 1)
			default = v
		else:
			default = None

		# Parse rest of list
		uris = []
		for i, line in enumerate(text):
			if not line or line.isspace():
				break
			elif line.startswith('#'):
				continue

			# assumed to be urls, but we check to be sure
			uri = File(line.strip()).uri
			uris.append(uri)

		# Parse rest of the file with cache
		cache = {}
		config = ConfigDict()
		config['Notebook'] = []
		config.parse(text[i:])
		for section in config['Notebook']:
			uri = section['uri']
			cache[uri] = dict(section)

		# Populate ourselves
		for uri in uris:
			section = cache.get(uri, {'uri': uri})
			info = NotebookInfo(**section)
			self.append(info)

		if default:
			self.set_default(default)

	def parse_old_format(self, text):
		'''Parses the config and cache and populates the list

		Method for backward compatibility with list format with no
		seciton headers and a whitespace separator between notebook
		name and uri.

		@param text: a string or a list of lines
		'''
		# Old format is name, value pair, separated by whitespace
		# with all other whitespace escaped by a \
		# Default was _default_ which could refer a notebook name.
		if isinstance(text, basestring):
			text = text.splitlines(True)

		import re
		fields_re = re.compile(r'(?:\\.|\S)+') # match escaped char or non-whitespace
		escaped_re = re.compile(r'\\(.)') # match single escaped char

		default = None
		defaulturi = None
		uris = []
		for line in text:
			if not line or line.isspace() or line.startswith('#'):
				continue

			cols = fields_re.findall(line.strip())
			if len(cols) == 2:
				name = escaped_re.sub(r'\1', cols[0])
				path = escaped_re.sub(r'\1', cols[1])
				if name == '_default_':
					default = path
				else:
					uri = File(path).uri
					uris.append(uri)
					if name == default:
						defaulturi = uri

		if default and not defaulturi:
			defaulturi = File(default).uri

		# Populate ourselves
		for uri in uris:
			info = NotebookInfo(uri)
			self.append(info)

		if defaulturi:
			self.set_default(defaulturi)

	def write(self):
		'''Write the config and cache'''
		if self.default:
			default = self.default.uri
		else:
			default = None

		lines = [
			'[NotebookList]\n',
			'Default=%s\n' % (default or '')
		]
		lines.extend(info.uri + '\n' for info in self)

		for info in self:
			lines.extend([
				'\n',
				'[Notebook]\n',
				'uri=%s\n' % info.uri,
				'name=%s\n' % info.name,
				'icon=%s\n' % info.icon,
			])

		self._file.writelines(lines)

	def update(self):
		'''Update L{NotebookInfo} objects and write cache'''
		changed = False
		for info in self:
			changed = info.update() or changed
		if changed:
			self.write()

	def set_default(self, uri):
		'''Set the default to 'uri' '''
		for info in self:
			if info.uri == uri:
				self.default = info
				return
		else:
			info = NotebookInfo(uri)
			self.insert(0, info)
			self.default = info

	def get_by_name(self, name):
		'''Get the L{NotebookInfo} object for a notebook by name

		Names are checked case sensitive first, then case-unsensitive

		@param name: notebook name as string
		@returns: a L{NotebookInfo} object or C{None}
		'''
		for info in self:
			if info.name == name:
				return info

		for info in self:
			if info.name.lower() == name.lower():
				return info

		return None


def get_notebook_list():
	'''Returns a list of known notebooks as a L{NotebookInfoList}

	This will load the list from the default X{notebooks.list} file
	'''
	# TODO use weakref here
	return config_file('notebooks.list', klass=NotebookInfoList)


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
		if string.startswith('zim+'): string = string[4:]
		assert string.startswith('file://')
		if '?' in string:
			filepath, page = string.split('?', 1)
			page = Path(page)
		else:
			filepath = string
	elif os.path.sep in string:
		filepath = string
	else:
		nblist = get_notebook_list()
		info = nblist.get_by_name(string)
		if info is None:
			if os.path.exists(string):
				filepath = string # fall back to file path
			else:
				return None, None # not found
		else:
			filepath = info.uri

	file = File(filepath) # Fixme need generic FS Path object here
	if filepath.endswith('notebook.zim'):
		return file.dir, page
	elif not page and file.exists(): # file exists and really is a file
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


def get_notebook(path):
	'''Convenience method that constructs a notebook from either a
	uri, or a File or a Dir object.
	'''
	# TODO this is where the hook goes to automount etc.
	if isinstance(path, basestring):
		file = File(path)
		if file.exists(): # exists and is a file
			path = file
		else:
			path = Dir(path)
	else:
		assert isinstance(path, (File, Dir))

	if path.exists():
		if isinstance(path, File):
			return Notebook(file=path)
		else:
			return Notebook(dir=path)
	else:
		return None


def init_notebook(path, name=None):
	'''Initialize a new notebook in a directory'''
	assert isinstance(path, Dir)
	path.touch()
	config = ConfigDictFile(path.file('notebook.zim'))
	config['Notebook']['name'] = name or path.basename
	config['Notebook']['version'] = '.'.join(map(str, DATA_FORMAT_VERSION))
	if os.name == 'nt': endofline = 'dos'
	else: endofline = 'unix'
	config['Notebook']['endofline'] = endofline
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
		info = list.get_by_name(key)
		if info:
			url = 'zim+' + info.uri + '?{NAME}'

	if url and is_url_re.match(url):
		if not ('{NAME}' in url or '{URL}' in url):
			url += '{URL}'

		url = url.replace('{NAME}', page)
		url = url.replace('{URL}', url_encode(page))

		return url
	else:
		return None


def _resolve_relative_config(dir, config):
	# Some code shared between Notebook and NotebookInfo

	# Resolve icon, can be relative
	icon = config.get('icon')
	if icon:
		if zim.fs.isabs(icon) or not dir:
			icon = File(icon)
		else:
			icon = dir.resolve_file(icon)

	# Resolve document_root, can also be relative
	document_root = config.get('document_root')
	if document_root:
		if zim.fs.isabs(document_root) or not dir:
			document_root = Dir(document_root)
		else:
			document_root = dir.resolve_dir(document_root)

	return icon, document_root


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

	description = _('''\
Index is still busy updating while we try to do an
operation that needs the index.
''') # T: error message


class PageExistsError(Error):
	pass

	# TODO verbose description


class PageReadOnlyError(Error):

	# TODO verbose description

	def __init__(self, page):
		self.msg = _('Can not modify page: %s') % page.name
			# T: error message for read-only pages


_first_char_re = re.compile(r'^\W', re.UNICODE)


class Notebook(gobject.GObject):
	'''Main class to access a notebook. Proxies between backend Store
	and Index objects on the one hand and the gui application on the other

	This class has the following signals:
		* store-page (page) - emitted before actually storing the page
		* stored-page (page) - emitted after storing the page
		* move-page (oldpath, newpath, update_links)
		* moved-page (oldpath, newpath, update_links)
		* delete-page (path) - emitted when deleting a page -- listen to
		"deleted-page" if you need to know the delete was successful
		* deleted-page (path) - emitted after deleting a page
		* properties-changed ()

	Signals for store, move and delete are defined double with one
	emitted before the action and the other after the action run
	succesfully. THis is done this way because exceptions thrown from
	a signal handler are difficult to handle. For store_async() the
	'page-stored' signal is emitted after scheduling the store, but
	potentially before it was really executed.

	Notebook objects have a 'lock' attribute with a AsyncLock object.
	This lock is used when storing pages. In general this lock is not
	needed when only reading data from the notebook. However it should
	be used when doing operations that need a fixed state, e.g.
	exporting the notebook or when executing version control commands
	on the storage directory.

	@ivar name: The name of the notebook (string)
	@ivar icon: The path for the notebook icon (if any) # FIXME should be L{File} object
	@ivar document_root: The L{Dir} object for the X{document root} (if any)
	'''

	# TODO add checks for read-only page in much more methods

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'store-page': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'stored-page': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'move-page': (gobject.SIGNAL_RUN_LAST, None, (object, object, bool)),
		'moved-page': (gobject.SIGNAL_RUN_LAST, None, (object, object, bool)),
		'delete-page': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'deleted-page': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'properties-changed': (gobject.SIGNAL_RUN_FIRST, None, ()),
	}

	properties = (
		('name', 'string', _('Name')), # T: label for properties dialog
		('home', 'page', _('Home Page')), # T: label for properties dialog
		('icon', 'image', _('Icon')), # T: label for properties dialog
		('document_root', 'dir', _('Document Root')), # T: label for properties dialog
		('shared', 'bool', _('Shared Notebook')), # T: label for properties dialog
		#~ ('autosave', 'bool', _('Auto-version when closing the notebook')),
			# T: label for properties dialog
	)

	def __init__(self, dir=None, file=None, config=None, index=None):
		assert not (dir and file), 'BUG: can not provide both dir and file '
		gobject.GObject.__init__(self)
		self._namespaces = []	# list used to resolve stores
		self._stores = {}		# dict mapping namespaces to stores
		self.namespace_properties = HierarchicDict({
				'template': 'Default'
			})
		self._page_cache = weakref.WeakValueDictionary()
		self.dir = None
		self.file = None
		self.cache_dir = None
		self.name = None
		self.icon = None
		self.document_root = None
		self.config = config
		self.lock = AsyncLock()
			# We don't use FS.get_async_lock() at this level. A store
			# backend will automatically trigger this when it calls any
			# async file operations. This one is more abstract for the
			# notebook as a whole, regardless of storage

		if dir:
			assert isinstance(dir, Dir)
			self.dir = dir
			self.readonly = not dir.iswritable()

			if self.config is None:
				self.config = ConfigDictFile(dir.file('notebook.zim'))

			self.cache_dir = dir.subdir('.zim')
			if self.readonly or self.config['Notebook'].get('shared') \
			or not self.cache_dir.iswritable():
				self.cache_dir = self._cache_dir(dir)
			logger.debug('Cache dir: %s', self.cache_dir)

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
			self.config['Notebook']['version'] = '.'.join(map(str, DATA_FORMAT_VERSION))
		else:
			if self.needs_upgrade:
				logger.warn('This notebook needs to be upgraded to the latest data format')

		self.config['Notebook'].setdefault('name', None, check=basestring)
		self.config['Notebook'].setdefault('home', ':Home', check=basestring)
		self.config['Notebook'].setdefault('icon', None, check=basestring)
		self.config['Notebook'].setdefault('document_root', None, check=basestring)
		self.config['Notebook'].setdefault('shared', False)
		if os.name == 'nt': endofline = 'dos'
		else: endofline = 'unix'
		self.config['Notebook'].setdefault('endofline', endofline, check=set(('dos', 'unix')))
		self.config['Notebook'].setdefault('disable_trash', False)

		self.do_properties_changed()

	@property
	def uri(self):
		'''Returns a file:// uri for this notebook that can be opened by zim'''
		assert self.dir or self.file, 'Notebook does not have a dir or file'
		if self.dir:
			return self.dir.uri
		else:
			return self.file.uri

	@property
	def endofline(self):
		return self.config['Notebook']['endofline']

	def _cache_dir(self, dir):
		from zim.config import XDG_CACHE_HOME
		if os.name == 'nt':
			path = 'notebook-' + dir.path.replace('\\', '_').replace(':', '').strip('_')
		else:
			path = 'notebook-' + dir.path.replace('/', '_').strip('_')
		return XDG_CACHE_HOME.subdir(('zim', path))

	def save_properties(self, **properties):
		# Check if icon is relative
		icon = properties.get('icon')
		if icon and not isinstance(icon, basestring):
			assert isinstance(icon, File)
			if self.dir and icon.ischild(self.dir):
				properties['icon'] = './' + icon.relpath(self.dir)
			else:
				properties['icon'] = icon.path

		# Check document root is relative
		root = properties.get('document_root')
		if root and not isinstance(root, basestring):
			assert isinstance(root, Dir)
			if self.dir and root.ischild(self.dir):
				properties['document_root'] = './' + root.relpath(self.dir)
			else:
				properties['document_root'] = root.path

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

		# Resolve icon and document root, can be relative
		icon, document_root = _resolve_relative_config(self.dir, config)
		if icon:
			self.icon = icon.path # FIXME rewrite to use File object
		else:
			self.icon = None
		self.document_root = document_root

		# TODO - can we switch cache_dir on run time when 'shared' chagned ?

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
		elif href.ischild(source):
			return '+' + href.relname(source)
		else:
			parent = source.commonparent(href)
			if parent.isroot:
				return ':' + href.name
			elif parent == source.parent:
				if parent == href:
					return href.basename
				else:
					return href.relname(parent)
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
	def cleanup_pathname(name, purge=False):
		'''Returns a safe version of name, used internally by functions like
		resolve_path() to parse user input.
		It raises a PageNameError when the name is not valid

		If 'purge' is True any invalid characters will be removed,
		otherwise they will result in a PageNameError exception.
		'''
		# Reserved characters are:
		# The ':' is reserrved as seperator
		# The '?' is reserved to encode url style options
		# The '#' is reserved as anchor separator
		# The '/' and '\' are reserved to distinquise file links & urls
		# First character of each part MUST be alphanumeric
		#		(including utf8 letters / numbers)

		# Zim version < 0.42 restricted all special charachters but
		# white listed ".", "-", "_", "(", ")", ":" and "%".

		# For file system we should reserve (win32 & posix)
		# "\", "/", ":", "*", "?", '"', "<", ">", "|"

		# Do not allow '\n' for obvious reasons

		# Allowing '%' will cause problems with sql wildcards sooner
		# or later - also for url decoding ambiguity it is better to
		# keep this one reserved

		orig = name
		name = name.replace('_', ' ')
			# Avoid duplicates with and without '_' (e.g. in index)
			# Note that leading "_" is stripped, due to strip() below

		if purge:
			for char in ("?", "#", "/", "\\", "*", '"', "<", ">", "|", "%", "\n"):
				name = name.replace(char, '')
		else:
			for char in ("?", "#", "/", "\\", "*", '"', "<", ">", "|", "%", "\n"):
				if char in name:
					raise PageNameError, orig

		parts = map(unicode.strip, filter(
			lambda n: len(n)>0, unicode(name).split(':') ) )

		for part in parts:
			if _first_char_re.match(part):
				raise PageNameError, orig

		name = ':'.join(parts)

		if not name:
			raise PageNameError, orig

		return name

	@staticmethod
	def cleanup_pathname_zim028(name):
		'''Like cleanup_pathname(), but applies logic as it was in
		zim 0.28 which replaces illegal characters by "_" instead of
		throwing an exception. Needed to fix broken links in older
		notebooks.
		'''
		# OLD CODE WAS:
		# $name =~ s/^:*/:/ unless $rel;	# absolute name
		# $name =~ s/:+$//;					# not a namespace
		# $name =~ s/::+/:/g;				# replace multiple ":"
		# $name =~ s/[^:\w\.\-\(\)\%]/_/g;	# replace forbidden chars
		# $name =~ s/(:+)[\_\.\-\(\)]+/$1/g;	# remove non-letter at begin
		# $name =~ s/_+(:|$)/$1/g;			# remove trailing underscore

		forbidden_re = re.compile(r'[^\w\.\-\(\)]', re.UNICODE)
		non_letter_re = re.compile(r'^\W+', re.UNICODE)

		prefix = ''
		if name[0] in (':', '.', '+'):
			prefix = name[0]
			name = name[1:]

		path = []
		for n in filter(len, name.split(':')):
			n = forbidden_re.sub('_', n) # replace forbidden chars
			n = non_letter_re.sub('', n) # remove non-letter at begin
			n = n.rstrip('_') # remove trailing underscore
			if len(n):
				path.append(n)

		return prefix + ':'.join(path)

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
			indexpath = self.index.lookup_path(path)
			if indexpath and indexpath.haschildren:
				page.haschildren = True
				# page might be the parent of a placeholder, in that case
				# the index knows it has children, but the store does not

			# TODO - set haschildren if page maps to a store namespace
			self._page_cache[path.name] = page
			return page

	def get_new_page(self, path):
		'''Like get_page() but guarantees the page does not yet exist.
		Will add a number to make name unique.
		'''
		i = 0
		base = path.name
		page = self.get_page(path)
		while page.hascontent or page.haschildren:
			i += 1
			path = Path(base + ' %i' % i)
			page = self.get_page(path)
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
		with self.lock:
			store = self.get_store(path)
			list = store.get_pagelist(path)
		# TODO: add sub-stores in this namespace if any
		return list

	def store_page(self, page):
		'''Store a page permanently. Commits the parse tree from the page
		object to the backend store.
		'''
		assert page.valid, 'BUG: page object no longer valid'
		self.emit('store-page', page)
		store = self.get_store(page)
		store.store_page(page)
		self.emit('stored-page', page)

	def store_page_async(self, page, callback=None, data=None):
		'''Like store_page but asynchronous. Falls back to store_page
		when the backend does not support asynchronous operation.

		If you add a callback function it will be called after the
		page was stored (in the main thread). Callback is called like:

			callback(ok, exc_info, data)

			* 'ok' is True is the page was stored OK
			* 'error' is an Exception object or None
			* 'exc_info' is a 3 tuple of sys.exc_info() or None
			* 'data' is the data given to the constructor

		The callback should be used to do proper error handling if you
		want to use this interface e.g. from the UI.
		'''
		# TODO: make consistent with store-page signal

		# Note that we do not assume here that async function is always
		# performed by zim.async. Different backends could have their
		# native support for asynchronous actions. So we do not return
		# an AsyncOperation object to prevent lock in.
		# This assumption may change in the future.
		assert page.valid, 'BUG: page object no longer valid'
		self.emit('store-page', page)
		store = self.get_store(page)
		store.store_page_async(page, self.lock, callback, data)
		self.emit('stored-page', page)

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

	def move_page(self, path, newpath, update_links=True, callback=None):
		'''Move a page from 'path' to 'newpath'. If 'update_links' is
		True all links from and to the page will be modified as well.
		The original page 'path' does not have to exist, this is usefull
		to update links for a placeholder. If 'newpath' exists a
		PageExistsError error will be raised.
		'''
		if path == newpath:
			return

		if update_links and self.index.updating:
			raise IndexBusyError, 'Index busy'
			# Index need to be complete in order to be 100% sure we
			# know all backlinks, so no way we can update links before.

		page = self.get_page(path)
		assert not page.modified, 'BUG: moving a page with uncomitted changes'

		newpage = self.get_page(newpath)
		if newpage.exists():
			raise PageExistsError, 'Page already exists: %s' % newpath.name

		self.emit('move-page', path, newpath, update_links)
		logger.debug('Move %s to %s (%s)', path, newpath, update_links)

		# Collect backlinks
		if update_links:
			from zim.index import LINK_DIR_BACKWARD
			backlinkpages = set()
			for l in self.index.list_links(path, LINK_DIR_BACKWARD):
				backlinkpages.add(l.source)

			if page.haschildren:
				for child in self.index.walk(path):
					for l in self.index.list_links(child, LINK_DIR_BACKWARD):
						backlinkpages.add(l.source)

		# Do the actual move (if the page exists)
		if page.exists():
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
			if callback: callback(page)
			self._update_links_from(page, path, page, path)
			store = self.get_store(page)
			store.store_page(page)
			# do not use self.store_page because it emits signals
		for child in self._no_index_walk(newpath):
			if not child.hascontent:
				continue
			if callback: callback(child)
			oldpath = path + child.relname(newpath)
			self._update_links_from(child, oldpath, newpath, path)
			store = self.get_store(child)
			store.store_page(child)
			# do not use self.store_page because it emits signals

		# Update links to the moved page tree
		if update_links:
			# Need this indexed before we can resolve links to it
			self.index.delete(path)
			self.index.update(newpath)
			#~ print backlinkpages
			total = len(backlinkpages)
			for p in backlinkpages:
				if p == path or p.ischild(path):
					continue
				page = self.get_page(p)
				if callback: callback(page, total=total)
				self._update_links_in_page(page, path, newpath)
				self.store_page(page)

		self.emit('moved-page', path, newpath, update_links)

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

	def _update_links_from(self, page, oldpath, parent, oldparent):
		logger.debug('Updating links in %s (was %s)', page, oldpath)
		tree = page.get_parsetree()
		if not tree:
			return

		for tag in tree.getiterator('link'):
			try:
				href = tag.attrib['href']
				type = link_type(href)
				if type == 'page':
					hrefpath = self.resolve_path(href, source=page)
					oldhrefpath = self.resolve_path(href, source=oldpath)
					#~ print 'LINK', oldhrefpath, '->', hrefpath
					if hrefpath != oldhrefpath:
						if (hrefpath == page or hrefpath.ischild(page)) \
						and (oldhrefpath == oldpath or oldhrefpath.ischild(oldpath)):
							#~ print '\t.. Ignore'
							pass
						else:
							newhref = self.relative_link(page, oldhrefpath)
							#~ print '\t->', newhref
							self._update_link_tag(tag, newhref)
					elif (hrefpath == oldparent or hrefpath.ischild(oldparent)):
						# Special case where we e.g. link to our own children using
						# a common parent between old and new path as an anchor for resolving
						newhrefpath = parent
						if hrefpath.ischild(oldparent):
							newhrefpath = parent + hrefpath.relname(oldparent)
						newhref = self.relative_link(page, newhrefpath)
						#~ print '\t->', newhref
						self._update_link_tag(tag, newhref)
					else:
						pass
			except:
				logger.exception('Error while updating link "%s"', href)

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
			try:
				href = tag.attrib['href']
				type = link_type(href)
				if type == 'page':
					hrefpath = self.resolve_path(href, source=page)
					#~ print 'LINK', hrefpath
					if hrefpath == oldpath:
						newhrefpath = newpath
						#~ print '\t==', oldpath, '->', newhrefpath
					elif hrefpath.ischild(oldpath):
						rel = hrefpath.relname(oldpath)
						newhrefpath = newpath + rel
						#~ print '\t>', oldpath, '->', newhrefpath
					else:
						continue

					newhref = self.relative_link(page, newhrefpath)
					self._update_link_tag(tag, newhref)
			except:
				logger.exception('Error while updating link "%s"', href)

		page.set_parsetree(tree)

	def rename_page(self, path, newbasename, update_heading=True, update_links=True, callback=None):
		'''Rename page to a page in the same namespace but with a new
		basename. If 'update_heading' is True the first heading in the
		page will be updated to it's new name.  If 'update_links' is
		True all links from and to the page will be modified as well.
		'''
		logger.debug('Rename %s to "%s" (%s, %s)',
			path, newbasename, update_heading, update_links)

		newbasename = self.cleanup_pathname(newbasename)
		newpath = Path(path.namespace + ':' + newbasename)
		if newbasename.lower() != path.basename.lower():
			# allow explicit case-sensitive renaming
			newpath = self.index.resolve_case(
				newbasename, namespace=path.parent) or newpath

		self.move_page(path, newpath, update_links, callback)
		if update_heading:
			page = self.get_page(newpath)
			tree = page.get_parsetree()
			if not tree is None:
				tree.set_heading(newbasename)
				page.set_parsetree(tree)
				self.store_page(page)

		return newpath

	def delete_page(self, path, update_links=True, callback=None):
		'''Delete a page. If 'update_links' is True pages linking to the
		deleted page will be updated and the link are removed.
		'''
		return self._delete_page(path, update_links, callback)

	def trash_page(self, path, update_links=True, callback=None):
		'''Like delete_page() but will use Trash. Raises TrashNotSupportedError
		if trashing is not supported by the storage backend or when trashing
		is explicitly disabled for this notebook.
		'''
		if self.config['Notebook']['disable_trash']:
			raise TrashNotSupportedError, 'disable_trash is set'
		return self._delete_page(path, update_links, callback, trash=True)

	def _delete_page(self, path, update_links=True, callback=None, trash=False):
		# Collect backlinks
		indexpath = self.index.lookup_path(path)
		if update_links and indexpath:
			from zim.index import LINK_DIR_BACKWARD
			backlinkpages = set()
			for l in self.index.list_links(path, LINK_DIR_BACKWARD):
				backlinkpages.add(l.source)

			page = self.get_page(path)
			if page.haschildren:
				for child in self.index.walk(path):
					for l in self.index.list_links(child, LINK_DIR_BACKWARD):
						backlinkpages.add(l.source)
		else:
			update_links = False

		# actual delete
		self.emit('delete-page', path)

		store = self.get_store(path)
		if trash:
			store.trash_page(path)
		else:
			store.delete_page(path)

		self.flush_page_cache(path)
		path = Path(path.name)

		# Update links to the deleted page tree
		if update_links:
			#~ print backlinkpages
			total = len(backlinkpages)
			for p in backlinkpages:
				if p == path or p.ischild(path):
					continue
				page = self.get_page(p)
				if callback: callback(page, total=total)
				self._remove_links_in_page(page, path)
				self.store_page(page)

		# let everybody know what happened
		self.emit('deleted-page', path)

	def _remove_links_in_page(self, page, path):
		logger.debug('Removing links in %s to %s', page, path)
		tree = page.get_parsetree()
		if not tree:
			logger.warn('Page turned out to be empty: %s', page)
			return

		def walk_links(parent):
			# Yields parent element, previous element and link element.
			# we actually yield links in reverse order, so removal
			# algorithm works for consequetive links as well.
			children = parent.getchildren()
			for i in range(len(children)-1, -1, -1):
				if children[i].tag == 'link':
					if i > 0: yield parent, children[i-1], children[i]
					else: yield parent, None, children[i]
				for items in walk_links(children[i]): # recurs
					yield items

		for parent, prev, element in walk_links(tree.getroot()):
			try:
				href = element.attrib['href']
				type = link_type(href)
				if type == 'page':
					hrefpath = self.resolve_path(href, source=page)
					#~ print 'LINK', hrefpath
					if hrefpath == path \
					or hrefpath.ischild(path):
						# Remove the link
						text = (element.text or '') + (element.tail or '')
						if not prev is None:
							prev.tail = (prev.tail or '') + text
						else:
							parent.text = (parent.text or '') + text
						parent.remove(element)
					else:
						continue
			except:
				logger.exception('Error while removing link "%s"', href)

		page.set_parsetree(tree)

	def resolve_file(self, filename, path=None):
		'''Resolves a file or directory path relative to a page or
		Notebook. Returns a File object. However the file does not
		have to exist.

		File urls and paths that start with '~/' or '~user/' are
		considered absolute paths and the corresponding File objects
		are returned. Also handles windows absolute paths.

		In case the file path starts with '/' the the path is taken relative
		to the document root - this can e.g. be a parent directory of the
		notebook. Defaults to the filesystem root when no document root
		is set.

		Other paths are considered attachments and are resolved relative
		to the namespace below the page. If no path is given but the
		notebook has a root folder, this folder is used as base path.
		'''
		assert isinstance(filename, basestring)
		filename = filename.replace('\\', '/')
		if filename.startswith('~') or filename.startswith('file:/'):
			return File(filename)
		elif filename.startswith('/'):
			dir = self.document_root or Dir('/')
			return dir.file(filename)
		elif is_win32_path_re.match(filename):
			if not filename.startswith('/'):
				filename = '/'+filename
				# make absolute on unix
			return File(filename)
		else:
			if path:
				dir = self.get_attachments_dir(path)
			else:
				assert self.dir, 'Can not resolve relative path for notebook without root folder'
				dir = self.dir

			return File((dir, filename))

	def relative_filepath(self, file, path=None):
		'''Returns a filepath relative to either the documents dir
		(/xxx), the attachments dir (if a path is given) or the notebook
		folder (./xxx or ../xxx) or the users home dir (~/xxx).
		Returns None otherwise.

		Intended as the counter part of resolve_file(). Typically this
		function is used to present the user with readable paths or to
		shorten the paths inserted in the wiki code. It is advised to
		use file uris for links that can not be made relative.

		Relative file paths are always given with unix path semantics
		(so "/" even on windows). A leading "/" does not mean the path
		is absolute, but rather that it is relative to the
		X{document root}.

		@param file: L{File} object we want to link
		@keyword path: L{Path} object for the page where we want to link this file

		@return: relative file path or C{None} when no relative path was found
		@rtype: string or C{None}
		'''
		notebook_root = self.dir
		document_root = self.document_root

		# Look within the notebook
		if path:
			attachments_dir = self.get_attachments_dir(path)

			if file.ischild(attachments_dir):
				return './'+file.relpath(attachments_dir)
			elif document_root and notebook_root \
			and document_root.ischild(notebook_root) \
			and file.ischild(document_root) \
			and not attachments_dir.ischild(document_root):
				# special case when document root is below notebook root
				# the case where document_root == attachment_folder is
				# already caught by above if clause
				return '/'+file.relpath(document_root)
			elif notebook_root \
			and file.ischild(notebook_root) \
			and attachments_dir.ischild(notebook_root):
				parent = file.commonparent(attachments_dir)
				uppath = attachments_dir.relpath(parent)
				downpath = file.relpath(parent)
				up = 1 + uppath.count('/')
				return '../'*up + downpath
		else:
			if document_root and notebook_root \
			and document_root.ischild(notebook_root) \
			and file.ischild(document_root):
				# special case when document root is below notebook root
				return '/'+file.relpath(document_root)
			elif notebook_root and file.ischild(notebook_root):
				return './'+file.relpath(notebook_root)

		# If that fails look for global folders
		if document_root and file.ischild(document_root):
			return '/'+file.relpath(document_root)

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

	def get_template(self, path):
		'''Returns a template object for path. Typically used to set initial
		content for a new page.
		'''
		from zim.templates import get_template
		template = self.namespace_properties[path]['template']
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

	@property
	def needs_upgrade(self):
		try:
			version = str(self.config['Notebook']['version'])
			version = tuple(version.split('.'))
			return version < DATA_FORMAT_VERSION
		except KeyError:
			return True

	def upgrade_notebook(self, callback=None):
		'''Tries to update older notebook to format supported by the
		latest version.
		'''
		# Currently we just assume upgrade from zim < 0.43
		# may need to add more sophisticated logic later..
		#
		# We check for links based on old pagename cleanup rules
		# also we write every page, just to be sure they are stored in
		# the latest wiki format.
		logger.info('Notebook update started')
		self.index.ensure_update(callback=callback)

		candidate_re = re.compile('[\W_]')
		for page in self.walk():
			if callback:
				cont = callback(page)
				if not cont:
					logger.info('Notebook update cancelled')
					return

			try:
				tree = page.get_parsetree()
			except:
				# Some issue we can't fix
				logger.exception('Error while parsing page: "%s"', page.name)
				tree = None

			if tree is None:
				continue

			changed = False
			for tag in tree.getiterator('link'):
				href = tag.attrib['href']
				type = link_type(href)
				if type == 'page' and candidate_re.search(href):
					# Skip if we can resolve it already
					try:
						link = self.resolve_path(href, source=page)
						link = self.get_page(link)
					except:
						pass
					else:
						if link and link.hascontent:
							# Do not check haschildren here, children could be placeholders as well
							continue

					# Otherwise check if old version would have found a match
					try:
						newhref = self.cleanup_pathname_zim028(href)
						if newhref != href:
							link = self.resolve_path(newhref, source=page)
							link = self.get_page(link)
						else:
							link = None
					except:
						pass
					else:
						if link and link.hascontent:
							# Do not check haschildren here, children could be placeholders as well
							tag.attrib['href'] = newhref
							changed = True
							logger.info('Changed link "%s" to "%s"', href, newhref)

			# Store this page
			try:
				if changed:
					page.set_parsetree(tree)

				self.store_page(page)
			except:
				logger.exception('Could not store page: "%s"', page.name)

		# Update the version and we are done
		self.config['Notebook']['version'] = '.'.join(map(str, DATA_FORMAT_VERSION))
		self.config.write()
		logger.info('Notebook update done')

# Need to register classes defining gobject signals
gobject.type_register(Notebook)


import warnings


class Path(object):
	'''This is the parent class for the Page class. It contains the name
	of the page and is used instead of the actual page object by methods
	that only know the name of the page. Path objects have no internal state
	and are essentially normalized page names.

	@note: There are several subclasses of this class like
	L{index.IndexPath}, L{Page}, and L{stores.files.FileStorePage}.
	In any API call where a path object is needed each of these
	subclasses can be used instead.
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

		try:
			self.name = unicode(self.name)
		except UnicodeDecodeError:
			raise Error, 'BUG: invalid input, page names should be in ascii, or given as unicode'

	def serialize_zim_config(self):
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
		return not self.__eq__(other)

	def __add__(self, name):
		'''"path + name" is an alias for path.child(name)'''
		return self.child(name)

	def __lt__(self, other):
		'''`self < other` evaluates True when self is a parent of other'''
		warnings.warn('Usage of Path.__lt__ is deprecated', DeprecationWarning, 2)
		return self.isroot or other.name.startswith(self.name+':')

	def __le__(self, other):
		'''`self <= other` is True if `self == other or self < other`'''
		warnings.warn('Usage of Path.__le__ is deprecated', DeprecationWarning, 2)
		return self.__eq__(other) or self.__lt__(other)

	def __gt__(self, other):
		'''`self > other` evaluates True when self is a child of other'''
		warnings.warn('Usage of Path.__gt__ is deprecated', DeprecationWarning, 2)
		return other.isroot or self.name.startswith(other.name+':')

	def __ge__(self, other):
		'''`self >= other` is True if `self == other or self > other`'''
		warnings.warn('Usage of Path.__ge__ is deprecated', DeprecationWarning, 2)
		return self.__eq__(other) or self.__gt__(other)

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

	def ischild(self, parent):
		'''Returns True if this path is a child of 'parent' '''
		return parent.isroot or self.name.startswith(parent.name + ':')

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
		return self.haschildren or self.hascontent

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

	def append_parsetree(self, tree):
		'''Append to the current parsetree'''
		ourtree = self.get_parsetree()
		if ourtree:
			self.set_parsetree(ourtree + tree)
		else:
			self.set_parsetree(tree)

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

	def parse(self, format, text, append=False):
		'''Convenience method that parses text and sets the parse tree
		for this page. Format can be either a format module or a string which
		can be passed to formats.get_format(). Text can be either a string or
		a list or iterable of lines. If 'append' is True the text is
		appended instead of replacing current content.
		'''
		if isinstance(format, basestring):
			import zim.formats
			format = zim.formats.get_format(format)

		if append:
			self.append_parsetree(format.Parser().parse(text))
		else:
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

	def get_tags(self):
		'''Generator of an unordered list of unique tuples of name and attrib
		for tags in the parsetree.
		'''
		tree = self.get_parsetree()
		if tree:
			tags = {}
			for tag in tree.getiterator('tag'):
				tags[tag.text.strip()] = tag.attrib.copy()
			for tag, attrib in tags.iteritems():
				yield tag, attrib


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

		tree = zim.formats.ParseTree(builder.close())
		#~ print "!!!", tree.tostring()
		return tree


class Link(object):

	__slots__ = ('source', 'href', 'type')

	def __init__(self, source, href, type=None):
		self.source = source
		self.href = href
		self.type = type

	def __repr__(self):
		return '<%s: %s to %s (%s)>' % (self.__class__.__name__, self.source, self.href, self.type)
