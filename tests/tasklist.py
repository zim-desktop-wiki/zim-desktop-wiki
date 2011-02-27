# -*- coding: utf-8 -*-

# Copyright 2011 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from tests import TestCase, MockObject, get_test_notebook

import zim.plugins
import zim.config
import zim.formats


class TestTaskList(TestCase):

	def runTest(self):
		'''Check indexing of tasklist plugin'''
		klass = zim.plugins.get_plugin('tasklist')
		ui = MockUI()
		plugin = klass(ui)

		# Test indexing based on index signals
		ui.notebook.index.flush()
		ui.notebook.index.update()
		self.assertTrue(plugin.db_initialized)
		tasks = list(plugin.list_tasks())
		self.assertTrue(len(tasks) > 5)
		for task in tasks:
			path = plugin.get_path(task)
			self.assertTrue(not path is None)

		# Test specific examples
		text = '''\
Foo Bar

TODO:
[ ] A
[ ] B
[ ] C

[ ] D
[ ] E

FIXME: dus
~~FIXME:~~ foo
'''
		parser = zim.formats.get_format('wiki').Parser()
		tree = parser.parse(text)
		origtree = tree.tostring()

		tasks = plugin.extract_tasks(tree)
		labels = [task[-1] for task in tasks]
		self.assertEqual(labels, ['A', 'B', 'C', 'D', 'E', 'FIXME: dus'])
		self.assertEqualDiff(tree.tostring(), origtree)
			# extract should not modify the tree

		plugin.preferences['all_checkboxes'] = False
		tasks = plugin.extract_tasks(tree)
		labels = [task[-1] for task in tasks]
		self.assertEqual(labels, ['A', 'B', 'C', 'FIXME: dus'])
		self.assertEqualDiff(tree.tostring(), origtree)
			# extract should not modify the tree

		# TODO: test tags, due dates, tags for whole list, etc.



class MockUI(MockObject):

	def __init__(self):
		MockObject.__init__(self)
		self.preferences = zim.config.ConfigDict()
		self.uistate = zim.config.ConfigDict()
		self.notebook = get_test_notebook()
