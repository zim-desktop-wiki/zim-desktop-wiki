
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
from tests.pageview import TextBufferTestCaseMixin


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


class TestReplaceWordWithFormatting(TextBufferTestCaseMixin, tests.TestCase):

	# Since spell checker is hard to trigger from test, copied relevant code from:
	# https://github.com/koehlma/pygtkspellcheck/blob/4a77ccea2e892d0379a31a66b0a863782a2ca44b/src/gtkspellcheck/spellcheck.py#L598
	def replace_word(self, buffer, start, end, new_word):
		offset = start.get_offset()
		buffer.begin_user_action()
		buffer.delete(start, end)
		buffer.insert(buffer.get_iter_at_offset(offset), new_word)
		buffer.end_user_action()

	def runTest(self):
		# Ensure that replacing a word the formatting is preserved
		buffer = self.get_buffer(
			'<strong>mispelld</strong>\n'
			'<emphasis>here misplled here as well</emphasis>\n\n'
		)
		new_word = "misspelled"
		start, end = buffer.get_iter_at_offset(0), buffer.get_iter_at_offset(8)
		self.replace_word(buffer, start, end, new_word)
		self.assertBufferEquals(buffer,
			'<strong>misspelled</strong>\n'
			'<emphasis>here misplled here as well</emphasis>\n\n'
		)
		start, end = buffer.get_iter_at_offset(16), buffer.get_iter_at_offset(24)
		self.replace_word(buffer, start, end, new_word)
		self.assertBufferEquals(buffer,
			'<strong>misspelled</strong>\n'
			'<emphasis>here misspelled here as well</emphasis>\n\n'
		)
