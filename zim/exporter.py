# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains the export functions for zim.
Main class is L{Exporter}, which implements the export action.
See L{zim.gui.exportdialog} for the graphical user interface.
'''

import logging

from zim.fs import Dir, File
from zim.config import data_file
from zim.formats import get_format, BaseLinker
from zim.templates import get_template, Template
from zim.notebook import Path, Page, IndexPage, PageNameError
from zim.stores import encode_filename
from zim.parsing import url_encode, url_decode

logger = logging.getLogger('zim.exporter')


class Exporter(object):
	'''Class that handles an export action.
	The object instance holds all settings for the export. Once created
	the actual export is done by calling L{export_all()} or by multiple
	calls to L{export_page()}.
	'''

	def __init__(self, notebook, format, template=None,
					index_page=None, document_root_url=None):
		'''Constructor.

		Takes all input parameters on how to format the exported
		content.

		@param notebook: the L{Notebook} object
		@param format: the output format as string, or formatting
		module object
		@param template: the template name as string, or a L{Template}
		object, if C{None} no template is used
		@param index_page: path name for the index page, if C{None} no
		index page is generated
		@param document_root_url: prefix for links that link to the
		document root (e.g. URL for the document root on some server).
		If C{None} document root files are considered the same as
		other files.

		@todo: check why index_page is a string and not a Path object
		'''
		self.notebook = notebook
		self.document_root_url = document_root_url
		self.linker = StaticLinker(format, notebook,
						document_root_url=document_root_url)

		if index_page:
			self.index_page = notebook.cleanup_pathname(index_page)
		else:
			self.index_page = None

		if isinstance(format, basestring):
			self.format = get_format(format)
		else:
			self.format = format

		if template and not isinstance(template, Template):
			self.template = get_template(format, template)
		else:
			self.template = template

		if self.template:
			self.template.set_linker(self.linker)

	def export_all(self, dir, callback=None):
		'''Export all pages in the notebook

		Will also copy all attachments and created a folder with icons
		for checkboxes etc. So the resulting folder should contain all
		the notebook information.

		@param dir: a L{Dir} object for the target folder
		@param callback: a callback function that will be called after
		each page being exported with the page object as single argument.
		If the function returns C{False} the export is canceled.

		@returns: C{False} if the action was cancelled, C{True} otherwise
		'''
		logger.info('Exporting notebook to %s', dir)
		self.linker.target_dir = dir # Needed to resolve icons

		# Copy icons
		for name in ('checked-box', 'unchecked-box', 'xchecked-box'):
			icon = data_file('pixmaps/%s.png' % name)
			file = dir.file('_resources/' + name + '.png')
			icon.copyto(file)

		# Copy template resources (can overwrite icons)
		if self.template and self.template.resources_dir \
		and self.template.resources_dir.exists():
			resources = dir.subdir('_resources')
			self.template.resources_dir.copyto(resources)

		# Set special pages
		if self.index_page:
			indexpage = Page(Path(self.index_page))
		else:
			indexpage = None

		pages = {
			'index': indexpage,
			'home': self.notebook.get_home_page(),
		}

		# Export the pages
		prev, current, next = None, None, None
		for page in self.notebook.walk():
			if page.hascontent:
				prev, current, next = current, next, page # shift
				if current:
					pages['previous'] = prev
					pages['next'] = next
					self.export_page(dir, current, pages, use_namespace=True)
					if callback and not callback(current):
						logger.warn('Export canceled')
						return False

		prev, current, next = current, next, None # shift once more
		if current:
			pages['previous'] = prev
			pages['next'] = next
			self.export_page(dir, current, pages, use_namespace=True)
			if callback and not callback(current):
				logger.warn('Export canceled')
				return False

		# Generate index page
		if indexpage:
			_page = IndexPage(self.notebook, Path(':'))
			# Bit of a HACK here - need better support for these index pages
			indexpage.readonly = False
			indexpage.set_parsetree(_page.get_parsetree())
			indexpage.readonly = True
			self.export_page(dir, indexpage, use_namespace=True)

		self.linker.target_dir = None # reset
		logger.info('Export done')
		return True

	def export_page(self, dir, page, pages=None, use_namespace=False, filename=None, dirname=None):
		'''Export a single page and copy it's attachments. Does not
		include sub-pages.

		@param dir: a L{Dir} object for the target folder
		@param page: the L{page} to export
		@param pages: dict with special pages that is passed on to the
		template
		@param use_namespace: when C{False} the export file will be
		placed directly in C{dir}, when C{True} the page will be put
		in a sub-folder structure that reflects the namespace of the
		page
		@param filename: alternative filename to use for the export
		file instead of the page name. If needed the appropriate
		file extension is added to the name.
		@param dirname: alternative name to use for the folder with
		attachments, if C{None} it takes the filename without the
		extension.

		@todo: Get rid of C{use_namespace} by creating a seperate
		function for that. Maybe create a variant that does a single
		page in an folder directly and a higher level function that
		does an entire namespace including sub-pages
		@todo: change filename and dirname in File and Dir arguments
		'''
		logger.info('Exporting %s', page.name)

		if filename is None:
			if use_namespace:
				filename = encode_filename(page.name)
			else:
				filename = encode_filename(page.basename)

		extension = '.' + self.format.info['extension']
		if not filename.endswith(extension):
			filename += extension

		if dirname is None:
			dirname = filename[:-len(extension)]

		file = dir.file(filename)
		attachments = self.notebook.get_attachments_dir(page)
		self.linker.set_base(attachments.dir) # parent of attachment dir
			# FIXME, assuming standard file store layout to get correct relative links
		self.linker.target_file = file

		fh = file.open('w')
		self.export_page_to_fh(fh, page, pages)
		fh.close()

		subdir = dir.subdir(dirname)
		for name in attachments.list():
			file = attachments.file(name)
			if file.exists(): # tests os.isfile
				file.copyto(subdir)
			# TODO option to recurs for directories
			# - check we don't copy the same file many times
			# - ignore directories that belong to a page themselves
			# - also include "attachments" in the root namespace

	def export_page_to_fh(self, fh, page, pages=None):
		'''Output the export content for a single page to an open file

		@param fh: an open file object, or any object that has a
		C{writelines()} method
		@param page: the L{page} to export
		@param pages: dict with special pages that is passed on to the
		template
		'''
		if self.template is None:
			self.linker.set_path(page)
			lines = page.dump(self.format, linker=self.linker)
		else:
			lines = self.template.process(self.notebook, page, pages)
		fh.writelines(lines)


class StaticLinker(BaseLinker):
	'''Linker object to be used by the template when exporting.
	It links files, images and icons with absolute or relative file paths
	(based on whether the format supports relative links or not).
	Other pages are linked as files.

	See L{BaseLinker} for the API docs.
	'''

	def __init__(self, format, notebook, path=None, document_root_url=None):
		BaseLinker.__init__(self)
		if isinstance(format, basestring):
			format = get_format(format)
		self.notebook = notebook
		self.path = path
		self.document_root_url = document_root_url
		self.target_dir = None
		self.target_file = None
		self._extension = '.' + format.info['extension']

	def resource(self, path):
		if self.target_dir and self.target_file:
			file = self.target_dir.file('_resources/'+path)
			return self._filepath(file, self.target_file.dir)
		else:
			path

	def icon(self, name):
		if self.target_dir and self.target_file:
			file = self.target_dir.file('_resources/'+name+'.png')
			return self._filepath(file, self.target_file.dir)
		else:
			return BaseLinker.icon(self, name)

	def link_page(self, link):
		try:
			page = self.notebook.resolve_path(link, source=self.path)
		except PageNameError:
			return ''
		else:
			if page == self.path:
				return ''

			parent = page.commonparent(self.path)
			if parent == self.path:
				path = './' + self.path.basename + '/'
				downpath = page.relname(parent)
				path += downpath
			elif parent == page:
				uppath = self.path.relname(parent)
				path = '../' * (uppath.count(':') + 1)
				path += page.basename
			else:
				uppath = self.path.relname(parent)
				downpath = page.relname(parent)
				path = '../' * uppath.count(':') or './'
				path += downpath

			path = encode_filename(path) + self._extension
			#~ print '>>>', path
			return url_encode(path.replace(' ', '_'))

	def resolve_file(self, link):
		try:
			file = self.notebook.resolve_file(link, self.path)
		except:
			# typical error is a non-local file:// uri
			return None
		else:
			return file

	def link_file(self, link):
		if self.document_root_url and link.startswith('/'):
			return ''.join((self.document_root_url.rstrip('/'), link))
		else:
			try:
				file = self.notebook.resolve_file(link, self.path)
				if self.usebase and self.base:
					return self._filepath(file, self.base)
				else:
					return file.uri
			except:
				# typical error is a non-local file:// uri
				return link

	def _filepath(self, file, ref):
		relpath = file.relpath(ref, allowupward=True)
		if relpath and not relpath.startswith('.'):
			relpath = './' + relpath
		return url_encode(relpath) or file.uri

	def link_notebook(self, url):
		if url.startswith('zim+'):
			url = url[4:]

		if '?' in url:
			uri, path = url.split('?')
			# FIXME: code below is not robust because we don't know the
			# storage mode of linked notebook...
			path = url_decode(path) # was already encoded by interwiki_link()
			path = encode_filename(path).replace(' ', '_')
			return uri + '/' + url_encode(path) + '.txt'
		else:
			return url
