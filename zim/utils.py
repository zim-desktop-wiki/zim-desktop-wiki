
# Copyright 2012-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>


'''Module with assorted useful classes and functions used in the zim code'''

import functools
import collections


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
		raise AssertionError('BUG: Multiple subclasses found of type: %s' % klass)
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
	string = unicodedata.normalize('NFC', string.strip())
	string = _num_re.sub(lambda m: templ % int(m.group()), string)
	string = string.lower() # sort case insensitive

	try:
		bytestring = locale.strxfrm(string)
			# 8-bit byte string - enode to hex -- in pyton3 check if byte data type is handled better by sqlite3 and others
	except MemoryError:
		# Known python issue :(
		bytestring = string

	key = ''.join(["%02x" % ord(c) for c in bytestring])
	return key


class DefinitionOrderedDict(collections.OrderedDict):
	'''Class that behaves like a dict but keeps items the order they were defined.
	Updating an items keeps it at the current position, removing and
	re-inserting an item puts it at the end of the sequence.
	'''

	def __setitem__(self, key, value):
		if not key in self:
			super().__setitem__(key, value)
			self.move_to_end(key)
		else:
			super().__setitem__(key, value)


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
			first = next(self._iter)
		except StopIteration:
			# empty list
			self.last = True
			self.last = (None, None, None)
		else:
			self.last = False
			self.items = (None, None, first)

	def __iter__(self):
		return self

	def __next__(self):
		if self.last:
			raise StopIteration

		discard, prev, current = self.items
		try:
			mynext = next(self._iter)
		except StopIteration:
			self.last = True
			self.items = (prev, current, None)
		else:
			self.items = (prev, current, mynext)

		return self.items
