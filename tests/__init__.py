# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Zim test suite'''

import unittest
import codecs

from zim.notebook import Notebook

__all__ = ['utils', 'fs', 'formats', 'templates', 'stores', 'notebook']

__unittest = 1 # needed to get stack trace OK for class TestCase

def get_notebook_data(format):
	'''Generator function for test data'''
	assert format == 'wiki' # No other formats available for now
	file = codecs.open('tests/data/notebook-wiki.txt', encoding='utf8')
	pagename = None
	buffer = u''
	for line in file:
		if line.startswith('%%%%'):
			# new page start, yield previous page
			if not pagename is None:
				yield (pagename, buffer)
			pagename = line.strip('% \n')
			buffer = u''
		else:
			buffer += line
	yield (pagename, buffer)


def	get_test_notebook(format='wiki'):
	'''Returns a notebook with a memory store and some test data'''
	notebook = Notebook()
	store = notebook.add_store('', 'memory')
	for name, text in get_notebook_data(format):
			store._set_node(name, text)
	return notebook


def get_test_page(name=':Foo'):
	'''FIXME'''
	notebook = Notebook()
	notebook.add_store('', 'memory')
	return notebook.get_page(name)


class TestCase(unittest.TestCase):
	'''FIXME'''

	def assertEqualDiff(self, first, second, msg=None):
		'''Fail if the two strings are unequal as determined by
		the '==' operator. On failure shows a diff of both strings.
		'''
		if msg is None:
			msg = u'Strings differ:'
		else:
			msg = unicode(msg)
		if not first == second:
			#~ print '>>>>\n'+first+'=====\n'+second+'<<<<\n'
			if not first:
				msg += ' first string is empty'
			elif not second:
				msg += ' second string is empty'
			elif not type(first) == type(second):
				types = type(first), type(second)
				msg += ' types differ, %s and %s' % types
			else:
				from difflib import Differ
				diff = Differ().compare(
					second.splitlines(), first.splitlines() )
				# switching first and second, because usually second
				# is the reference we are testing against
				msg += '\n' + '\n'.join(diff)
			raise self.failureException, msg.encode('utf8')


