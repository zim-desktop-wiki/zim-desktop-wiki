# -*- coding: utf-8 -*-

# Copyright 2012-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>


from __future__ import absolute_import, with_statement

import sys
import logging
import threading


logger = logging.getLogger('threading')


class FunctionThread(threading.Thread):
	'''Subclass of C{threading.Thread} that runs a single function and
	keeps the result and any exceptions raised.

	@ivar done: C{True} is the function is done running
	@ivar result: the return value of C{func}
	@ivar error: C{True} if done and an exception was raised
	@ivar exc_info: 3-tuple with exc_info
	'''

	def __init__(self, func, args=(), kwargs={}, lock=None):
		'''Constructor
		@param func: the function to run in the thread
		@param args: arguments for C{func}
		@param kwargs: keyword arguments for C{func}
		@param lock: optional lock, will be acquired in main thread
		before running and released once done in background
		'''
		threading.Thread.__init__(self)

		self.func = func
		self.args = args
		self.kwargs = kwargs

		self.lock = lock

		self.done = False
		self.result = None
		self.error = False
		self.exc_info = (None, None, None)

	def start(self):
		if self.lock:
			self.lock.acquire()
		threading.Thread.start(self)

	def run(self):
		try:
			self.result = self.func(*self.args, **self.kwargs)
		except:
			self.error = True
			self.exc_info = sys.exc_info()
		finally:
			self.done = True
			if self.lock:
				self.lock.release()


class WorkerThread(threading.Thread):
	'''Wrapper to run a function in a worker thread. The function
	should be a generator that "yield"s often such that we can
	interrupt it.
	'''

	_lock = threading.Lock()
	_active = set()

	@classmethod
	def _acquire(klass, name):
		with klass._lock:
			if name in klass._active:
				raise AssertionError, 'BUG: Another "%s" WorkerThread is still active'
			else:
				klass._active.add(name)

	@classmethod
	def _release(klass, name):
		with klass._lock:
			klass._active.discard(name)

	def __init__(self, iterable, name):
		threading.Thread.__init__(self)
		self.iterable = iterable
		self.name = name
		self._stop = threading.Event()

	def start(self):
		self._acquire(self.name)
		self._stop.clear()
		threading.Thread.start(self)

	def stop(self):
		self._stop.set()
		self.join()

	def run(self):
		try:
			logger.debug('Worker thread starts: %s', self.name)
			for i in self.iterable:
				if self._stop.is_set():
					logger.debug('Worker thread stopped: %s', self.name)
					break
			else:
				logger.debug('Worker thread exitted: %s', self.name)
		except:
			logger.exception('Exception in worker thread: %s', self.name)
		finally:
			self._release(self.name)
