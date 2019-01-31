
# Copyright 2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>




import tests

try:
	import gi
	gi.require_version('GtkSpell', '3.0')
	from gi.repository import GtkSpell as gtkspell
except:
	gtkspell = None

try:
	import gtkspellcheck
except:
	gtkspellcheck = None


import zim.plugins.spell

from zim.plugins import find_extension, PluginManager
from zim.notebook import Path

from tests.mainwindow import setUpMainWindow


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
			window = setUpMainWindow(self.setUpNotebook(content=('Test', 'Foo', 'Bar')))

			plugin = PluginManager.load_plugin('spell')
			ext = find_extension(window.pageview, zim.plugins.spell.SpellPageViewExtension)

			self.assertIs(ext._adapter_cls, adapterclass) # ensure switching library worked

			ext.toggle_spellcheck()
			ext.toggle_spellcheck()
			ext.toggle_spellcheck()

			window.open_page(Path('Foo'))
			window.open_page(Path('Bar'))
			ext.toggle_spellcheck()

			window.open_page(Path('Foo'))
			window.open_page(Path('Bar'))
			#ext.toggle_spellcheck()

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
