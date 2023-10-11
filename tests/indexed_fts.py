# coding=utf-8

import tests

from zim.plugins import PluginManager
from zim.plugins import indexed_fts

@tests.skipIf(
	indexed_fts.IndexedFTSPlugin.check_dependencies()[0] == False,
	"Indexed FTS plugin not available"
)
class TestIndexedFTS(tests.TestCase):

	def testIndexing(self):
		'''Check indexing of Indexed Full Text Search plugin'''
		plugin = PluginManager.load_plugin('indexed_fts')
		notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)

		notebook.index.check_and_update()

		# Only pages with content will actually be indexed, so
		# after indexing some should be FTS-indexed.
		self.assertNotEqual(
			notebook.index._db.execute(
				"SELECT count(*) FROM pages WHERE fts_id IS NOT NULL;"
			).fetchone()[0], 0
		)


