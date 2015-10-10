# -*- coding: utf-8 -*-

# Copyright 2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement


import tests

try:
	import gtkspell
except:
	gtkspell = None

try:
	import gtkspellcheck
except:
	gtkspellcheck = None


import zim.plugins.spell

from tests.gui import setupGtkInterface, Path


class TestSpell(object):

	def setUp(self):
		self._restore = (
			zim.plugins.spell.gtkspell,
			zim.plugins.spell.gtkspellcheck
		)

	def tearDown(self):
		zim.plugins.spell.gtkspell, zim.plugins.spell.gtkspellcheck = \
			self._restore

	def runTest(self, adapterclass):
		with tests.LoggingFilter(logger='zim.plugins.spell'): # Hide exceptions
			ui = setupGtkInterface(self)
			plugin = ui.plugins.load_plugin('spell')
			plugin.extend(ui.mainwindow)
			ext = plugin.get_extension(zim.plugins.spell.MainWindowExtension)

			self.assertIs(ext._adapter, adapterclass) # ensure switching library worked

			ext.toggle_spellcheck()
			ext.toggle_spellcheck()
			ext.toggle_spellcheck()

			ui.open_page(Path('Foo'))
			ui.open_page(Path('Bar'))
			ext.toggle_spellcheck()

			ui.open_page(Path('Foo'))
			ui.open_page(Path('Bar'))
			ext.toggle_spellcheck()

			# TODO check it actually shows on screen ...


@tests.skipIf(gtkspell is None, 'gtkspell not installed')
class TestGtkspell(TestSpell, tests.TestCase):

	def runTest(self):
		zim.plugins.spell.gtkspell = gtkspell
		zim.plugins.spell.gtkspellcheck = None
		TestSpell.runTest(self, zim.plugins.spell.GtkspellAdapter)


@tests.skipIf(gtkspellcheck is None, 'gtkspellcheck not installed')
class TestGtkspellchecker(TestSpell, tests.TestCase):

	def runTest(self):
		zim.plugins.spell.gtkspell = None
		zim.plugins.spell.gtkspellcheck = gtkspellcheck
		TestSpell.runTest(self, zim.plugins.spell.GtkspellcheckAdapter)
