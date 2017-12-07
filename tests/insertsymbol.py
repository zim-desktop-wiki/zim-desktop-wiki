# -*- coding: utf-8 -*-

# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement

import tests

from tests.pageview import setUpPageView, press

from zim.config import SectionedConfigDict, ConfigManager

from zim.plugins.insertsymbol import *


ALPHA = unichr(945)
EACUTE = unichr(201)
ECIRC = unichr(202)
EGRAVE = unichr(200)


class TestInsertSymbolPlugin(tests.TestCase):

	def runTest(self):
		plugin = InsertSymbolPlugin(ConfigManager())

		pageview = setUpPageView(self.setUpNotebook(content=tests.FULL_NOTEBOOK))
		textview = pageview.view
		buffer = textview.get_buffer()

		mainwindow = tests.MockObject()
		mainwindow.pageview = pageview
		mainwindow.uimanager = tests.MockObject()

		plugin.extend(mainwindow, 'MainWindow')

		# Need a window to get the widget realized
		window = Gtk.Window()
		window.add(pageview)
		pageview.realize()
		textview.realize()

		# insert on end-of-word with space
		press(textview, '\\alpha ')
		start, end = buffer.get_bounds()
		text = start.get_text(end).decode('UTF-8')
		self.assertEqual(text, ALPHA + ' \n')

		# Check undo - first undo replace, then the insert space
		pageview.undo()
		start, end = buffer.get_bounds()
		text = start.get_text(end).decode('UTF-8')
		self.assertEqual(text, '\\alpha \n')
		pageview.undo()
		start, end = buffer.get_bounds()
		text = start.get_text(end).decode('UTF-8')
		self.assertEqual(text, '\\alpha\n') # no trailing space

		# insert on end-of-word with ;
		buffer.clear()
		press(textview, r'\alpha;')
		start, end = buffer.get_bounds()
		text = start.get_text(end).decode('UTF-8')
		self.assertEqual(text, ALPHA) # no trailing space

		# no insert in code or pre section
		buffer.clear()
		pageview.toggle_format(VERBATIM)
		press(textview, r'\alpha ')
		start, end = buffer.get_bounds()
		text = start.get_text(end).decode('UTF-8')
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
		text = start.get_text(end).decode('UTF-8')
		self.assertEqual(text, EACUTE + ECIRC + EGRAVE)
