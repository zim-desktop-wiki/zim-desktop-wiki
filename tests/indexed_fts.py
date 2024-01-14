# coding=utf-8

import tests

from zim.plugins import PluginManager

class TestIndexedFTS(tests.TestCase):

	def testIndexing(self):
		'''Check indexing of Indexed Full Text Search plugin'''
		plugin = PluginManager.load_plugin('indexed_fts')
		notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)

		notebook.index.check_and_update()

		# One page will never be indexed: the root page
		self.assertNotEqual(
			notebook.index._db.execute(
				"SELECT count(*) FROM pages WHERE fts_id IS NOT NULL;"
			).fetchone()[0], 0
		)


