
# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from functools import partial

import logging

logger = logging.getLogger('zim.export')

from zim.utils import MovingWindowIter

from zim.config import data_file
from zim.notebook import Path
from zim.formats import get_format

from zim.export.exporters import Exporter, createIndexPage
from zim.export.linker import ExportLinker
from zim.export.template import ExportTemplateContext

from zim.fs import Dir
from zim.newfs import FileNotFoundError, LocalFolder



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

	def export_attachments_iter(self, notebook, page):
		# XXX FIXME remove need for notebook here
		# XXX what to do with folders that do not map to a page ?
		source = notebook.get_attachments_dir(page)
		target = self.layout.attachments_dir(page)
		try:
			for file in source.list_files():
					yield file
					targetfile = target.file(file.basename)
					if targetfile.exists():
						targetfile.remove() # Export does overwrite by default
					file.copyto(targetfile)
		except FileNotFoundError:
			pass

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
			if dir.exists(): # Export does overwrite by default
				dir.remove_children()
				dir.remove()

			resources = self.template.resources_dir
			if isinstance(resources, Dir):
				resources = LocalFolder(resources.path)
			resources.copyto(dir)


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
		if index_page:
			if isinstance(index_page, str):
				self.index_page = Path(Path.makeValidPageName(index_page))
			else:
				self.index_page = index_page
		else:
			self.index_page = None
		# TODO make index_page generic special page in output selection

	def export_iter(self, pages):
		self.export_resources()

		for prev, page, next in MovingWindowIter(pages):
			yield page
			try:
				self.export_page(pages.notebook, page, pages, prevpage=prev, nextpage=next)
					# XXX FIXME remove need for notebook here
				for file in self.export_attachments_iter(pages.notebook, page):
					yield file
					# XXX FIXME remove need for notebook here
			except:
				raise
				logger.exception('Error while exporting: %s', page.name)

		if self.index_page:
			try:
				logger.info('Export index: %s', self.index_page)
				yield self.index_page
				self.export_index(self.index_page, pages)
			except:
				logger.exception('Error while exporting index')

	def export_page(self, notebook, page, pages, prevpage=None, nextpage=None):
		# XXX FIXME remove need for notebook here

		file = self.layout.page_file(page)
		if file.exists():
			file.remove() # export does overwrite by default

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
			home=notebook.get_home_page(),
			up=None, # TODO
			prevpage=prevpage, nextpage=nextpage,
			links={'index': self.index_page},
			index_generator=pages.index,
			index_page=page,
		)

		lines = []
		self.template.process(lines, context)
		file.writelines(lines)

	def export_index(self, index_page, pages):
		if pages.prefix:
			index_page = pages.prefix + index_page

		page = createIndexPage(pages.notebook, index_page, pages.prefix)
		self.export_page(pages.notebook, page, pages)


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
		if self.layout.file.exists():
			self.layout.file.remove() # export does overwrite by default
		self.layout.file.writelines(lines)

		# TODO incremental write to save memory on large notebooks...
		# TODO also yield while exporting main page

		for page in pages:
			yield page
			for file in self.export_attachments_iter(pages.notebook, page):
				yield file


#~ class StaticFileExporter(SingleFileExporter):

	# Single file, but link files with absolute path
	# used e.g. for print-to-browser

	# TODO overload to prevent copying files
