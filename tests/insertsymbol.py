
# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>



import tests

from tests.mainwindow import setUpMainWindow
from tests.pageview import press

from zim.config import SectionedConfigDict, ConfigManager

from zim.plugins.insertsymbol import *


ALPHA = chr(945)
EACUTE = chr(201)
ECIRC = chr(202)
EGRAVE = chr(200)


class TestInsertSymbolPlugin(tests.TestCase):

	def runTest(self):
		plugin = InsertSymbolPlugin(ConfigManager())

		mainwindow = setUpMainWindow(self.setUpNotebook(content={'Test': ''}), path='Test')
		pageview = mainwindow.pageview
		textview = pageview.view
		buffer = textview.get_buffer()

		plugin.extend(mainwindow)

		# Widget needs to be realized
		pageview.realize()
		textview.realize()

		# insert on end-of-word with space
		press(textview, '\\alpha ')
		start, end = buffer.get_bounds()
		text = start.get_text(end)
		self.assertEqual(text, ALPHA + ' \n')

		# Check undo - first undo replace, then the insert space
		pageview.undo()
		start, end = buffer.get_bounds()
		text = start.get_text(end)
		self.assertEqual(text, '\\alpha \n')
		pageview.undo()
		start, end = buffer.get_bounds()
		text = start.get_text(end)
		self.assertEqual(text, '\\alpha\n') # no trailing space

		# insert on end-of-word with ;
		buffer.clear()
		press(textview, r'\alpha;')
		start, end = buffer.get_bounds()
		text = start.get_text(end)
		self.assertEqual(text, ALPHA) # no trailing space

		# no insert in code or pre section
		buffer.clear()
		pageview.toggle_format(VERBATIM)
		press(textview, r'\alpha ')
		start, end = buffer.get_bounds()
		text = start.get_text(end)
		self.assertEqual(text, r'\alpha ') # no replace

		# test dialog
		def check_dialog(dialog):
			self.assertIsInstance(dialog, InsertSymbolDialog)
			dialog.iconview.item_activated(Gtk.TreePath((9,))) # path for 10th item in symbol list
			dialog.iconview.item_activated(Gtk.TreePath((10,))) # path for 11th item in symbol list
			dialog.iconview.item_activated(Gtk.TreePath((11,))) # path for 12th item in symbol list
			dialog.assert_response_ok()

		buffer.clear()
		mainwindow_ext = plugin.get_extension(mainwindow, InsertSymbolMainWindowExtension)
		with tests.DialogContext(check_dialog):
			mainwindow_ext.insert_symbol()
		start, end = buffer.get_bounds()
		text = start.get_text(end)
		self.assertEqual(text, EACUTE + ECIRC + EGRAVE)
