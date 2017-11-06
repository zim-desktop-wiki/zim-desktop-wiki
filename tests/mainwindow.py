# -*- coding: utf-8 -*-

# Copyright 2009-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

from tests.gui import newSetupGtkInterface, setupGtkInterface

from zim.notebook import Path

import zim.gui

is_sensitive = lambda w: w.get_property('sensitive')


class TestHistoryNavigation(tests.TestCase):

	def runTest(self):
		pages = [Path('page1'), Path('page2'), Path('page3'), Path('page4')]
		notebook = self.setUpNotebook(content=pages)

		ui = newSetupGtkInterface(self, notebook=notebook)
		window = ui._mainwindow # XXX
		history = ui.history
		historylist = history._history # XXX

		back_action = window.actiongroup.get_action('open_page_back')
		forward_action = window.actiongroup.get_action('open_page_forward')

		# Setup history
		self.assertFalse(is_sensitive(back_action))
		self.assertFalse(is_sensitive(forward_action))
		for i, p in enumerate(pages):
			window.open_page(p)
			self.assertEqual(is_sensitive(back_action), i > 0)
			self.assertFalse(is_sensitive(forward_action))

		self.assertEqual([p.name for p in historylist], [p.name for p in pages])
		p = history.get_current()
		self.assertEqual(p.name, pages[-1].name)

		# Navigate backward
		while is_sensitive(back_action):
			window.open_page_back()
			self.assertTrue(is_sensitive(forward_action))

		self.assertEqual([p.name for p in historylist], [p.name for p in pages])
		p = history.get_current()
		self.assertEqual(p.name, pages[0].name)

		# Navigate forward
		while is_sensitive(forward_action):
			window.open_page_forward()
			self.assertTrue(is_sensitive(back_action))

		self.assertEqual([p.name for p in historylist], [p.name for p in pages])
		p = history.get_current()
		self.assertEqual(p.name, pages[-1].name)


class TestUpDownNavigation(tests.TestCase):

	@tests.expectedFailure
	def runTest(self):
		raise NotImplementedError


class TestTogglingState(tests.TestCase):

	def setUp(self):
		self.ui = setupGtkInterface(self)

	def runTest(self):
		path = Path('Test:foo:bar')
		window = self.ui._mainwindow # XXX

		self.assertTrue(window.uistate['show_menubar'])
		window.toggle_menubar()
		self.assertFalse(window.uistate['show_menubar'])
		window.toggle_menubar()
		self.assertTrue(window.uistate['show_menubar'])

		self.assertTrue(window.uistate['show_toolbar'])
		window.toggle_toolbar()
		self.assertFalse(window.uistate['show_toolbar'])
		window.toggle_toolbar()
		self.assertTrue(window.uistate['show_toolbar'])

		self.assertTrue(window.uistate['show_statusbar'])
		window.toggle_statusbar()
		self.assertFalse(window.uistate['show_statusbar'])
		window.toggle_statusbar()
		self.assertTrue(window.uistate['show_statusbar'])

		self.assertTrue(window.uistate['left_pane'][0])
		window.toggle_panes()
		self.assertFalse(window.uistate['left_pane'][0])
		window.toggle_panes()
		self.assertTrue(window.uistate['left_pane'][0])

		# note: no default style here - system default unknown
		for style in (
			zim.gui.TOOLBAR_ICONS_AND_TEXT,
			zim.gui.TOOLBAR_ICONS_ONLY,
			zim.gui.TOOLBAR_TEXT_ONLY,
		):
			window.set_toolbar_style(style)
			self.assertEqual(window.preferences['toolbar_style'], style)

		# note: no default style here - system default unknown
		for size in (
			zim.gui.TOOLBAR_ICONS_LARGE,
			zim.gui.TOOLBAR_ICONS_SMALL,
			zim.gui.TOOLBAR_ICONS_TINY,
		):
			window.set_toolbar_icon_size(size)
			self.assertEqual(window.preferences['toolbar_size'], size)

		# FIXME: test fails because "readonly" not active because notebook was already readonly, so action never activatable
		#~ self.assertTrue(ui.readonly)
		#~ self.assertTrue(window.uistate['readonly'])
		#~ window.toggle_readonly()
		#~ self.assertFalse(ui.readonly)
		#~ self.assertFalse(window.uistate['readonly'])
		#~ window.toggle_readonly()
		#~ self.assertTrue(ui.readonly)
		#~ self.assertTrue(window.uistate['readonly'])



class TestSavingPages(tests.TestCase):

	def setUp(self):
		self.ui = setupGtkInterface(self)

	def testSave(self):
		'''Test saving a page from the interface'''
		self.ui._mainwindow.toggle_readonly(False)
		self.ui._mainwindow.open_page(Path('Non-exsiting:page'))
		self.assertFalse(self.ui.page.exists())
		self.assertIsNone(self.ui.page.get_parsetree())
		self.assertTrue(self.ui._mainwindow.pageview._showing_template) # XXX check HACK
		self.ui._mainwindow.pageview.save_page()
		self.assertTrue(self.ui.page.exists())
		self.assertIsNotNone(self.ui.page.get_parsetree())
		self.assertFalse(self.ui._mainwindow.pageview._showing_template) # XXX check HACK

	def testClosePage(self):
		# Specific bug found when trying to close the page while auto-save
		# in progress, test it here
		self.ui._mainwindow.pageview.view.get_buffer().insert_at_cursor('...')
		self.ui._mainwindow.pageview._save_page_handler.try_save_page()
		self.assertTrue(self.ui.page.modified)
		self.ui._mainwindow.destroy()
		self.assertFalse(self.ui.page.modified)
