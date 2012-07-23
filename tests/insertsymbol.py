# -*- coding: utf-8 -*-

# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement

import tests

from tests.pageview import setUpPageView, press, UndoStackManager

from zim.config import ConfigDict

from zim.plugins.insertsymbol import *


ALPHA = unichr(945)
EACUTE = unichr(201)
ECIRC = unichr(202)
EGRAVE = unichr(200)


class TestInsertSymbolPlugin(tests.TestCase):

	def runTest(self):
		ui = MockUI()
		plugin = InsertSymbolPlugin(ui)
		plugin.finalize_ui(ui)

		pageview = ui.mainwindow.pageview
		textview = pageview.view
		buffer = textview.get_buffer()
		pageview.undostack = UndoStackManager(buffer)

		print '\n!! Two GtkWarnings expected here for gdk display !!'
		# Need a window to get the widget realized
		window = gtk.Window()
		window.add(pageview)
		pageview.realize()
		textview.realize()

		# insert on end-of-word with space
		press(textview, r'\alpha ')
		text = buffer.get_text(*buffer.get_bounds())
		self.assertEqual(text, ALPHA + ' ')

		# Check undo - first undo replace, then the insert space
		pageview.undo()
		text = buffer.get_text(*buffer.get_bounds())
		self.assertEqual(text, r'\alpha ')
		pageview.undo()
		text = buffer.get_text(*buffer.get_bounds())
		self.assertEqual(text, r'\alpha') # no trailing space

		# insert on end-of-word with ;
		buffer.clear()
		press(textview, r'\alpha;')
		text = buffer.get_text(*buffer.get_bounds())
		self.assertEqual(text, ALPHA) # no trailing space

		# no insert in code or pre section
		buffer.clear()
		pageview.toggle_format(VERBATIM)
		press(textview, r'\alpha ')
		text = buffer.get_text(*buffer.get_bounds())
		self.assertEqual(text, r'\alpha ') # no replace

		# test dialog
		def check_dialog(dialog):
			self.assertIsInstance(dialog, InsertSymbolDialog)
			dialog.iconview.item_activated((9,)) # path for 10th item in symbol list
			dialog.iconview.item_activated((10,)) # path for 11th item in symbol list
			dialog.iconview.item_activated((11,)) # path for 12th item in symbol list
			dialog.assert_response_ok()

		buffer.clear()
		with tests.DialogContext(check_dialog):
			plugin.insert_symbol()
		text = buffer.get_text(*buffer.get_bounds())
		self.assertEqual(text, EACUTE + ECIRC + EGRAVE)


class MockUI(tests.MockObject):

	ui_type = 'gtk'

	def __init__(self):
		tests.MockObject.__init__(self)
		self.preferences = ConfigDict()
		self.uistate = ConfigDict()
		self.mainwindow = tests.MockObject()
		self.mainwindow.pageview = setUpPageView()
		self.windows = []
