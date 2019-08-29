


import tests

from tests.pageview import setUpPageView
from tests.mainwindow import setUpMainWindow

from zim.fs import Dir
from zim.notebook import Notebook, Path
from zim.notebook.operations import ongoing_operation
from zim.gui.pageview import SavePageHandler, SavePageErrorDialog, PageView

from gi.repository import Gtk


@tests.slowTest
class TestSavePageHandler(tests.TestCase):

	def runTest(self):
		dir = Dir(self.create_tmp_dir())
		notebook = Notebook.new_from_dir(dir)
		page = notebook.get_page(Path('SomePage'))

		orig_store_page_1 = notebook.store_page
		orig_store_page_2 = notebook.store_page_async
		store_page_counter = tests.Counter()

		def wrapper1(page):
			store_page_counter()
			orig_store_page_1(page)

		def wrapper2(page, tree):
			store_page_counter()
			return orig_store_page_2(page, tree)

		notebook.store_page = wrapper1
		notebook.store_page_async = wrapper2

		pageview = tests.MockObject()
		pageview.readonly = False

		handler = SavePageHandler(pageview, notebook, lambda: page)

		# Normal operation
		self.assertFalse(page.modified)
		handler.try_save_page()
		self.assertEqual(store_page_counter.count, 0)

		self.assertFalse(page.modified)
		handler.save_page_now()
		self.assertEqual(store_page_counter.count, 1)

		page.modified = True
		handler.try_save_page()
		self.assertEqual(store_page_counter.count, 2)
		ongoing_operation(notebook)() # effectively a join
		self.assertFalse(page.modified)

		page.modified = True
		handler.save_page_now()
		self.assertEqual(store_page_counter.count, 3)
		self.assertFalse(page.modified)

		# With errors
		def wrapper3(page):
			raise AssertionError

		def wrapper4(page, tree):
			def error_cb():
				raise AssertionError
			return orig_store_page_2(page, error_cb)

		notebook.store_page = wrapper3
		notebook.store_page_async = wrapper4

		page.modified = True

		def catch_dialog(dialog):
			assert isinstance(dialog, SavePageErrorDialog)

		with tests.LoggingFilter('zim'):
			with tests.DialogContext(catch_dialog):
				handler.save_page_now()
		self.assertTrue(page.modified)

		# For autosave first error is ignore, 2nd results in dialog
		self.assertFalse(handler._error_event and handler._error_event.is_set())
		with tests.LoggingFilter('zim'):
			handler.try_save_page()
			ongoing_operation(notebook)() # effectively a join
		self.assertTrue(handler._error_event and handler._error_event.is_set())

		with tests.LoggingFilter('zim'):
			with tests.DialogContext(catch_dialog):
				handler.try_save_page()
		self.assertTrue(page.modified)


from zim.notebook.operations import NotebookState

import threading


class TestRaceCondition(tests.TestCase):

	def runTest(self):
		notebook = self.setUpNotebook(content = {'test': 'test123\n'})
		pageview = setUpPageView(notebook)

		# Install wrapper with events
		orig = notebook._store_page_async_thread_main
		start_thread_event = threading.Event()
		thread_done_event = threading.Event()
		def wrapper(*a):
			start_thread_event.wait()
			orig(*a)
			thread_done_event.set()
		notebook._store_page_async_thread_main = wrapper

		# Test1 - normal scenario
		page = notebook.get_page(Path('Test'))
		pageview.set_page(page)
		pageview.readonly = False

		pageview.textview.get_buffer().set_text('foo')
		self.assertTrue(page.modified)
		pageview._save_page_handler.try_save_page()
		self.assertTrue(page.modified)
		start_thread_event.set()
		thread_done_event.wait()
		with NotebookState(notebook):
			self.assertFalse(page.modified)

		# Test2 - with race condition
		start_thread_event.clear()
		thread_done_event.clear()
		pageview.textview.get_buffer().set_text('bar')
		self.assertTrue(page.modified)
		pageview._save_page_handler.try_save_page()
		self.assertTrue(page.modified)
		pageview.textview.get_buffer().set_text('dusss') # edit while save ongoing
		start_thread_event.set()
		thread_done_event.wait()
		with NotebookState(notebook):
			self.assertTrue(page.modified) # page must still show modified is True


class TestDialog(tests.TestCase):

	def setUp(self):
		notebook = self.setUpNotebook()
		pageview = setUpPageView(notebook)

		def raise_error(*a):
			raise AssertionError

		notebook.store_page = raise_error

		pageview.textview.get_buffer().set_text('Editing ...\n')
		assert pageview.page.modified

		self.page = pageview.page
		self.pageview = pageview
		self.handler = SavePageHandler(pageview, notebook, pageview.get_page)

	def testCancel(self):

		def cancel(dialog):
			self.assertIsInstance(dialog, SavePageErrorDialog)
			self.assertTrue(self.page.modified)
			self.assertEqual(self.page.dump('wiki'), ['Editing ...\n'])
			dialog.response(Gtk.ResponseType.CANCEL)
			self.assertTrue(self.page.modified)
			self.assertEqual(self.page.dump('wiki'), ['Editing ...\n'])

		with tests.LoggingFilter('zim'):
			with tests.DialogContext(cancel):
				self.handler.save_page_now()

	def testDiscard(self):

		def discard(dialog):
			self.assertIsInstance(dialog, SavePageErrorDialog)
			self.assertTrue(self.page.modified)
			self.assertEqual(self.page.dump('wiki'), ['Editing ...\n'])
			dialog.discard()
			self.assertFalse(self.page.modified)
			self.assertNotEqual(self.page.dump('wiki'), ['Editing ...\n'])

		with tests.LoggingFilter('zim'):
			with tests.DialogContext(discard):
				self.handler.save_page_now()

	def testSaveCopy(self):
		folder = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		file = folder.file('copy.txt')

		def save_copy(dialog):
			self.assertIsInstance(dialog, SavePageErrorDialog)
			self.assertTrue(self.page.modified)
			self.assertEqual(self.page.dump('wiki'), ['Editing ...\n'])
			dialog.save_copy()
			self.assertFalse(self.page.modified)
			self.assertNotEqual(self.page.dump('wiki'), ['Editing ...\n'])

		def save_copy_dialog(dialog):
			dialog.set_file(file)
			dialog.do_response_ok()

		with tests.LoggingFilter('zim'):
			with tests.DialogContext(save_copy, save_copy_dialog):
				self.handler.save_page_now()

		self.assertEqual(file.read(), 'Editing ...\n')


class TestNavigation(tests.TestCase):

	def testNavigationDiscard(self):
		notebook = self.setUpNotebook(content = {'test': 'test123\n'})
		mainwindow = setUpMainWindow(notebook, path='Test')

		def raise_error(page):
			raise AssertionError

		notebook.store_page = raise_error

		mainwindow.pageview.textview.get_buffer().set_text('Changed!')

		def discard(dialog):
			self.assertIsInstance(dialog, SavePageErrorDialog)
			self.assertTrue(mainwindow.page.modified)
			self.assertEqual(mainwindow.page.dump('wiki'), ['Changed!\n'])
			dialog.discard()
			self.assertFalse(mainwindow.page.modified)
			self.assertNotEqual(mainwindow.page.dump('wiki'), ['Changed!\n'])

		self.assertEqual(mainwindow.page.name, 'Test')

		with tests.LoggingFilter('zim'):
			with tests.DialogContext(discard):
				mainwindow.open_page(Path('Other page'))

		self.assertEqual(mainwindow.page.name, 'Other page')


	def testNavigationCancel(self):
		notebook = self.setUpNotebook(content = {'test': 'test123\n'})
		mainwindow = setUpMainWindow(notebook, path='Test')

		def raise_error(page):
			raise AssertionError

		notebook.store_page = raise_error

		mainwindow.pageview.textview.get_buffer().set_text('Changed!')

		def cancel(dialog):
			self.assertIsInstance(dialog, SavePageErrorDialog)
			self.assertTrue(mainwindow.page.modified)
			self.assertEqual(mainwindow.page.dump('wiki'), ['Changed!\n'])
			dialog.response(Gtk.ResponseType.CANCEL)
			self.assertTrue(mainwindow.page.modified)
			self.assertEqual(mainwindow.page.dump('wiki'), ['Changed!\n'])

		self.assertEqual(mainwindow.page.name, 'Test')

		with tests.LoggingFilter('zim'):
			with tests.DialogContext(cancel):
				mainwindow.open_page(Path('Other page'))

		self.assertEqual(mainwindow.page.name, 'Test')
			# Cancelling save page should cancel open_page as well
