# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

'''This module contains the export functions for zim'''

import logging

from zim.fs import *
from zim.formats import get_format, BaseLinker
from zim.templates import get_template
from zim.notebook import Page, IndexPage, PageNameError
from zim.stores import encode_filename

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
		self.index_page = index_page
		self.document_root_url = document_root_url
		self.linker = StaticLinker(format, notebook,
						document_root_url=document_root_url)

		if isinstance(format, basestring):
			self.format = get_format(format)
		else:
			self.format = format

		if template and isinstance(template, basestring):
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

		for page in self.notebook.walk():
			if page.hascontent:
				self.export_page(dir, page)
				if callback and not callback(page):
					logger.warn('Export cancelled')
					return False

		if self.index_page:
			page = IndexPage(self.notebook)
			page.name = self.index_page # HACK
			self.export_page(dir, page)

		logger.info('Export done')
		return True

	def export_page(self, dir, page):
		'''Export 'page' to a file below 'dir'. Path below 'dir' will be
		determined by the namespace of 'page'. Attachments wil also be
		copied along.
		'''
		logger.info('Exporting %s', page.name)
		dirname = encode_filename(page.name)
		filename = dirname + '.' + self.format.info['extension']
		file = dir.file(filename)
		attachments = self.notebook.get_attachments_dir(page)
		self.linker.set_base(attachments.dir)
			# FIXME, assuming standard file store layout to get correct relative links
		fh = file.open('w')
		self.export_page_to_fh(fh, page)
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

	def export_page_to_fh(self, fh, page):
		'''Export 'page' and print the output to open file handle 'fh'.
		(Does not do anything with attachments.)
		'''
		if self.template is None:
			self.linker.set_path(page)
			lines = page.dump(self.format, linker=self.linker)
		else:
			lines = self.template.process(self.notebook, page)
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
		self._extension = '.' + format.info['extension']

	def page(self, link):
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
				path += encode_filename(downpath) + self._extension
			elif parent == page:
				uppath = self.path.relname(parent)
				path = '../' * (uppath.count(':') + 1)
				path += encode_filename(page.basename) + self._extension
			else:
				uppath = self.path.relname(parent)
				downpath = page.relname(parent)
				path = '../' * uppath.count(':') or './'
				path += encode_filename(downpath) + self._extension
			#~ print '>>>', path
			return path

	def file(self, link):
		if self.document_root_url and link.startswith('/'):
			return ''.join((self.document_root_url.rstrip('/'), link))
		else:
			file = self.notebook.resolve_file(link, self.path)
			if self.usebase and self.base:
				relpath = file.relpath(self.base, allowupward=True)
				if relpath and not relpath.startswith('.'):
					relpath = './' + relpath
				return relpath or file.uri
			else:
				return file.uri
