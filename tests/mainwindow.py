
# Copyright 2009-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>



import tests

from zim.notebook import Path
from zim.plugins import PluginManager

from zim.gui.mainwindow import *


is_sensitive = lambda w: w.get_property('sensitive')


def setUpMainWindow(notebook, path='Test', plugins=None):
	if isinstance(path, str):
		path = Path(path)

	mainwindow = MainWindow(notebook, page=path)
	mainwindow.__pluginmanager__ = plugins or PluginManager()
	mainwindow.init_uistate() # XXX
	return mainwindow


class TestHistoryNavigation(tests.TestCase):

	def runTest(self):
		pages = [Path('page1'), Path('page2'), Path('page3'), Path('page4')]
		notebook = self.setUpNotebook(content=pages)

		window = setUpMainWindow(notebook, path=pages[0])
		history = window.history
		historylist = history._history # XXX

		back_action = window.actiongroup.get_action('open_page_back')
		forward_action = window.actiongroup.get_action('open_page_forward')

		# Setup history
		self.assertFalse(is_sensitive(back_action))
		self.assertFalse(is_sensitive(forward_action))
		for i, p in enumerate(pages[1:]):
			window.open_page(p)
			self.assertTrue(is_sensitive(back_action))
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

	def testUpDown(self):
		pages = (
			'A',
			'A:B',
			'A:B:C',
			'D',
		)
		window = setUpMainWindow(self.setUpNotebook(content=pages), path='A')
		child_action = window.actiongroup.get_action('open_page_child')
		parent_action = window.actiongroup.get_action('open_page_parent')
		historylist = window.history._history # XXX

		while is_sensitive(child_action):
			window.open_page_child()

		self.assertEqual([p.name for p in historylist], ['A', 'A:B', 'A:B:C'])

		while is_sensitive(parent_action):
			window.open_page_parent()

		self.assertEqual([p.name for p in historylist], ['A', 'A:B', 'A:B:C', 'A:B', 'A'])

	def testDownHistory(self):
		pages = (
			'A',
			'A:B',
			'A:C'
		)
		window = setUpMainWindow(self.setUpNotebook(content=pages), path='A')

		self.assertEqual(window.page, Path('A'))
		window.open_page_child()
		self.assertEqual(window.page, Path('A:B'))

		window.open_page(Path('A:C'))
		window.open_page(Path('A'))

		self.assertEqual(window.page, Path('A'))
		window.open_page_child()
		self.assertEqual(window.page, Path('A:C'))


class TestPreviousNextNavigation(tests.TestCase):

	def runTest(self):
		pages = (
			'A',
			'A:B1',
			'A:B2',
			'B',
		)
		window = setUpMainWindow(self.setUpNotebook(content=pages), path='A')
		next_action = window.actiongroup.get_action('open_page_next')
		previous_action = window.actiongroup.get_action('open_page_previous')
		historylist = window.history._history # XXX

		while is_sensitive(next_action):
			window.open_page_next()

		self.assertEqual([p.name for p in historylist], list(pages))

		while is_sensitive(previous_action):
			window.open_page_previous()

		self.assertEqual([p.name for p in historylist], list(pages) + ['A:B2', 'A:B1', 'A'])


class TestActions(tests.TestCase):

	def testJumpToPage(self):
		window = setUpMainWindow(self.setUpNotebook(content=('A', 'B')), path='A')

		def jump(dialog):
			dialog.set_input(page='B')
			dialog.assert_response_ok()

		self.assertEqual(window.page, Path('A'))
		with tests.DialogContext(jump):
			window.show_jump_to()

		self.assertEqual(window.page, Path('B'))

	def testOpenHome(self):
		window = setUpMainWindow(self.setUpNotebook(), path='A')

		self.assertEqual(window.page, Path('A'))
		window.open_page_home()
		self.assertEqual(window.page, Path('Home'))

	def testReloadPage(self):
		window = setUpMainWindow(self.setUpNotebook(), path='A')

		page1 = window.page
		window.reload_page()
		page2 = window.page
		self.assertEqual(page1, Path('A'))
		self.assertEqual(page2, Path('A'))
		self.assertNotEqual(id(page1), id(page2))


from gi.repository import Gtk

from zim.gui.widgets import WindowSidePaneWidget, LEFT_PANE


class MockSidePaneWidget(Gtk.VBox, WindowSidePaneWidget):
	title = 'MockSidePaneWidget'


class TestTogglingState(tests.TestCase):

	def runTest(self):
		path = Path('Test:foo:bar')
		window = setUpMainWindow(self.setUpNotebook(), path)

		#self.assertTrue(window.uistate['show_menubar'])
		window.toggle_menubar()
		#self.assertFalse(window.uistate['show_menubar'])
		window.toggle_menubar()
		#self.assertTrue(window.uistate['show_menubar'])

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

		mywidget = MockSidePaneWidget()
		mywidget.show_all()
		window.add_tab('Test', mywidget, LEFT_PANE)

		self.assertTrue(window.uistate['left_pane'][0])
		window.toggle_panes()
		self.assertFalse(window.uistate['left_pane'][0])
		window.toggle_panes()
		self.assertTrue(window.uistate['left_pane'][0])

		# note: no default style here - system default unknown
		for style in (
			TOOLBAR_ICONS_AND_TEXT,
			TOOLBAR_ICONS_ONLY,
			TOOLBAR_TEXT_ONLY,
		):
			window.set_toolbar_style(style)
			self.assertEqual(window.preferences['toolbar_style'], style)

		# note: no default style here - system default unknown
		for size in (
			TOOLBAR_ICONS_LARGE,
			TOOLBAR_ICONS_SMALL,
			TOOLBAR_ICONS_TINY,
		):
			window.set_toolbar_icon_size(size)
			self.assertEqual(window.preferences['toolbar_size'], size)

		# ..
		window.toggle_fullscreen()
		window.toggle_fullscreen()


class TestSavingPages(tests.TestCase):

	def setUp(self):
		self.mainwindow = setUpMainWindow(self.setUpNotebook())

	def testSave(self):
		'''Test saving a page from the interface'''
		self.mainwindow.open_page(Path('Non-exsiting:page'))
		self.assertFalse(self.mainwindow.page.exists())
		self.assertIsNone(self.mainwindow.page.get_parsetree())
		self.assertTrue(self.mainwindow.pageview._showing_template) # XXX check HACK
		self.mainwindow.pageview.save_page()
		self.assertTrue(self.mainwindow.page.exists())
		self.assertIsNotNone(self.mainwindow.page.get_parsetree())
		self.assertFalse(self.mainwindow.pageview._showing_template) # XXX check HACK

	def testClose(self):
		# Specific bug found when trying to close the page while auto-save
		# in progress, test it here
		self.mainwindow.pageview.textview.get_buffer().insert_at_cursor('...')
		self.mainwindow.pageview._save_page_handler.try_save_page()
		self.assertTrue(self.mainwindow.page.modified)
		self.mainwindow.close()
		self.assertFalse(self.mainwindow.page.modified)

	def testCloseByDestroy(self):
		# Specific bug found when trying to close the page while auto-save
		# in progress, test it here
		self.mainwindow.pageview.textview.get_buffer().insert_at_cursor('...')
		self.mainwindow.pageview._save_page_handler.try_save_page()
		self.assertTrue(self.mainwindow.page.modified)
		self.mainwindow.destroy()
		self.assertFalse(self.mainwindow.page.modified)
