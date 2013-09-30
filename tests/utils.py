# -*- coding: utf-8 -*-

# Copyright 2012-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import tests

from copy import copy

from zim.utils import *

class TestNaturalSorting(tests.TestCase):

	def runTest(self):
		input = [
			'a', 'Aa', 'AA', # (these last 2 should be swapped due to case)
			'1.1 foo', '10.1.1 bar', '2.1 dus', '1.01 foo',
			'foo2bar', 'foo10bar', 'foo01bar',
		]
		wanted = [
			'1.01 foo', '1.1 foo', '2.1 dus', '10.1.1 bar',
			'a', 'AA', 'Aa',
			'foo01bar', 'foo2bar', 'foo10bar',
		]
		# TODO: add utf-8 test data and set matching locale

		result = natural_sorted(input)
		self.assertEqual(result, wanted)
		self.assertTrue(id(result) != id(input))

		result = copy(input)
		natural_sort(result)
		self.assertEqual(result, wanted)

		input = [(1, 'b'), (2, 'a')]
		wanted = [(2, 'a'), (1, 'b')]
		result = natural_sorted(input, key=lambda t: t[1])
		self.assertEqual(result, wanted)
		self.assertTrue(id(result) != id(input))


class TestOrderedDict(tests.TestCase):

	def runTest(self):
		items = [('foo', 1), ('bar', 2), ('baz', 3)]
		mydict = OrderedDict(items)

		self.assertIsInstance(repr(mydict), str)

		self.assertEqual(mydict.items(), items)
		self.assertEqual(list(mydict), [i[0] for i in items])
		self.assertEqual(mydict.keys(), [i[0] for i in items])

		mydict['bar'] = 'X'
		mydict.setdefault('foo', 'dus')
		items = [('foo', 1), ('bar', 'X'), ('baz', 3)]
		self.assertEqual(mydict.items(), items)
		self.assertEqual(list(mydict), [i[0] for i in items])
		self.assertEqual(mydict.keys(), [i[0] for i in items])

		del mydict['bar']
		mydict['bar'] = 'Y'
		items = [('foo', 1), ('baz', 3), ('bar', 'Y')]
		self.assertEqual(mydict.items(), items)
		self.assertEqual(list(mydict), [i[0] for i in items])
		self.assertEqual(mydict.keys(), [i[0] for i in items])

		mydict.pop('foo')
		mydict.setdefault('foo', 'dus')
		items = [('baz', 3), ('bar', 'Y'), ('foo', 'dus')]
		self.assertEqual(mydict.items(), items)
		self.assertEqual(list(mydict), [i[0] for i in items])
		self.assertEqual(mydict.keys(), [i[0] for i in items])
