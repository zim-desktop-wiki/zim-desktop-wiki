
# Copyright 2020 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

from zim.import_files import *
from zim.notebook import Path, PageNotAvailableError
from zim.notebook.index import IndexNotFoundError


class TestImportFile(tests.TestCase):

	def setUp(self):
		self.notebook = self.setUpNotebook(content={'Existing_page': 'Existing 123\n'}, mock=tests.MOCK_DEFAULT_REAL)
		self.notebook.folder.file('Not_yet_a_page.txt').write('Existing file 123\n')
		self.folder = self.setUpFolder('external', mock=tests.MOCK_DEFAULT_REAL)

	def testImportFile(self):
		# If the to-be-imported file is outside the notebook, it should
		# be imported without touching the original
		file = self.folder.file('input.txt')
		file.write('Imported 123\n')
		path = Path('New_page')
		page1 = import_file(file, self.notebook, path)
		self.assertEqual(page1, path)
		self.assertEqual(file.read(), 'Imported 123\n')
		page = self.notebook.get_page(path)
		self.assertTrue(page.exists and page.hascontent)
		self.assertEqual(page.dump('wiki'), ['Imported 123\n'])

	def testImportFileExistingPage(self):
		# If the target page already exists, import to a new page instead
		file = self.folder.file('input.txt')
		file.write('Imported 123\n')
		path = Path('Existing_page')
		page = self.notebook.get_page(path)
		page1 = import_file(file, self.notebook, path)
		self.assertNotEqual(page1, path)
		file = self.notebook.folder.file('Not_yet_a_page.txt').write('Existing file 123\n')

		self.assertEqual(page.dump('wiki'), ['Existing 123\n'])
		self.assertEqual(page1.dump('wiki'), ['Imported 123\n'])

	def testImportFileExistingFile(self):
		# If the target source file already exists (but is not a page)
		# and the to-be-imported file is a diffferent file, import to a new page instead
		file = self.folder.file('input.txt')
		file.write('Imported 123\n')
		path = Path('Not_yet_a_page')
		with self.assertRaises(PageNotAvailableError):
			page = self.notebook.get_page(path)
		page1 = import_file(file, self.notebook, path)
		self.assertNotEqual(page1, path)
		self.assertEqual(page1.dump('wiki'), ['Imported 123\n'])

		file = self.notebook.folder.file('Not_yet_a_page.txt')
		self.assertEqual(file.read(), 'Existing file 123\n')

	def testImportFileConvertFile(self):
		# If the to-be-imported file is within the notebook, it should
		# be converted to a page and move the original to a backup file
		file = self.notebook.folder.file('Not_yet_a_page.txt')
		path = Path('Not yet a page')

		# Ensure file is not seen as a page by the notebook
		with self.assertRaises(PageNotAvailableError):
			page = self.notebook.get_page(path)
		with self.assertRaises(IndexNotFoundError):
			indexpath = self.notebook.pages.lookup_by_pagename(path)

		# Do import
		page1 = import_file(file, self.notebook, path)

		# Ensure the file is converted "in place" and is now seen as a page
		self.assertEqual(page1, path)
		self.assertEqual(page1.dump('wiki'), ['Existing file 123\n'])
		indexpath = self.notebook.pages.lookup_by_pagename(path)
		self.assertTrue(indexpath.exists)
		self.assertTrue(indexpath.hascontent)

		# Ensure backup is made of original file
		file1 = self.notebook.folder.file('Not_yet_a_page.txt~')
		self.assertEqual(file1.read(), 'Existing file 123\n')

	def testImportFileConvertFileConflict(self):
		# Test behavior if there is an existing backup file
		self.notebook.folder.file('Not_yet_a_page.txt~').write('Some other file 123\n')
		file = self.notebook.folder.file('Not_yet_a_page.txt')
		path = Path('Not_yet_a_page')
		with self.assertRaises(PageNotAvailableError):
			page = self.notebook.get_page(path)
		page1 = import_file(file, self.notebook, path)
		self.assertEqual(page1, path)
		self.assertEqual(page1.dump('wiki'), ['Existing file 123\n'])
		file1 = self.notebook.folder.file('Not_yet_a_page.txt~')
		self.assertEqual(file1.read(), 'Some other file 123\n')
		file2 = self.notebook.folder.file('Not_yet_a_page001.txt~')
		self.assertEqual(file2.read(), 'Existing file 123\n')
