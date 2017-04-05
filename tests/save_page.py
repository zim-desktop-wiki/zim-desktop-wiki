
from __future__ import with_statement

import tests

from zim.fs import Dir
from zim.notebook import Notebook, Path
from zim.notebook.operations import ongoing_operation
from zim.gui.pageview import SavePageHandler, SavePageErrorDialog


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
