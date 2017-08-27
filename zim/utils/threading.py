# -*- coding: utf-8 -*-

# Copyright 2012-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>


from __future__ import absolute_import, with_statement

import sys
import logging
import threading


logger = logging.getLogger('threading')


try:
    import gobject
except ImportError:
    gobject = None


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
        if gobject:
            gobject.idle_add(self._monitor_on_idle)

    def _monitor_on_idle(self):
        # Only goal if this callback is to ensure python runs in mainloop
        # as long as thread is alive - avoid C code blocking for a long time
        # See comment at threads_init() in zim/main/__init__.py
        return self.is_alive()  # if False, stop event

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
