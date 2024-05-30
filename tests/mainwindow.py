
# Copyright 2009-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from gi.repository.Gtk import ImageMenuItem

import tests

import sys

from zim.notebook import Path
from zim.plugins import PluginManager

from zim.gui.mainwindow import *

is_sensitive = lambda w: w.get_property('sensitive')


def setUpMainWindow(notebook, path='Test'):
	if isinstance(path, str):
		path = Path(path)

	mainwindow = MainWindow(notebook, page=path)
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


class TestOpenPageImportTextFile(tests.TestCase):

	def runTest(self):
		# See also uiactions.TestUIActions.testCreateNewPageImportExistingTextFile
		notebook = self.setUpNotebook(content=('A',))
		file = notebook.folder.file('B.txt')
		file.write('Test 123\n') # Not a page, just text !

		window = setUpMainWindow(notebook, path='A')

		def do_import(questiondialog):
			questiondialog.answer_yes()

		with tests.DialogContext(do_import):
			window.open_page(Path('B'))

		self.assertEqual(window.page, Path('B'))
		lines = file.readlines()
		self.assertEqual(lines[0], 'Content-Type: text/x-zim-wiki\n')
		self.assertEqual(lines[-1], 'Test 123\n')


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

		mywidget = MockSidePaneWidget()
		mywidget.show_all()
		window.add_sidepane_widget('Test', mywidget, LEFT_PANE)

		self.assertTrue(window.uistate['left_pane'][0])
		window.toggle_panes()
		self.assertFalse(window.uistate['left_pane'][0])
		window.toggle_panes()
		self.assertTrue(window.uistate['left_pane'][0])

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
		self.assertTrue(self.mainwindow.pageview.textview.get_buffer().showing_template)
		self.mainwindow.pageview.save_page()
		self.assertTrue(self.mainwindow.page.exists())
		self.assertIsNotNone(self.mainwindow.page.get_parsetree())
		self.assertFalse(self.mainwindow.pageview.textview.get_buffer().showing_template)

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


class TestMenuDocs(tests.TestCase):

	def setUp(self):
		self.mainwindow = setUpMainWindow(self.setUpNotebook())
		self.manual = tests.ZIM_DATA_FOLDER.file('manual/Help/Menu_Items.txt').read()

	def testAllMenuItemsAreDocumented(self):
		def menuitems(parent, level=0):
			for mi in parent.get_children():
				if isinstance(mi, ImageMenuItem):
					yield mi, level
				sm = mi.get_submenu()
				if sm:
					for mi_sm in menuitems(sm, level+1):
						yield mi_sm

		for menuitem,level in menuitems(self.mainwindow.menubar):
			label = menuitem.get_label().replace('_','').rstrip('.')
			accel_path = menuitem.get_accel_path()
			accel_label = Gtk.accelerator_get_label(
				Gtk.AccelMap().lookup_entry(accel_path).key.accel_key,
				Gtk.AccelMap().lookup_entry(accel_path).key.accel_mods)
			if accel_label:
				if sys.platform == 'darwin':
					accel_label = accel_label.replace('⌘', 'Ctrl+')
					accel_label = accel_label.replace('⇧', 'Shift+')
					accel_label = accel_label.replace('⌥', 'Alt+')
					accel_label = accel_label.replace('←', 'Left')
					accel_label = accel_label.replace('→', 'Right')
					accel_label = accel_label.replace('↑', 'Up')
					accel_label = accel_label.replace('↓', 'Down')
					accel_label = accel_label.replace('⇞', 'Page Up')
					accel_label = accel_label.replace('⇟', 'Page Down')
					accel_label = accel_label.replace('↖', 'Home')

				if '++' in accel_label:
					label += ' <' + accel_label.replace('++', '><+') + '>'
				else:
					label += ' <' + accel_label.replace('+', '><') + '>'


			if level:
				label = '**' + label + '**'
			else:
				label = '===== ' + label + ' ====='
			self.assertTrue(label in self.manual, 'Menu item "{}" not documented'.format(label))


class TestReadOnlyMainWindow(tests.TestCase):

	def runTest(self):
		'''Test switching behavior when page opened with read-only status'''
		notebook = self.setUpNotebook(content=('Test', 'Foo', 'Bar'))
		window = setUpMainWindow(notebook)
		self.assertReadWriteState(window)

		notebook.readonly = True # XXX: should never be assigned liek this in apoplication usage
		notebook._page_cache.clear() # XXX
		window.open_page(Path('Foo'))
		self.assertReadOnlyState(window)

		notebook.readonly = False # XXX: should never be assigned liek this in apoplication usage
		notebook._page_cache.clear() # XXX
		window.open_page(Path('Bar'))
		self.assertReadWriteState(window)

	def assertReadWriteState(self, window):
		for headerbar in (window._headerbar, window._fullscreen_headerbar):
			title = window.get_title()
			self.assertNotIn('[' + _('readonly') + ']', title)

		self.assertTrue(window.toggle_editable.get_sensitive())
		self.assertFalse(window.pageview.readonly)

	def assertReadOnlyState(self, window):
		for headerbar in (window._headerbar, window._fullscreen_headerbar):
			title = window.get_title()
			self.assertIn('[' + _('readonly') + ']', title)

		self.assertFalse(window.toggle_editable.get_sensitive())
		self.assertTrue(window.pageview.readonly)


class TestReadOnlyPageWindow(TestReadOnlyMainWindow):

	def runTest(self):
		notebook = self.setUpNotebook(content=('Test',))
		page = notebook.get_page(Path('Test'))
		window = PageWindow(notebook, page, navigation=None)
		self.assertReadWriteState(window)

		notebook.readonly = True # XXX: should never be assigned liek this in apoplication usage
		notebook._page_cache.clear() # XXX
		page = notebook.get_page(Path('Test'))
		window = PageWindow(notebook, page, navigation=None)
		self.assertReadOnlyState(window)


class TestUIStateInitSave(tests.TestCase):

	def testMainWindow(self):
		notebook = self.setUpNotebook(content=('Test',))
		window = setUpMainWindow(notebook)
		self.doTest(window)

	def testPageWindow(self):
		notebook = self.setUpNotebook(content=('Test',))
		page = notebook.get_page(Path('Test'))
		window = PageWindow(notebook, page, navigation=None)
		self.doTest(window)

	def doTest(self, window):
		from zim.gui.widgets import LEFT_PANE, RIGHT_PANE, TOP_PANE, BOTTOM_PANE

		# Check keys defined in Window.init_uistate()
		window.show_all()
		for key in (LEFT_PANE, RIGHT_PANE, TOP_PANE, BOTTOM_PANE):
			self.assertIn(key, window.uistate)

		# Check Window.save_uistate() is called
		cb = tests.wrap_method_with_logger(window, 'save_uistate')
		window.emit('delete-event', None)
		self.assertTrue(cb.hasBeenCalled)
