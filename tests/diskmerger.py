
import tests

from zim.plugins import PluginManager
from zim.plugins.diskmerger import *

class TestMergerPlugin(tests.TestCase):
	def setUp(self):

		self.notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)
		plugin = PluginManager.load_plugin('diskmerger')


