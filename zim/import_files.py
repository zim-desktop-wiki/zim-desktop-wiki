
# Copyright 2020-2023 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# This module contains functions to import text files into a zim
# notebook

# TODO:
# - implement import_folder
# - autodetect format to import from
# - import attachments as well as pages (incl. filter to force e.g. txt as attachment)


import logging

from zim.newfs import File
from zim.notebook.page import Path


logger = logging.getLogger('zim')


def _page_name_from_file(file):
	name = file.basename
	if '.' in name:
		name, e = name.rsplit('.', 1) # remove extension, .txt / .md / ...
	return Path.makeValidPageName(name)


def import_file_from_user_input(file, notebook, path=None, format='wiki'):
	'''Wrapper for L{import_file()} which handles sanatizing user input
	Imports a single file or folder to a given notebook location
	@param file: file or folder object to be imported
	@notebook: notebook object
	@path: **target** notebook path, if C{None} import in top-level
	@returns: imported page object
	'''
	if path is None:
		path = Path(_page_name_from_file(file))
	else:
		path = notebook.pages.lookup_from_user_input(path.name)

	return import_file(file, notebook, path)


def import_files_from_user_input(files, notebook, path=None, format='wiki'):
	'''Wrapper for L{import_file() and L{import_folder()} which handles sanatizing user input
	Imports multiple files or folders as children of a given notebook location
	@param files: sequence of file or folder objects to be imported
	@notebook: notebook object
	@path: **parent** notebook path, if C{None} import into the top-level
	'''
	if path is None:
		path = Path(':')
	else:
		path = notebook.pages.lookup_from_user_input(path.name)

	for f in files:
		p = path + _page_name_from_file(f)
		if isinstance(f, File):
			import_file(f, notebook, p, format)
		else:
			import_folder(f, notebook, p, format)


def import_file(file, notebook, path, format='wiki'):
	'''Import a file into a zim notebook page
	@param file: a L{File} object to import from
	@param notebook: a L{Notebook} object to import into
	@param path: the L{Path} to import to within the notebook
	@returns: the L{Page} object for the imported page, this may be a different
	page than the one C{path} is pointing - see L{notebook.get_new_page()}
	'''
	logging.debug('Import file "%s" to "%s" as %s', file, path, format)
	if not file.istext:
		raise ValueError('Not a text file: %s' % file.path)

	if file.ischild(notebook.folder):
		newfile = file.parent().new_file(file.basename + '~')
		file.moveto(newfile)
		file = newfile

	page = notebook.get_new_page(path)
	assert not page.exists()

	page.parse(format, file.readlines())
	notebook.store_page(page)
	return page


def import_folder(folder, notebook, path, filter=None, format='wiki'):
	'''Import a folder recursively
	@param folder: a L{Folder} object to import from
	@param notebook: a L{Notebook} object to import into
	@param path: the L{Path} to import to within the notebook
	@param filter: optional filter function to decide which files and folder
	to import when scanning C{folder}. Will be given each file or folder found
	when scanning C{folder} and expected to return boolean whether to import
	yes or no.
	'''
	# Preserve folder / sub-folder names when creating target paths
	raise NotImplementedError
