# -*- coding: utf-8 -*-

# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>


'''The ExportLayout object determines the mapping of pages to files
when exporting. The subclasses give alternative file layouts.
'''

from zim.fs import Dir, File, PathLookupError
from zim.stores import encode_filename


class ExportLayout(object):
	'''The ExportLayout object determines the mapping of pages to files
	when exporting. This is the base class that defines the public API.
	'''

	relative_root = None #: Used by linker to make paths relative

	def page_file(self, page):
		'''Returns the file for a page
		@param page: a L{Page} or L{Path} object
		@returns: a L{File} object
		@raises PathLookupError: if page can not be mapped
		@implementation: must be implemented by subclasses
		'''
		raise NotImplementedError

	def attachments_dir(self, page):
		'''Returns the attachments folder for a page
		@param page: a L{Page} or L{Path} object
		@returns: a L{Dir} object
		@raises PathLookupError: if folder can not be mapped
		@implementation: must be implemented by subclasses
		'''
		raise NotImplementedError

	def resources_dir(self):
		'''Returns the folder for template resources
		@returns: a L{Dir} object
		'''
		raise NotImplementedError


class DirLayoutBase(ExportLayout):

	# Assumes "namespace" and "dir" attributes

	def attachments_dir(self, page):
		if self.namespace:
			if page == self.namespace:
				return self.dir
			elif page.ischild(self.namespace):
				path = page.relname(self.namespace)
			else:
				raise PathLookupError(
					'%s not a child of %s' % (page, self.namespace)
				)
			name = page.relname(self.namespace)
		else:
			name = page.name
		return self.dir.subdir(encode_filename(name))

	def resources_dir(self):
		return self.dir.subdir('_resources')


class MultiFileLayout(DirLayoutBase):
	'''Layout that maps pages to files in a folder similar to how a
	notebook is stored.

	Layout::

	  dir/
	   `--> _resources/
	   `--> page.html
	   `--> page/
	         `--> attachment.png

	The root for relative links is "dir/"
	'''

	def __init__(self, dir, ext, namespace=None):
		'''Constructor
		@param dir: a L{Dir} object
		@param ext: the file extension to be used, e.g. 'html'
		@param namespace: optional namespace prefix to strip from
		page names
		'''
		self.dir = dir
		self.ext = ext
		self.namespace = namespace
		self.relative_root = self.dir

	def page_file(self, page):
		if page.isroot:
			raise PathLookupError('Can not export: %s', page)
		elif self.namespace:
			if page.ischild(self.namespace):
				name = page.relname(self.namespace)
			else:
				# This layout can not store page == namespace !
				raise PathLookupError(
					'%s not a child of %s' % (page, self.namespace)
				)
		else:
			name = page.name
		return self.dir.file(encode_filename(name) + '.' + self.ext)


#~ class MultiFolderLayout(DirLayoutBase):

	# dir/
	#  `--> _resources/
	#  `--> page/
	#        `--> index.html  # page contents
	#        `--> attachment.png

	# Root for relative links is "dir/"


class FileLayout(DirLayoutBase):
	'''Layout that maps pages to files in a folder with one specific
	page as the top level file. Use to export sub-tree of a notebook.

	Layout::

	  page.html
	  page_files/
	   `--> attachment.png
	   `--> subpage.html
	   `--> subpage/attachment.pdf
	   `--> _resources/

	The root for relative links is "page_files/"
	'''

	def __init__(self, file, page, ext):
		'''Constructor
		@param file: a L{File} object
		@param page: a L{Path} object for the top level page
		@param ext: the file extension to be used for sub-pages, e.g. 'html'
		'''
		self.file = file
		self.namespace = page
		self.ext = ext

		basename = file.basename
		if '.' in basename:
			basename, x = basename.rsplit('.', 1)
		self.dir = file.dir.subdir(basename + '_files')
		self.relative_root = self.dir

	def page_file(self, page):
		if page == self.namespace:
			return self.file
		elif page.ischild(self.namespace):
			name = page.relname(self.namespace)
		else:
			raise PathLookupError(
				'%s not a child of %s' % (page, self.namespace)
			)
		return self.dir.file(encode_filename(name) + '.' + self.ext)



class SingleFileLayout(DirLayoutBase):
	'''Like FileLayout, except all pages are stored in a single file
	while attachments still follow folder structure per page.
	Can be used to export a page with sub-pages, but also for a
	complete notebook.

	Layout::

	  page.html
	  page_files/
	   `--> attachment.png
	   `--> subpage/attachment.pdf
	   `--> _resources/

	The root for relative links is "page_files/"
	'''

	def __init__(self, file, page=None):
		'''Constructor
		@param file: a L{File} object
		@param page: an optional L{Path} object for the top level page
		'''
		self.file = file

		basename = file.basename
		if '.' in basename:
			basename, x = basename.rsplit('.')
		self.dir = file.dir.subdir(basename + '_files')
		self.relative_root = self.dir

		self.namespace = page

	def page_file(self, page):
		if page.isroot:
			raise PathLookupError('Can not export: %s', page)
		elif self.namespace \
		and not page == self.namespace \
		and not page.ischild(self.namespace):
			raise PathLookupError(
				'%s not a child of %s' % (page, self.namespace)
			)
		else:
			return self.file

