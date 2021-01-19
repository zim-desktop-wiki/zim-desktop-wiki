
# Copyright 2020 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# This module contains functions to import text files into a zim
# notebook

import logging


logger = logging.getLogger('zim')


def import_file(file, notebook, path, format='wiki'):
	'''Import a file into a zim notebook page
	@param file: a L{File} object to import from
	@param notebook: a L{Notebook} object to import into
	@param path: the L{Path} to import to within the notebook
	@returns: the L{Page} object for the imported page, this may be a different
	page than the one C{path} is pointing - see L{notebook.get_new_page()}
	'''
	logging.debug('Import file "%s" to "%s" as %s', file, path, format)
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
	raise NotImplementedError
