# -*- coding: utf-8 -*-

# Copyright 2010 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Asynchronous operations based on threading.

We define the AsyncOperation class to wrap a function that can be
executed asynchronous. AsyncOperation wraps the function in a thread
so it can run in parralel with the main program.

The idea is to only do low level actions in separate threads, e.g.
blocking I/O. In the main thread we have the gtk or gobject main loop
and there we also have "gobject.idle_add()" to queue actions that run
in between gui updates etc. The reason to do it like this is that it
gives headaches trying to get things right if gobject or gtk signals
can fire in a separate thread. Also the sqlite index is not thread
save either.

The AsyncLock class can be used for locking a resource. The lock is
always aquired in the main thread before the async operation starts and
is released when the operation finishes. THis way race conditions can
be avoided in case you queue the same operation several times. Using
the lock enforces that the async actions are still run in the same
order as they are spawned from the main thread.
'''

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

	def __init__(self, function, args=(), kwargs={}, lock=None, callback=None, data=None):
		'''Construct a new thread. You can pass it a function to
		execute and its arguments and keyword arguments.

		If a lock object is provided start() will block until the lock
		is available and we will release the lock once the operation is
		done.

		If you add a callback function it will be called in the main
		thread after the function is finished. Callback is called like:

			callback(value, error, exc_info, data)

			* 'value' is the return value of the function
			* 'error' is an Exception object or None
			* 'exc_info' is a 3 tuple of sys.exc_info() or None
			* 'data' is the data given to the constructor
		'''
		self.result = None

		def wrapper(function, args, kwargs, lock, callback, data):
			try:
				self.result = function(*args, **kwargs)
			except Exception, error:
				if lock:
					lock.release()

				if callback:
					exc_info = sys.exc_info()
					call_in_main_thread(
						callback, (self.result, error, exc_info, data) )
				else:
					logger.exception('Error in AsyncOperation')
			else:
				if lock:
					lock.release()

				if callback:
					call_in_main_thread(
						callback, (self.result, None, None, data) )

		myargs = (function, args, kwargs, lock, callback, data)
		threading.Thread.__init__(self, target=wrapper, args=myargs)
		self.lock = lock

	def start(self):
		'''Start the operation'''
		if self.lock:
			self.lock.acquire()
		threading.Thread.start(self)

	def wait(self):
		'''Wait for this thread to exit and return the result
		of the function handled by this thread.
		'''
		self.join()
		return self.result


class AsyncLock(object):
	'''This class functions as a threading.Lock object.

	This class also functions as a context manager, so you can use:

		lock = AsyncLock()

		with lock:
			....
	'''

	# Not sure why we can not subclass threading.Lock, but it throws
	# an error, so we wrap it.

	__slots__ = ('_lock',)

	def __init__(self):
		self._lock = threading.Lock()

	def __enter__(self):
		self._lock.acquire()

	def __exit__(self, *a):
		self._lock.release()
		return False # propagate any errors

	def acquire(self, blocking=True):
		self._lock.acquire(blocking)

	def release(self):
		self._lock.release()
