# -*- coding: utf8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import tests

from zim.index import Index, IndexPath
from zim.notebook import Path

class TestIndex(tests.TestCase):

	def testDB(self):
		index = Index(dbfile=':memory:')
		notebook = tests.get_test_notebook()
		manifest = notebook.testdata_manifest
		index.set_notebook(notebook)
		index.update()

		#~ cursor = index.db.cursor()
		#~ cursor.execute('select * from pages')
		#~ print '\n==== DB ===='
		#~ for row in cursor:
		#~ 	print row

		path = index.lookup_path(Path('Test:foo:bar'))
		self.assertTrue(isinstance(path, IndexPath))
		path = index.lookup_id(path.id)
		self.assertTrue(isinstance(path, IndexPath))
		self.assertEqual(path.name, 'Test:foo:bar')

