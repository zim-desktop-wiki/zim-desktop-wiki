import tests

from zim.import_files import import_file
from zim.notebook import Path

import logging

logger = logging.getLogger('tests.page_identifier')

class TestPageIdentifier(tests.TestCase):

	def setUp(self):
		# Notebook to be used.
		self.notebook = self.setUpNotebook(
			content = { 'Existing_page': 'Existing 123\n' },
			mock = tests.MOCK_DEFAULT_REAL
		)

		# External folder.
		self.folder = self.setUpFolder(
			'external',
			mock=tests.MOCK_DEFAULT_REAL
		)


	# An imported file should have gained a page identifier.
	def testImportFileYieldsPageIdentifier(self):
		file_to_import = self.folder.file( 'new-page.txt')
		file_to_import.write( 'New page!\n')

		# Import file.
		path = Path( 'NewPage')
		import_file(file_to_import, self.notebook, path)

		# Retrieve.
		page = self.notebook.get_page(path)
		
		# Test.
		self.assertFalse(page.page_identifier is None, 'An imported page should have an page identifier.')


	# An imported file already in Zim-format, holding a page identifier
	# which corresponds with an identifier already in the database, causes
	# the removal of the identifier registered with the existing page.
	# The imported file keeps its idenfifier.
	def testImportFileWithPageSameIdentifierAsExistingFile(self):
		file_to_import = self.folder.file( 'new-page.txt')
		file_to_import.write( 
			'Content-Type: text/x-zim-wiki\n' +
		    'Wiki-Format: zim 0.6\n' +
			'Page-Identifier: 00000000-0000-0000-0000-000000000001\n' +
			'\n' +
			'New page!\n'
		)

		# First file.
		path1 = Path('NewPage1')
		import_file(file_to_import, self.notebook, path1, 'wiki')

		# Second file.
		path2 = Path('NewPage2')
		import_file(file_to_import, self.notebook, path2, 'wiki')

		# Retrieve.
		page1 = self.notebook.get_page(path1)
		page2 = self.notebook.get_page(path2)
		
		# Test.
		self.assertTrue(page1.page_identifier is None, 'A page with the same identifier as an imported one gets its identifier deleted.')
		self.assertTrue(page2.page_identifier == '00000000-0000-0000-0000-000000000001', 'An imported file with a page identifier which is already known should get a new one.')


	# An imported file already in Zim-format, holding a page identifier,
	# should have that same page identifier after importing.
	def testImportFileWithPageIdentifierYieldsPageWithThatSamePageIdentifier(self):
		file_to_import = self.folder.file( 'new-page.txt')
		file_to_import.write( 
			'Content-Type: text/x-zim-wiki\n' +
		    'Wiki-Format: zim 0.6\n' +
			'Page-Identifier: 00000000-0000-0000-0000-000000000001\n' +
			'\n' +
			'New page!\n'
		)

		# Import file.
		path = Path('NewPage')
		import_file(file_to_import, self.notebook, path, 'wiki')

		# Retreive.
		page = self.notebook.get_page(path)
		
		# Test.
		self.assertFalse(page.page_identifier is None, 'An imported page should have an page identifier.')
		self.assertTrue(page.page_identifier == '00000000-0000-0000-0000-000000000001')
		
		
	# A page identifier can be used to retrieve a page.
	def testImportedFileCanBeRetreivedViaPageIdentifier(self):
		file_to_import = self.folder.file( 'new-page.txt')
		file_to_import.write( 
			'Content-Type: text/x-zim-wiki\n' +
		    'Wiki-Format: zim 0.6\n' +
			'Page-Identifier: 00000000-0000-0000-0000-000000000001\n' +
			'\n' +
			'New page!\n'
		)

		# Import file.
		path = Path('NewPage')
		import_file(file_to_import, self.notebook, path, 'wiki')
		
		page1 = self.notebook.pages.lookup_by_page_identifier( '00000000-0000-0000-0000-000000000001' )
		page2 = self.notebook.pages.lookup_by_page_identifier( '00000000-0000-0000-0000-000000000000' )
		
		self.assertFalse(page1 is None, 'A page should be retrievable via its page identifier.')
		self.assertTrue(page2 is None, 'An unknown page identifier should yield "None".')
		self.assertTrue(page1.page_identifier() == '00000000-0000-0000-0000-000000000001', 'Page identifier can be retrieved via property.')
		
	def testModifyPageIdentifierOfPageYieldsModifieddatabase(self):
		file_to_import = self.folder.file( 'new-page.txt')
		file_to_import.write( 
			'Content-Type: text/x-zim-wiki\n' +
		    'Wiki-Format: zim 0.6\n' +
			'Page-Identifier: 00000000-0000-0000-0000-000000000001\n' +
			'\n' +
			'New page!\n'
		)

		# Import file.
		path = Path('NewPage')
		page = import_file(file_to_import, self.notebook, path, 'wiki')
		
		# Fetch record.
		pageRecord = self.notebook.pages.lookup_by_page_identifier( '00000000-0000-0000-0000-000000000001' )

		# Test.
		self.assertTrue(pageRecord.page_identifier() == '00000000-0000-0000-0000-000000000001', 'Page should be able to be looked up by page identifier.')
		
		# Change page identifier.
		page.set_page_identifier('00000000-0000-0000-0000-000000000002' )
		self.notebook.store_page(page)
		
		# Retrieve using new page identifier.
		pageRecord = self.notebook.pages.lookup_by_page_identifier( '00000000-0000-0000-0000-000000000002' )
		
		# Test.
		self.assertTrue(pageRecord.page_identifier() == '00000000-0000-0000-0000-000000000002', 'When changing the page identifier, this should result in being able to find the page using the new page identifier.')