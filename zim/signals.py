# -*- coding: utf-8 -*-

# Copyright 2012-2016 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import weakref
import logging
import gobject
import os


logger = logging.getLogger('zim')

# Constants for signal order
SIGNAL_RUN_FIRST = 1
SIGNAL_BEFORE = SIGNAL_NORMAL = 2
SIGNAL_RUN_LAST = 3
SIGNAL_AFTER = 4


class SignalHandler(object):
    '''Wrapper for a signal handler method that allows blocking the
    handler for incoming signals. To be used as function decorator.

    The method will be replaced by a L{BoundSignalHandler} object that
    supports a C{blocked()} method which returns a context manager
    to temporarily block a callback.

    Intended to be used as::

            class Foo():

                    @SignalHandler
                    def on_changed(self):
                            ...

                    def update(self):
                            with self.on_changed.blocked():
                                    ... # do something that results in a "changed" signal

    '''

    def __init__(self, func):
        self._func = func

    def __get__(self, instance, klass):
        if instance is None:
            # class access
            return self
        else:
            # instance acces, return bound version
            name = '_bound_' + self._func.__name__
            if not hasattr(instance, name) \
                    or getattr(instance, name) is None:
                bound_obj = BoundSignalHandler(instance, self._func)
                setattr(instance, name, bound_obj)

            return getattr(instance, name)


class BoundSignalHandler(object):

    def __init__(self, instance, func):
        self._instance = instance
        self._func = func
        self._blocked = 0

    def __call__(self, *args, **kwargs):
        if self._blocked == 0:
            return self._func(self._instance, *args, **kwargs)

    def _block(self):
        self._blocked += 1

    def _unblock(self):
        if self._blocked > 0:
            self._blocked -= 1

    def blocked(self):
        '''Returns a context manager that can be used to temporarily
        block a callback.
        '''
        return SignalHandlerBlockContextManager(self)


class SignalHandlerBlockContextManager(object):

    def __init__(self, handler):
        self.handler = handler

    def __enter__(self):
        self.handler._block()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.handler._unblock()


class ConnectorMixin(object):
    '''Mixin class that has convenience methods for objects that
    want to connect to signals of other objects.
    '''

    # TODO connect variant that wraps with a handler that catches
    #  unwanted arguments -- kind of reverse "partial()"

    def connectto(self, obj, signal, handler=None, order=SIGNAL_NORMAL):
        '''Connect to signals of another object
        E.g.::

                self.connectto(button, 'clicked', self.on_button_clicked)

        @param obj: the object to connect to
        @param signal: the signal name
        @param handler: the callback function, or C{None} to map to
        a method prefixed with "on_".
        @param order: if order is C{SIGNAL_NORMAL} then C{GObject.connect()}
        is used, if order is C{SIGNAL_AFTER} then C{GObject.connect_after()}
        is used.
        @returns: the handler id
        '''
        if handler is None:
            name = "on_" + signal.replace('-', '_')
            handler = getattr(self, name)
            if handler is None:
                raise NotImplementedError('No method "%s"' % name)

        if order == SIGNAL_AFTER:
            i = obj.connect_after(signal, handler)
        else:
            i = obj.connect(signal, handler)

        if not hasattr(self, '_connected_signals'):
            self._connected_signals = {}
            # We might want a dict here that is cleaned up
            # when references disappear, but for now this will do

        key = id(obj)
        if not key in self._connected_signals:
            self._connected_signals[key] = (weakref.ref(obj), [])
        self._connected_signals[key][1].append(i)

        return i

    def connectto_all(self, obj, signals, handler=None, order=SIGNAL_NORMAL):
        '''Convenience method to combine multiple calls to
        L{connectto()}.

        @param obj: the object to connect to
        @param signals: a list of signals. Elements can either be signal
        names or tuples where the sub-elements are the parameters
        for L{connectto()}. For example::

                self.connectto_all(self.ui (
                        'open-page' # defaults to on_open_page
                        ('open-notebook', on_open_notebook, None, SIGNAL_AFTER),
                ))

        The optional parameters are used as default values when these
        parameters are not specified explicitly per signal.

        @param handler: optional parameter
        @param order: optional parameter
        '''
        default = (None, handler, order)
        for signal in signals:
            if isinstance(signal, basestring):
                self.connectto(obj, signal, handler, order)
            else:
                arg = signal + default[len(signal):]
                # fill in missing positional arguments
                self.connectto(obj, *arg)

    def disconnect_from(self, obj):
        '''Disc all signals that have been connected with
        L{connectto} and friends to a specific object.
        '''
        key = id(obj)
        if hasattr(self, '_connected_signals') \
                and key in self._connected_signals:
            self._disconnect_from(key)

    def disconnect_all(self):
        '''Disconnect all signals that have been connected with
        L{connectto} and friends. Typically called when you want to
        destroy this object.
        '''
        if hasattr(self, '_connected_signals'):
            for key in self._connected_signals.keys():
                try:
                    self._disconnect_from(key)
                except:
                    logger.exception('Exception in disconnect_all()')

    def _disconnect_from(self, key):
        ref, signals = self._connected_signals[key]
        obj = ref()
        if obj is not None:
            for i in signals:
                obj.disconnect(i)
        del self._connected_signals[key]


class SignalEmitterMeta(type):

    def __init__(cls, name, bases, dct):
        # Init class

        assert hasattr(cls, '__signals__')

        #  1/ setup inheritance for signals

        if name != 'SignalEmitter':
            for base in bases:
                if issubclass(base, SignalEmitter):
                    for key, value in base.__signals__.items():
                        cls.__signals__.setdefault(key, value)

        #  2/ set list of closures to be initialized per instance

        cls._signal_closures = []
        for signal in cls.__signals__:
            name = 'do_' + signal.replace('-', '_')
            if hasattr(cls, name):
                order = cls.__signals__[signal][0]
                if not order in (SIGNAL_RUN_FIRST, SIGNAL_RUN_LAST):
                    order = SIGNAL_RUN_LAST  # for backward compatibility, fallback to this default
                closure = getattr(cls, name)  # unbound version!
                cls._signal_closures.append((signal, order, closure))

        super(SignalEmitterMeta, cls).__init__(name, bases, dct)


class SignalEmitter(object):
    '''Replacement for C{GObject} to make objects emit signals.
    API should be backward compatible with API offered by GObject.

    Supported signals need to be defined in the dict C{__signals__}. For
    each signal a 3-tuple is provided where the first argument is either
    C{SIGNAL_RUN_FIRST} or C{SIGNAL_RUN_LAST}, the second is the return
    argument (or C{None} for most signals) and the third is the argument
    spec for the signal. See Glib documentation for more notes on execution
    order etc.
    '''

    __metaclass__ = SignalEmitterMeta

    # define signals we want to use - (closure type, return type and arg types)
    # E.g. {signal: (SIGNAL_RUN_LAST, None, (object, object))}
    __signals__ = {}  # : signals supported by this class

    def __new__(cls, *arg, **kwarg):
        # New instance: init attributes for signal handling
        obj = super(SignalEmitter, cls).__new__(cls, *arg, **kwarg)

        obj._signal_handlers = {}
        obj._signal_blocks = {}
        obj._signal_count = 0  # ensure signals execute in order of connecting

        for signal, order, closure in obj._signal_closures:
            obj._signal_handlers[signal] = [(order, 0, closure)]

        return obj

    def connect(self, signal, handler):
        '''Register a handler for a specific object.

        Note that connecting makes a hard reference to the connected
        object. So connecting an bound method will prevent the
        object the method belongs to to be destroyed untill the
        signal is disconnected.

        @param signal: the signal name
        @param handler: callback to be called upon the signal,
        first object to the callback will be the emitting object,
        other params are signal specific.
        @returns: an id for the registered handler
        '''
        return self._connect(SIGNAL_BEFORE, signal, handler)

    def connect_after(self, signal, handler):
        '''Like L{connect()} but handler will be called after default handler'''
        return self._connect(SIGNAL_AFTER, signal, handler)

    def _connect(self, category, signal, callback):
        assert signal in self.__signals__, 'No such signal: %s::%s' % (self.__class__.__name__, signal)

        if not signal in self._signal_handlers:
            self._signal_handlers[signal] = []
            self._setup_signal(signal)

        # The "handler" is a tuple with an unique object id, which is
        # used as the handler id. It starts with a category and a counter
        # to ensure sorting is stable, both for categories and for the
        # order of connecting
        handler = (category, self._signal_count, callback)
        self._signal_count += 1
        self._signal_handlers[signal].append(handler)
        self._signal_handlers[signal].sort()
        return id(handler)

    def _setup_signal(self, signal):
        pass

    def disconnect(self, handlerid):
        for signal, handlers in self._signal_handlers.items():
            # unique id, so when we find it, stop searching
            ids = map(id, handlers)
            try:
                i = ids.index(handlerid)
            except ValueError:
                continue
            else:
                handlers.pop(i)
                if not handlers:
                    self._signal_handlers.pop(signal)
                    self._teardown_signal(signal)
                break

    def _teardown_signal(self, signal):
        pass

    def emit(self, signal, *args):
        assert signal in self.__signals__, 'No such signal: %s::%s' % (self.__class__.__name__, signal)

        if not len(args) == len(self.__signals__[signal][2]):
            logger.warning('Signal args do not match spec for %s::%s', self.__class__.__name__, signal)

        if self._signal_blocks.get(signal):
            return  # ignore emit

        return_first = self.__signals__[signal][1] is not None
        for c, i, handler in self._signal_handlers.get(signal, []):
            try:
                r = handler(self, *args)
            except:
                logger.exception('Exception in signal handler for %s on %s', signal, self)
            else:
                if return_first and r is not None:
                    return r

    def block_signals(self, *signals):
        '''Returns a context manager for blocking one or more signals'''
        return BlockSignalsContextManager(self, signals)


class BlockSignalsContextManager(object):

    def __init__(self, obj, signals):
        self.obj = obj
        self.signals = signals

    def __enter__(self):
        for signal in self.signals:
            self.obj._signal_blocks.setdefault(signal, 0)
            self.obj._signal_blocks[signal] += 1

    def __exit__(self, exc_type, exc_val, exc_tb):
        for signal in self.signals:
            if signal in self.obj._signal_blocks \
                    and self.obj._signal_blocks[signal] > 0:
                self.obj._signal_blocks[signal] -= 1


class DelayedCallback(object):
    '''Wrapper for callbacks that need to be delayed after a signal

    This class allows you to add a callback to a signal, but only have
    it called after a certain timeout. If the signal is emitted
    again during this time the callback will be canceled and the
    timeout starts again. (So the callback is not called for each repeat
    of the signal.) This can be used e.g. in case want to update some
    other widget after the user changes a text entry widget, but this
    can be done once the user pauses, while calling the callback for
    every key stroke would make the application non-responsive.

    Objects of this class wrap the actual callback function and can be
    called as a normal function.

    Note that when a repeated callback is canceled, only the arguments
    of the last call are passed on.

    @todo: allow an option to check arguments and pass on all unique
    combinations ?

    @todo: add support for async callbacks, in this case block
    the callback until the async process is finished
    '''

    __slots__ = ('timeout', 'cb_func', 'timer_id')

    def __init__(self, timeout, cb_func):
        '''Constructor

        @param timeout: timeout in milliseconds (e.g. 500)
        @param cb_func: the callback to call
        '''
        self.cb_func = cb_func
        self.timeout = timeout
        self.timer_id = None

    def __call__(self, *arg, **kwarg):
        if self.timer_id:
            gobject.source_remove(self.timer_id)
            self.timer_id = None

        def callback():
            self.timer_id = None
            self.cb_func(*arg, **kwarg)
            return False  # destroy timeout

        self.timer_id = gobject.timeout_add(self.timeout, callback)

    def __del__(self):
        if self.timer_id:
            gobject.source_remove(self.timer_id)

    def cancel(self):
        '''Cancel the scheduled callback'''
        self.__del__()


def callback(func, *arg, **kwarg):
    '''Returns a wrapper functions that call func and.
    Intended as wrapper for callbacks connected to (gtk) signals. The
    wrapper ignores any arguments given.
    '''
    def cb(*a):
        func(*arg, **kwarg)
    return cb
