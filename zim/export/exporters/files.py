# -*- coding: utf-8 -*-

# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from functools import partial

import logging

logger = logging.getLogger('zim.exporter')


from zim.config import data_file
from zim.notebook import IndexPage, Page, Path
from zim.formats import get_format

from zim.export.exporters import Exporter
from zim.export.linker import ExportLinker
from zim.export.template import ExportTemplateContext


class FilesExporterBase(Exporter):
	'''Base class for exporters that export to files'''

	def __init__(self, layout, template, format):
		'''Constructor
		@param layout: a L{ExportLayout} to map pages to files
		@param template: a L{Template} object
		@param format: the format for the file content
		'''
		self.layout = layout
		self.template = template
		self.format = get_format(format) # XXX

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
		for name in ('checked-box', 'unchecked-box', 'xchecked-box'):
			icon = data_file('pixmaps/%s.png' % name)
			file = dir.file(name + '.png')
			icon.copyto(file)

		# Copy template resources (can overwrite icons)
		if self.template.resources_dir \
		and self.template.resources_dir.exists():
			self.template.resources_dir.copyto(dir)


class MultiFileExporter(FilesExporterBase):
	'''Exporter that exports each page to a single file'''

	def __init__(self, layout, template, format, index_page=None):
		'''Constructor
		@param layout: a L{ExportLayout} to map pages to files
		@param template: a L{Template} object
		@param format: the format for the file content
		@param index_page: a page to output the index or C{None}
		'''
		FilesExporterBase.__init__(self, layout, template, format)
		self.index_page = index_page # TODO make generic special page in output selection

	def export_iter(self, pages):
		# Install template method for ToC
		# TODO

		self.export_resources()

		for page in pages:
			yield page
			try:
				self.export_page(pages.notebook, page)
					# XXX FIXME remove need for notebook here
				self.export_attachments(pages.notebook, page)
					# XXX FIXME remove need for notebook here
			except:
				logger.exception('Error while exporting: %s', page.name)

		if self.index_page:
			try:
				index_page = self.index_page
				if isinstance(index_page, basestring):
					index_page = pages.notebook.cleanup_pathname(index_page) # XXX
				yield index_page
				self.export_index(index_page, pages)
			except:
				logger.exception('Error while exporting index')

	def export_page(self, notebook, page):
		# XXX FIXME remove need for notebook here

		file=self.layout.page_file(page)
		linker_factory = partial(ExportLinker,
			notebook=notebook,
			layout=self.layout,
			output=file,
			usebase=True # XXX TODO base on format
		)
		dumper_factory = self.format.Dumper # XXX

		context = ExportTemplateContext(
			notebook,
			linker_factory, dumper_factory,
			title=page.name, # XXX implement page.title (use heading)
			content=[page],
			home=None, up=None, prevpage=None, nextpage=None, # TODO
			links=None, # TODO
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

		self.export_page(pages.notebook, indexpage)


class SingleFileExporter(FilesExporterBase):
	'''Exporter that exports all page to the same file'''

	# TODO make robust for errors during page iteration - needs to be in template code - allow removing try .. except in multifile above ?

	def export_iter(self, pages):
		# Install template method for ToC
		# TODO

		self.export_resources()

		linker_factory = partial(ExportLinker,
			notebook=notebook,
			layout=self.layout,
			output=self.layout.file,
			usebase=True # XXX TODO base on format
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
