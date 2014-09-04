# -*- coding: utf-8 -*-

# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from functools import partial

import logging

logger = logging.getLogger('zim.export')

from zim.utils import MovingWindowIter

from zim.config import data_file
from zim.notebook import IndexPage, Page, Path
from zim.formats import get_format

from zim.export.exporters import Exporter
from zim.export.linker import ExportLinker
from zim.export.template import ExportTemplateContext


class FilesExporterBase(Exporter):
	'''Base class for exporters that export to files'''

	def __init__(self, layout, template, format, document_root_url=None):
		'''Constructor
		@param layout: a L{ExportLayout} to map pages to files
		@param template: a L{Template} object
		@param format: the format for the file content
		@param document_root_url: optional URL for the document root
		'''
		self.layout = layout
		self.template = template
		self.format = get_format(format) # XXX
		self.document_root_url = document_root_url

	def export_attachments(self, notebook, page):
		# XXX FIXME remove need for notebook here
		source = notebook.get_attachments_dir(page)
		target = self.layout.attachments_dir(page)
		for name in source.list():
			file = source.file(name)
			if not file.isdir():
				file.copyto(target)
			# XXX what to do with folders that do not map to a page ?

	def export_resources(self):
		dir = self.layout.resources_dir()

		# Copy icons -- TODO should we define default resources somewhere ?
		#~ for name in ('checked-box', 'unchecked-box', 'xchecked-box'):
			#~ icon = data_file('pixmaps/%s.png' % name)
			#~ file = dir.file(name + '.png')
			#~ icon.copyto(file)

		# Copy template resources (can overwrite icons)
		if self.template.resources_dir \
		and self.template.resources_dir.exists():
			self.template.resources_dir.copyto(dir)


class MultiFileExporter(FilesExporterBase):
	'''Exporter that exports each page to a single file'''

	def __init__(self, layout, template, format, index_page=None, document_root_url=None):
		'''Constructor
		@param layout: a L{ExportLayout} to map pages to files
		@param template: a L{Template} object
		@param format: the format for the file content
		@param index_page: a page to output the index or C{None}
		@param document_root_url: optional URL for the document root
		'''
		FilesExporterBase.__init__(self, layout, template, format, document_root_url)
		self.index_page = index_page # TODO make generic special page in output selection

	def export_iter(self, pages):
		self.export_resources()

		for prev, page, next in MovingWindowIter(pages):
			logger.info('Exporting page: %s', page.name)
			yield page
			try:
				self.export_page(pages.notebook, page, pages, prevpage=prev, nextpage=next)
					# XXX FIXME remove need for notebook here
				self.export_attachments(pages.notebook, page)
					# XXX FIXME remove need for notebook here
			except:
				raise
				logger.exception('Error while exporting: %s', page.name)

		if self.index_page:
			try:
				index_page = self.index_page
				if isinstance(index_page, basestring):
					index_page = pages.notebook.cleanup_pathname(index_page) # XXX

				logger.info('Export index: %s', index_page, pages)
				yield Path(index_page)
				self.export_index(index_page, pages)
			except:
				logger.exception('Error while exporting index')

	def export_page(self, notebook, page, pages, prevpage=None, nextpage=None):
		# XXX FIXME remove need for notebook here

		file=self.layout.page_file(page)
		linker_factory = partial(ExportLinker,
			notebook=notebook,
			layout=self.layout,
			output=file,
			usebase=self.format.info['usebase'],
			document_root_url=self.document_root_url
		)
		dumper_factory = self.format.Dumper # XXX

		context = ExportTemplateContext(
			notebook,
			linker_factory, dumper_factory,
			title=page.get_title(),
			content=[page],
			home=None, up=None, # TODO
			prevpage=prevpage, nextpage=nextpage,
			links={'index': self.index_page},
			index_generator=pages.index,
			index_page=page,
		)

		lines = []
		self.template.process(lines, context)
		file.writelines(lines)

	def export_index(self, index_page, pages):
		# TODO remove hack here, and get rid of IndexPage in current shape from Notebook

		if pages.prefix:
			indexpage = Page(pages.prefix + index_page)
		else:
			indexpage = Page(Path(index_page))

		# Bit of a HACK here - need better support for these index pages
		_page = IndexPage(pages.notebook, pages.prefix) # TODO make more flexible - use pages iter itself
		indexpage.readonly = False
		indexpage.set_parsetree(_page.get_parsetree())
		indexpage.readonly = True

		self.export_page(pages.notebook, indexpage, pages)


class SingleFileExporter(FilesExporterBase):
	'''Exporter that exports all page to the same file'''

	# TODO make robust for errors during page iteration - needs to be in template code - allow removing try .. except in multifile above ?

	def export_iter(self, pages):
		self.export_resources()

		linker_factory = partial(ExportLinker,
			notebook=pages.notebook,
			layout=self.layout,
			output=self.layout.file,
			usebase=self.format.info['usebase'],
			document_root_url=self.document_root_url
		)
		dumper_factory = self.format.Dumper # XXX

		context = ExportTemplateContext(
			pages.notebook,
			linker_factory, dumper_factory,
			title=pages.title, # XXX
			content=pages,
			special=None, # TODO
			home=None,  # TODO
			links=None,
			index_generator=pages.index,
			index_page=None,
		)

		lines = []
		self.template.process(lines, context)
		self.layout.file.writelines(lines)

		# TODO incremental write to save memory on large notebooks...
		# TODO also yield while exporting main page

		for page in pages:
			self.export_attachments(pages.notebook, page)
			yield page


#~ class StaticFileExporter(SingleFileExporter):

	# Single file, but link files with absolute path
	# used e.g. for print-to-browser

	# TODO overload to prevent copying files
