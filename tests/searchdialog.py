
# Copyright 2009-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>



import tests

from gi.repository import Gtk

from zim.notebook import Path

from zim.gui.searchdialog import SearchDialog


class testSearchDialog(tests.TestCase):

	def testResults(self):
		notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)
		page = None
		navigation = tests.MockObject()
		navigation.open_page = lambda page: tests.MockObject()

		dialog = SearchDialog(None, notebook, page, navigation)
		dialog.query_entry.set_text('Foo')
		dialog.query_entry.activate()
		model = dialog.results_treeview.get_model()
		self.assertTrue(len(model) > 3)

		col = dialog.results_treeview.get_column(0)
		dialog.results_treeview.row_activated(Gtk.TreePath((0,)), col)

	def testResultsInSection(self):
		# Results with "only search in section" enabled
		notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)
		page = notebook.get_page(Path('TaskList'))
		navigation = tests.MockObject()
		navigation.open_page = lambda page: tests.MockObject()

		dialog = SearchDialog(None, notebook, page, navigation)
		dialog.namespacecheckbox.set_active(True)
		dialog.query_entry.set_text('*fix*')
		dialog.query_entry.activate()
		model = dialog.results_treeview.get_model()
		self.assertTrue(len(model) > 1)

		col = dialog.results_treeview.get_column(0)
		dialog.results_treeview.row_activated(Gtk.TreePath((0,)), col)

	@tests.expectedFailure
	def testCancelSearch(self):
		# Start searching but cancel before it completes
		raise NotImplementedError
