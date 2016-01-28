# -*- coding: utf-8 -*-

# Copyright 2011-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests


import zim.plugins
import zim.config
import zim.formats

from zim.plugins import PluginManager
from zim.parsing import parse_date
from zim.plugins.tasklist import *


class TestTaskList(tests.TestCase):

	def testParsing(self):
		# Test correctnest of parsing
		from zim.plugins.tasklist import _task_labels_re, _next_label_re
		NO_DATE = '9999'

		def extract_tasks(text,
			task_label_re=_task_labels_re(['TODO', 'FIXME', 'Next']),
			next_label_re=_next_label_re('Next:'),
			nonactionable_tags=[],
			all_checkboxes=True,
			deadline=None,
		):
			# Returns a nested list of tuples, where each node is
			# like "(TASK, [CHILD, ...]) where each task (and child)
			# is a tuple like (open, actionable, prio, due, description)
			parser = zim.formats.get_format('wiki').Parser()
			parsetree = parser.parse(text)
			origtree = parsetree.tostring()
			#~ print 'TREE', origtree

			parser = TasksParseTreeParser(
				task_label_re,
				next_label_re,
				nonactionable_tags,
				all_checkboxes,
				deadline,
			)
			parser.parse(parsetree)
			tasks = parser.get_tasks()

			self.assertEqual(parsetree.tostring(), origtree) # parser should not modify the tree
			return tasks

		def t(label, open=True, due=NO_DATE, prio=0, tags='', actionable=True):
			# Generate a task tuple
			# (open, actionable, prio, due, tags, description)
			if tags:
				tags = set(unicode(tags).split(','))
			else:
				tags = set()
			return [open, actionable, prio, due, tags, unicode(label)]

		# Note that this same text is in the test notebook
		# so it gets run through the index as well - keep in sync
		text = '''\
Try all kind of combos - see if the parser trips

TODO:
[ ] A
[ ] B
[ ] C

[ ] D
[ ] E

FIXME: dus
~~FIXME:~~ foo

[ ] Simple
[ ] List

[ ] List with
	[ ] Nested items
	[*] Some are done
	[*] Done but with open child
		[x] Others not
		[ ] FOOOOO
[ ] Bar

[ ] And then there are @tags
[ ] Next: And due dates
[ ] Date [d: 11/12]
[ ] Date [d: 11/12/2012]
	[ ] TODO: BAR !!!

TODO @home:
[ ] Some more tasks !!!
	[ ] Foo !
		* some sub item
		* some other item
	[ ] Bar

TODO: dus
FIXME: jaja - TODO !! @FIXME
~~TODO~~: Ignore this one - it is strike out

* TODO: dus - list item
* FIXME: jaja - TODO !! @FIXME - list item
* ~~TODO~~: Ignore this one - it is strike out - list item

* Bullet list
* With tasks as sub items
	[ ] Sub item bullets
* dus

1. Numbered list
2. With tasks as sub items
	[ ] Sub item numbered
3. dus

Test task inheritance:

[ ] Main @tag1 @tag2 !
	[*] Sub1
	[ ] Sub2 @tag3 !!!!
		[*] Sub2-1
		[*] Sub2-2 @tag4
		[ ] Sub2-3
	[ ] Sub3

TODO: @someday
[ ] A
[ ] B
	[ ] B-1
[ ] C

TODO @home
[ ] main task
	[x] do this
	[ ] Next: do that
	[ ] Next: do something else
'''

		mydate = '%04i-%02i-%02i' % parse_date('11/12')

		wanted = [
			(t('A'), []),
			(t('B'), []),
			(t('C'), []),
			(t('D'), []),
			(t('E'), []),
			(t('FIXME: dus'), []),
			(t('Simple'), []),
			(t('List'), []),
			(t('List with'), [
				(t('Nested items'), []),
				(t('Some are done', open=False), []),
				(t('Done but with open child', open=True), [
					(t('Others not', open=False), []),
					(t('FOOOOO'), []),
				]),
			]),
			(t('Bar'), []),
			(t('And then there are @tags', tags='tags'), []),
			(t('Next: And due dates', actionable=False), []),
			(t('Date [d: 11/12]', due=mydate), []),
			(t('Date [d: 11/12/2012]', due='2012-12-11'), [
				(t('TODO: BAR !!!', prio=3, due='2012-12-11'), []),
				# due date is inherited
			]),
			# this list inherits the @home tag - and inherits prio
			(t('Some more tasks !!!', prio=3, tags='home'), [
				(t('Foo !', prio=1, tags='home'), []),
				(t('Bar', prio=3, tags='home'), []),
			]),
			(t('TODO: dus'), []),
			(t('FIXME: jaja - TODO !! @FIXME', prio=2, tags='FIXME'), []),
			(t('TODO: dus - list item'), []),
			(t('FIXME: jaja - TODO !! @FIXME - list item', prio=2, tags='FIXME'), []),
			(t('Sub item bullets'), []),
			(t('Sub item numbered'), []),
			(t('Main @tag1 @tag2 !', prio=1, tags='tag1,tag2'), [
				(t('Sub1', prio=1, open=False, tags='tag1,tag2'), []),
				(t('Sub2 @tag3 !!!!', prio=4, tags='tag1,tag2,tag3'), [
					(t('Sub2-1', prio=4, open=False, tags='tag1,tag2,tag3'), []),
					(t('Sub2-2 @tag4', prio=4, open=False, tags='tag1,tag2,tag3,tag4'), []),
					(t('Sub2-3', prio=4, tags='tag1,tag2,tag3'), []),
				]),
				(t('Sub3', prio=1, tags='tag1,tag2'), []),
			]),
			(t('A', tags='someday', actionable=False), []),
			(t('B', tags='someday', actionable=False), [
				(t('B-1', tags='someday', actionable=False), []),
			]),
			(t('C', tags='someday', actionable=False), []),
			(t('main task', tags='home'), [
				(t('do this', open=False, tags='home'), []),
				(t('Next: do that', tags='home'), []),
				(t('Next: do something else', tags='home', actionable=False), []),
			])
		]
		tasks = extract_tasks(text, nonactionable_tags=['someday', 'maybe'])
		self.assertEqual(tasks, wanted)

		wanted = [
			(t('A'), []),
			(t('B'), []),
			(t('C'), []),
			(t('FIXME: dus'), []),
			(t('Next: And due dates', actionable=False), []),
			(t('TODO: BAR !!!', prio=3), []),
			# this list inherits the @home tag - and inherits prio
			(t('Some more tasks !!!', prio=3, tags='home'), [
				(t('Foo !', prio=1, tags='home'), []),
				(t('Bar', prio=3, tags='home'), []),
			]),
			(t('TODO: dus'), []),
			(t('FIXME: jaja - TODO !! @FIXME', prio=2, tags='FIXME'), []),
			(t('TODO: dus - list item'), []),
			(t('FIXME: jaja - TODO !! @FIXME - list item', prio=2, tags='FIXME'), []),
			(t('A', tags='someday', actionable=False), []),
			(t('B', tags='someday', actionable=False), [
				(t('B-1', tags='someday', actionable=False), []),
			]),
			(t('C', tags='someday', actionable=False), []),
			(t('main task', tags='home'), [
				(t('do this', open=False, tags='home'), []),
				(t('Next: do that', tags='home'), []),
				(t('Next: do something else', tags='home', actionable=False), []),
			])
		]
		tasks = extract_tasks(text, nonactionable_tags=['someday', 'maybe'], all_checkboxes=False)
		self.assertEqual(tasks, wanted)

		# TODO: more tags, due dates, tags for whole list, etc. ?

	def testIndexing(self):
		'''Check indexing of tasklist plugin'''
		klass = PluginManager.get_plugin_class('tasklist')
		plugin = klass()

		notebook = tests.new_notebook()
		plugin.extend(notebook)
		self.assertIsInstance(notebook.index._indexers[-1], TasksIndexer)

		# Test indexing based on index signals
		notebook.index.update()

		view = TasksView.new_from_index(notebook.index)
		tasks = list(view.list_tasks())
		self.assertTrue(len(tasks) > 5)
		for task in tasks:
			path = view.get_path(task)
			self.assertTrue(not path is None)

	def testTaskListTreeView(self):
		klass = PluginManager.get_plugin_class('tasklist')
		plugin = klass()

		notebook = tests.new_notebook()
		plugin.extend(notebook)
		notebook.index.update()

		from zim.plugins.tasklist import TaskListTreeView
		view = TasksView.new_from_index(notebook.index)
		opener = tests.MockObject()
		treeview = TaskListTreeView(view, opener, task_labels=['TODO', 'FIXME'], next_label='Next')

		menu = treeview.get_popup()

		# Check these do not cause errors - how to verify state ?
		tests.gtk_activate_menu_item(menu, _("Expand _All"))
		tests.gtk_activate_menu_item(menu, _("_Collapse All"))

		# Copy tasklist -> csv
		from zim.gui.clipboard import Clipboard
		tests.gtk_activate_menu_item(menu, 'gtk-copy')
		text = Clipboard.get_text()
		lines = text.splitlines()
		self.assertTrue(len(lines) > 10)
		self.assertTrue(len(lines[0].split(',')) > 3)
		self.assertFalse(any('<span' in l for l in lines)) # make sure encoding is removed

		# Test tags
		tags = treeview.get_tags()
		for tag in ('home', 'FIXME', '__no_tags__', 'tags'):
			self.assertIn(tag, tags)
			self.assertGreater(tags[tag], 0)

		# TODO test filtering for tags, labels, string - all case insensitive


	#~ def testDialog(self):
		#~ '''Check tasklist plugin dialog'''
		#
		# TODO
