# -*- coding: utf-8 -*-

# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

from zim.plugins.tableofcontents import *

@tests.slowTest
class TestTableOfContents(tests.TestCase):

	def setUp(self):
		self.ui = tests.MockObject()
		self.ui.page = None
		self.ui.notebook = tests.new_notebook()

	def runTest(self):
		'''Test Tabel Of Contents plugin'''

		widget = ToCWidget(self.ui)

		def count():
			# Count number of rows in TreeModel
			model = widget.treeview.get_model()
			rows = []
			def c(model, path, iter):
				rows.append(model[iter])
			model.foreach(c)
			return len(rows)

		page = self.ui.notebook.get_page(Path('Test:wiki'))
		widget.on_open_page(self.ui, page, page)
		self.assertTrue(count() > 2)
		widget.on_stored_page(self.ui.notebook, page)
		self.assertTrue(count() > 2)

		emptypage = tests.MockObject()
		widget.on_open_page(self.ui, emptypage, emptypage)
		self.assertTrue(count() == 0)
		widget.on_stored_page(self.ui.notebook, emptypage)
		self.assertTrue(count() == 0)

		for page in self.ui.notebook.walk():
			widget.on_open_page(self.ui, page, page)
			widget.on_stored_page(self.ui.notebook, page)

# TODO check selecting heading in actual PageView
# especially test selecting a non-existing item to check we don't get infinite loop
