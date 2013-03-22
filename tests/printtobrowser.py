# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

import zim.plugins
from zim.notebook import Path
from zim.config import ConfigDict


@tests.slowTest
class TestPrintToBrowser(tests.TestCase):

	def runTest(self):
		'Test PrintToBrowser plugin'
		ui = StubUI()
		pluginklass = zim.plugins.get_plugin('printtobrowser')
		plugin = pluginklass(ui)
		file = plugin.print_to_file(ui.page)
		self.assertTrue(file.exists())
		content = file.read()
		self.assertTrue('<h1>Foo</h1>' in content)


class StubUI(object):

	ui_type = 'stub'

	def __init__(self):
		self.notebook = tests.new_notebook()
		self.page = self.notebook.get_page(Path('Test:foo'))
		self.preferences = ConfigDict()
		self.uistate = ConfigDict()

	def connect(*a): pass

	def connect_after(*a): pass
