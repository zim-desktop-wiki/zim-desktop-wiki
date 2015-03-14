# -*- coding: utf-8 -*-

# Copyright 2008-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''
This module contains the main Notebook class and related classes.

This package defines the public C{Notebook} interface. This is a generic
API for accessing and storing pages and other data in the notebook.

The notebook object is agnostic about the actual source of the data
(files, database, etc.), this is implemented by "store" objects which
handle a specific storage model. Storage models live below the
L{zim.stores} module; e.g. the default mapping of a notebook to a folder
with one file per page is implemented in the module L{zim.stores.files}.
The Notebook can map multiple store backends under different namespaces
(much in the same way you can 'mount' various filesystems under a
single root on unix systems) although this is not used in the default
configuration.

The class L{Path} abstracts the location of a single page in the
notebook. Once a path object is constructed we can assume we have
sanitized user input etc. Therefore almost all methods in the Notebook
API require path objects. (See L{notebook.pages.lookup_from_user_input()} to convert a
page name as string to a Path object, or L{Path.makeValidPageName()}
to sanitize user input without creating a Path object.)

L{Page} object map to a page and it's actual content. It derives from
L{Path} so it can be used anywhere in the API where a path is required.

This module also contains some functions and classes to resolve
notebook locations and keep a list of known notebooks.


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

from __future__ import with_statement

import os
import re
import weakref
import logging
import threading

import gobject

from zim.signals import ConnectorMixin, SignalEmitter

import zim.fs

from zim.fs import File, Dir, FS, FilePath, FileNotFoundError
from zim.errors import Error, TrashNotSupportedError
from zim.utils import natural_sort_key
from zim.config import SectionedConfigDict, INIConfigFile, HierarchicDict, \
	data_dir, ConfigManager, XDGConfigFileIter #list_profiles
from zim.parsing import Re, is_url_re, is_email_re, is_win32_path_re, \
	is_interwiki_keyword_re, link_type, url_encode, url_decode
import zim.templates
import zim.formats
import zim.stores


logger = logging.getLogger('zim.notebook')

DATA_FORMAT_VERSION = (0, 4)


class NotebookInfo(object):
	'''This class keeps the info for a notebook

	@ivar uri: The location of the notebook
	@ivar user_path: The location of the notebook relative to the
	home folder (starts with '~/') or C{None}
	@ivar name: The notebook name (or the basename of the uri)
	@ivar icon: The file uri for the notebook icon
	@ivar icon_path: The location of the icon as configured (either
	relative to the notebook location, relative to home folder or
	absolute path)
	@ivar mtime: The mtime of the config file this info was read from (if any)
	@ivar active: The attribute is used to signal whether the notebook
	is already open or not, used in the daemon context, C{None} if this
	is not used, C{True} or C{False} otherwise
	@ivar interwiki: The interwiki keyword (if any)
	'''

	def __init__(self, uri, name=None, icon=None, mtime=None, interwiki=None, **a):
		'''Constructor

		Known values for C{name}, C{icon} etc. can be specified.
		Alternatively L{update()} can be called to read there from the
		notebook configuration (if any). If C{mtime} is given the
		object acts as a cache and L{update()} will only read the config
		if it is newer than C{mtime}

		@param uri: location uri or file path for the notebook (esp. C{user_path})
		@param name: notebook name
		@param icon: the notebook icon path
		@param mtime: the mtime when config was last read
		@param interwiki: the interwiki keyword for this notebook
		@param a: any additional arguments will be discarded
		'''
		# **a is added to be future proof of unknown values in the cache
		if isinstance(uri, basestring) \
		and is_url_re.match(uri) and not uri.startswith('file://'):
			self.uri = uri
			self.user_path = None
			self.name = name
		else:
			f = File(uri)
			self.uri = f.uri
			self.user_path = f.user_path # set to None when uri is not a file uri
			self.name = name or f.basename
		self.icon_path = icon
		self.icon = File(icon).uri
		self.mtime = mtime
		self.interwiki = interwiki
		self.active = None

	def __eq__(self, other):
		# objects describe the same notebook when the uri is the same
		if isinstance(other, basestring):
			return self.uri == other
		elif hasattr(other, 'uri'):
			return self.uri == other.uri
		else:
			return False

	def __repr__(self):
		return '<%s: %s>' % (self.__class__.__name__, self.uri)

	def update(self):
		'''Check if info is still up to date and update this object

		This method will check the X{notebook.zim} file for notebook
		folders and read it if it changed. It uses the C{mtime}
		attribute to keep track of changes.

		@returns: C{True} when data was updated, C{False} otherwise
		'''
		# TODO support for paths that turn out to be files
		dir = Dir(self.uri)
		file = dir.file('notebook.zim')
		if file.exists() and file.mtime() != self.mtime:
			config = NotebookConfig(file)
			section = config['Notebook']

			self.name = section['name']
			self.interwiki = section['interwiki']
			self.icon_path = section['icon']
			icon, document_root = _resolve_relative_config(dir, section)
			if icon:
				self.icon = icon.uri
			else:
				self.icon = None

			self.mtime = file.mtime()
			return True
		else:
			return False


class VirtualFile(object):
	### TODO - proper class for this in zim.fs
	###        unify with code in config manager

	def __init__(self, lines):
		self.lines = lines

	def readlines(self):
		return self.lines

	def connect(self, handler, *a):
		pass

	def disconnect(self, handler):
		pass


class NotebookInfoList(list):
	'''This class keeps a list of L{NotebookInfo} objects

	It maps to a X{notebooks.list} config file that keeps a list of
	notebook locations and cached attributes from the various
	X{notebook.zim} config files

	@ivar default: L{NotebookInfo} object for the default
	'''

	def __init__(self, file):
		'''Constructor
		@param file: a L{File} or L{ConfigFile} object for X{notebooks.list}
		'''
		self.file = file
		self.default = None # default notebook
		self.read()
		try:
			self.update()
		except:
			logger.exception('Exception while loading notebook list:')

	def read(self):
		'''Read the config and cache and populate the list'''
		lines = self.file.readlines()
		if len(lines) > 0:
			if lines[0].startswith('[NotebookList]'):
				self.parse(lines)
			else:
				self.parse_old_format(lines)

	def parse(self, text):
		'''Parses the config and cache and populates the list

		Format is::

		  [NotebookList]
		  Default=uri1
		  1=uri1
		  2=uri2

		  [Notebook 1]
		  name=Foo
		  uri=uri1

		Then followed by more "[Notebook]" sections that are cache data

		@param text: a string or a list of lines
		'''
		# Format <= 0.60 was:
		#
		#  [NotebookList]
		#  Default=uri1
		#  uri1
		#  uri2
		#
		#  [Notebook]
		#  name=Foo
		#  uri=uri1


		if isinstance(text, basestring):
			text = text.splitlines(True)

		assert text[0].strip() == '[NotebookList]'

		# Backward compatibility, make valid INI file:
		# - make redundant [Notebook] sections numbered
		# - prefix lines without a key with a number
		n = 0
		l = 0
		for i, line in enumerate(text):
			if line.strip() == '[Notebook]':
				n += 1
				text[i] = '[Notebook %i]\n' % n
			elif line and not line.isspace()  \
			and not line.lstrip().startswith('[') \
			and not line.lstrip().startswith('#') \
			and not '=' in line:
				l += 1
				text[i] = ('%i=' % l) + line
		###

		from zim.config import String
		config = INIConfigFile(VirtualFile(text))

		mylist = config['NotebookList']
		mylist.define(Default=String(None))
		mylist.define((k, String(None)) for k in mylist._input.keys()) # XXX

		for key, uri in config['NotebookList'].items():
			if key == 'Default':
				continue

			section = config['Notebook %s' % key]
			section.define(
				uri=String(None),
				name=String(None),
				icon=String(None),
				mtime=String(None),
				interwiki=String(None)
			)
			if section['uri'] == uri:
				info = NotebookInfo(**section)
			else:
				info = NotebookInfo(uri)
			self.append(info)

		if 'Default' in config['NotebookList'] \
		and config['NotebookList']['Default']:
			self.set_default(config['NotebookList']['Default'])

	def parse_old_format(self, text):
		'''Parses the config and cache and populates the list

		Method for backward compatibility with list format with no
		section headers and a whitespace separator between notebook
		name and uri.

		@param text: a string or a list of lines
		'''
		# Old format is name, value pair, separated by whitespace
		# with all other whitespace escaped by a \
		# Default was _default_ which could refer a notebook name.
		if isinstance(text, basestring):
			text = text.splitlines(True)

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
			default = self.default.user_path or self.default.uri
		else:
			default = None

		lines = [
			'[NotebookList]\n',
			'Default=%s\n' % (default or '')
		]
		for i, info in enumerate(self):
			n = i+1
			uri = info.user_path or info.uri
			lines.append('%i=%s\n' % (n, uri))

		for i, info in enumerate(self):
			n = i+1
			uri = info.user_path or info.uri
			lines.extend([
				'\n',
				'[Notebook %i]\n' % n,
				'uri=%s\n' % uri,
				'name=%s\n' % info.name,
				'interwiki=%s\n' % info.interwiki,
				'icon=%s\n' % info.icon_path,
			])

		self.file.writelines(lines)

	def update(self):
		'''Update L{NotebookInfo} objects and write cache'''
		changed = False
		for info in self:
			changed = info.update() or changed
		if changed:
			self.write()

	def set_default(self, uri):
		'''Set the default notebook
		@param uri: the file uri or file path for the default notebook
		'''
		uri = File(uri).uri # e.g. "~/foo" to file:// uri
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

		Names are checked case sensitive first, then case-insensitive

		@param name: notebook name as string
		@returns: a L{NotebookInfo} object or C{None}
		'''
		for info in self:
			if info.name == name:
				return info

		lname = name.lower()
		for info in self:
			if info.name.lower() == lname:
				return info

		return None

	def get_interwiki(self, key):
		'''Get the L{NotebookInfo} object for a notebook by interwiki key

		First checks the interwiki key for all notebooks (case insensitive)
		than falls back to L{get_by_name()}.

		@param key: notebook name or interwiki key as string
		@returns: a L{NotebookInfo} object or C{None}
		'''
		lkey = key.lower()
		for info in self:
			if info.interwiki and info.interwiki.lower() == lkey:
				return info
		else:
			return self.get_by_name(key)


def get_notebook_list():
	'''Returns a list of known notebooks as a L{NotebookInfoList}

	This will load the list from the default X{notebooks.list} file
	'''
	config = ConfigManager() # XXX should be passed in
	file = config.get_config_file('notebooks.list')
	return NotebookInfoList(file)


def resolve_notebook(string):
	'''Takes either a notebook name or a file or dir path. For a name
	it resolves the path by looking for a notebook of that name in the
	notebook list.
	Note that the L{NotebookInfo} for an file path is not using any
	actual info from the notebook, it just passes on the uri. Use
	L{build_notebook()} to split the URI in a notebook location and
	an optional page path.
	@returns: a L{NotebookInfo} or C{None}
	'''
	assert isinstance(string, basestring)

	if '/' in string or os.path.sep in string:
		# FIXME do we need a isfilepath() function in fs.py ?
		return NotebookInfo(string)
	else:
		nblist = get_notebook_list()
		return nblist.get_by_name(string)


def _get_path_object(path):
	if isinstance(path, basestring):
		file = File(path)
		if file.exists(): # exists and is a file
			path = file
		else:
			path = Dir(path)
	else:
		assert isinstance(path, (File, Dir))
	return path


def get_notebook_info(path):
	'''Look up the notebook info for either a uri,
	or a File or a Dir object.
	@param path: path as string, L{File} or L{Dir} object
	@returns: L{NotebookInfo} object, or C{None} if no notebook config
	was found
	'''
	path = _get_path_object(path)
	info = NotebookInfo(path.uri)
	if info.update():
		return info
	else:
		return None


def build_notebook(location, notebookclass=None):
	'''Create a L{Notebook} object for a file location
	Tries to automount file locations first if needed
	@param location: a L{FilePath} or a L{NotebookInfo}
	@param notebookclass: class to instantiate, used for testing
	@returns: a L{Notebook} object and a L{Path} object or C{None}
	@raises FileNotFoundError: if file location does not exist and could not be mounted
	'''
	uri = location.uri
	page = None

	# Decipher zim+file:// uris
	if uri.startswith('zim+file://'):
		uri = uri[4:]
		if '?' in uri:
			uri, page = uri.split('?', 1)
			page = url_decode(page)
			page = Path(page)

	# Automount if needed
	filepath = FilePath(uri)
	if not filepath.exists():
		mount_notebook(filepath)
		if not filepath.exists():
			raise FileNotFoundError(filepath)

	# Figure out the notebook dir
	if filepath.isdir():
		dir = Dir(uri)
		file = None
	else:
		file = File(uri)
		dir = file.dir

	if file and file.basename == 'notebook.zim':
		file = None
	else:
		parents = list(dir)
		parents.reverse()
		for parent in parents:
			if parent.file('notebook.zim').exists():
				dir = parent
				break

	# Resolve the page for a file
	if file:
		path = file.relpath(dir)
		if '.' in path:
			path, _ = path.rsplit('.', 1) # remove extension
		path = path.replace('/', ':')
		page = Path(path)

	# And finally create the notebook
	if notebookclass is None:
		notebookclass = Notebook
	notebook = notebookclass(dir=dir)

	return notebook, page


def mount_notebook(filepath):
	from zim.config import String

	config = ConfigManager() # XXX should be passed in
	configdict = config.get_config_dict('automount.conf')

	groups = [k for k in configdict.keys() if k.startswith('Path')]
	groups.sort() # make order predictable for nested paths
	for group in groups:
		path = group[4:].strip() # len('Path') = 4
		dir = Dir(path)
		if filepath.path == dir.path or filepath.ischild(dir):
			configdict[group].define(mount=String(None))
			handler = ApplicationMountPointHandler(dir, **configdict[group])
			if handler(filepath):
				break


class ApplicationMountPointHandler(object):
	# TODO add password prompt logic, provide to cmd as argument, stdin

	def __init__(self, dir, mount, **a):
		self.dir = dir
		self.mount = mount

	def __call__(self, path):
		if path.path == self.dir.path or path.ischild(self.dir) \
		and not self.dir.exists() \
		and self.mount:
			from zim.applications import Application
			Application(self.mount).run()
			return path.exists()
		else:
			return False


def init_notebook(path, name=None):
	'''Initialize a new notebook in a directory'''
	assert isinstance(path, Dir)
	path.touch()
	config = NotebookConfig(path.file('notebook.zim'))
	config['Notebook']['name'] = name or path.basename
	config.write()


def interwiki_link(link):
	'''Convert an interwiki link into an url'''
	assert isinstance(link, basestring) and '?' in link
	key, page = link.split('?', 1)
	lkey = key.lower()

	# First check known notebooks
	list = get_notebook_list()
	info = list.get_interwiki(key)
	if info:
		url = 'zim+' + info.uri + '?{NAME}'

	# Then search all "urls.list" in config and data dirs
	else:
		url = None
		files = XDGConfigFileIter('urls.list') # FIXME, shouldn't this be passed in ?
		for file in files:
			for line in file.readlines():
				if line.startswith('#') or line.isspace():
					continue
				try:
					mykey, myurl = line.split(None, 1)
				except ValueError:
					continue
				if mykey.lower() == lkey:
					url = myurl.strip()
					break

			if url is not None:
				break

	# Format URL
	if url:
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
	'''Error for an invalid page name'''

	description = _('''\
The given page name is not valid.
''') # T: error description
	# TODO add to explanation what are valid characters

	def __init__(self, name):
		self.msg = _('Invalid page name "%s"') % name # T: error message


class LookupError(Error):
	'''Error for failing to resolving a path'''

	description = '''\
Failed to lookup this page in the notebook storage.
This is likely a glitch in the application.
'''

class IndexBusyError(Error):
	'''Error for operations that need the index when the index is not
	yet updated.'''

	description = _('''\
Index is still busy updating while we try to do an
operation that needs the index.
''') # T: error message


class PageExistsError(Error):
	'''Error for trying to create a page which already exists'''
	pass

	# TODO verbose description


class PageReadOnlyError(Error):
	'''Error when trying to modify a read-only page'''
	# TODO verbose description

	def __init__(self, page):
		self.msg = _('Can not modify page: %s') % page.name
			# T: error message for read-only pages




from zim.config import String, ConfigDefinitionByClass, Boolean, Choice


class NotebookConfig(INIConfigFile):
	'''Wrapper for the X{notebook.zim} file'''

	# TODO - unify this call with NotebookInfo ?

	def __init__(self, file):
		INIConfigFile.__init__(self, file)
		if os.name == 'nt': endofline = 'dos'
		else: endofline = 'unix'
		self['Notebook'].define((
			('version', String('.'.join(map(str, DATA_FORMAT_VERSION)))),
			('name', String(file.dir.basename)),
			('interwiki', String(None)),
			('home', ConfigDefinitionByClass(Path('Home'))),
			('icon', String(None)), # XXX should be file, but resolves relative
			('document_root', String(None)), # XXX should be dir, but resolves relative
			('shared', Boolean(True)),
			('endofline', Choice(endofline, set(('dos', 'unix')))),
			('disable_trash', Boolean(False)),
			('profile', String(None)),
		))


class Notebook(ConnectorMixin, SignalEmitter):
	'''Main class to access a notebook

	This class defines an API that proxies between backend L{zim.stores}
	and L{Index} objects on the one hand and the user interface on the
	other hand. (See L{module docs<zim.notebook>} for more explanation.)

	@signal: C{store-page (page)}: emitted before actually storing the page
	@signal: C{stored-page (page)}: emitted after storing the page
	@signal: C{move-page (oldpath, newpath, update_links)}: emitted before
	actually moving a page
	@signal: C{moved-page (oldpath, newpath, update_links)}: emitted after
	moving the page
	@signal: C{delete-page (path)}: emitted before deleting a page
	@signal: C{deleted-page (path)}: emitted after deleting a page
	means that the preferences need to be loaded again as well
	@signal: C{properties-changed ()}: emitted when properties changed
	@signal: C{suggest-link (path, text)}: hook that is called when trying
	to resolve links
	@signal: C{new-page-template (path, template)}: emitted before
	evaluating a template for a new page, intended for plugins that want
	to extend page templates

	@note: For store_async() the 'page-stored' signal is emitted
	after scheduling the store, but potentially before it was really
	executed. This may bite when you do direct access to the underlying
	files - however when using the API this should not be visible.

	@ivar name: The name of the notebook (string)
	@ivar icon: The path for the notebook icon (if any)
	# FIXME should be L{File} object
	@ivar document_root: The L{Dir} object for the X{document root} (if any)
	@ivar dir: Optional L{Dir} object for the X{notebook folder}
	@ivar file: Optional L{File} object for the X{notebook file}
	@ivar cache_dir: A L{Dir} object for the folder used to cache notebook state
	@ivar config: A L{SectionedConfigDict} for the notebook config
	(the C{X{notebook.zim}} config file in the notebook folder)
	@ivar lock: An C{threading.Lock} for async notebook operations
	@ivar profile: The name of the profile used by the notebook or C{None}

	In general this lock is not needed when only reading data from
	the notebook. However it should be used when doing operations that
	need a fixed state, e.g. exporting the notebook or when executing
	version control commands on the storage directory.

	@ivar index: The L{Index} object used by the notebook
	'''

	# Signals for store, move and delete are defined double with one
	# emitted before the action and the other after the action run
	# successfully. This is different from the normal connect vs.
	# connect_after strategy. However in exceptions thrown from
	# a signal handler are difficult to handle, so we split the signal
	# in two steps.

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
		'suggest-link': (gobject.SIGNAL_RUN_LAST, None, (object, object)),
		'new-page-template': (gobject.SIGNAL_RUN_LAST, None, (object, object)),
	}
	__hooks__ = ('suggest-link',)

	properties = (
		('name', 'string', _('Name')), # T: label for properties dialog
		('interwiki', 'string', _('Interwiki Keyword'), lambda v: not v or is_interwiki_keyword_re.search(v)), # T: label for properties dialog
		('home', 'page', _('Home Page')), # T: label for properties dialog
		('icon', 'image', _('Icon')), # T: label for properties dialog
		('document_root', 'dir', _('Document Root')), # T: label for properties dialog
		#~ ('profile', 'string', _('Profile'), list_profiles), # T: label for properties dialog
		('profile', 'string', _('Profile')), # T: label for properties dialog
		# 'shared' property is not shown in properties anymore
	)

	def __init__(self, dir=None, file=None, config=None, index=None, store=None):
		assert not (dir and file), 'BUG: can not provide both dir and file '
		self._namespaces = []	# list used to resolve stores
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
		self.lock = threading.Lock()
			# We don't use FS.get_async_lock() at this level. A store
			# backend will automatically trigger this when it calls any
			# async file operations. This one is more abstract for the
			# notebook as a whole, regardless of storage
		self.readonly = True

		if dir:
			assert isinstance(dir, Dir)
			self.dir = dir
			#~ self.readonly = not dir.iswritable()

			# Test access - (iswritable turns out to be unreliable
			# for folders on windows..)
			f = dir.file('.zim/tmp')
			try:
				f.write('Test')
				f.remove()
			except:
				logger.info('Notebook readonly')
				self.readonly = True
			else:
				self.readonly = False

			if self.config is None:
				self.config = NotebookConfig(dir.file('notebook.zim'))

			self.cache_dir = dir.subdir('.zim')
			if self.readonly or self.config['Notebook'].get('shared') \
			or not self.cache_dir.iswritable():
				self.cache_dir = self._cache_dir(dir)
			logger.debug('Cache dir: %s', self.cache_dir)

			# TODO check if config defined root namespace
			if store:
				self.store = store
			else:
				from zim.stores.files import FilesStore
				self.store = FilesStore(dir, self.endofline)
		elif file:
			assert isinstance(file, File)
			self.file = file
			self.readonly = not file.iswritable()
			assert False, 'TODO: support for single file notebooks'
		else:
			assert store, 'Provide a dir or a store'
			self.store = store

		if index is None:
			import zim.index # XXX circular import
			self.index = zim.index.Index.new_from_file(
				self.cache_dir.file('index.db'),
				self.store
			)
		else:
			self.index = index

		from zim.index import PagesView, LinksView, TagsView
		self.pages = PagesView.new_from_index(self.index)
		self.links = LinksView.new_from_index(self.index)
		self.tags = TagsView.new_from_index(self.index)

		def on_page_updated(index, indexpath):
			## FIXME still not called for parent pages -- need refactor
			## of index to deal with this properly I'm afraid...
			#~ print "UPDATED", indexpath
			if indexpath.name in self._page_cache:
				#~ print "  --> IN CAHCE"
				self._page_cache[indexpath.name].haschildren = indexpath.haschildren

		self.index.connect('page-added', on_page_updated)
		self.index.connect('page-changed', on_page_updated)

		if self.config is None:
			from zim.config import VirtualConfigBackend
			### XXX - Big HACK here - Get better classes for this - XXX ###
			dir = VirtualConfigBackend()
			file = dir.file('notebook.zim')
			file.dir = dir
			file.dir.basename = 'Unnamed Notebook'
			###
			self.config = NotebookConfig(file)
		else:
			if self.needs_upgrade:
				logger.warn('This notebook needs to be upgraded to the latest data format')

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
		'''The 'endofline' property for this notebook

		This property can be one of 'unix' or 'dos'. Typically this
		property reflects the platform on which the notebook was created.

		For page files etc. this convention should be used when writing
		the file. This way a notebook can be edited from different
		platforms and we avoid showing the whole file as changed after
		every edit. (Especially important when a notebook is under
		version control.)
		'''
		return self.config['Notebook']['endofline']

	@property
	def info(self):
		'''The L{NotebookInfo} object for this notebook'''
		try:
			uri = self.uri
		except AssertionError:
			uri = None

		return NotebookInfo(uri, **self.config['Notebook'])

	@property
	def profile(self):
		'''The 'profile' property for this notebook'''
		return self.config['Notebook'].get('profile') or None # avoid returning ''

	def _cache_dir(self, dir):
		from zim.config import XDG_CACHE_HOME
		if os.name == 'nt':
			path = 'notebook-' + dir.path.replace('\\', '_').replace(':', '').strip('_')
		else:
			path = 'notebook-' + dir.path.replace('/', '_').strip('_')
		return XDG_CACHE_HOME.subdir(('zim', path))

	def save_properties(self, **properties):
		'''Save a set of properties in the notebook config

		This method does an C{update()} on the dict with properties but
		also updates the object attributes that map those properties.

		@param properties: the properties to update

		@emits: properties-changed
		'''
		# Check if icon is relative
		icon = properties.get('icon')
		if icon and not isinstance(icon, basestring):
			assert isinstance(icon, File)
			if self.dir and icon.ischild(self.dir):
				properties['icon'] = './' + icon.relpath(self.dir)
			else:
				properties['icon'] = icon.user_path or icon.path

		# Check document root is relative
		root = properties.get('document_root')
		if root and not isinstance(root, basestring):
			assert isinstance(root, Dir)
			if self.dir and root.ischild(self.dir):
				properties['document_root'] = './' + root.relpath(self.dir)
			else:
				properties['document_root'] = root.user_path or root.path

		# Set home page as string
		if 'home' in properties and isinstance(properties['home'], Path):
			properties['home'] = properties['home'].name

		# Actual update and signals
		# ( write is the last action - in case update triggers a crash
		#   we don't want to get stuck with a bad config )
		self.config['Notebook'].update(properties)
		self.emit('properties-changed')

		if hasattr(self.config, 'write'): # Check needed for tests
			self.config.write()

	def do_properties_changed(self):
		config = self.config['Notebook']

		self.name = config['name']
		icon, document_root = _resolve_relative_config(self.dir, config)
		if icon:
			self.icon = icon.path # FIXME rewrite to use File object
		else:
			self.icon = None
		self.document_root = document_root

		# TODO - can we switch cache_dir on run time when 'shared' changed ?

	def relative_link(self, source, href):
		'''Returns a relative links for a page link

		More or less the opposite of resolve_link().

		@param source: L{Path} for the referring page
		@param href: L{Path} for the linked page
		@returns: a link for href, either relative to 'source' or an
		absolute link
		'''
		if href == source: # page linking to itself
			return href.basename
		elif href.ischild(source): # link to a child or grand child
			return '+' + href.relname(source)
		else:
			parent = source.commonparent(href)
			if parent.isroot: # no common parent except for root
				if href.parts[0].lower() in [p.lower() for p in source.parts]:
					# there is a conflicting anchor name in path
					return ':' + href.name
				else:
					return href.name
			elif parent == href: # link to an parent or grand parent
				return href.basename
			elif parent == source.parent: # link to sibling of same parent
				return href.relname(parent)
			else:
				return parent.basename + ':' + href.relname(parent)

	def suggest_link(self, source, word):
		'''Suggest a link Path for 'word' or return None if no suggestion is
		found. By default we do not do any suggestion but plugins can
		register handlers to add suggestions using the 'C{suggest-link}'
		signal.
		'''
		return self.emit('suggest-link', source, word)

	def get_page(self, path):
		'''Get a L{Page} object for a given path

		This method requests the page object from the store object and
		hashes it in a weakref dictionary to ensure that an unique
		object is being used for each page.

		Typically a Page object will be returned even when the page
		does not exist. In this case the C{hascontent} attribute of
		the Page will be C{False} and C{get_parsetree()} will return
		C{None}. This means that you do not have to create a page
		explicitly, just get the Page object and store it with new
		content (if it is not read-only of course).

		However in some cases this method will return C{None}. This
		means that not only does the page not exist, but also that it
		can not be created. This should only occur for certain special
		pages and depends on the store implementation.

		@param path: a L{Path} object
		@returns: a L{Page} object or C{None}
		'''
		# As a special case, using an invalid page as the argument should
		# return a valid page object.
		from zim.index import IndexNotFoundError # FIXME
		assert isinstance(path, Path)
		if path.name in self._page_cache \
		and self._page_cache[path.name].valid:
			return self._page_cache[path.name]
		else:
			page = self.store.get_page(path)
			try:
				indexpath = self.pages.lookup_by_pagename(path)
			except IndexNotFoundError:
				pass
				# TODO trigger indexer here if page exists !
			else:
				if indexpath and indexpath.haschildren:
					page.haschildren = True
				# page might be the parent of a placeholder, in that case
				# the index knows it has children, but the store does not

			# TODO - set haschildren if page maps to a store namespace
			self._page_cache[path.name] = page
			return page

	def get_new_page(self, path):
		'''Like get_page() but guarantees the page does not yet exist
		by adding a number to the name to make it unique.

		This method is intended for cases where e.g. a automatic script
		wants to store a new page without user interaction. Conflicts
		are resolved automatically by appending a number to the name
		if the page already exists. Be aware that the resulting Page
		object may not match the given Path object because of this.

		@param path: a L{Path} object
		@returns: a L{Page} object
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
		'''Flush the cache used by L{get_page()}

		After this method calling L{get_page()} for C{path} or any of
		its children will return a fresh page object. Be aware that the
		old Page objects may still be around but will be flagged as
		invalid and can no longer be used in the API.

		@param path: a L{Path} object
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
		'''Returns a L{Page} object for the home page'''
		return self.get_page(self.config['Notebook']['home'])

	def store_page(self, page):
		'''Save the data from the page in the storage backend

		@param page: a L{Page} object
		@emits: store-page before storing the page
		@emits: stored-page on success
		'''
		assert page.valid, 'BUG: page object no longer valid'
		self.emit('store-page', page)
		self.store.store_page(page)
		self.emit('stored-page', page)

	def store_page_async(self, page):
		'''Save the data from a page in the storage backend
		asynchronously

		Like L{store_page()} but asynchronous, so the method returns
		as soon as possible without waiting for success. Falls back to
		L{store_page()} when the backend does not support asynchronous
		operations.

		@param page: a L{Page} object
		@returns: A L{FunctionThread} for the background job or C{None}
		if save was performed in the foreground
		@emits: store-page before storing the page
		@emits: stored-page on success
		'''
		assert page.valid, 'BUG: page object no longer valid'
		self.emit('store-page', page)
		func = self.store.store_page_async(page)
		try:
			self.emit('stored-page', page)
				# FIXME - stored-page is emitted early, but emitting from
				# the thread is also not perfect, since the page may have
				# changed already in the gui
				# (we tried this and it broke autosave for some users!)
		finally:
			return func

	def delete_page(self, path):
		# TODO integrate operation with update links again
		self.store.delete_page(path)
		self.index.on_delete_page(path)

	def revert_page(self, page):
		'''Reload the page from the storage backend, discarding all
		changes

		This method changes the state of a Page object to revert all
		changes compared to the data in the store. For a file based
		store this can mean for example re-reading the file and putting
		the data into the Page object.

		This is different from just flushing the cache and getting a
		new object with L{get_page()} because the old object remains
		valid - which is important when it is in use in the user
		interface.

		@param page: a L{Page} object
		'''
		assert page.valid, 'BUG: page object no longer valid'
		self.store.revert_page(page)

	def resolve_file(self, filename, path=None):
		'''Resolve a file or directory path relative to a page or
		Notebook

		This method is intended to lookup file links found in pages and
		turn resolve the absolute path of those files.

		File URIs and paths that start with '~/' or '~user/' are
		considered absolute paths. Also windows path names like
		'C:\user' are recognized as absolute paths.

		Paths that starts with a '/' are taken relative to the
		to the I{document root} - this can e.g. be a parent directory
		of the notebook. Defaults to the filesystem root when no document
		root is set. (So can be relative or absolute depending on the
		notebook settings.)

		Paths starting with any other character are considered
		attachments. If C{path} is given they are resolved relative to
		the I{attachment folder} of that page, otherwise they are
		resolved relative to the I{notebook folder} - if any.

		The file is resolved purely based on the path, it does not have
		to exist at all.

		@param filename: the (relative) file path or uri as string
		@param path: a L{Path} object for the page
		@returns: a L{File} object.
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
				# make absolute on Unix
			return File(filename)
		else:
			if path:
				dir = self.get_attachments_dir(path)
			else:
				assert self.dir, 'Can not resolve relative path for notebook without root folder'
				dir = self.dir

			return File((dir, filename))

	def relative_filepath(self, file, path=None):
		'''Get a file path relative to the notebook or page

		Intended as the counter part of L{resolve_file()}. Typically
		this function is used to present the user with readable paths or to
		shorten the paths inserted in the wiki code. It is advised to
		use file URIs for links that can not be made relative with
		this method.

		The link can be relative:
		  - to the I{document root} (link will start with "/")
		  - the attachments dir (if a C{path} is given) or the notebook
		    (links starting with "./" or "../")
		  - or the users home dir (link like "~/user/")

		Relative file paths are always given with Unix path semantics
		(so "/" even on windows). But a leading "/" does not mean the
		path is absolute, but rather that it is relative to the
		X{document root}.

		@param file: L{File} object we want to link
		@keyword path: L{Path} object for the page where we want to
		link this file

		@returns: relative file path as string, or C{None} when no
		relative path was found
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

		# Finally check HOME or give up
		return file.user_path or None

	def get_attachments_dir(self, path):
		'''Get the X{attachment folder} for a specific page

		@param path: a L{Path} object
		@returns: a L{Dir} object or C{None}

		Always returns a Dir object when the page can have an attachment
		folder, even when the folder does not (yet) exist. However when
		C{None} is returned the store implementation does not support
		an attachments folder for this page.
		'''
		return self.store.get_attachments_dir(path)

	def get_template(self, path):
		'''Get a template for the intial text on new pages
		@param path: a L{Path} object
		@returns: a L{ParseTree} object
		'''
		# FIXME hardcoded that template must be wiki format

		template = self.namespace_properties[path]['template']
		logger.debug('Found template \'%s\' for %s', template, path)
		template = zim.templates.get_template('wiki', template)
		return self.eval_new_page_template(path, template)

	def eval_new_page_template(self, path, template):
		lines = []
		context = {
			'page': {
				'name': path.name,
				'basename': path.basename,
				'section': path.namespace,
				'namespace': path.namespace, # backward compat
			}
		}
		self.emit('new-page-template', path, template) # plugin hook
		template.process(lines, context)

		parser = zim.formats.get_parser('wiki')
		return parser.parse(lines)

	@property
	def needs_upgrade(self):
		'''Checks if the notebook is uptodate with the current zim version'''
		try:
			version = str(self.config['Notebook']['version'])
			version = tuple(version.split('.'))
			return version < DATA_FORMAT_VERSION
		except KeyError:
			return True


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
			import zim.formats
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
		import zim.formats
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


class Link(object):
	'''Class used to represent links between two pages

	@ivar source: L{Path} object for the source of the link
	@ivar href: L{Path} object for the target of the link
	@ivar type: link type (not used at this moment - always None)
	'''

	__slots__ = ('source', 'href', 'type')

	def __init__(self, source, href, type=None):
		self.source = source
		self.href = href
		self.type = type

	def __repr__(self):
		return '<%s: %s to %s (%s)>' % (self.__class__.__name__, self.source, self.href, self.type)
