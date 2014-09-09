# -*- coding: utf-8 -*-

# Copyright 2012-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>


'''Module with assorted useful classes and functions used in the zim code'''


class classproperty(object):
	'''Like C{property()} but for klass properties
	Typically used as decorator
	'''

	def __init__(self, func):
		self.func = func

	def __get__(self, obj, owner):
		return self.func(owner)


## Functions for dynamic loading of modules and klasses
import inspect


def get_module(name):
	'''Import a module

	@param name: the module name
	@returns: module object
	@raises ImportError: if the given name does not exist
	'''
	# __import__ has some quirks, see the reference manual
	mod = __import__(name)
	for part in name.split('.')[1:]:
		mod = getattr(mod, part)
	return mod


def lookup_subclass(module, klass):
	'''Look for a subclass of klass in the module

	This function is used in several places in zim to get extension
	classes. Typically L{get_module()} is used first to get the module
	object, then this lookup function is used to locate a class that
	derives of a base class (e.g. PluginClass).

	@param module: module object
	@param klass: base class

	@note: don't actually use this method to get plugin classes, see
	L{PluginManager.get_plugin_class()} instead.
	'''
	subclasses = lookup_subclasses(module, klass)
	if len(subclasses) > 1:
		raise AssertionError, 'BUG: Multiple subclasses found of type: %s' % klass
	elif subclasses:
		return subclasses[0]
	else:
		return None


def lookup_subclasses(module, klass):
	'''Look for all subclasses of klass in the module

	@param module: module object
	@param klass: base class
	'''
	subclasses = []
	for name, obj in inspect.getmembers(module, inspect.isclass):
		if issubclass(obj, klass) \
		and obj.__module__.startswith(module.__name__):
			subclasses.append(obj)

	return subclasses


#### sorting functions
import locale
import re
import unicodedata


_num_re = re.compile(r'\d+')


def natural_sort(list, key=None):
	'''Natural sort a list in place.
	See L{natural_sort_key} for details.
	@param list: list of strings to be sorted
	@param key: function producing strings for list items
	'''
	if key:
		def func(s):
			s = key(s)
			return (natural_sort_key(s), s)
	else:
		func = lambda s: (natural_sort_key(s), s)
	list.sort(key=func)


def natural_sorted(iter, key=None):
	'''Natural sort a list.
	See L{natural_sort_key} for details.
	@param iter: list or iterable of strings to be sorted
	@param key: function producing strings for list items
	@returns: sorted copy of the list
	'''
	l = list(iter) # cast to list and implicit copy
	natural_sort(l, key=key)
	return l


def natural_sort_key(string, numeric_padding=5):
	'''Format string such that it gives 'natural' sorting on string
	compare. Will pad any numbers in the string with "0" such that "10"
	sorts after "9". Also includes C{locale.strxfrm()}.

	@note: sorting not 100% stable for case, so order between "foo" and
	"Foo" is not defined. For this reason when sort needs to be absolutely
	stable it is advised to sort based on tuples of
	C{(sort_key, original_string)}. Or use either L{natural_sort()} or
	L{natural_sorted()} instead.

	@param string: the string to format
	@param numeric_padding: number of digits to use for padding
	@returns: string transformed to sorting key
	'''
	templ = '%0' + str(numeric_padding) + 'i'
	string.strip()
	string = _num_re.sub(lambda m: templ % int(m.group()), string)
	if isinstance(string, unicode):
		string = unicodedata.normalize('NFKC', string)
		# may be done by strxfrm as well, but want to be sure
	string = locale.strxfrm(string.lower())
	return string.decode('utf-8') # not really utf-8, but 8bit bytes


####

# Python 2.7 has a weakref.WeakSet, but using this one for compatibility with 2.6 ..
# Did not switch implementations per version to make sure we test
# all modules with this implementation

import weakref

class WeakSet(object):
	'''Class that behaves like a set, but keeps weak references to
	memebers of the set.
	'''

	def __init__(self):
		self._refs = []

	def __iter__(self):
		return (
			obj for obj in
					[ref() for ref in self._refs]
							if obj is not None
		)

	def add(self, obj):
		ref = weakref.ref(obj, self._del)
		self._refs.append(ref)

	def _del(self, ref):
		try:
			self._refs.remove(ref)
		except ValueError:
			pass

	def discard(self, obj):
		for ref in self._refs:
			if ref() == obj:
				self._refs.remove(ref)


# Python 2.7 has a collections.OrderedDict, but using this one for compatibility
# Did not switch implementations per version to make sure we test
# all modules with this implementation

import collections

class OrderedDict(collections.MutableMapping):
	'''Class that behaves like a dict but keeps items in same order.
	Updating an items keeps it at the current position, removing and
	re-inserting an item puts it at the end of the sequence.
	'''

	# By using collections.MutableMapping we ensure all dict API calls
	# are proxied by the methods below. When inheriting from dict
	# directly e.g. "pop()" does not use "__delitem__()" but is
	# optimized on it's own

	def __init__(self, E=None, **F):
		if not hasattr(self, '_keys') \
		and not hasattr(self, '_values'):
			# Some classes have double inheritance from this class
			self._keys = []
			self._values = {}

		if self.__class__.__getitem__ == OrderedDict.__getitem__:
			# optimization by just using the real dict.__getitem__
			# but skip if subclass overloaded the method
			self.__getitem__ = self._values.__getitem__

		if E or F:
			assert not (E and F)
			self.update(E or F)

	def __repr__(self):
		return '<%s:\n%s\n>' % (
			self.__class__.__name__,
			',\n'.join('  %r: %r' % (k, v) for k, v in self.items())
		)

	def __getitem__(self, k):
		return self._values[k]
		# Overloaded in __init__ for optimization

	def __setitem__(self, k, v):
		self._values[k] = v
		if not k in self._keys:
			self._keys.append(k)

	def __delitem__(self, k):
		del self._values[k]
		self._keys.remove(k)

	def __iter__(self):
		return iter(self._keys)

	def __len__(self):
		return len(self._keys)


## Special iterator class
class MovingWindowIter(object):
	'''Iterator yields a 3-tuple of the previous item, the current item
	and the next item while iterating a give iterator.
	Previous or next item will be C{None} if not available.
	Use as:

		for prev, current, next in MovingWindowIter(mylist):
			....

	@ivar items: current 3-tuple
	@ivar last: C{True} if we are at the last item
	'''

	def __init__(self, iterable):
		self._iter = iter(iterable)
		try:
			first = self._iter.next()
		except StopIteration:
			# empty list
			self.last = True
			self.last = (None, None, None)
		else:
			self.last = False
			self.items = (None, None, first)

	def __iter__(self):
		return self

	def next(self):
		if self.last:
			raise StopIteration

		discard, prev, current = self.items
		try:
			next = self._iter.next()
		except StopIteration:
			self.last = True
			self.items = (prev, current, None)
		else:
			self.items = (prev, current, next)

		return self.items



## Wrapper for using threads for e.g. async IO
import threading
import sys


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
