
# Copyright 2022 introt <introt@koti.fimnet.fi>

# based on original work (c) Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

from tests.mainwindow import setUpMainWindow

from zim.notebook.page import Page, Path
from zim.gui.mainwindow import PageWindow, WindowBaseMixin
from zim.plugins.windowtitleeditor import (
		WindowTitleEditorPlugin,
		WindowTitleEditorExtension,
		READONLY)

class TestWindowTitleEditorExtension(tests.TestCase):

	def setUp(self):
		""" Successful setup indicates the monkey patching was successful... """
		self.plugin = WindowTitleEditorPlugin()
		self.window = setUpMainWindow(self.setUpNotebook())
		self.extension = WindowTitleEditorExtension(self.plugin, self.window)

	def testMonkeyPatch(self):
		""" ...but we test it anyway :) """
		self.assertEqual(
				self.window._update_window_title,
				self.extension.update_window_title,
				"Patching main window failed!")
		self.assertEqual(PageWindow.set_title.__module__,
				self.window._update_window_title.__module__,
				"Patching PageWindow failed!")

	def get_title(self):
		# used twice, just think of the convenience!
		return self.window.get_title()

	def testMainWindowApi(self):
		self.window.set_title('test')
		self.assertEqual(self.get_title(), 'test', "Can't get/set title!")

	def testMakeTitleWithCustomTemplate(self):
		n = self.window.notebook
		n.readonly = True
		p = self.window.page
		self.plugin.preferences['custom_format'] = ' $path;$page;$title;$source;' + \
				'$notebook;$folder$$Zim$ro'
		self.plugin.preferences['format'] = 'custom'
		self.assertEqual(
				self.get_title(),
				f'Test;Test;Test;{p.source_file};' + \
						f'testnotebook;{n.folder}$Zim{READONLY}'.strip(),
				"Templating broke!"
		)

	def testTeardown(self):
		self.extension.teardown()
		self.assertEqual(
				PageWindow.set_title,
				WindowBaseMixin.set_title,
				"Restoring PageWindow failed!"
		)
		self.assertEqual(
				self.window._update_window_title.__func__,
				self.window.__class__._update_window_title,
				"Restoring main window failed!"
		)
