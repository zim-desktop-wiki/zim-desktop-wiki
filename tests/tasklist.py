
# Copyright 2011-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>



import tests

from functools import partial

from zim.plugins import PluginManager
from zim.plugins.tasklist import *
from zim.plugins.tasklist.indexer import *
from zim.plugins.tasklist.indexer import _MAX_DUE_DATE, _MIN_START_DATE

from zim.parse.dates import old_parse_date
from zim.parse.tokenlist import testTokenStream
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
[ ] Waiting: waiting items
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


def t(desc, status=TASK_STATUS_OPEN, waiting=False, start=_MIN_START_DATE, due=_MAX_DUE_DATE, prio=0, tags=''):
	# Generate a task tuple
	# 0:status, 1:prio, 2:waiting, 3:start, 4:due, 5:tags, 6:desc
	if tags:
		tags = set(str(tags).split(','))
	else:
		tags = set()
	return [status, prio, waiting, start, due, tags, str(desc)]


class TestTaskParser(tests.TestCase):

	def assertWikiTextToTasks(self, wikitext, wanted, parser_args={}, parse_args={}):
		tree = WikiParser().parse(wikitext)
		tokens = list(tree.iter_tokens())
		testTokenStream(tokens)

		parser = TaskParser(**parser_args)
		with tests.LoggingFilter('zim.plugins.tasklist', 'Invalid date format'):
			tasks = parser.parse(tokens, **parse_args)

		#~ import pprint; pprint.pprint(tasks)
		self.assertEqual(tasks, wanted)

	def testAllCheckboxes(self):
		mydate = '%04i-%02i-%02i' % old_parse_date('11/12')

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
				(t('Some are done', status=TASK_STATUS_CLOSED), []),
				(t('Done but with open child'), [
					(t('Others not', status=TASK_STATUS_CANCELLED), []),
					(t('FOOOOO'), []),
				]),
			]),
			(t('Bar'), []),
			(t('And then there are @tags', tags='tags'), []),
			(t('Waiting: waiting items', waiting=True), []),
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
				(t('Sub1', prio=1, status=TASK_STATUS_CLOSED, tags='tag1,tag2'), []),
				(t('Sub2 @tag3 !!!!', prio=4, tags='tag1,tag2,tag3'), [
					(t('Sub2-1', prio=4, status=TASK_STATUS_CLOSED, tags='tag1,tag2,tag3'), []),
					(t('Sub2-2 @tag4', prio=4, status=TASK_STATUS_CLOSED, tags='tag1,tag2,tag3,tag4'), []),
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
				(t('do this', status=TASK_STATUS_CANCELLED, tags='home'), []),
				(t('Next: do that', tags='home'), []),
				(t('Next: do something else', tags='home'), []),
			]),
			(t('Closed parent task'), [
				(t('With open child'), []),
				(t('Must be open as well to show up in list'), []),
			]),
			(t('Closed parent task', status=TASK_STATUS_CLOSED), [
				(t('With closed children', status=TASK_STATUS_CLOSED), []),
				(t('Should not', status=TASK_STATUS_CLOSED), []),
			]),
		]

		self.assertWikiTextToTasks(WIKI_TEXT, wanted)

	def testLabelledCheckboxes(self):
		mydate = '%04i-%02i-%02i' % old_parse_date('11/12')

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
				(t('do this', status=TASK_STATUS_CANCELLED, tags='home'), []),
				(t('Next: do that', tags='home'), []),
				(t('Next: do something else', tags='home'), []),
			]),
		]

		self.assertWikiTextToTasks(WIKI_TEXT, wanted, parser_args={'all_checkboxes': False})

	def testDate(self):
		text = '''\
[ ] Task <2018-12
[ ] Task >2018-12
'''
		wanted = [
			(t('Task <2018-12', due='2018-12-31'), []),
			(t('Task >2018-12', start='2018-12-01'), [])
		]

		self.assertWikiTextToTasks(text, wanted)

	def testDueDateInHeading(self):
		text = '''
=== Head {{id: 2021-10-30}} ===
[ ] Task 1

TODO: Task 2
'''
		wanted = [
			(t('Task 1', due='2021-10-30'), []),
			(t('TODO: Task 2', due='2021-10-30'), []),
		]

		daterange = (datetime.date(2021, 10, 25), datetime.date(2021, 10, 31))
		self.assertWikiTextToTasks(text, wanted, parse_args={
			'default_due_date': daterange[1].isoformat(),
			'daterange': daterange
		})

	def testStartDateInHeading(self):
		text = '''
=== Head {{id: 20211030}} ===
[ ] Task 1

TODO: Task 2
'''
		wanted = [
			(t('Task 1', start='2021-10-30'), []),
			(t('TODO: Task 2', start='2021-10-30'), []),
		]

		daterange = (datetime.date(2021, 10, 25), datetime.date(2021, 10, 31))
		self.assertWikiTextToTasks(text, wanted, parse_args={
			'default_start_date': daterange[0].isoformat(),
			'daterange': daterange
		})

	def testDateInHeadingEnforceRange(self):
		text = '''
=== Head {{id: 2021-10-30}} ===
[ ] Task 1
=== Head {{id: 2022-10-30}} ===
[ ] Task 2
=== Head {{id: 2021-10-30}} ===
[ ] Task 3
'''

		wanted = [
			(t('Task 1', start='2021-10-30'), []),
			(t('Task 2', start='2021-10-25'), []),
			(t('Task 3', start='2021-10-30'), []),
		]

		daterange = (datetime.date(2021, 10, 25), datetime.date(2021, 10, 31))
		self.assertWikiTextToTasks(text, wanted, parse_args={
			'default_start_date': daterange[0].isoformat(),
			'daterange': daterange
		})

	def testDateInHeadingMultipleIDs(self):
		text = '''
=== Head {{id: foo}} {{id: 2021-10-30}} {{id bar}} ===
[ ] Task
'''
		wanted = [
			(t('Task', start='2021-10-30'), []),
		]

		daterange = (datetime.date(2021, 10, 25), datetime.date(2021, 10, 31))
		self.assertWikiTextToTasks(text, wanted, parse_args={
			'default_start_date': daterange[0].isoformat(),
			'daterange': daterange
		})

	def testDateInHeadingResetNextHeading(self):
		text = '''
== Top Head ==
=== Head {{id: 2021-10-30}} ===
[ ] Task 1
==== Subhead ====
[ ] Task 2
=== New Head ===
[ ] Task 3
=== New Head {{id: 2021-10-31}} ===
[ ] Task 4
== Top Head ==
[ ] Task 5
'''

		wanted = [
			(t('Task 1', start='2021-10-30'), []),
			(t('Task 2', start='2021-10-30'), []),
			(t('Task 3', start='2021-10-25'), []),
			(t('Task 4', start='2021-10-31'), []),
			(t('Task 5', start='2021-10-25'), []),
		]

		daterange = (datetime.date(2021, 10, 25), datetime.date(2021, 10, 31))
		self.assertWikiTextToTasks(text, wanted, parse_args={
			'default_start_date': daterange[0].isoformat(),
			'daterange': daterange
		})

	def testInheritTags(self):
		text = '''
[ ] Task 1 @work
	[ ] Task 2 @phone
[ ] Task 3 @home
'''

		wanted = [
			(t('Task 1 @work', tags='work'), [
				(t('Task 2 @phone', tags='work,phone'), []),
			]),
			(t('Task 3 @home', tags='home'), []),
		]

		self.assertWikiTextToTasks(text, wanted)

	def testLabelsWithAndWithoutColon(self):
		text = '''
=== TODO heading 1 ===

=== TODO: heading 2 ===

TODO: Task 1
TODO Task 2
'''

		wanted = [
			(t('TODO heading 1'), []),
			(t('TODO: heading 2'), []),
			(t('TODO: Task 1'), []),
			(t('TODO Task 2'), []),
		]

		self.assertWikiTextToTasks(text, wanted)

	def testParseTaskLabels(self):
		from zim.plugins.tasklist.indexer import _parse_task_labels
		self.assertEqual(_parse_task_labels('TODO, FIXME'), ['TODO', 'FIXME'])
		self.assertEqual(_parse_task_labels('TODO,FIXME'), ['TODO', 'FIXME'])
		self.assertEqual(_parse_task_labels('TODO FIXME'), ['TODO', 'FIXME'])

	def testLabelHeadedList(self):
		# with / without colon, with / without empty line
		text = '''
TODO:
[ ] Task 1
[ ] Task 2

TODO
[ ] Task 3
[ ] Task 4


TODO:

[ ] No task 1
[ ] No task 2

TODO: my task
[ ] No task 3
[ ] No task 4
'''

		wanted = [
			(t('Task 1'), []),
			(t('Task 2'), []),
			(t('Task 3'), []),
			(t('Task 4'), []),
			(t('TODO:'), []),
			(t('TODO: my task'), []),
		]

		self.assertWikiTextToTasks(text, wanted, parser_args={'all_checkboxes': False})

	def testLabelHeadedListInheritAll(self):
		# tags, start / due date, priority all same as a parent task, vary colon placement
		text = '''
TODO @home:
[ ] Task 1
[ ] Task 2

TODO !!!
[ ] Task 3
[ ] Task 4

TODO: <2021-11-01 >2021-10-01
[ ] Task 5
[ ] Task 6
'''

		wanted = [
			(t('Task 1', tags='home'), []),
			(t('Task 2', tags='home'), []),
			(t('Task 3', prio=3), []),
			(t('Task 4', prio=3), []),
			(t('Task 5', start='2021-10-01', due='2021-11-01'), []),
			(t('Task 6', start='2021-10-01', due='2021-11-01'), []),
		]

		self.assertWikiTextToTasks(text, wanted, parser_args={'all_checkboxes': False})


class TestTaskList(tests.TestCase):

	def testIndexing(self):
		'''Check indexing of tasklist plugin'''
		plugin = PluginManager.load_plugin('tasklist')
		notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)

		# Test indexing based on index signals
		notebook.index.check_and_update()

		for klass in (AllTasks, ActiveTasks, NextActionTasks, InboxTasks, OpenProjectsTasks): # WaitingTasks
			view = klass.new_from_index(notebook.index)
			tasks = list(view)
			self.assertGreater(len(tasks), 3, klass.__name__)
			for task in tasks:
				path = view.get_path(task)
				self.assertTrue(not path is None)

	def testTaskListTreeView(self):
		plugin = PluginManager.load_plugin('tasklist')

		notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)
		notebook.index.check_and_update()

		from zim.plugins.tasklist.gui import TaskListTreeView
		view = AllTasks.new_from_index(notebook.index)
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
		#tags = treeview.get_tags()
		#for tag in ('home', 'FIXME', '__no_tags__', 'tags'):
		#	self.assertIn(tag, tags)
		#	self.assertGreater(tags[tag], 0)

		# TODO test filtering for tags, labels, string - all case insensitive


	#~ def testDialog(self):
		#~ '''Check tasklist plugin dialog'''
		#
		# TODO


class TestIndexViewMixin(object):

	def setUpClass():
		PluginManager.load_plugin('tasklist')

	def setUp(self):
		self.notebook = self.setUpNotebook(content={'Test': self.input})
		self.selection = self.klass.new_from_index(self.notebook.index)

	def testListTasks(self):
		def walk(parent):
			tasks = []
			for row in self.selection.list_tasks(parent=parent):
				task = t(row['description'], row['status'], bool(row['waiting']), row['start'], row['due'], row['prio'], row['tags'])
				if row['haschildren']:
					children = walk(row)
					tasks.append((task, children))
				else:
					tasks.append((task, []))

			return tasks

		tasks = walk(None)
		self.assertEqual(tasks, self.tasks)


class TestAllTasks(TestIndexViewMixin, tests.TestCase):

	klass = AllTasks

	input = '''
	[ ] Foo
	[*] Bar
	[ ] Parent 1
		[ ] Child 1.1
	[ ] Parent 2
		[x] Child 2.1
	[ ] Parent with prio !!!
		[*] Child with prio !!!
	[ ] Later >3000-01-01
	[ ] Started >2000-01-01
	[ ] Waiting: foo
	[ ] Prio !!!
	[ ] With due date <3000-01-01
	'''

	tasks = [
		(t('Parent with prio !!!', prio=3), []),
		(t('Prio !!!', prio=3), []),
		(t('With due date <3000-01-01', due='3000-01-01'), []),
		(t('Foo'), []),
		(t('Parent 1'), [
			(t('Child 1.1'), [])
		]),
		(t('Parent 2'), []),
		(t('Started >2000-01-01', start='2000-01-01'), []),
		(t('Waiting: foo', waiting=True), []),
		(t('Later >3000-01-01', start='3000-01-01'), []),
	]


class TestActiveTasks(TestIndexViewMixin, tests.TestCase):

	klass = ActiveTasks

	input = '''
	[ ] Foo
	[*] Bar
	[ ] Parent 1
		[ ] Child 1.1
	[ ] Parent 2
		[x] Child 2.1
	[ ] Later >3000-01-01
	[ ] Started >2000-01-01
	[ ] Waiting: foo
	'''

	tasks = [
		(t('Foo'), []),
		(t('Child 1.1'), []),
		(t('Parent 2'), []),
		(t('Started >2000-01-01', start='2000-01-01'), []),
	]


class TestNextActionTasks(TestIndexViewMixin, tests.TestCase):

	klass = NextActionTasks

	input = '''
	[ ] Foo
	[*] Bar
	[ ] Parent 1
		[ ] Child 1.1
	[ ] Parent 2
		[x] Child 2.1
	[ ] Parent with prio !!!
		[*] Child with prio !!!
	[ ] Later >3000-01-01
	[ ] Started >2000-01-01
	[ ] Waiting: foo
	[ ] Prio !!!
	[ ] With due date <3000-01-01
	'''

	tasks = [
		(t('Prio !!!', prio=3), []),
		(t('With due date <3000-01-01', due='3000-01-01'), []),
		(t('Child 1.1'), []),
	]


class TestInboxTasks(TestIndexViewMixin, tests.TestCase):

	klass = InboxTasks

	input = '''
	[ ] Foo
	[*] Bar
	[ ] Parent 1
		[ ] Child 1.1
	[ ] Parent 2
		[x] Child 2.1
	[ ] Parent with prio !!!
		[*] Child with prio !!!
	[ ] Later >3000-01-01
	[ ] Started >2000-01-01
	[ ] Waiting: foo
	[ ] Prio !!!
	[ ] With due date <3000-01-01
	'''

	tasks = [
		(t('Foo'), []),
		(t('Started >2000-01-01', start='2000-01-01'), []),
	]


class TestOpenProjectsTasks(TestIndexViewMixin, tests.TestCase):

	klass = OpenProjectsTasks

	input = '''
	[ ] Foo
	[*] Bar
	[ ] Parent 1
		[ ] Child 1.1
	[ ] Parent 2
		[x] Child 2.1
	[ ] Parent with prio !!!
		[*] Child with prio !!!
	[ ] Later >3000-01-01
	[ ] Started >2000-01-01
	[ ] Waiting: foo
	[ ] Prio !!!
	[ ] With due date <3000-01-01
	'''

	tasks = [
		(t('Parent with prio !!!', prio=3), []),
		(t('Parent 1'), [
			(t('Child 1.1'), [])
		]),
		(t('Parent 2'), []),
	]


class TestWaitingTasks(TestIndexViewMixin, tests.TestCase):

	klass = WaitingTasks

	input = '''
	[ ] Foo
	[ ] Waiting: Bar
	'''

	tasks = [
		(t('Waiting: Bar', waiting=True), [])
	]


class TestSelection(tests.TestCase):

	def runTest(self):
		PluginManager.load_plugin('tasklist')
		notebook = self.setUpNotebook(content={
			'PageA': '''
			[ ] Foo
			[ ] Bar @bar

			TODO: test
			TODO: test @bar
			''',
			'PageB': '''
			[ ] Foo
			[ ] Bar @bar
			[ ] Test @foo @bar
			''',
			'PageB:Child': '''
			[ ] Foo
			[ ] Bar @bar

			FIXME: dus
			FIXME: dus @foo
			'''
		})
		alltasks = AllTasks.new_from_index(notebook.index)
		count = partial(alltasks.count_labels_and_tags_pages, task_labels=('TODO', 'FIXME'))

		self.assertEqual(count(), (
			{'TODO': 2, 'FIXME': 2},
			{'__no_tags__': 5, 'bar': 5, 'foo': 2},
			{'PageA': 4, 'PageB': 7, 'Child': 4} # "PageB" includes child pages
		))
		self.assertEqual(count(intersect=((), ('bar',))), (
			{'TODO': 1},
			{'__no_tags__': 0, 'bar': 5, 'foo': 1},
			{'PageA': 2, 'PageB': 3, 'Child': 1}
		))
		self.assertEqual(count(intersect=((), ('foo',))), (
			{'FIXME': 1},
			{'__no_tags__': 0, 'bar': 1, 'foo': 2},
			{'PageB': 2, 'Child': 1}
		))
		self.assertEqual(count(intersect=((), ('foo', 'bar'))), ( # "Tag AND tag"
			{},
			{'__no_tags__': 0, 'bar': 1, 'foo': 1},
			{'PageB': 1}
		))
		self.assertEqual(count(intersect=(('TODO',), ())), (
			{'TODO': 2},
			{'__no_tags__': 1, 'bar': 1},
			{'PageA': 2}
		))
		self.assertEqual(count(intersect=(('TODO',), ('bar',))), ( # "Label AND tag"
			{'TODO': 1},
			{'__no_tags__': 0, 'bar': 1},
			{'PageA': 1}
		))
		self.assertEqual(count(intersect=(('TODO', 'FIXME'), ())), ( # "Label OR label"
			{'TODO': 2, 'FIXME': 2},
			{'__no_tags__': 2, 'bar': 1, 'foo': 1},
			{'PageA': 2, 'PageB': 2, 'Child': 2}
		))
		self.assertEqual(count(intersect=(('TODO', 'FIXME'), ('bar',))), ( # "(Label OR label) AND tag"
			{'TODO': 1},
			{'__no_tags__': 0, 'bar': 1},
			{'PageA': 1}
		))
		self.assertEqual(count(intersect=(('TODO', 'FIXME'), ('bar', 'foo'))), ( # "(Label OR label) AND (tag AND tag)"
			{},
			{'__no_tags__': 0},
			{}
		))


class TestUI(tests.TestCase):

	def testDaysToString(self):
		from zim.plugins.tasklist.gui import days_to_str

		# Without use_workweek
		for days, wanted in (
			(600, '2y'),
			(300, '1y'),
			(270, '9m'),
			(200, '7m'),
			(30, '1m'),
			(21, '3w'),
			(14, '2w'),
			(10, '10d'),
			(7, '7d'),
			(2, '2d'),
		):
			self.assertEqual(days_to_str(days, False, 1), wanted)

		# With use_workweek
		for days, weekday, wanted in (
			# all offsets for monday
			(14, 1, '2w'), # due: mon in two weeks
			(13, 1, '9d'), # due: next sun == fri
			(12, 1, '9d'), # due: next sat == fri
			(11, 1, '9d'), # due: next fri
			(10, 1, '8d'), # due: next thu
			(9, 1, '7d'), # due: next wed
			(8, 1, '6d'), # due: next tue
			(7, 1, '5d'), # due: next mon
			(6, 1, '4d'), # due: sun == fri
			(5, 1, '4d'), # due: sat == fri
			(4, 1, '4d'), # due: fri
			(3, 1, '3d'), # due: thu
			(2, 1, '2d'), # due: wed
			(1, 1, '1d'), # due: tue
			# different weekdays
			(4, 1, '4d'), # mon: tue, wed, thu, fri
			(4, 2, '3d'), # tue: wed, thu, fri, (sat)
			(4, 3, '2d'), # wed: thu, fri, (sat, sun)
			(4, 4, '2d'), # thu: fri (sat, sun), mon
			(4, 5, '2d'), # fri: (sat, sun) mon, thu
			(4, 6, '3d'), # sat: (sun), mon, tue, wed
			(4, 7, '4d'), # sun: mon, tue, wed, thu
		):
			self.assertEqual(days_to_str(days, True, weekday), wanted)
