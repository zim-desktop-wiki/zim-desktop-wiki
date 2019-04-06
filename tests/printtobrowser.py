
# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

from zim.plugins import PluginManager
from zim.notebook import Path


@tests.slowTest
class TestPrintToBrowser(tests.TestCase):

	def runTest(self):
		'Test PrintToBrowser plugin'
		pluginklass = PluginManager.get_plugin_class('printtobrowser')
		plugin = pluginklass()

		notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)
		page = notebook.get_page(Path('Test:foo'))
		file = plugin.print_to_file(notebook, page)
		self.assertTrue(file.exists())
		content = file.read()
		self.assertTrue('<h1>Foo</h1>' in content)
