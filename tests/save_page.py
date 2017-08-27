
from __future__ import with_statement

import tests

from zim.fs import Dir
from zim.notebook import Notebook, Path
from zim.notebook.operations import ongoing_operation
from zim.gui.pageview import SavePageHandler, SavePageErrorDialog, PageView


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
        ongoing_operation(notebook)()  # effectively a join
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
            ongoing_operation(notebook)()  # effectively a join
        self.assertTrue(handler._error_event and handler._error_event.is_set())

        with tests.LoggingFilter('zim'):
            with tests.DialogContext(catch_dialog):
                handler.try_save_page()
        self.assertTrue(page.modified)


from tests.pageview import setUpPageView

from zim.notebook.operations import NotebookState

import threading


class TestRaceCodition(tests.TestCase):

    def runTest(self):
        notebook = self.setUpNotebook(content = {'test': 'test123\n'})
        pageview = setUpPageView(notebook=notebook)

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

        pageview.view.get_buffer().set_text('foo')
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
        pageview.view.get_buffer().set_text('bar')
        self.assertTrue(page.modified)
        pageview._save_page_handler.try_save_page()
        self.assertTrue(page.modified)
        pageview.view.get_buffer().set_text('dusss')  # edit while save ongoing
        start_thread_event.set()
        thread_done_event.wait()
        with NotebookState(notebook):
            self.assertTrue(page.modified)  # page must still show modified is True
