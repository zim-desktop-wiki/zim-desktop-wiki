
# Copyright 2012-2024 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Module with assorted useful classes and functions used in the zim code'''


import collections


class classproperty(object):
	'''Like C{property()} but for klass properties
	Typically used as decorator
	'''

	def __init__(self, func):
		self.func = func

	def __get__(self, obj, owner):
		return self.func(owner)


class LastDefinedOrderedDict(collections.OrderedDict):
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
