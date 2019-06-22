
# Copyright 2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>



import tests

from gi.repository import Gtk

from zim.notebook.operations import *


class MockProgressDialog(object):

	def __init__(self, parent, operation):
		# self.heading.set_text(operation.msg)
		operation.connect('step', self.on_iteration_step)
		operation.connect('finished', self.on_iteration_finished)
		self.steps = []
		self.finished = False

	def on_iteration_step(self, o, progress):
		self.steps.append(progress)
		if isinstance(progress, tuple) and len(progress) == 3:
			i, total, msg = progress
			# self.bar.set_fraction(i/total)
			# self.bar.set_text('%i / %i' % (i, total))
		else:
			msg = progress
			# self.bar.pulse()

		# if isinstance(msg, basestring):
			# self.label.set_text(msg)

	def on_iteration_finished(self, o):
		self.finished = True
		# self.response(...) # break run() loop


class MockNotebook(object):

	def __init__(self):
		self._operation_check = NOOP
		self.value = None

	@notebook_state
	def test(self, value):
		self.value = value

	def raw(self, value):
		self.value = value


def mock_iterator(notebook):
	for i in 0, 1, 2:
		notebook.test('Test %i' % i)
		yield i

def mock_gtk_iter(notebook):
	for i in 0, 1, 2:
		notebook.test('Test %i' % i)
		yield i
	Gtk.main_quit()


class TestNotebookOperation(tests.TestCase):

	## TODO add signal monitor to check step and finished emitted

	def testIterator(self):
		nb = MockNotebook()
		nb.test('Foo')
		self.assertEqual(nb.value, 'Foo')

		# Test iterator
		op = NotebookOperation(nb, 'My Op', mock_iterator(nb))

		self.assertFalse(op.is_running())
		nb.test('Bar')
		self.assertEqual(nb.value, 'Bar')

		i = None
		for i, x in enumerate(op):
			self.assertTrue(op.is_running())
			self.assertEqual(nb.value, 'Test %i' % i)
			self.assertRaises(NotebookOperationOngoing, nb.test, 'Foo')

		self.assertEqual(i, 2)
		self.assertFalse(op.is_running())
		self.assertFalse(op.cancelled)

		nb.test('Baz')
		self.assertEqual(nb.value, 'Baz')

		# Test cancel
		op = NotebookOperation(nb, 'My Op', mock_iterator(nb))

		i = None
		for i, x in enumerate(op):
			self.assertTrue(op.is_running())
			op.cancel()

		self.assertEqual(i, 0)
		self.assertFalse(op.is_running())
		self.assertTrue(op.cancelled)

	def testIdle(self):
		nb = MockNotebook()
		op = NotebookOperation(nb, 'My Op', mock_gtk_iter(nb))
		op.run_on_idle()
		Gtk.main()
		self.assertFalse(op.is_running())
		self.assertEqual(nb.value, 'Test %i' % 2)

	def testContext(self):
		nb = MockNotebook()

		def test():
			with NotebookState(nb):
				nb.raw('Foo')

		test()
		self.assertEqual(nb.value, 'Foo')

		op = NotebookOperation(nb, 'My Op', mock_iterator(nb))
		for i, x in enumerate(op):
			self.assertRaises(NotebookOperationOngoing, test)

	def testSignals(self):
		nb = MockNotebook()

		op = NotebookOperation(nb, 'My Op', mock_iterator(nb))
		dialog = MockProgressDialog(None, op)

		i = None
		for i, x in enumerate(op):
			pass

		self.assertEqual(i, 2)
		self.assertEqual(len(dialog.steps), 3)
		self.assertTrue(dialog.finished)

		op = NotebookOperation(nb, 'My Op', mock_iterator(nb))
		dialog = MockProgressDialog(None, op)

		i = None
		for i, x in enumerate(op):
			self.assertTrue(op.is_running())
			op.cancel()

		self.assertEqual(i, 0)
		self.assertEqual(len(dialog.steps), 1)
		self.assertTrue(dialog.finished)


import threading

def mock_thread_main(notebook, lock):
	with lock:
		for i in 0, 1, 2:
			notebook.test('Test %i' % i)


class TestSimpleAsyncOperation(tests.TestCase):

	def runTest(self):
		nb = MockNotebook()
		lock = threading.Lock()
		lock.acquire()
		thread = threading.Thread(target=mock_thread_main, args=(nb, lock))
		thread.start()
		# using lock to ensure thread doesn't finish before iteration seen

		result = []
		def post():
			result.append('foo')

		op = SimpleAsyncOperation(nb, 'my op', thread, post)
		for i, x in enumerate(op):
			self.assertTrue(op.is_running())
			if i == 1:
				lock.release()
		self.assertTrue(i >= 1)

		self.assertFalse(op.is_running())
		self.assertFalse(op.cancelled)

		self.assertEqual(nb.value, 'Test 2')
		self.assertEqual(result, ['foo'])

		# now with cancel - result can vary depending on who goes first
		lock = threading.Lock()
		lock.acquire()
		thread = threading.Thread(target=mock_thread_main, args=(nb, lock))
		thread.start()

		op = SimpleAsyncOperation(nb, 'my op', thread, post)
		for i, x in enumerate(op):
			if i == 1:
				lock.release()
				op.cancel()

		self.assertFalse(op.is_running())
		self.assertTrue(op.cancelled)
