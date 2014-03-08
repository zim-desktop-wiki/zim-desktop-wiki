# -*- coding: utf-8 -*-

# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>


'''The ExportLinker object translates links in zim pages to URLS
for the export content
'''

import logging

logger = logging.getLogger('zim.exporter')


from zim.formats import BaseLinker

from zim.fs import File
from zim.notebook import PageNameError, interwiki_link
from zim.parsing import link_type, is_win32_path_re


class ExportLinker(object): # TODO should inherit from BaseLinker
	'''This object translate links in zim pages to (relative) URLs.
	This is used when exporting data to resolve links.
	Relative URLs start with "./" or "../" and should be interpreted
	in the same way as in HTML. Both URLs and relative URLs are
	already URL encoded

	@TODO: info on formats to know how to set "usebase"
	'''

	def __init__(self, notebook, layout, source=None, output=None, usebase=False):
		'''Contructor
		@param notebook: the source L{Notebook} for resolving links
		@oaram layout: the L{ExportLayout} for resolving target files
		@param source: is the L{Path} of the source page being exported
		@param output: is a L{File} object for the destination file
		@param usebase: if C{True} the format allows returning relative paths
		'''
		self.notebook = notebook
		self.layout = layout
		self.source = source
		self.output = output

		if output:
			self.base = output.dir
		else:
			self.base = None

		self.usebase = usebase

		self._icons = {} # memorize them because the occur often in one page


	## Methods used while exporting to resolve links etc. ##

	def link(self, link):
		'''Returns an url for a link in a zim page
		This method is used to translate links of any type.

		@param link: link to be translated
		@returns: url, uri, or relative path
		context of this linker
		'''
		# Determines the link type and dispatches any of the "link_*" methods
		type = link_type(link)
		methodname = '_link_' + type
		if hasattr(self, methodname):
			href = getattr(self, methodname)(link)
		else:
			href = link
		#~ print "Linker:", link, '-->', href
		return href

	def img(self, src):
		'''Returns an url for image file 'src' '''
		return self._link_file(src)

	def icon(self, name):
		'''Returns an url for an icon'''
		if not name in self._icons:
			path = 'icons/%s.png' % name
			self._icons[name] = self.resource(path)
		return self._icons[name]

	def resource(self, path):
		'''Return an url for template resources'''
		dir = self.layout.resources_dir()
		file = dir.file(path)
		return self.file_object(file)

	# TODO rename to resolve_source_file() ?
	def resolve_file(self, link):
		'''Find the source file for an attachment
		Used e.g. by the latex format to find files for equations to
		be inlined. Do not use this method to resolve links, the file
		given here might be temporary and is not guaranteed to be
		available after the export.
		@returns: a L{File} object or C{None} if no file was found
		'''
		return self.notebook.resolve_file(link, self.source)

	def page_object(self, path):
		'''Turn a L{Path} object in a relative link or URI'''
		try:
			file = self.layout.page_file(path)
		except PathLookupError:
			return '' # Link outside of current export ?
		else:
			if file == self.output:
				return '#' + path.name # single page layout ?
			else:
				return self.file_object(file)

	def file_object(self, file):
		'''Turn a L{File} object in a relative link or URI'''
		if self.base and self.usebase \
		and file.ischild(self.layout.relative_root):
			return file.relpath(self.base, allowupward=True)
		else:
			return file.uri





	## Methods below are internal, not used by format or template ##

	def _link_page(self, link):
		try:
			path = self.notebook.resolve_path(link, source=self.source)
				# Allows source to be None
		except PageNameError:
			return ''
		else:
			return self.page_object(path)

	def _link_file(self, link):
		# TODO checks here are copy of notebook.resolve_file - should be single function
		#      to determine type of file link: attachment / document / other
		#      or generic function that takes attachment folder & document folder as args

		filename = link.replace('\\', '/')
		if filename.startswith('~') or filename.startswith('file:/'):
			file = File(filename)
		elif filename.startswith('/'):
			if self.notebook.document_root:
				dir = self.layout.resources_dir()
				file = dir.file(filename)
			else:
				file = File(filename)
		elif is_win32_path_re.match(filename):
			if not filename.startswith('/'):
				filename = '/'+filename # make absolute on Unix
			file = File(filename)
		else:
			if self.source:
				dir = self.layout.attachments_dir(self.source)
			else:
				dir = self.layout.relative_root

			file = dir.resolve_file(filename)
				# Allow ../ here - limit resulting relative link
				# in self.file_object()

		return self.file_object(file)

	def _link_mailto(self, link):
		if link.startswith('mailto:'):
			return link
		else:
			return 'mailto:' + link

	def _link_interwiki(self, link):
		href = interwiki_link(link)
		if href and href != link:
			return self.link(href) # recurs
		else:
			logger.warn('No URL found for interwiki link "%s"', link)
			return None

	def _link_notebook(self, link):
		pass # TODO resolve file uri for notebook



#~ class StaticExportLinker(ExportLinker):
	#~ pass

	# Resolve icons to data_dir()
	# Link by absolute path to attachments and documents in original location

