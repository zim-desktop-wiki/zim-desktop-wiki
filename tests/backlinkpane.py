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

	def _getBackLinkTexts(self, name, content, show_full_paths=False):
		notebook = self.setUpNotebook(name=name, content=content)
		plugin = PluginManager.load_plugin('backlinkpane')
		plugin.preferences['show_full_paths'] = show_full_paths
		widget = BackLinksWidget(tests.MockObject(), plugin.preferences)
		widget.set_page(notebook, Path('Foo'))
		model = widget.treeview.get_model()
		return [row[TEXT_COL] for row in model]

	def testShowsBackLinks(self):
		model = self.widget.treeview.get_model()
		self.assertEqual([row[TEXT_COL] for row in model], ['Test'])

	def testBackLinksNaturalSorted(self):
		texts = self._getBackLinkTexts('backlinkpane-sorted', {
			'Foo': 'Test page\n',
			'Page10': 'Link to [[Foo]]\n',
			'Page9': 'Link to [[Foo]]\n',
			'page2': 'Link to [[Foo]]\n',
			'Alpha': 'Link to [[Foo]]\n',
		})
		self.assertEqual(texts, ['Alpha', 'page2', 'Page9', 'Page10'])

	def testBackLinksNaturalSortedFullPaths(self):
		texts = self._getBackLinkTexts('backlinkpane-sorted-fullpaths', {
			'Foo': 'Test page\n',
			'Page10': 'Link to [[Foo]]\n',
			'Page9': 'Link to [[Foo]]\n',
			'page2': 'Link to [[Foo]]\n',
			'Alpha': 'Link to [[Foo]]\n',
			'Other:Child': 'Link to [[Foo]]\n',
		}, show_full_paths=True)
		self.assertEqual(texts, ['Alpha', 'Other:Child', 'page2', 'Page9', 'Page10'])

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
