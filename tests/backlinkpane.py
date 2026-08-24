import tests

from gi.repository import Gtk

from zim.notebook import Path
from zim.plugins import PluginManager

from zim.plugins.backlinkpane import BackLinksWidget, TEXT_COL


class TestBackLinksWidget(tests.TestCase):

	def setUp(self):
		self.notebook = self.setUpNotebook(content={
			'Test': 'Link to [[Foo]]\n',
			'Foo': 'Test page\n',
		})
		plugin = PluginManager.load_plugin('backlinkpane')
		self.widget = BackLinksWidget(tests.MockObject(), plugin.preferences)
		self.widget.set_page(self.notebook, Path('Foo'))

	def testShowsBackLinks(self):
		model = self.widget.treeview.get_model()
		self.assertEqual([row[TEXT_COL] for row in model], ['Test'])

	def testContextMenuHasPageActions(self):
		# Used to be a single hard-coded "Open in New Window" item
		treeview = self.widget.treeview
		treeview.get_selection().select_path(Gtk.TreePath((0,)))
		menu = treeview.get_popup()
		self.assertIsInstance(menu, Gtk.Menu)
		self.assertGreater(len(menu.get_children()), 1)

	def testNoContextMenuWithoutSelection(self):
		treeview = self.widget.treeview
		treeview.get_selection().unselect_all()
		self.assertIsNone(treeview.get_popup())
