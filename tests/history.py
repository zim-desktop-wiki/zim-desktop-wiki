# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from tests import TestCase, get_test_notebook

import zim.history
from zim.history import History, HistoryPath
from zim.notebook import Path
from zim.config import ConfigDict

class TestHistory(TestCase):

	def setUp(self):
		zim.history.MAX_HISTORY = 100
		self.notebook = get_test_notebook()
		self.pages = [self.notebook.get_page(Path(name))
			for name in self.notebook.testdata_manifest]

	def _assertCurrent(self, history, page):
		current = history.get_current()
		self.assertTrue(isinstance(current, HistoryPath))
		self.assertEqual(current.name, page.name)

	def testLinear(self):
		'''Walk back and forth through the history'''
		history = History(self.notebook)
		self.assertTrue(history.get_current() is None)
		for page in self.pages:
			history.append(page)
		self.assertEqual(len(history.history), len(self.pages))
		self.assertEqual(history.current, len(self.pages) - 1)

		self._assertCurrent(history, self.pages[-1])

		pages = list(history.get_history())
		self.assertEqual(pages[0], history.get_current())
		self.assertEqual(len(pages), len(self.pages))

		self.assertEqual(pages[0].cursor, None)
			# Newly appended pages should not have the cursor
			# set - pageview has logic to do the right thing when
			# no cursor is set. Setting default e.g. 0 will
			# overrule this logic.

		# walk backwards
		for i in range(2, len(self.pages)+1):
			prev = history.get_previous()
			self.assertFalse(prev is None)
			self.assertEqual(prev.name, self.pages[-i].name)
			self.assertFalse(prev.is_last)
			history.set_current(prev)

		self._assertCurrent(history, self.pages[0])
		self.assertTrue(history.get_previous() is None)
		self.assertTrue(prev.is_first)

		# walk forward
		for i in range(1, len(self.pages)):
			next = history.get_next()
			self.assertFalse(next is None)
			self.assertEqual(next.name, self.pages[i].name)
			self.assertFalse(next.is_first)
			history.set_current(next)

		self._assertCurrent(history, self.pages[-1])
		self.assertTrue(history.get_next() is None)
		self.assertTrue(history.get_current().is_last)

		# Add page multiple times
		i = len(history.history)
		path = Path(history.history[-1].name)
		for j in range(5):
			history.append(path)
		self.assertEqual(len(history.history), i)
		self.assertEqual(history.current, i - 1)

		# Test dropping forward stack
		path1 = history.history[10]
		path2 = history.history[-1]
		history.set_current(path1)
		self.assertEqual(history.current, 10)
		self.assertEqual(len(history.history), len(self.pages))

		history.append(path2)
		self.assertEqual(history.current, 11)
		self.assertEqual(len(history.history), 12)

		# Test max entries
		old = zim.history.MAX_HISTORY
		zim.history.MAX_HISTORY = 3
		for page in self.pages:
			history.append(page)
		zim.history.MAX_HISTORY = old

		self.assertEqual(len(history.history), 3)

	def testUnique(self):
		'''Get recent pages from history'''
		history = History(self.notebook)
		for page in self.pages:
			history.append(page)
		self.assertEqual(len(history.history), len(self.pages))

		unique = list(history.get_unique())
		self.assertEqual(unique[0], history.get_current())
		self.assertEqual(len(unique), len(self.pages))

		for page in self.pages:
			history.append(page)
		self.assertEqual(len(history.history), 2*len(self.pages))

		unique = list(history.get_unique())
		self.assertEqual(unique[0], history.get_current())
		self.assertEqual(len(unique), len(self.pages))

		unique = set([page.name for page in unique]) # collapse doubles
		self.assertEqual(len(unique), len(self.pages))

	def testChildren(self):
		'''Test getting namespace from history'''
		history = History(self.notebook)
		for name in ('Test:wiki', 'Test:foo:bar', 'Test:foo', 'TODOList:bar'):
			page = self.notebook.get_page(Path(name))
			history.append(page)

		self.assertEqual(history.get_child(Path('Test')), Path('Test:foo'))
		self.assertEqual(history.get_grandchild(Path('Test')), Path('Test:foo:bar'))
		self.assertEqual(history.get_child(Path('NonExistent')), None)
		self.assertEqual(history.get_grandchild(Path('NonExistent')), None)

		history.append(self.notebook.get_page(Path('Test:wiki')))
		self.assertEqual(history.get_child(Path('Test')), Path('Test:wiki'))
		self.assertEqual(history.get_grandchild(Path('Test')), Path('Test:wiki'))

	def testMovePage(self):
		'''Test history is updated for moved pages'''
		history = History(self.notebook)
		for page in self.pages:
			history.append(page)

		self.assertTrue(Path('Test:wiki') in history.history)

		history._on_page_moved(Path('Test'), Path('New'), False)
		self.assertFalse(Path('Test:wiki') in history.history)
		self.assertTrue(Path('New:wiki') in history.history)

		history._on_page_moved(Path('New'), Path('Test'), False)
		self.assertFalse(Path('New:wiki') in history.history)
		self.assertTrue(Path('Test:wiki') in history.history)

		self.assertEqual(history.history, self.pages)

	def testDeletedNotInUnique(self):
		'''Test if deleted pages and their children show up in unique history list'''
		history = History(self.notebook)
		for page in self.pages:
			history.append(page)
		for page in self.pages:
			history.append(page)

		self.assertEqual(len(history.history), 2 * len(self.pages))

		uniques = list(history.get_unique())
		self.assertEqual(len(uniques), len(self.pages))

		history._on_page_deleted(self.pages[0])
		uniques = list(history.get_unique())
		self.assertTrue(len(uniques) < len(self.pages))
		i = len(uniques)

		history._on_page_stored(self.pages[0])
		uniques = list(history.get_unique())
		self.assertEqual(len(uniques), i + 1)
			# Not same as len(self.pages) because of deleted children

		for page in self.pages:
			history._on_page_deleted(page)
		uniques = list(history.get_unique())
		self.assertEqual(len(uniques), 0)

		self.assertEqual(
			len(list(history.get_history())),
			2 * len(self.pages)  )

		for page in self.pages:
			history._on_page_stored(page)
		uniques = list(history.get_unique())
		self.assertEqual(len(uniques), len(self.pages))


	def testSerialize(self):
		'''Test parsing the history from the state file'''
		uistate = ConfigDict()
		history = History(self.notebook, uistate)

		for page in self.pages:
			history.append(page)
		self.assertEqual(len(history.history), len(self.pages))
		self._assertCurrent(history, self.pages[-1])

		# rewind 2
		for i in range(2):
			prev = history.get_previous()
			history.set_current(prev)

		# check state
		#~ import pprint
		#~ pprint.pprint(uistate)
		self.assertEqual(len(uistate['History']['list']), len(history.history))
		self.assertEqual(uistate['History']['current'], len(history.history)-3)

		# clone uistate by text
		lines = uistate.dump()
		newuistate = ConfigDict()
		newuistate.parse(lines)

		# check new state
		self.assertEqual(len(uistate['History']['list']), len(history.history))
		self.assertEqual(newuistate['History']['current'], len(history.history)-3)

		# and compare resulting history object
		newhistory = History(self.notebook, newuistate)
		self.assertEqual(newhistory.history, history.history)
		self.assertEqual(newhistory.current, history.current)
