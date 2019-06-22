
# Copyright 2008-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>




import os
import re
import weakref
import logging
import threading

logger = logging.getLogger('zim.notebook')

from functools import partial

import zim.templates
import zim.formats

from zim.fs import File, Dir, SEP
from zim.newfs import LocalFolder
from zim.config import INIConfigFile, String, ConfigDefinitionByClass, Boolean, Choice
from zim.errors import Error
from zim.utils import natural_sort_key
from zim.newfs.helpers import TrashNotSupportedError
from zim.config import HierarchicDict
from zim.parsing import link_type, is_win32_path_re
from zim.signals import ConnectorMixin, SignalEmitter, SIGNAL_NORMAL

from .operations import notebook_state, NOOP, SimpleAsyncOperation, ongoing_operation
from .page import Path, Page, HRef, HREF_REL_ABSOLUTE, HREF_REL_FLOATING, HREF_REL_RELATIVE
from .index import IndexNotFoundError, LINK_DIR_BACKWARD

DATA_FORMAT_VERSION = (0, 4)


class NotebookConfig(INIConfigFile):
	'''Wrapper for the X{notebook.zim} file'''

	# TODO - unify this call with NotebookInfo ?

	def __init__(self, file):
		INIConfigFile.__init__(self, file)
		if os.name == 'nt':
			endofline = 'dos'
		else:
			endofline = 'unix'
		name = file.dir.basename if hasattr(file, 'dir') else file.parent().basename # HACK zim.fs and zim.newfs compat
		self['Notebook'].define((
			('version', String('.'.join(map(str, DATA_FORMAT_VERSION)))),
			('name', String(name)),
			('interwiki', String(None)),
			('home', ConfigDefinitionByClass(Path('Home'))),
			('icon', String(None)), # XXX should be file, but resolves relative
			('document_root', String(None)), # XXX should be dir, but resolves relative
			('shared', Boolean(True)),
			('endofline', Choice(endofline, {'dos', 'unix'})),
			('disable_trash', Boolean(False)),
		))


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


def _iswritable(dir):
	if os.name == 'nt':
		# Test access - (iswritable turns out to be unreliable
		# for folders on windows..)
		f = dir.file('.zim.tmp')
		try:
			f.write('Test')
			f.remove(cleanup=False)
		except:
			return False
		else:
			return True
	else:
		return dir.iswritable()


def _cache_dir_for_dir(dir):
	# Consider using md5 for path name here, like thumbnail spec
	from zim.config import XDG_CACHE_HOME

	if os.name == 'nt':
		path = 'notebook-' + dir.path.replace('\\', '_').replace(':', '').strip('_')
	else:
		path = 'notebook-' + dir.path.replace('/', '_').strip('_')

	return XDG_CACHE_HOME.subdir(('zim', path))


class PageError(Error):

	def __init__(self, path):
		self.path = path
		self.msg = self._msg % path.name


class PageNotFoundError(PageError):
	_msg = _('No such page: %s') # T: message for PageNotFoundError


class PageNotAllowedError(PageNotFoundError):
	_msg = _('Page not allowed: %s') # T: message for PageNotAllowedError
	description = _('This page name cannot be used due to technical limitations of the storage')
			# T: description for PageNotAllowedError


class PageExistsError(Error):
	_msg = _('Page already exists: %s') # T: message for PageExistsError


class PageReadOnlyError(Error):
	_msg = _('Can not modify page: %s') # T: error message for read-only pages


class IndexNotUptodateError(Error):
	pass # TODO description here?


def assert_index_uptodate(method):
	def wrapper(notebook, *arg, **kwarg):
		if not notebook.index.is_uptodate:
			raise IndexNotUptodateError('Index not up to date')
		return method(notebook, *arg, **kwarg)

	return wrapper


_NOTEBOOK_CACHE = weakref.WeakValueDictionary()


from zim.plugins import ExtensionBase, extendable

class NotebookExtension(ExtensionBase):
	'''Base class for extending the notebook

	@ivar notebook: the L{Notebook} object
	'''

	def __init__(self, plugin, notebook):
		ExtensionBase.__init__(self, plugin, notebook)
		self.notebook = notebook


@extendable(NotebookExtension)
class Notebook(ConnectorMixin, SignalEmitter):
	'''Main class to access a notebook

	This class defines an API that proxies between backend L{zim.stores}
	and L{Index} objects on the one hand and the user interface on the
	other hand. (See L{module docs<zim.notebook>} for more explanation.)

	@signal: C{store-page (page)}: emitted before actually storing the page
	@signal: C{stored-page (page)}: emitted after storing the page
	@signal: C{move-page (oldpath, newpath)}: emitted before
	actually moving a page
	@signal: C{moved-page (oldpath, newpath)}: emitted after
	moving the page
	@signal: C{delete-page (path)}: emitted before deleting a page
	@signal: C{deleted-page (path)}: emitted after deleting a page
	means that the preferences need to be loaded again as well
	@signal: C{suggest-link (path, text)}: hook that is called when trying
	to resolve links
	@signal: C{get-page-template (path)}: emitted before
	when a template for a new page is requested, intended for plugins that
	want to customize a namespace
	@signal: C{init-page-template (path, template)}: emitted before
	evaluating a template for a new page, intended for plugins that want
	to extend page templates

	@ivar name: The name of the notebook (string)
	@ivar icon: The path for the notebook icon (if any)
	# FIXME should be L{File} object
	@ivar document_root: The L{Dir} object for the X{document root} (if any)
	@ivar dir: Optional L{Dir} object for the X{notebook folder}
	@ivar file: Optional L{File} object for the X{notebook file}
	@ivar cache_dir: A L{Dir} object for the folder used to cache notebook state
	@ivar config: A L{SectionedConfigDict} for the notebook config
	(the C{X{notebook.zim}} config file in the notebook folder)
	@ivar index: The L{Index} object used by the notebook
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__signals__ = {
		'store-page': (SIGNAL_NORMAL, None, (object,)),
		'stored-page': (SIGNAL_NORMAL, None, (object,)),
		'move-page': (SIGNAL_NORMAL, None, (object, object)),
		'moved-page': (SIGNAL_NORMAL, None, (object, object)),
		'delete-page': (SIGNAL_NORMAL, None, (object,)),
		'deleted-page': (SIGNAL_NORMAL, None, (object,)),
		'page-info-changed': (SIGNAL_NORMAL, None, (object,)),
		'get-page-template': (SIGNAL_NORMAL, str, (object,)),
		'init-page-template': (SIGNAL_NORMAL, None, (object, object)),

		# Hooks
		'suggest-link': (SIGNAL_NORMAL, object, (object, object)),
	}

	@classmethod
	def new_from_dir(klass, dir):
		'''Constructor to create a notebook based on a specific
		file system location.
		Since the file system is an external resource, this method
		will return unique objects per location and keep (weak)
		references for re-use.

		@param dir: a L{Dir} object
		@returns: a L{Notebook} object
		'''
		assert isinstance(dir, Dir)

		nb = _NOTEBOOK_CACHE.get(dir.uri)
		if nb:
			return nb

		from .index import Index
		from .layout import FilesLayout

		config = NotebookConfig(dir.file('notebook.zim'))
		endofline = config['Notebook']['endofline']
		shared = config['Notebook']['shared']

		subdir = dir.subdir('.zim')
		if not shared and subdir.exists() and _iswritable(subdir):
			cache_dir = subdir
		else:
			cache_dir = _cache_dir_for_dir(dir)

		folder = LocalFolder(dir.path)
		layout = FilesLayout(folder, endofline)
		cache_dir.touch() # must exist for index to work
		index = Index(cache_dir.file('index.db').path, layout)

		nb = klass(cache_dir, config, folder, layout, index)
		_NOTEBOOK_CACHE[dir.uri] = nb
		return nb

	def __init__(self, cache_dir, config, folder, layout, index):
		'''Constructor
		@param cache_dir: a L{Folder} object used for caching the notebook state
		@param config: a L{NotebookConfig} object
		@param folder: a L{Folder} object for the notebook location
		@param layout: a L{NotebookLayout} object
		@param index: an L{Index} object
		'''
		self.folder = folder
		self.cache_dir = cache_dir
		self.state = INIConfigFile(cache_dir.file('state.conf'))
		self.config = config
		self.properties = config['Notebook']
		self.layout = layout
		self.index = index
		self._operation_check = NOOP

		self.readonly = not _iswritable(folder)

		if self.readonly:
			logger.info('Notebook read-only: %s', folder.path)

		self._page_cache = weakref.WeakValueDictionary()

		self.name = None
		self.icon = None
		self.document_root = None

		if folder.watcher is None:
			from zim.newfs.helpers import FileTreeWatcher
			folder.watcher = FileTreeWatcher()

		from .index import PagesView, LinksView, TagsView
		self.pages = PagesView.new_from_index(self.index)
		self.links = LinksView.new_from_index(self.index)
		self.tags = TagsView.new_from_index(self.index)

		def on_page_row_changed(o, row, oldrow):
			if row['name'] in self._page_cache:
				self._page_cache[row['name']].haschildren = row['n_children'] > 0
				self.emit('page-info-changed', self._page_cache[row['name']])

		def on_page_row_deleted(o, row):
			if row['name'] in self._page_cache:
				self._page_cache[row['name']].haschildren = False
				self.emit('page-info-changed', self._page_cache[row['name']])

		self.index.update_iter.pages.connect('page-row-changed', on_page_row_changed)
		self.index.update_iter.pages.connect('page-row-deleted', on_page_row_deleted)

		self.connectto(self.properties, 'changed', self.on_properties_changed)
		self.on_properties_changed(self.properties)

	@property
	def uri(self):
		'''Returns a file:// uri for this notebook that can be opened by zim'''
		return self.layout.root.uri

	@property
	def info(self):
		'''The L{NotebookInfo} object for this notebook'''
		try:
			uri = self.uri
		except AssertionError:
			uri = None

		return NotebookInfo(uri, **self.config['Notebook'])

	@notebook_state
	def save_properties(self, **properties):
		'''Save a set of properties in the notebook config

		This method does an C{update()} on the dict with properties but
		also updates the object attributes that map those properties.

		@param properties: the properties to update
		'''
		dir = Dir(self.layout.root.path) # XXX

		# Check if icon is relative
		icon = properties.get('icon')
		if icon and not isinstance(icon, str):
			assert isinstance(icon, File)
			if icon.ischild(dir):
				properties['icon'] = './' + icon.relpath(dir)
			else:
				properties['icon'] = icon.user_path or icon.path

		# Check document root is relative
		root = properties.get('document_root')
		if root and not isinstance(root, str):
			assert isinstance(root, Dir)
			if root.ischild(dir):
				properties['document_root'] = './' + root.relpath(dir)
			else:
				properties['document_root'] = root.user_path or root.path

		# Set home page as string
		if 'home' in properties and isinstance(properties['home'], Path):
			properties['home'] = properties['home'].name

		# Actual update and signals
		# ( write is the last action - in case update triggers a crash
		#   we don't want to get stuck with a bad config )
		self.properties.update(properties)
		if hasattr(self.config, 'write'): # XXX Check needed for tests
			self.config.write()

	def on_properties_changed(self, properties):
		dir = Dir(self.layout.root.path) # XXX

		self.name = properties['name']
		icon, document_root = _resolve_relative_config(dir, properties)
		if icon:
			self.icon = icon.path # FIXME rewrite to use File object
		else:
			self.icon = None
		self.document_root = document_root

	def suggest_link(self, source, word):
		'''Suggest a link Path for 'word' or return None if no suggestion is
		found. By default we do not do any suggestion but plugins can
		register handlers to add suggestions using the 'C{suggest-link}'
		signal.
		'''
		return self.emit_return_first('suggest-link', source, word)

	def get_page(self, path):
		'''Get a L{Page} object for a given path

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
		assert isinstance(path, Path)
		if path.name in self._page_cache \
		and self._page_cache[path.name].valid:
			page = self._page_cache[path.name]
			assert isinstance(page, Page)
			page._check_source_etag()
			return page
		else:
			file, folder = self.layout.map_page(path)
			folder = self.layout.get_attachments_folder(path)
			page = Page(path, False, file, folder)
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

	@notebook_state
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
		names.extend(k for k in list(self._page_cache.keys()) if k.startswith(ns))
		for name in names:
			if name in self._page_cache:
				page = self._page_cache[name]
				assert not page.modified, 'BUG: Flushing page with unsaved changes'
				page.valid = False
				del self._page_cache[name]

	def get_home_page(self):
		'''Returns a L{Page} object for the home page'''
		return self.get_page(self.config['Notebook']['home'])

	@notebook_state
	def store_page(self, page):
		'''Save the data from the page in the storage backend

		@param page: a L{Page} object
		@emits: store-page before storing the page
		@emits: stored-page on success
		'''
		assert page.valid, 'BUG: page object no longer valid'
		logger.debug('Store page: %s', page)
		self.emit('store-page', page)
		page._store()
		file, folder = self.layout.map_page(page)
		self.index.update_file(file)
		page.modified = False
		self.emit('stored-page', page)

	@notebook_state
	def store_page_async(self, page, parsetree):
		assert page.valid, 'BUG: page object no longer valid'
		logger.debug('Store page in background: %s', page)
		self.emit('store-page', page)
		error = threading.Event()
		thread = threading.Thread(
			target=partial(self._store_page_async_thread_main, page, parsetree, error)
		)
		thread.start()
		pre_modified = page.modified
		op = SimpleAsyncOperation(
			notebook=self,
			message='Store page in progress',
			thread=thread,
			post_handler=partial(self._store_page_async_finished, page, error, pre_modified)
		)
		op.error_event = error
		op.run_on_idle()
		return op

	def _store_page_async_thread_main(self, page, parsetree, error):
		try:
			page._store_tree(parsetree)
		except:
			error.set()
			logger.exception('Error in background save')

	def _store_page_async_finished(self, page, error, pre_modified):
		if not error.is_set():
			file, folder = self.layout.map_page(page)
			self.index.update_file(file)
			if page.modified == pre_modified:
				# HACK: Checking modified state protects against race condition
				# in async store. Works because pageview sets "page.modified"
				# to a counter rather than a boolean
				page.modified = False
				self.emit('stored-page', page)

	def wait_for_store_page_async(self):
		op = ongoing_operation(self)
		if isinstance(op, SimpleAsyncOperation):
			op()

	def move_page(self, path, newpath, update_links=True):
		'''Move a page in the notebook

		@param path: a L{Path} object for the old/current page name
		@param newpath: a L{Path} object for the new page name
		@param update_links: if C{True} all links B{from} and B{to} this
		page and any of it's children will be updated to reflect the
		new page name

		The original page C{path} does not have to exist, in this case
		only the link update will done. This is useful to update links
		for a placeholder.

		Where:
		  - C{page} is the L{Page} object for the page being updated
		  - C{total} is an optional parameter for the number of pages
		    still to go - if known

		@raises PageExistsError: if C{newpath} already exists

		@emits: move-page before the move
		@emits: moved-page after successfull move
		'''
		for p in self.move_page_iter(path, newpath, update_links):
			pass

	@assert_index_uptodate
	@notebook_state
	def move_page_iter(self, path, newpath, update_links=True):
		'''Like L{move_page()} but yields pages that are being updated
		if C{update_links} is C{True}
		'''
		logger.debug('Move page %s to %s', path, newpath)

		self.emit('move-page', path, newpath)
		try:
			n_links = self.links.n_list_links_section(path, LINK_DIR_BACKWARD)
		except IndexNotFoundError:
			raise PageNotFoundError(path)
		self._move_file_and_folder(path, newpath)
		self.flush_page_cache(path)
		self.emit('moved-page', path, newpath)

		if update_links:
			for p in self._update_links_in_moved_page(path, newpath):
				yield p

			for p in self._update_links_to_moved_page(path, newpath):
				yield p

			new_n_links = self.links.n_list_links_section(newpath, LINK_DIR_BACKWARD)
			if new_n_links != n_links:
				logger.warn('Number of links after move (%i) does not match number before move (%i)', new_n_links, n_links)
			else:
				logger.debug('Number of links after move does match number before move (%i)', new_n_links)

	def _move_file_and_folder(self, path, newpath):
		file, folder = self.layout.map_page(path)
		if not (file.exists() or folder.exists()):
			raise PageNotFoundError(path)

		newfile, newfolder = self.layout.map_page(newpath)
		if file.path.lower() == newfile.path.lower():
			if newfile.isequal(file) or newfolder.isequal(folder):
				pass # renaming on case-insensitive filesystem
			elif newfile.exists() or newfolder.exists():
				raise PageExistsError(newpath)
		elif newfile.exists() or newfolder.exists():
			raise PageExistsError(newpath)

		# First move the dir - if it fails due to some file being locked
		# the whole move is cancelled. Chance is bigger than the other
		# way around, e.g. attachment open in external program.

		changes = []

		if folder.exists():
			if newfolder.ischild(folder):
				# special case where we want to move a page down
				# into it's own namespace
				parent = folder.parent()
				tmp = parent.new_folder(folder.basename)
				folder.moveto(tmp)
				tmp.moveto(newfolder)
			else:
				folder.moveto(newfolder)

			changes.append((folder, newfolder))

			# check if we also moved the file inadvertently
			if file.ischild(folder):
				rel = file.relpath(folder)
				movedfile = newfolder.file(rel)
				if movedfile.exists() and movedfile.path != newfile.path:
						movedfile.moveto(newfile)
						changes.append((movedfile, newfile))
			elif file.exists():
				file.moveto(newfile)
				changes.append((file, newfile))

		elif file.exists():
			file.moveto(newfile)
			changes.append((file, newfile))

		# Process index changes after all fs changes
		# more robust if anything goes wrong in index update
		for old, new in changes:
			self.index.file_moved(old, new)


	def _update_links_in_moved_page(self, oldroot, newroot):
		# Find (floating) links that originate from the moved page
		# check if they would resolve different from the old location
		seen = set()
		for link in list(self.links.list_links_section(newroot)):
			if link.source.name not in seen:
				if link.source == newroot:
					oldpath = oldroot
				else:
					oldpath = oldroot + link.source.relname(newroot)

				yield link.source
				self._update_moved_page(link.source, oldpath, newroot, oldroot)
				seen.add(link.source.name)

	def _update_moved_page(self, path, oldpath, newroot, oldroot):
		logger.debug('Updating links in page moved from %s to %s', oldpath, path)
		page = self.get_page(path)
		tree = page.get_parsetree()
		if not tree:
			return

		def replacefunc(elt):
			text = elt.attrib['href']
			if link_type(text) != 'page':
				raise zim.formats.VisitorSkip

			href = HRef.new_from_wiki_link(text)
			if href.rel == HREF_REL_RELATIVE:
				raise zim.formats.VisitorSkip
			elif href.rel == HREF_REL_ABSOLUTE:
				oldtarget = self.pages.resolve_link(page, href)
				if oldtarget == oldroot:
					return self._update_link_tag(elt, page, newroot, href)
				elif oldtarget.ischild(oldroot):
					newtarget = newroot + oldtarget.relname(oldroot)
					return self._update_link_tag(elt, page, newtarget, href)
				else:
					raise zim.formats.VisitorSkip
			else:
				assert href.rel == HREF_REL_FLOATING
				newtarget = self.pages.resolve_link(page, href)
				oldtarget = self.pages.resolve_link(oldpath, href)

				if oldtarget == oldroot:
					return self._update_link_tag(elt, page, newroot, href)
				elif oldtarget.ischild(oldroot):
					oldanchor = self.pages.resolve_link(oldpath, HRef(HREF_REL_FLOATING, href.parts()[0]))
					if oldanchor.ischild(oldroot):
						raise zim.formats.VisitorSkip # oldtarget cannot be trusted
					else:
						newtarget = newroot + oldtarget.relname(oldroot)
						return self._update_link_tag(elt, page, newtarget, href)
				elif newtarget != oldtarget:
					# Redirect back to old target
					return self._update_link_tag(elt, page, oldtarget, href)
				else:
					raise zim.formats.VisitorSkip

		tree.replace(zim.formats.LINK, replacefunc)
		page.set_parsetree(tree)
		self.store_page(page)

	def _update_links_to_moved_page(self, oldroot, newroot):
		# 1. Check remaining placeholders, update pages causing them
		seen = set()
		try:
			oldroot = self.pages.lookup_by_pagename(oldroot)
		except IndexNotFoundError:
			pass
		else:
			for link in list(self.links.list_links_section(oldroot, LINK_DIR_BACKWARD)):
				if link.source.name not in seen:
					yield link.source
					self._move_links_in_page(link.source, oldroot, newroot)
					seen.add(link.source.name)

		# 2. Check for links that have anchor of same name as the moved page
		# and originate from a (grand)child of the parent of the moved page
		# and no longer resolve to the moved page
		parent = oldroot.parent
		for link in list(self.links.list_floating_links(oldroot.basename)):
			if link.source.name not in seen \
			and link.source.ischild(parent) \
			and not (
				link.target == newroot
				or link.target.ischild(newroot)
			):
				yield link.source
				self._move_links_in_page(link.source, oldroot, newroot)
				seen.add(link.source.name)

	def _move_links_in_page(self, path, oldroot, newroot):
		logger.debug('Updating page %s to move link from %s to %s', path, oldroot, newroot)
		page = self.get_page(path)
		tree = page.get_parsetree()
		if not tree:
			return

		def replacefunc(elt):
			text = elt.attrib['href']
			if link_type(text) != 'page':
				raise zim.formats.VisitorSkip

			href = HRef.new_from_wiki_link(text)
			target = self.pages.resolve_link(page, href)

			if target == oldroot:
				return self._update_link_tag(elt, page, newroot, href)
			elif target.ischild(oldroot):
				newtarget = newroot.child(target.relname(oldroot))
				return self._update_link_tag(elt, page, newtarget, href)

			elif href.rel == HREF_REL_FLOATING \
			and natural_sort_key(href.parts()[0]) == natural_sort_key(oldroot.basename) \
			and page.ischild(oldroot.parent):
				targetrecord = self.pages.lookup_by_pagename(target)
				if not target.ischild(oldroot.parent) \
				or not targetrecord.exists():
					# An link that was anchored to the moved page,
					# but now resolves somewhere higher in the tree
					# Or a link that no longer resolves
					if len(href.parts()) == 1:
						return self._update_link_tag(elt, page, newroot, href)
					else:
						mynewroot = newroot.child(':'.join(href.parts()[1:]))
						return self._update_link_tag(elt, page, mynewroot, href)

			raise zim.formats.VisitorSkip

		tree.replace(zim.formats.LINK, replacefunc)
		page.set_parsetree(tree)
		self.store_page(page)

	def _update_link_tag(self, elt, source, target, oldhref):
		if oldhref.rel == HREF_REL_ABSOLUTE: # prefer to keep absolute links
			newhref = HRef(HREF_REL_ABSOLUTE, target.name)
		else:
			newhref = self.pages.create_link(source, target)

		text = newhref.to_wiki_link()
		if elt.gettext() == elt.get('href'):
			elt[:] = [text]
		elt.set('href', text)
		return elt

	def rename_page(self, path, newbasename, update_heading=True, update_links=True):
		'''Rename page to a page in the same namespace but with a new
		basename.

		This is similar to moving within the same namespace, but
		conceptually different in the user interface. Internally
		L{move_page()} is used here as well.

		@param path: a L{Path} object for the old/current page name
		@param newbasename: new name as string
		@param update_heading: if C{True} the first heading in the
		page will be updated to the new name
		@param update_links: if C{True} all links B{from} and B{to} this
		page and any of it's children will be updated to reflect the
		new page name

		@emits: move-page before the move
		@emits: moved-page after successfull move
		'''
		newbasename = Path.makeValidPageName(newbasename)
		newpath = Path(path.namespace + ':' + newbasename)

		for p in self.rename_page_iter(path, newbasename, update_heading, update_links):
			pass

		return newpath

	@assert_index_uptodate
	@notebook_state
	def rename_page_iter(self, path, newbasename, update_heading=True, update_links=True):
		'''Like L{rename_page()} but yields pages that are being updated
		if C{update_links} is C{True}
		'''
		logger.debug('Rename %s to "%s" (%s, %s)',
			path, newbasename, update_heading, update_links)

		newbasename = Path.makeValidPageName(newbasename)
		newpath = Path(path.namespace + ':' + newbasename)

		for p in self.move_page_iter(path, newpath, update_links):
			yield p

		if update_heading:
			page = self.get_page(newpath)
			tree = page.get_parsetree()
			if not tree is None:
				tree.set_heading(newbasename)
				page.set_parsetree(tree)
				self.store_page(page)

	@assert_index_uptodate
	@notebook_state
	def delete_page(self, path, update_links=True):
		'''Delete a page from the notebook

		@param path: a L{Path} object
		@param update_links: if C{True} pages linking to the
		deleted page will be updated and the link are removed.

		@returns: C{True} when the page existed and was deleted,
		C{False} when the page did not exist in the first place.

		Raises an error when delete failed.

		@emits: delete-page before the actual delete
		@emits: deleted-page after successfull deletion
		'''
		existed = self._delete_page(path)

		for p in self._deleted_page(path, update_links):
			pass

		return existed

	@assert_index_uptodate
	@notebook_state
	def delete_page_iter(self, path, update_links=True):
		'''Like L{delete_page()}'''
		self._delete_page(path)

		for p in self._deleted_page(path, update_links):
			yield p

	def _delete_page(self, path):
		logger.debug('Delete page: %s', path)
		self.emit('delete-page', path)

		file, folder = self.layout.map_page(path)
		assert file.path.startswith(self.folder.path)
		assert folder.path.startswith(self.folder.path)

		if not (file.exists() or folder.exists()):
			return False
		else:
			if folder.exists():
				folder.remove_children()
				folder.remove()
			if file.exists():
				file.remove()

			self.index.update_file(file)
			self.index.update_file(folder)

			return True

	@assert_index_uptodate
	@notebook_state
	def trash_page(self, path, update_links=True):
		'''Move a page to Trash

		Like L{delete_page()} but will use the system Trash (which may
		depend on the OS we are running on). This is used in the
		interface as a more user friendly version of delete as it is
		undoable.

		@param path: a L{Path} object
		@param update_links: if C{True} pages linking to the
		deleted page will be updated and the link are removed.

		@returns: C{True} when the page existed and was deleted,
		C{False} when the page did not exist in the first place.

		Raises an error when trashing failed.

		@raises TrashNotSupportedError: if trashing is not supported by
		the storage backend or when trashing is explicitly disabled
		for this notebook.

		@emits: delete-page before the actual delete
		@emits: deleted-page after successfull deletion
		'''
		existed = self._trash_page(path)

		for p in self._deleted_page(path, update_links):
			pass

		return existed

	@assert_index_uptodate
	@notebook_state
	def trash_page_iter(self, path, update_links=True):
		'''Like L{trash_page()}'''
		self._trash_page(path)

		for p in self._deleted_page(path, update_links):
			yield p

	def _trash_page(self, path):
		from zim.newfs.helpers import TrashHelper

		logger.debug('Trash page: %s', path)

		if self.config['Notebook']['disable_trash']:
			raise TrashNotSupportedError('disable_trash is set')

		self.emit('delete-page', path)

		file, folder = self.layout.map_page(path)
		helper = TrashHelper()

		re = False
		if folder.exists():
			re = helper.trash(folder)
			if isinstance(path, Page):
				path.haschildren = False

		if file.exists():
			re = helper.trash(file) or re

		self.index.update_file(file)
		self.index.update_file(folder)

		return re

	def _deleted_page(self, path, update_links):
		self.flush_page_cache(path)
		path = Path(path.name)

		if update_links:
			# remove persisting links
			try:
				indexpath = self.pages.lookup_by_pagename(path)
			except IndexNotFoundError:
				pass
			else:
				pages = set(
					l.source for l in self.links.list_links_section(path, LINK_DIR_BACKWARD))

				for p in pages:
					yield p
					page = self.get_page(p)
					self._remove_links_in_page(page, path)
					self.store_page(page)

		# let everybody know what happened
		self.emit('deleted-page', path)

	def _remove_links_in_page(self, page, path):
		logger.debug('Removing links in %s to %s', page, path)
		tree = page.get_parsetree()
		if not tree:
			return

		def replacefunc(elt):
			href = elt.attrib['href']
			type = link_type(href)
			if type != 'page':
				raise zim.formats.VisitorSkip

			hrefpath = self.pages.lookup_from_user_input(href, page)
			#~ print('LINK', hrefpath)
			if hrefpath == path \
			or hrefpath.ischild(path):
				# Replace the link by it's text
				return zim.formats.DocumentFragment(*elt)
			else:
				raise zim.formats.VisitorSkip

		tree.replace(zim.formats.LINK, replacefunc)
		page.set_parsetree(tree)

	def resolve_file(self, filename, path=None):
		'''Resolve a file or directory path relative to a page or
		Notebook

		This method is intended to lookup file links found in pages and
		turn resolve the absolute path of those files.

		File URIs and paths that start with '~/' or '~user/' are
		considered absolute paths. Also windows path names like
		'C:\\user' are recognized as absolute paths.

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
		assert isinstance(filename, str)
		filename = filename.replace('\\', '/')
		if filename.startswith('~') or filename.startswith('file:/'):
			return File(filename)
		elif filename.startswith('/'):
			dir = self.document_root or Dir('/')
			return dir.file(filename)
		elif is_win32_path_re.match(filename):
			if not filename.startswith('/'):
				filename = '/' + filename
				# make absolute on Unix
			return File(filename)
		else:
			if path:
				dir = self.get_attachments_dir(path)
				return File((dir.path, filename)) # XXX LocalDir --> File -- will need get_abspath to resolve
			else:
				dir = Dir(self.layout.root.path) # XXX
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
		from zim.newfs import LocalFile, LocalFolder
		file = LocalFile(file.path) # XXX
		notebook_root = self.layout.root
		document_root = LocalFolder(self.document_root.path) if self.document_root else None# XXX

		rootdir = '/'
		mydir = '.' + SEP
		updir = '..' + SEP

		# Look within the notebook
		if path:
			attachments_dir = self.get_attachments_dir(path)

			if file.ischild(attachments_dir):
				return mydir + file.relpath(attachments_dir)
			elif document_root and notebook_root \
			and document_root.ischild(notebook_root) \
			and file.ischild(document_root) \
			and not attachments_dir.ischild(document_root):
				# special case when document root is below notebook root
				# the case where document_root == attachment_folder is
				# already caught by above if clause
				return rootdir + file.relpath(document_root)
			elif notebook_root \
			and file.ischild(notebook_root) \
			and attachments_dir.ischild(notebook_root):
				parent = file.commonparent(attachments_dir)
				uppath = attachments_dir.relpath(parent)
				downpath = file.relpath(parent)
				up = 1 + uppath.count('/')
				return updir * up + downpath
		else:
			if document_root and notebook_root \
			and document_root.ischild(notebook_root) \
			and file.ischild(document_root):
				# special case when document root is below notebook root
				return rootdir + file.relpath(document_root)
			elif notebook_root and file.ischild(notebook_root):
				return mydir + file.relpath(notebook_root)

		# If that fails look for global folders
		if document_root and file.ischild(document_root):
			return rootdir + file.relpath(document_root)

		# Finally check HOME or give up
		path = file.userpath
		return path if path.startswith('~') else None

	def get_attachments_dir(self, path):
		'''Get the X{attachment folder} for a specific page

		@param path: a L{Path} object
		@returns: a L{Dir} object or C{None}

		Always returns a Dir object when the page can have an attachment
		folder, even when the folder does not (yet) exist. However when
		C{None} is returned the store implementation does not support
		an attachments folder for this page.
		'''
		return self.layout.get_attachments_folder(path)

	def get_template(self, path):
		'''Get a template for the intial text on new pages
		@param path: a L{Path} object
		@returns: a L{ParseTree} object
		'''
		# FIXME hardcoded that template must be wiki format

		template = self.get_page_template_name(path)
		logger.debug('Got page template \'%s\' for %s', template, path)
		template = zim.templates.get_template('wiki', template)
		return self.eval_new_page_template(path, template)

	def get_page_template_name(self, path=None):
		'''Returns the name of the template to use for a new page.
		(To get the contents of the template directly, see L{get_template()})
		'''
		return self.emit_return_first('get-page-template', path or Path(':')) or 'Default'

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
		self.emit('init-page-template', path, template) # plugin hook
		template.process(lines, context)

		parser = zim.formats.get_parser('wiki')
		return parser.parse(lines)
