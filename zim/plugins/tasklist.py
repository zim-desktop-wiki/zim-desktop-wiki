# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement

import gobject
import gtk
import pango
import logging
import re

import zim.datetimetz as datetime
from zim.utils import natural_sorted
from zim.parsing import parse_date
from zim.parser import Visitor, VisitorSkip, TreeFilter, TextCollectorFilter
from zim.plugins import PluginClass
from zim.notebook import Path
from zim.gui.widgets import ui_environment, \
	Dialog, MessageDialog, \
	InputEntry, Button, IconButton, MenuButton, \
	BrowserTreeView, SingleClickTreeView, \
	encode_markup_text, decode_markup_text
from zim.gui.clipboard import Clipboard
from zim.async import DelayedCallback
from zim.formats import get_format, \
	UNCHECKED_BOX, CHECKED_BOX, XCHECKED_BOX, BULLET
from zim.config import check_class_allow_empty

from zim.plugins.calendar import daterange_from_path

logger = logging.getLogger('zim.plugins.tasklist')


ui_actions = (
	# name, stock id, label, accelerator, tooltip, read only
	('show_task_list', 'zim-task-list', _('Task List'), '', _('Task List'), True), # T: menu item
)

ui_xml = '''
<ui>
	<menubar name='menubar'>
		<menu action='view_menu'>
			<placeholder name="plugin_items">
				<menuitem action="show_task_list" />
			</placeholder>
		</menu>
	</menubar>
	<toolbar name='toolbar'>
		<placeholder name='tools'>
			<toolitem action='show_task_list'/>
		</placeholder>
	</toolbar>
</ui>
'''

SQL_FORMAT_VERSION = (0, 5)
SQL_FORMAT_VERSION_STRING = "0.5"

SQL_CREATE_TABLES = '''
create table if not exists tasklist (
	id INTEGER PRIMARY KEY,
	source INTEGER,
	parent INTEGER,
	haschildren BOOLEAN,
	open BOOLEAN,
	actionable BOOLEAN,
	prio INTEGER,
	due TEXT,
	description TEXT
);
'''


tag_re = re.compile(r'(?<!\S)@(\w+)\b', re.U)
date_re = re.compile(r'\s*\[d:(.+)\]')


_NO_DATE = '9999' # Constant for empty due date - value chosen for sorting properties


# FUTURE: add an interface for this plugin in the WWW frontend

# TODO allow more complex queries for filter, in particular (NOT tag AND tag)
# TODO: think about what "actionable" means
#       - no open dependencies
#       - no defer date in the future
#       - no child item ?? -- hide in flat list ?
#       - no @waiting ?? -> use defer date for this use case


class TaskListPlugin(PluginClass):

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'tasklist-changed': (gobject.SIGNAL_RUN_LAST, None, ()),
	}

	plugin_info = {
		'name': _('Task List'), # T: plugin name
		'description': _('''\
This plugin adds a dialog showing all open tasks in
this notebook. Open tasks can be either open checkboxes
or items marked with tags like "TODO" or "FIXME".

This is a core plugin shipping with zim.
'''), # T: plugin description
		'author': 'Jaap Karssenberg',
		'help': 'Plugins:Task List'
	}

	plugin_preferences = (
		# key, type, label, default
		('all_checkboxes', 'bool', _('Consider all checkboxes as tasks'), True),
			# T: label for plugin preferences dialog
		('tag_by_page', 'bool', _('Turn page name into tags for task items'), False),
			# T: label for plugin preferences dialog
		('deadline_by_page', 'bool', _('Implicit deadline for task items in calendar pages'), False),
			# T: label for plugin preferences dialog
		('labels', 'string', _('Labels marking tasks'), 'FIXME, TODO', check_class_allow_empty),
			# T: label for plugin preferences dialog - labels are e.g. "FIXME", "TODO", "TASKS"
		('next_label', 'string', _('Label for next task'), 'Next:', check_class_allow_empty),
			# T: label for plugin preferences dialog - label is by default "Next"
	)
	_rebuild_on_preferences = ['all_checkboxes', 'labels', 'next_label', 'deadline_by_page']
		# Rebuild database table if any of these preferences changed.
		# But leave it alone if others change.

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		self.task_labels = None
		self.task_label_re = None
		self.next_label = None
		self.next_label_re = None
		self.db_initialized = False

	def initialize_ui(self, ui):
		if ui.ui_type == 'gtk':
			ui.add_actions(ui_actions, self)
			ui.add_ui(ui_xml, self)

	def finalize_notebook(self, notebook):
		# This is done regardsless of the ui type of the application
		self.index = notebook.index
		self.index.connect_after('initialize-db', self.initialize_db)
		self.index.connect('page-indexed', self.index_page)
		self.index.connect('page-deleted', self.remove_page)
		# We don't care about pages that are moved

		db_version = self.index.properties['plugin_tasklist_format']
		if db_version == SQL_FORMAT_VERSION_STRING:
			self.db_initialized = True

		self._set_preferences()

	def initialize_db(self, index):
		with index.db_commit:
			index.db.executescript(SQL_CREATE_TABLES)
		self.index.properties['plugin_tasklist_format'] = SQL_FORMAT_VERSION_STRING
		self.db_initialized = True

	def do_preferences_changed(self):
		new_preferences = self._serialize_rebuild_on_preferences()
		if new_preferences != self._current_preferences:
			self._drop_table()
		self._set_preferences()

	def _set_preferences(self):
		self._current_preferences = self._serialize_rebuild_on_preferences()

		string = self.preferences['labels'].strip(' ,')
		if string:
			self.task_labels = [s.strip() for s in self.preferences['labels'].split(',')]
		else:
			self.task_labels = []

		if self.preferences['next_label']:
			self.next_label = self.preferences['next_label']
				# Adding this avoid the need for things like "TODO: Next: do this next"
			self.next_label_re = re.compile(r'^' + re.escape(self.next_label) + r'(?!\w)' )
			self.task_labels.append(self.next_label)
		else:
			self.next_label = None
			self.next_label_re = None

		if self.task_labels:
			regex = r'^(' + '|'.join(map(re.escape, self.task_labels)) + r')(?!\w)'
			self.task_label_re = re.compile(regex)
		else:
			self.task_label_re = None

	def _serialize_rebuild_on_preferences(self):
		# string mapping settings that influence building the table
		string = ''
		for pref in self._rebuild_on_preferences:
			string += str(self.preferences[pref])
		return string

	def disconnect(self):
		self._drop_table()
		PluginClass.disconnect(self)

	def _drop_table(self):
		self.index.properties['plugin_tasklist_format'] = 0
		if self.db_initialized:
			try:
				self.index.db.execute('DROP TABLE "tasklist"')
			except:
				logger.exception('Could not drop table:')
			else:
				self.db_initialized = False
		else:
			try:
				self.index.db.execute('DROP TABLE "tasklist"')
			except:
				pass

	def index_page(self, index, path, page):
		if not self.db_initialized: return
		#~ print '>>>>>', path, page, page.hascontent
		tasksfound = self.remove_page(index, path, _emit=False)

		parsetree = page.get_parsetree()
		if not parsetree:
			return

		if page._ui_object:
			# FIXME - HACK - dump and parse as wiki first to work
			# around glitches in pageview parsetree dumper
			# make sure we get paragraphs and bullets are nested properly
			# Same hack in gui clipboard code
			dumper = get_format('wiki').Dumper()
			text = ''.join( dumper.dump(parsetree) ).encode('utf-8')
			parser = get_format('wiki').Parser()
			parsetree = parser.parse(text)

		#~ print '!! Checking for tasks in', path
		dates = daterange_from_path(path)
		if dates and self.preferences['deadline_by_page']:
			deadline = dates[2]
		else:
			deadline = None
		tasks = self._extract_tasks(parsetree, deadline)
		if tasks:
			# Do insert with a single commit
			with self.index.db_commit:
				self._insert(path, 0, tasks)

			self.emit('tasklist-changed')

	def _insert(self, page, parentid, children):
		# Helper function to insert tasks in table
		c = self.index.db.cursor()
		for task, grandchildren in children:
			c.execute(
				'insert into tasklist(source, parent, haschildren, open, actionable, prio, due, description)'
				'values (?, ?, ?, ?, ?, ?, ?, ?)',
				(page.id, parentid, bool(grandchildren)) + task
			)
			if grandchildren:
				self._insert(page, c.lastrowid, grandchildren) # recurs

	def _extract_tasks(self, parsetree, defaultdate=None):
		'''Extract all tasks from a parsetree.
		@param parsetree: a L{zim.formats.ParseTree} object
		@param defaultdate: default due date for the whole page (e.g. for calendar pages) as string
		@returns: nested list of tasks, each task is given as a 2-tuple, 1st item is a tuple
		with following properties: C{(open, actionable, prio, due, description)}, 2nd item
		is a list of child tasks (if any).
		'''
		parser = TasksParser(
			self.task_label_re,
			self.next_label_re,
			self.preferences['all_checkboxes'],
			defaultdate
		)
		parser.parse(parsetree)
		return parser.get_tasks()

	def remove_page(self, index, path, _emit=True):
		if not self.db_initialized: return

		tasksfound = False
		with index.db_commit:
			cursor = index.db.cursor()
			cursor.execute(
				'delete from tasklist where source=?', (path.id,) )
			tasksfound = cursor.rowcount > 0

		if tasksfound and _emit:
			self.emit('tasklist-changed')

		return tasksfound

	def list_tasks(self, parent=None):
		'''List tasks
		@param parent: the parent task (as returned by this method) or C{None} to list
		all top level tasks
		@returns: a list of tasks at this level as sqlite Row objects
		'''
		if parent: parentid = parent['id']
		else: parentid = 0

		if self.db_initialized:
			cursor = self.index.db.cursor()
			cursor.execute('select * from tasklist where parent=?', (parentid,))
			for row in cursor:
				yield row

	def get_task(self, taskid):
		cursor = self.index.db.cursor()
		cursor.execute('select * from tasklist where id=?', (taskid,))
		return cursor.fetchone()

	def get_path(self, task):
		'''Get the L{Path} for the source of a task
		@param task: the task (as returned by L{list_tasks()}
		@returns: an L{IndexPath} object
		'''
		return self.index.lookup_id(task['source'])

	def show_task_list(self):
		if not self.db_initialized:
			MessageDialog(self.ui, (
				_('Need to index the notebook'),
				# T: Short message text on first time use of task list plugin
				_('This is the first time the task list is opened.\n'
				  'Therefore the index needs to be rebuild.\n'
				  'Depending on the size of the notebook this can\n'
				  'take up to several minutes. Next time you use the\n'
				  'task list this will not be needed again.' )
				# T: Long message text on first time use of task list plugin
			) ).run()
			logger.info('Tasklist not initialized, need to rebuild index')
			finished = self.ui.reload_index(flush=True)
			# Flush + Reload will also initialize task list
			if not finished:
				self.db_initialized = False
				return

		dialog = TaskListDialog.unique(self, plugin=self)
		dialog.present()

# Need to register classes defining gobject signals
gobject.type_register(TaskListPlugin)


class TasksParser(Visitor):
	'''Parse tasks from a parsetree'''

	def __init__(self, task_label_re, next_label_re, all_checkboxes, defaultdate):
		self.tasks = [] # tuples like (task, children)
		self.task_label_re = task_label_re
		self.next_label_re = next_label_re
		self.all_checkboxes = all_checkboxes

		defaults = (True, True, 0, defaultdate or _NO_DATE, None)
			#(open, actionable, prio, due, description)

		self.state = None # context while parsing
		self.stack = [(-1, defaults, self.tasks)] # tuples like (level, task, children)
		self.list_level = 0 # current list level
		self.bullet = None # current bullet
		self.istasklist = False
		self.tasklist_tags = None

	def parse(self, parsetree):
		filter = TreeFilter(
			TextCollectorFilter(self),
			tags=['p', 'ul', 'ol', 'li'],
			exclude=['strike']
		)
		parsetree.visit(filter)

	def get_tasks(self):
		'''Get the tasks that were collected by visiting the tree
		@returns: nested list of tasks, each task is given as a 2-tuple,
		1st item is a tuple with following properties:
		C{(open, actionable, prio, due, description)},
		2nd item is a list of child tasks (if any).
		'''
		return self.tasks

	def start(self, tag, attrib):
		# Set context for parsing
		self.bullet = None # reset
		if tag == 'p':
			self.istasklist = False # reset
			self.state = "start_para"
		elif tag in ('ol', 'ul'):
			if self.state == 'list':
				self.list_level += 1
				# (first list level is equal to line items in para)
			self.state = 'list'
		elif tag == 'li':
			self.bullet = attrib.get('bullet')
		else:
			assert False, 'BUG: got tag: %s' % tag

		#~ print 'START', tag, self.state, self.list_level

	def end(self, tag):
		self.bullet = None # reset
		if tag in ('ol', 'ul'):
			if self.list_level > 0:
				self.list_level -= 1
			else:
				self.state = 'para' # end of list

			while self.stack[-1][0] > self.list_level:
				self.stack.pop()
		elif tag == 'p':
			self.stack = [self.stack[0]] # Reset

		#~ print 'END', tag, self.state, self.list_level

	def text(self, text):
		# Dispatch depending on state
		assert self.state in ('start_para', 'list', 'para'), 'BUG: Text outside para !??'
		if self.state == 'start_para':
			self._parse_start_para(text)
		elif self.state == 'para':
			self._parse_para(text)
		elif self.state == 'list':
			self._parse_list_item(text)
		else:
			assert False, 'BUG: get state: %s' % self.state

	def _parse_start_para(self, text):
		# Check first line for task list header
		#~ print "START PARA >>>", text, "<<<"
		tags = []
		lines = text.splitlines()
		if len(lines) == 1 \
		and self._matches_label(lines[0]):
			words = lines[0].strip(':').split()
			words.pop(0) # label
			if all(w.startswith('@') for w in words):
				lines.pop(0)
				self.istasklist = True
				self.tasklist_tags = words
			else:
				self.istasklist = False
				self.tasklist_tags = []
				self._parse_para(text)
		else:
			self._parse_para(text)

	def _parse_para(self, text):
		# Paragraph text to be parsed - just look for lines with label
		for line in text.splitlines():
			if self._matches_label(line):
				self._parse_task(line)

	def _parse_list_item(self, text):
		#~ print 'LI', text
		# List item to parse - check bullet, then match label
		# Because we use TextCollector it is ensured we get
		# all text for a list item at once
		if (
			self.bullet in (UNCHECKED_BOX, CHECKED_BOX, XCHECKED_BOX)
			and (self.istasklist or self.all_checkboxes)
		) or self._matches_label(text):
			open = (self.bullet not in (CHECKED_BOX, XCHECKED_BOX))
			self._parse_task(text, open=open)
		# else not a task - skip

	def _matches_label(self, line):
		return self.task_label_re and self.task_label_re.match(line)

	def _matches_next_label(self, line):
		return self.next_label_re and self.next_label_re.match(line)

	def _parse_task(self, line, open=True):
		assert self.list_level >= 0, 'BUG: stack count corrupted'
		while self.stack[-1][0] >= self.list_level:
				self.stack.pop()

		parent_level, parent, parent_children = self.stack[-1]

		# Get prio
		prio = line.count('!')
		if prio == 0:
			prio = parent[2] # default to parent prio

		# Get date - and remove from description
		global __due # FIXME
		__due = _NO_DATE
		def set_date(match):
			global __due
			mydate = parse_date(match.group(0))
			if mydate and __due == _NO_DATE:
				__due = '%04i-%02i-%02i' % mydate # (y, m, d)
				#~ return match.group(0) # TEST
				return ''
			else:
				# No match or we already had a date
				return match.group(0)

		description = date_re.sub(set_date, line)
		due = __due

		if due == _NO_DATE:
			due = parent[3] # default to parent date (or default for root)

		# Deal with tags global for tasklist
		if self.istasklist:
			for tag in self.tasklist_tags:
				if not tag in description:
					description += ' ' + tag

		# Check actionable
		if self._matches_next_label(description):
			actionable = not parent[0] # previous task not open
		else:
			actionable = True

		# And really add to stack
		task = (open, actionable, prio, due, description)
		children = []
		parent_children.append((task, children))
		self.stack.append((self.list_level, task, children))


class TaskListDialog(Dialog):

	def __init__(self, plugin):
		if ui_environment['platform'] == 'maemo':
			defaultsize = (800, 480)
		else:
			defaultsize = (550, 400)

		Dialog.__init__(self, plugin.ui, _('Task List'), # T: dialog title
			buttons=gtk.BUTTONS_CLOSE, help=':Plugins:Task List',
			defaultwindowsize=defaultsize )
		self.plugin = plugin
		if ui_environment['platform'] == 'maemo':
			self.resize(800,480)
			# Force maximum dialog size under maemo, otherwise
			# we'll end with a too small dialog and no way to resize it
		hbox = gtk.HBox(spacing=5)
		self.vbox.pack_start(hbox, False)
		self.hpane = gtk.HPaned()
		self.uistate.setdefault('hpane_pos', 75)
		self.hpane.set_position(self.uistate['hpane_pos'])
		self.vbox.add(self.hpane)

		# Task list
		self.uistate.setdefault('only_show_act', False)
		self.task_list = TaskListTreeView(self.ui, plugin, filter_actionable=self.uistate['only_show_act'])
		self.task_list.set_headers_visible(True) # Fix for maemo
		scrollwindow = gtk.ScrolledWindow()
		scrollwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
		scrollwindow.set_shadow_type(gtk.SHADOW_IN)
		scrollwindow.add(self.task_list)
		self.hpane.add2(scrollwindow)

		# Tag list
		self.tag_list = TagListTreeView(self.task_list)
		scrollwindow = gtk.ScrolledWindow()
		scrollwindow.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
		scrollwindow.set_shadow_type(gtk.SHADOW_IN)
		scrollwindow.add(self.tag_list)
		self.hpane.add1(scrollwindow)

		# Filter input
		hbox.pack_start(gtk.Label(_('Filter')+': '), False) # T: Input label
		filter_entry = InputEntry()
		filter_entry.set_icon_to_clear()
		hbox.pack_start(filter_entry, False)
		filter_cb = DelayedCallback(500,
			lambda o: self.task_list.set_filter(filter_entry.get_text()))
		filter_entry.connect('changed', filter_cb)

		# Dropdown with options - TODO
		#~ menu = gtk.Menu()
		#~ showtree = gtk.CheckMenuItem(_('Show _Tree')) # T: menu item in options menu
		#~ menu.append(showtree)
		#~ menu.append(gtk.SeparatorMenuItem())
		#~ showall = gtk.RadioMenuItem(None, _('Show _All Items')) # T: menu item in options menu
		#~ showopen = gtk.RadioMenuItem(showall, _('Show _Open Items')) # T: menu item in options menu
		#~ menu.append(showall)
		#~ menu.append(showopen)
		#~ menubutton = MenuButton(_('_Options'), menu) # T: Button label
		#~ hbox.pack_start(menubutton, False)

		self.act_toggle = gtk.CheckButton(_('Only Show Actionable Tasks'))
			# T: Checkbox in task list
		self.act_toggle.set_active(self.uistate['only_show_act'])
		self.act_toggle.connect('toggled', lambda o: self.task_list.set_filter_actionable(o.get_active()))
		hbox.pack_start(self.act_toggle, False)

		# Statistics label
		self.statistics_label = gtk.Label()
		hbox.pack_end(self.statistics_label, False)

		def set_statistics(o):
			total, stats = self.task_list.get_statistics()
			text = ngettext('%i open item', '%i open items', total) % total
				# T: Label for statistics in Task List, %i is the number of tasks
			text += ' (' + '/'.join(map(str, stats)) + ')'
			self.statistics_label.set_text(text)

		set_statistics(self.task_list)
		self.plugin.connect('tasklist-changed', set_statistics)
			# Make sure this is connected after the task list connected to same signal

	def do_response(self, response):
		self.uistate['hpane_pos'] = self.hpane.get_position()
		self.uistate['only_show_act'] = self.act_toggle.get_active()
		Dialog.do_response(self, response)


class TagListTreeView(SingleClickTreeView):
	'''TreeView with a single column 'Tags' which shows all tags available
	in a TaskListTreeView. Selecting a tag will filter the task list to
	only show tasks with that tag.
	'''

	_type_separator = 0
	_type_label = 1
	_type_tag = 2

	def __init__(self, task_list):
		model = gtk.ListStore(str, int, int, int) # tag name, number of tasks, type, weight
		SingleClickTreeView.__init__(self, model)
		self.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
		self.task_list = task_list

		column = gtk.TreeViewColumn(_('Tags'))
			# T: Column header for tag list in Task List dialog
		self.append_column(column)

		cr1 = gtk.CellRendererText()
		cr1.set_property('ellipsize', pango.ELLIPSIZE_END)
		column.pack_start(cr1, True)
		column.set_attributes(cr1, text=0, weight=3) # tag name, weight

		cr2 = self.get_cell_renderer_number_of_items()
		column.pack_start(cr2, False)
		column.set_attributes(cr2, text=1) # number of tasks

		self.set_row_separator_func(lambda m, i: m[i][2] == self._type_separator)

		self._block_selection_change = False
		self.get_selection().connect('changed', self.on_selection_changed)

		self.refresh(task_list)
		task_list.plugin.connect('tasklist-changed', lambda o: self.refresh(task_list))
			# Make sure this is connected after the task list connected to same signal

	def get_tags(self):
		'''Returns current selected tags, or None for all tags'''
		tags = []
		for row in self._get_selected():
			if row[2] == self._type_tag:
				tags.append(row[0])
		return tags or None

	def get_labels(self):
		'''Returns current selected labels'''
		labels = []
		for row in self._get_selected():
			if row[2] == self._type_label:
				labels.append(row[0])
		return labels or None

	def _get_selected(self):
		selection = self.get_selection()
		if selection:
			model, paths = selection.get_selected_rows()
			if not paths or (0,) in paths:
				return []
			else:
				return [model[path] for path in paths]
		else:
			return []

	def refresh(self, task_list):
		self._block_selection_change = True
		selected = [(row[0], row[2]) for row in self._get_selected()] # remember name and type

		# Rebuild model
		model = self.get_model()
		if model is None: return
		model.clear()

		n_all = self.task_list.get_n_tasks()
		model.append((_('All Tasks'), n_all, self._type_label, pango.WEIGHT_BOLD)) # T: "tag" for showing all tasks

		labels = self.task_list.get_labels()
		plugin = self.task_list.plugin
		for label in plugin.task_labels: # explicitly keep sorting from preferences
			if label in labels and label != plugin.next_label:
				model.append((label, labels[label], self._type_label, pango.WEIGHT_BOLD))

		model.append(('', 0, self._type_separator, 0)) # separator

		tags = self.task_list.get_tags()
		for tag in natural_sorted(tags):
			model.append((tag, tags[tag], self._type_tag, pango.WEIGHT_NORMAL))

		# Restore selection
		def reselect(model, path, iter):
			row = model[path]
			name_type = (row[0], row[2])
			if name_type in selected:
				self.get_selection().select_iter(iter)

		if selected:
			model.foreach(reselect)
		self._block_selection_change = False

	def on_selection_changed(self, selection):
		if not self._block_selection_change:
			tags = self.get_tags()
			labels = self.get_labels()
			self.task_list.set_tag_filter(tags)
			self.task_list.set_label_filter(labels)


HIGH_COLOR = '#EF5151' # red (derived from Tango style guide - #EF2929)
MEDIUM_COLOR = '#FCB956' # orange ("idem" - #FCAF3E)
ALERT_COLOR = '#FCEB65' # yellow ("idem" - #FCE94F)
# FIXME: should these be configurable ?


class TaskListTreeView(BrowserTreeView):

	VIS_COL = 0 # visible
	PRIO_COL = 1
	TASK_COL = 2
	DATE_COL = 3
	PAGE_COL = 4
	ACT_COL = 5 # actionable
	OPEN_COL = 6 # item not closed
	TASKID_COL = 7

	def __init__(self, ui, plugin, filter_actionable):
		self.real_model = gtk.TreeStore(bool, int, str, str, str, bool, bool, int)
			# VIS_COL, PRIO_COL, TASK_COL, DATE_COL, PAGE_COL, ACT_COL, OPEN_COL, TASKID_COL
		model = self.real_model.filter_new()
		model.set_visible_column(self.VIS_COL)
		model = gtk.TreeModelSort(model)
		model.set_sort_column_id(self.PRIO_COL, gtk.SORT_DESCENDING)
		BrowserTreeView.__init__(self, model)
		self.ui = ui
		self.plugin = plugin
		self.filter = None
		self.tag_filter = None
		self.label_filter = None
		self.filter_actionable = filter_actionable
		self._tags = {}
		self._labels = {}

		# Add some rendering for the Prio column
		def render_prio(col, cell, model, i):
			prio = model.get_value(i, self.PRIO_COL)
			cell.set_property('text', str(prio))
			if prio >= 3: color = HIGH_COLOR
			elif prio == 2: color = MEDIUM_COLOR
			elif prio == 1: color = ALERT_COLOR
			else: color = None
			cell.set_property('cell-background', color)

		cell_renderer = gtk.CellRendererText()
		#~ column = gtk.TreeViewColumn(_('Prio'), cell_renderer)
			# T: Column header Task List dialog
		column = gtk.TreeViewColumn(' ! ', cell_renderer)
		column.set_cell_data_func(cell_renderer, render_prio)
		column.set_sort_column_id(self.PRIO_COL)
		self.append_column(column)

		# Rendering for task description column
		cell_renderer = gtk.CellRendererText()
		cell_renderer.set_property('ellipsize', pango.ELLIPSIZE_END)
		column = gtk.TreeViewColumn(_('Task'), cell_renderer, markup=self.TASK_COL)
				# T: Column header Task List dialog
		column.set_resizable(True)
		column.set_sort_column_id(self.TASK_COL)
		column.set_expand(True)
		if ui_environment['platform'] == 'maemo':
			column.set_min_width(250) # don't let this column get too small
		else:
			column.set_min_width(300) # don't let this column get too small
		self.append_column(column)
		self.set_expander_column(column)

		if gtk.gtk_version >= (2, 12, 0):
			self.set_tooltip_column(self.TASK_COL)

		# Rendering of the Date column
		today    = str( datetime.date.today() )
		tomorrow = str( datetime.date.today() + datetime.timedelta(days=1))
		dayafter = str( datetime.date.today() + datetime.timedelta(days=2))
		def render_date(col, cell, model, i):
			date = model.get_value(i, self.DATE_COL)
			if date == _NO_DATE:
				cell.set_property('text', '')
			else:
				cell.set_property('text', date)
				# TODO allow strftime here

			if date <= today: color = HIGH_COLOR
			elif date == tomorrow: color = MEDIUM_COLOR
			elif date == dayafter: color = ALERT_COLOR
			else: color = None
			cell.set_property('cell-background', color)

		cell_renderer = gtk.CellRendererText()
		column = gtk.TreeViewColumn(_('Date'), cell_renderer)
			# T: Column header Task List dialog
		column.set_cell_data_func(cell_renderer, render_date)
		column.set_sort_column_id(self.DATE_COL)
		self.append_column(column)

		# Rendering for page name column
		cell_renderer = gtk.CellRendererText()
		column = gtk.TreeViewColumn(_('Page'), cell_renderer, text=self.PAGE_COL)
				# T: Column header Task List dialog
		column.set_sort_column_id(self.PAGE_COL)
		self.append_column(column)

		# Finalize
		self.refresh()
		self.plugin.connect_object('tasklist-changed', self.__class__.refresh, self)

		# HACK because we can not register ourselves :S
		self.connect('row_activated', self.__class__.do_row_activated)

	def refresh(self):
		'''Refresh the model based on index data'''
		# Update data
		self._clear()
		self._append_tasks(None, None, {})

		# Make tags case insensitive
		tags = sorted((t.lower(), t) for t in self._tags)
			# tuple sorting will sort ("foo", "Foo") before ("foo", "foo"),
			# but ("bar", ..) before ("foo", ..)
		prev = ('', '')
		for tag in tags:
			if tag[0] == prev[0]:
				self._tags[prev[1]] += self._tags[tag[1]]
				self._tags.pop(tag[1])
			prev = tag

		# Set view
		self._eval_filter() # keep current selection
		self.expand_all()

	def _clear(self):
		self.real_model.clear() # flush
		self._tags = {}
		self._labels = {}

	def _append_tasks(self, task, iter, path_cache):
		rows = list(self.plugin.list_tasks(task))

		# First cache + sort tasks to ensure stability of the list
		for row in rows:
			if not row['source'] in path_cache:
				path = self.plugin.get_path(row)
				if path is None:
					# Be robust for glitches - filter these out
					row['source'] = None
				else:
					path_cache[row['source']] = path

		rows = [r for r in rows if r['source'] is not None] # filter out missing paths

		rows.sort(key=lambda r: path_cache[r['source']].name)

		# Count them (note: these matches fail after formatting applied)
		for row in rows:
			if not row['open']:
				continue # Only count open items

			for label in self.plugin.task_label_re.findall(row['description']):
				self._labels[label] = self._labels.get(label, 0) + 1

			for tag in tag_re.findall(row['description']):
				self._tags[tag] = self._tags.get(tag, 0) + 1

			if self.plugin.preferences['tag_by_page']:
				path = path_cache[row['source']]
				for part in path.parts:
					self._tags[part] = self._tags.get(part, 0) + 1

		# Then format them and add them to the model
		for row in rows:
			path = path_cache[row['source']]
			task = encode_markup_text(row['description'])
			task = re.sub('\s*!+\s*', ' ', task) # get rid of exclamation marks
			task = self.plugin.next_label_re.sub('', task) # get rid of "next" label in description
			if row['actionable']:
				task = tag_re.sub(r'<span color="#ce5c00">@\1</span>', task) # highlight tags - same color as used in pageview
				task = self.plugin.task_label_re.sub(r'<b>\1</b>', task) # highlight labels
			else:
				task = r'<span color="darkgrey">%s</span>' % task
			modelrow = [False, row['prio'], task, row['due'], path.name, row['actionable'], row['open'], row['id']]
				# VIS_COL, PRIO_COL, TASK_COL, DATE_COL, PAGE_COL, ACT_COL, OPEN_COL, TASKID_COL
			modelrow[0] = self._filter_item(modelrow)
			myiter = self.real_model.append(iter, modelrow)

			if row['haschildren']:
				self._append_tasks(row, myiter, path_cache) # recurs

	def set_filter_actionable(self, filter):
		'''Set filter state for non-actionable items
		@param filter: if C{False} all items are shown, if C{True} only actionable items
		'''
		self.filter_actionable = filter
		self._eval_filter()

	def set_filter(self, string):
		# TODO allow more complex queries here - same parse as for search
		if string:
			inverse = False
			if string.lower().startswith('not '):
				# Quick HACK to support e.g. "not @waiting"
				inverse = True
				string = string[4:]
			self.filter = (inverse, string.strip().lower())
		else:
			self.filter = None
		self._eval_filter()

	def get_labels(self):
		'''Get all labels that are in use
		@returns: a dict with labels as keys and the number of tasks
		per label as value
		'''
		return self._labels

	def get_tags(self):
		'''Get all tags that are in use
		@returns: a dict with tags as keys and the number of tasks
		per tag as value
		'''
		return self._tags

	def get_n_tasks(self):
		'''Get the number of tasks in the list
		@returns: total number
		'''
		counter = [0]
		def count(model, path, iter):
			if model[iter][self.OPEN_COL]:
				# only count open items
				counter[0] += 1
		self.real_model.foreach(count)
		return counter[0]

	def get_statistics(self):
		statsbyprio = {}

		def count(model, path, iter):
			# only count open items
			row = model[iter]
			if row[self.OPEN_COL]:
				prio = row[self.PRIO_COL]
				statsbyprio.setdefault(prio, 0)
				statsbyprio[prio] += 1

		self.real_model.foreach(count)

		if statsbyprio:
			total = reduce(int.__add__, statsbyprio.values())
			highest = max([0] + statsbyprio.keys())
			stats = [statsbyprio.get(k, 0) for k in range(highest+1)]
			stats.reverse() # highest first
			return total, stats
		else:
			return 0, []

	def set_tag_filter(self, tags):
		if tags:
			self.tag_filter = [tag.lower() for tag in tags]
		else:
			self.tag_filter = None
		self._eval_filter()

	def set_label_filter(self, labels):
		if labels:
			self.label_filter = [label.lower() for label in labels]
		else:
			self.label_filter = None
		self._eval_filter()

	def _eval_filter(self):
		logger.debug('Filtering with labels: %s tags: %s, filter: %s', self.label_filter, self.tag_filter, self.filter)

		def filter(model, path, iter):
			visible = self._filter_item(model[iter])
			model[iter][self.VIS_COL] = visible
			if visible:
				parent = model.iter_parent(iter)
				while parent:
					model[parent][self.VIS_COL] = visible
					parent = model.iter_parent(parent)

		self.real_model.foreach(filter)
		self.expand_all()

	def _filter_item(self, modelrow):
		# This method filters case insensitive because both filters and
		# text are first converted to lower case text.
		visible = True

		if not modelrow[self.OPEN_COL] \
		or (not modelrow[self.ACT_COL] and self.filter_actionable):
			visible = False

		description = modelrow[self.TASK_COL].decode('utf-8').lower()
		pagename = modelrow[self.PAGE_COL].decode('utf-8').lower()

		if visible and self.label_filter:
			# Any labels need to be present
			for label in self.label_filter:
				if label in description:
					break
			else:
				visible = False # no label found

		if visible and self.tag_filter:
			# And any tag should match (or pagename if tag_by_page)
			for tag in self.tag_filter:
				if self.plugin.preferences['tag_by_page']:
					if '@'+tag in description \
					or tag in pagename.split(':'):
						break # keep visible True
				else:
					if '@'+tag in description:
						break # keep visible True
			else:
				visible = False # no tag found

		if visible and self.filter:
			# And finally the filter string should match
			# FIXME: we are matching against markup text here - may fail for some cases
			inverse, string = self.filter
			match = string in description or string in pagename
			if (not inverse and not match) or (inverse and match):
				visible = False

		return visible

	def do_row_activated(self, path, column):
		model = self.get_model()
		page = Path( model[path][self.PAGE_COL] )
		text = self._get_raw_text(model[path])
		self.ui.open_page(page)
		self.ui.mainwindow.pageview.find(text)

	def _get_raw_text(self, task):
		id = task[self.TASKID_COL]
		row = self.plugin.get_task(id)
		return row['description']

	def do_initialize_popup(self, menu):
		item = gtk.ImageMenuItem('gtk-copy')
		item.connect_object('activate', self.__class__.copy_to_clipboard, self)
		menu.append(item)
		self.populate_popup_expand_collapse(menu)

	def copy_to_clipboard(self):
		'''Exports currently visible elements from the tasks list'''
		logger.debug('Exporting to clipboard current view of task list.')
		text = self.get_visible_data_as_csv()
		Clipboard.set_text(text)
			# TODO set as object that knows how to format as text / html / ..
			# unify with export hooks

	def get_visible_data_as_csv(self):
		text = ""
		for indent, prio, desc, date, page in self.get_visible_data():
			prio = str(prio)
			desc = decode_markup_text(desc)
			desc = '"' + desc.replace('"', '""') + '"'
			text += ",".join((prio, desc, date, page)) + "\n"
		return text

	def get_visible_data_as_html(self):
		html = '''\
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" "http://www.w3.org/TR/html4/loose.dtd">
<html>
	<head>
		<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
		<title>Task List - Zim</title>
		<meta name='Generator' content='Zim [%% zim.version %%]'>
		<style type='text/css'>
			table.tasklist {
				border-width: 1px;
				border-spacing: 2px;
				border-style: solid;
				border-color: gray;
				border-collapse: collapse;
			}
			table.tasklist th {
				border-width: 1px;
				padding: 1px;
				border-style: solid;
				border-color: gray;
			}
			table.tasklist td {
				border-width: 1px;
				padding: 1px;
				border-style: solid;
				border-color: gray;
			}
			.high {background-color: %s}
			.medium {background-color: %s}
			.alert {background-color: %s}
		</style>
	</head>
	<body>

<h1>Task List - Zim</h1>

<table class="tasklist">
<tr><th>Prio</th><th>Task</th><th>Date</th><th>Page</th></tr>
''' % (HIGH_COLOR, MEDIUM_COLOR, ALERT_COLOR)

		today    = str( datetime.date.today() )
		tomorrow = str( datetime.date.today() + datetime.timedelta(days=1))
		dayafter = str( datetime.date.today() + datetime.timedelta(days=2))
		for indent, prio, desc, date, page in self.get_visible_data():
			if prio >= 3: prio = '<td class="high">%s</td>' % prio
			elif prio == 2: prio = '<td class="medium">%s</td>' % prio
			elif prio == 1: prio = '<td class="alert">%s</td>' % prio
			else: prio = '<td>%s</td>' % prio

			if date and date <= today: date = '<td class="high">%s</td>' % date
			elif date == tomorrow: date = '<td class="medium">%s</td>' % date
			elif date == dayafter: date = '<td class="alert">%s</td>' % date
			else: date = '<td>%s</td>' % date

			desc = '<td>%s%s</td>' % ('&nbsp;' * (4 * indent), desc)
			page = '<td>%s</td>' % page

			html += '<tr>' + prio + desc + date + page + '</tr>\n'

		html += '''\
</table>

	</body>

</html>
'''
		return html

	def get_visible_data(self):
		rows = []

		def collect(model, path, iter):
			indent = len(path) - 1 # path is tuple with indexes

			row = model[iter]
			prio = row[self.PRIO_COL]
			desc = row[self.TASK_COL].decode('utf-8')
			date = row[self.DATE_COL]
			page = row[self.PAGE_COL].decode('utf-8')

			if date == _NO_DATE:
				date = ''

			rows.append((indent, prio, desc, date, page))

		model = self.get_model()
		model.foreach(collect)

		return rows

# Need to register classes defining gobject signals
#~ gobject.type_register(TaskListTreeView)
# NOTE: enabling this line causes this treeview to have wrong theming under default ubuntu them !???
