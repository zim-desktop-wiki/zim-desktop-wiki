# -*- coding: utf-8 -*-

# Copyright 2010 Jaap Karssenberg <pardus@cpan.org>

'''Asynchronous operations based on threading'''

import sys
import logging

import gobject


logger = logging.getLogger('zim.async')


try:
	import threading
except ImportError:
	logger.warn('No threading support - this may reduce performance')
	import dummy_threading as threading


def call_in_main_thread(callback, args=()):
	gobject.idle_add(callback, *args)


class AsyncOperation(threading.Thread):
	'''Wrapper class for a threading.Thread object.'''

	def __init__(self, function, args=(), kwargs={}, callback=None, data=None):
		'''Construct a new thread. You can pass it a function to
		execute and its arguments and keyword arguments.

		If you add a callback function it will be called in the main
		thread after the function is finished. Callback is called like:

			callback(value, exc_info, data)

			* 'value' is the return value of the function
			* 'exc_info' is a 3 tuple in case an error occured
			  or None when no error occured
			* 'data' is the data given to the constructor

		After construction you still need to call start() for
		execution to start.
		'''
		self.result = None

		def wrapper(function, args, kwargs, callback, data):
			try:
				self.result = function(*args, **kwargs)
			except Exception:
				if callback:
					exc_info = sys.exc_info()
					call_in_main_thread(
						callback, (data, self.result, exc_info) )
				else:
					logger.exception('Error in AsyncOperation')
			else:
				if callback:
					call_in_main_thread(
						callback, (self.result, None, data) )

		myargs = (function, args, kwargs, callback, data)
		threading.Thread.__init__(self, target=wrapper, args=myargs)

	def wait(self):
		'''Wait for this thread to exit and return the result
		of the function handled by this thread.
		'''
		self.join()
		return self.result


class AsyncLock(object):
	'''This class functions as a threading.RLock object.

	This class also functions as a context manager, so you can use:

		lock = AsyncLock()

		with lock:
			....
	'''

	# Not sure why we can not subclass threading.RLock, but it throws
	# an error, so we wrap it.

	__slots__ = ('_lock',)

	def __init__(self):
		self._lock = threading.RLock()

	def __enter__(self):
		self._lock.acquire()

	def __exit__(self, *a):
		self._lock.release()

	def acquire(blocking=True):
		self._lock.acquire(blocking)

	def release():
		self._lock.release()
