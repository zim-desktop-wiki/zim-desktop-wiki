# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains the export functions for zim'''

import logging

from zim.fs import *
from zim.config import data_file
from zim.formats import get_format, BaseLinker
from zim.templates import get_template, Template
from zim.notebook import Path, Page, IndexPage, PageNameError
from zim.stores import encode_filename
from zim.parsing import url_encode

logger = logging.getLogger('zim.exporter')


class Exporter(object):
	'''Class that handles an export action'''

	def __init__(self, notebook, format, template=None,
					index_page=None, document_root_url=None):
		'''Constructor. The 'notebook' is the source for pages to be exported.
		(The export target is given as an argument to export_all() or export().)
		The 'format' and 'template' arguments determine the output format.
		If 'index_page' is given a page index is generated and
		'document_root_url' is used to prefix any file links that start with '/'.
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
		'''Export all pages in the notebook to 'dir'. Attachments are copied
		along. The function 'callback' will be called after each page with the
		page object as single argument. If the callback returns False the
		export will be cancelled.
		'''
		logger.info('Exporting notebook to %s', dir)
		self.linker.target_dir = dir # Needed to resolve icons

		# Copy icons
		for name in ('checked-box', 'unchecked-box', 'xchecked-box'):
			icon = data_file('pixmaps/%s.png' % name)
			file = dir.file('_icons/'+name+'.png')
			icon.copyto(file)

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
						logger.warn('Export cancelled')
						return False

		prev, current, next = current, next, None # shift once more
		if current:
			pages['previous'] = prev
			pages['next'] = next
			self.export_page(dir, current, pages, use_namespace=True)
			if callback and not callback(current):
				logger.warn('Export cancelled')
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
		'''Export 'page' to a file below 'dir'. Attachments wil also be
		copied along.

		If only a page is given that output file will have the same
		basename as the page. If 'use_namespace' is set to True the
		path below 'dir' will be determined by the namespace of 'page'.
		The attachment directory will match the name of the file but
		without extension.

		Alternatively when a filename is given it will be used. If
		needed the apropriate file extension is added to the name.
		Similar the dirname option can be used to specify the directory
		for attachments, otherwise it is derived from the filename.
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
		self.linker.set_base(attachments.dir)
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
		'''Export 'page' and print the output to open file handle 'fh'.
		(Does not do anything with attachments.)
		'''
		if self.template is None:
			self.linker.set_path(page)
			lines = page.dump(self.format, linker=self.linker)
		else:
			lines = self.template.process(self.notebook, page, pages)
		fh.writelines(l.encode('utf-8') for l in lines)


class StaticLinker(BaseLinker):
	'''Linker object for exporting a single page. It links files, images
	and icons with absolute or relative file paths (based on whether the
	format supports relative links or not). Other pages are linked as
	files.
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

	def icon(self, name):
		if self.target_dir and self.target_file:
			file = self.target_dir.file('_icons/'+name+'.png')
			return self._filepath(file, self.target_file)
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
			path = encode_filename(path).replace(' ', '_')
			return uri + '/' + url_encode(path) + '.txt'
		else:
			return url
