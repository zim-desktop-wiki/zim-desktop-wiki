# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import logging

from zim.fs import *
from zim.formats import get_format
from zim.templates import get_template
from zim.notebook import Page, IndexPage
from zim.stores import encode_filename
from zim.config import data_file
from zim.parsing import link_type

logger = logging.getLogger('zim.exporter')


class Exporter(object):
	'''FIXME'''

	def __init__(self, notebook, format, template=None,
				index_page=None,
				include_documents=False, document_root_url=None):
		self.notebook = notebook
		self.index_page = index_page
		self.include_documents = include_documents
		self.document_root_url = document_root_url
		self.linker = BaseLinker(format, notebook)

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
		logger.info('Exporting %s', page.name)
		filename = encode_filename(page.name)
		filename += '.' + self.format.info['extension']
		file = dir.file(filename)
		fh = file.open('w')
		self.export_page_to_fh(fh, page)
		fh.close()
		# TODO add attachments + copy documents

	def export_page_to_fh(self, fh, page):
		# TODO use documents_url
		if self.template is None:
			self.linker.set_path(page)
			lines = page.dump(self.format, linker=self.linker)
		else:
			lines = self.template.process(self.notebook, page)
		fh.writelines(l.encode('utf-8') for l in lines)


class BaseLinker(object):
	'''Linker object for exporting a single page. It links files, images
	and icons with absolute file paths, but can not link other pages corectly.
	'''

	def __init__(self, format, notebook, path=None):
		if isinstance(format, basestring):
			format = get_format(format)
		self.notebook = notebook
		self.path = path
		self._extension = '.' + format.info['extension']
		self._icons = {}

	def set_path(self, path):
		self.path = path

	def link(self, link):
		'''Returns an url for 'link' '''
		type = link_type(link)
		if type == 'page':
			# even though useless in the typical use-case still resolve pages so they look OK
			page = self.notebook.resolve_path(link, namespace=self.path.get_parent())
			href = '/' + encode_filename(page.name) + self._extension
		elif type == 'file':
			href = self.src(link, path)
		elif type == 'mailto':
			if link.startswith('mailto:'):
				href = link
			else:
				href = 'mailto:' + link
		else:
			# I dunno, some url ?
			href = link
		return href

	def img(self, src):
		'''Returns an url for image file 'src' '''
		file = self.notebook.resolve_file(src, self.path)
		return file.uri

	def icon(self, name):
		'''Returns an url for an icon'''
		if not name in self._icons:
			self._icons[name] = data_file('pixmaps/%s.png' % name).uri
		return self._icons[name]

# TODO: linker for using a single page
