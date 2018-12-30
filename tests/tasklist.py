
# Copyright 2011-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>



import tests


import zim.plugins
import zim.config
import zim.formats

from zim.plugins import PluginManager
from zim.parsing import parse_date
from zim.plugins.tasklist import *


from zim.tokenparser import TokenBuilder, testTokenStream
from zim.formats import ParseTreeBuilder
from zim.formats.wiki import Parser as WikiParser

WIKI_TEXT = '''\
Try all kind of combos - see if the parser trips

=== TODO: test heading with label ===

=== Not a task ===

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
[ ] Date <2012-03-27 >2012-03-01
[ ] Date < wk1213.3
[ ] Date < wk1213.3! with punctuation
[ ] Not a date < wk1213.8
[ ] Not a date < wk1213foooooo

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

Some text
	With indenting that looks like list but isn't

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

[*] Closed parent task
	[ ] With open child
	[ ] Must be open as well to show up in list

[*] Closed parent task
	[*] With closed children
	[*] Should not

Edge case with wrongly nested list
* Foo
		* bullet 1
		* bullet 2

'''

from zim.plugins.tasklist.indexer import TaskParser
from zim.parsing import parse_date

NO_DATE = '9999'

def t(desc, open=True, start=0, due=NO_DATE, prio=0, tags=''):
	# Generate a task tuple
	# 0:open, 1:prio, 2:start, 3:due, 4:tags, 5:desc
	if tags:
		tags = set(str(tags).split(','))
	else:
		tags = set()
	return [open, prio, start, due, tags, str(desc)]


class TestTaskParser(tests.TestCase):

	def testAllCheckboxes(self):
		mydate = '%04i-%02i-%02i' % parse_date('11/12')

		wanted = [
			(t('TODO: test heading with label'), []),
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
			(t('Next: And due dates'), []),
			(t('Date [d: 11/12]', due=mydate), []),
			(t('Date [d: 11/12/2012]', due='2012-12-11'), [
				(t('TODO: BAR !!!', prio=3, due='2012-12-11'), []),
				# due date is inherited
			]),
			(t('Date <2012-03-27 >2012-03-01', due='2012-03-27', start='2012-03-01'), []),
			(t('Date < wk1213.3', due='2012-03-28'), []),
			(t('Date < wk1213.3! with punctuation', due='2012-03-28', prio=1), []),
			(t('Not a date < wk1213.8'), []),
			(t('Not a date < wk1213foooooo'), []),

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
			(t('A', tags='someday'), []),
			(t('B', tags='someday'), [
				(t('B-1', tags='someday'), []),
			]),
			(t('C', tags='someday'), []),
			(t('main task', tags='home'), [
				(t('do this', open=False, tags='home'), []),
				(t('Next: do that', tags='home'), []),
				(t('Next: do something else', tags='home'), []),
			]),
			(t('Closed parent task', open=True), [
				(t('With open child'), []),
				(t('Must be open as well to show up in list'), []),
			]),
			(t('Closed parent task', open=False), [
				(t('With closed children', open=False), []),
				(t('Should not', open=False), []),
			]),
		]


		tree = WikiParser().parse(WIKI_TEXT)
		tb = TokenBuilder()
		tree.visit(tb)
		tokens = tb.tokens
		testTokenStream(tokens)

		parser = TaskParser()
		with tests.LoggingFilter('zim.plugins.tasklist', 'Invalid date format'):
			tasks = parser.parse(tokens)

		#~ import pprint; pprint.pprint(tasks)
		self.assertEqual(tasks, wanted)

	def testLabelledCheckboxes(self):
		mydate = '%04i-%02i-%02i' % parse_date('11/12')

		wanted = [
			(t('TODO: test heading with label'), []),
			(t('A'), []),
			(t('B'), []),
			(t('C'), []),
			(t('FIXME: dus'), []),

			# this time does not inherit due-date from non-task:
			(t('TODO: BAR !!!', prio=3), []),

			(t('Some more tasks !!!', prio=3, tags='home'), [
				(t('Foo !', prio=1, tags='home'), []),
				(t('Bar', prio=3, tags='home'), []),
			]),
			(t('TODO: dus'), []),
			(t('FIXME: jaja - TODO !! @FIXME', prio=2, tags='FIXME'), []),
			(t('TODO: dus - list item'), []),
			(t('FIXME: jaja - TODO !! @FIXME - list item', prio=2, tags='FIXME'), []),
			(t('A', tags='someday'), []),
			(t('B', tags='someday'), [
				(t('B-1', tags='someday'), []),
			]),
			(t('C', tags='someday'), []),
			(t('main task', tags='home'), [
				(t('do this', open=False, tags='home'), []),
				(t('Next: do that', tags='home'), []),
				(t('Next: do something else', tags='home'), []),
			]),
		]


		tree = WikiParser().parse(WIKI_TEXT)
		tb = TokenBuilder()
		tree.visit(tb)
		tokens = tb.tokens
		testTokenStream(tokens)

		parser = TaskParser(all_checkboxes=False)
		with tests.LoggingFilter('zim.plugins.tasklist', 'Invalid date format'):
			tasks = parser.parse(tokens)

		#~ import pprint; pprint.pprint(tasks)
		self.assertEqual(tasks, wanted)

	def testDate(self):
		text = '''\
[ ] Task <2018-12
[ ] Task >2018-12
'''
		wanted = [
			(t('Task <2018-12', due='2018-12-31'), []),
			(t('Task >2018-12', start='2018-12-01'), [])
		]

		tree = WikiParser().parse(text)
		tb = TokenBuilder()
		tree.visit(tb)
		tokens = tb.tokens
		testTokenStream(tokens)

		parser = TaskParser()
		tasks = parser.parse(tokens)

		#import pprint; pprint.pprint(tasks)
		self.assertEqual(tasks, wanted)



class TestTaskList(tests.TestCase):

	def testIndexing(self):
		'''Check indexing of tasklist plugin'''
		plugin = PluginManager.load_plugin('tasklist')
		notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)

		# Test indexing based on index signals
		notebook.index.check_and_update()

		view = TasksView.new_from_index(notebook.index)
		for tasks in (
			list(view.list_open_tasks()),
			list(view.list_open_tasks_flatlist()),
		):
			self.assertTrue(len(tasks) > 5)
			for task in tasks:
				path = view.get_path(task)
				self.assertTrue(not path is None)

	def testTaskListTreeView(self):
		plugin = PluginManager.load_plugin('tasklist')

		notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)
		notebook.index.check_and_update()

		from zim.plugins.tasklist.gui import TaskListTreeView
		view = TasksView.new_from_index(notebook.index)
		opener = tests.MockObject()
		treeview = TaskListTreeView(view, opener, task_labels=['TODO', 'FIXME'])

		menu = treeview.get_popup()

		# Check these do not cause errors - how to verify state ?
		tests.gtk_activate_menu_item(menu, _("Expand _All"))
		tests.gtk_activate_menu_item(menu, _("_Collapse All"))

		# Copy tasklist -> csv
		from zim.gui.clipboard import Clipboard
		tests.gtk_activate_menu_item(menu, _('_Copy'))
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
