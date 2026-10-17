import tests

from gi.repository import Gtk

from zim.notebook import Path, LINK_DIR_BACKWARD
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

	def testBackLinksNaturalSortedRelativePaths(self):
		# Sorting should be on the visible text: 'Foo:Adam' is shown as
		# '+Adam' and so comes before 'Eve', although by full page name
		# it would come after
		texts = self._getBackLinkTexts('backlinkpane-sorted-relativepaths', {
			'Foo': 'Test page\n',
			'Eve': 'Link to [[Foo]]\n',
			'Foo:Adam': 'Link to [[Foo]]\n',
		})
		self.assertEqual(texts, ['+Adam', 'Eve'])

	def testSortAlphabeticallyByDefault(self):
		self.assertTrue(self.widget.uistate['sort_alphabetically'])

	def testSortAlphabeticallyOption(self):
		notebook = self.setUpNotebook(name='backlinkpane-sorting', content={
			'Foo': 'Test page\n',
			'Page10': 'Link to [[Foo]]\n',
			'Page9': 'Link to [[Foo]]\n',
			'page2': 'Link to [[Foo]]\n',
			'Alpha': 'Link to [[Foo]]\n',
		})
		plugin = PluginManager.load_plugin('backlinkpane')
		plugin.preferences['show_full_paths'] = True
		widget = BackLinksWidget(tests.MockObject(), plugin.preferences)

		index_order = [
			str(link.source)
			for link in notebook.links.list_links(Path('Foo'), LINK_DIR_BACKWARD)
		]
		sorted_order = ['Alpha', 'page2', 'Page9', 'Page10']
		self.assertNotEqual(index_order, sorted_order)
			# Guard: the test would be meaningless when both orders match

		widget.uistate['sort_alphabetically'] = False
		widget.set_page(notebook, Path('Foo'))
		model = widget.treeview.get_model()
		self.assertEqual([row[TEXT_COL] for row in model], index_order)

		widget.uistate['sort_alphabetically'] = True
		widget.set_page(notebook, Path('Foo'))
		model = widget.treeview.get_model()
		self.assertEqual([row[TEXT_COL] for row in model], sorted_order)

	def testToggleSortAlphabetically(self):
		notebook = self.setUpNotebook(name='backlinkpane-toggle-sorting', content={
			'Foo': 'Test page\n',
			'Page10': 'Link to [[Foo]]\n',
			'Page9': 'Link to [[Foo]]\n',
			'page2': 'Link to [[Foo]]\n',
			'Alpha': 'Link to [[Foo]]\n',
		})
		plugin = PluginManager.load_plugin('backlinkpane')
		plugin.preferences['show_full_paths'] = True
		widget = BackLinksWidget(tests.MockObject(), plugin.preferences)
		widget.set_page(notebook, Path('Foo'))

		treeview = widget.treeview
		treeview.get_selection().select_path(Gtk.TreePath((0,)))
		menu = treeview.get_popup()
		item = tests.gtk_get_menu_item(menu, _('Sort alphabetically'))
		self.assertIsInstance(item, Gtk.CheckMenuItem)
		self.assertTrue(item.get_active())

		item.activate()
		self.assertFalse(widget.uistate['sort_alphabetically'])

		index_order = [
			str(link.source)
			for link in notebook.links.list_links(Path('Foo'), LINK_DIR_BACKWARD)
		]
		model = treeview.get_model()
		self.assertEqual([row[TEXT_COL] for row in model], index_order)

	def testContextMenuHasPageActions(self):
		# Used to be a single hard-coded "Open in New Window" item
		treeview = self.widget.treeview
		treeview.get_selection().select_path(Gtk.TreePath((0,)))
		menu = treeview.get_popup()
		self.assertIsInstance(menu, Gtk.Menu)
		self.assertGreater(len(menu.get_children()), 1)

	def testContextMenuWithoutSelectionHasOnlySortItem(self):
		treeview = self.widget.treeview
		treeview.get_selection().unselect_all()
		menu = treeview.get_popup()
		self.assertIsInstance(menu, Gtk.Menu)
		items = menu.get_children()
		self.assertEqual(len(items), 1)
		self.assertIsInstance(items[0], Gtk.CheckMenuItem)
