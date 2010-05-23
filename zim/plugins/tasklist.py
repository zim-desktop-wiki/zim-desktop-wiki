# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

from __future__ import with_statement

import gobject
import gtk
import logging
import re
import datetime

from zim.parsing import parse_date
from zim.plugins import PluginClass
from zim.notebook import Path
from zim.gui.widgets import gtk_get_style, \
	Dialog, MessageDialog, \
	Button, IconButton, MenuButton, \
	BrowserTreeView, SingleClickTreeView
from zim.formats import UNCHECKED_BOX, CHECKED_BOX, XCHECKED_BOX


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

SQL_FORMAT_VERSION = (0, 4)
SQL_FORMAT_VERSION_STRING = "0.4"

SQL_CREATE_TABLES = '''
create table if not exists tasklist (
	id INTEGER PRIMARY KEY,
	source INTEGER,
	parent INTEGER,
	open BOOLEAN,
	actionable BOOLEAN,
	prio INTEGER,
	due TEXT,
	description TEXT
);
'''


tag_re = re.compile(r'(?<!\S)@(\w+)\b', re.U)
date_re = re.compile(r'\s*\[d:(.+)\]')


# FUTURE: add an interface for this plugin in the WWW frontend

# TODO allow more complex queries for filter, in particular (NOT tag AND tag)


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
		# ('use_checkboxes', 'bool', _('Use checkboxes'), True),
			# T: label for plugin preferences dialog
		# TODO: option for tags
		# TODO: option to limit to specific namespace
	)

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
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

	def initialize_db(self, index):
		with index.db_commit:
			index.db.executescript(SQL_CREATE_TABLES)
		self.index.properties['plugin_tasklist_format'] = SQL_FORMAT_VERSION_STRING
		self.db_initialized = True

	def disconnect(self):
		self.index.properties['plugin_tasklist_format'] = 0
		if self.db_initialized:
			try:
				self.index.db.execute('DROP TABLE "tasklist"')
			except:
				logger.exception('Could not drop table:')

	def index_page(self, index, path, page):
		if not self.db_initialized: return

		#~ print '>>>>>', path, page, page.hascontent
		tasksfound = self.remove_page(index, path, _emit=False)

		tree = page.get_parsetree()
		if not tree:
			return

		#~ print '!! Checking for tasks in', path
		tasks = []
		for element in tree.getiterator('li'):
			bullet = element.get('bullet')
			if bullet in (UNCHECKED_BOX, CHECKED_BOX, XCHECKED_BOX):
				open = bullet == UNCHECKED_BOX
				tasks.append(self._parse_task(path, element, open))
		
		if tasks:
			tasksfound = True

		# Much more efficient to do insert here at once for all tasks
		# rather than do it one by one while parsing the page.
		with self.index.db_commit:
			self.index.db.executemany(
				'insert into tasklist(source, parent, open, actionable, prio, due, description)'
				'values (?, ?, ?, ?, ?, ?, ?)',
				tasks
			)

		if tasksfound:
			self.emit('tasklist-changed')

	def _parse_task(self, path, node, open):
		# TODO - determine if actionable or not
		#~ '!! Found tasks in ', path
		text = self._flatten(node)
		prio = text.count('!')

		global date # FIXME
		date = '9999' # For sorting order this is good empty value

		def set_date(match):
			global date
			mydate = parse_date(match.group(0))
			if mydate and date == '9999':
				date = '%04i-%02i-%02i' % mydate # (y, m, d)
				#~ return match.group(0) # TEST
				return ''
			else:
				# No match or we already had a date
				return match.group(0)

		text = date_re.sub(set_date, text)
		return (path.id, 0, open, True, prio, date, text)
			# (source, parent, open, actionable, prio, due, description)

	def _flatten(self, node):
		text = node.text or ''
		for child in node.getchildren():
			if child.tag != 'li':
				text += self._flatten(child) # recurs
				text += child.tail or ''
		return text

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

	def list_tasks(self):
		if self.db_initialized:
			cursor = self.index.db.cursor()
			cursor.execute('select * from tasklist')
			for row in cursor:
				yield row

	def get_path(self, task):
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


class TaskListDialog(Dialog):

	def __init__(self, plugin):
		Dialog.__init__(self, plugin.ui, _('Task List'), # T: dialog title
			buttons=gtk.BUTTONS_CLOSE, help=':Help:Plugins:Task List')
		self.plugin = plugin

		hbox = gtk.HBox(spacing=5)
		self.vbox.pack_start(hbox, False)
		self.hpane = gtk.HPaned()
		self.uistate.setdefault('hpane_pos', 72)
		self.hpane.set_position(self.uistate['hpane_pos'])
		self.vbox.add(self.hpane)

		# Task list
		self.task_list = TaskListTreeView(self.ui, plugin)
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
		filter_entry = gtk.Entry()
		hbox.pack_start(filter_entry, False)
		clear_button = IconButton('gtk-clear')
		hbox.pack_start(clear_button, False)
		filter_button = Button(_('_Filter'), 'gtk-find') # T: Button
		hbox.pack_start(filter_button, False)
		filter_entry.connect('activate',
			lambda o: self.task_list.set_filter(filter_entry.get_text()))
		filter_button.connect('clicked',
			lambda o: self.task_list.set_filter(filter_entry.get_text()))
		clear_button.connect('clicked',
			lambda o: (filter_entry.set_text(''), filter_entry.activate()))

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

		# Statistics label
		self.statistics_label = gtk.Label()
		hbox.pack_end(self.statistics_label, False)

		def set_statistics(task_list):
			total, stats = task_list.get_statistics()
			text = ngettext('%i open item', '%i open items', total) % total
				# T: Label for statistics in Task List, %i is the number of tasks
			text += ' (' + '/'.join(map(str, stats)) + ')'
			self.statistics_label.set_text(text)

		set_statistics(self.task_list)
		self.task_list.connect('changed', set_statistics)

	def do_response(self, response):
		self.uistate['hpane_pos'] = self.hpane.get_position()
		Dialog.do_response(self, response)


class TagListTreeView(SingleClickTreeView):
	'''TreeView with a single column 'Tags' which shows all tags available
	in a TaskListTreeView. Selecting a tag will filter the task list to
	only show tasks with that tag.
	'''

	def __init__(self, task_list):
		model = gtk.ListStore(str, bool) # tag name, is seperator bool
		SingleClickTreeView.__init__(self, model)
		self.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
		self.task_list = task_list

		cell_renderer = gtk.CellRendererText()
		column = gtk.TreeViewColumn(_('Tags'), cell_renderer, text=0)
			# T: Column header for tag list in Task List dialog
		self.append_column(column)

		self.set_row_separator_func(lambda m, i: m[i][1])
			# just returns the bool in the second column

		self.get_selection().connect('changed', self.on_selection_changed)

		self.refresh(task_list)
		task_list.connect('changed', self.refresh)

	def get_tags(self):
		'''Returns current selected tags, or None for all tags'''
		model, paths = self.get_selection().get_selected_rows()
		if not paths or (0,) in paths:
			return None
		else:
			return [model[path][0] for path in paths]

	def refresh(self, task_list):
		# FIXME make sure selection is not reset when refreshing
		model = self.get_model()
		model.clear()
		model.append((_('All'), False)) # T: "tag" for showing all tasks
		# TODO - any other special tags ?
		model.append(('', True)) # separator
		for tag in sorted(self.task_list.get_tags()):
			model.append((tag, False))

	def on_selection_changed(self, selection):
		tags = self.get_tags()
		self.task_list.set_tag_filter(tags)


style = gtk_get_style()
NORMAL_COLOR = style.base[gtk.STATE_NORMAL]
HIGH_COLOR = gtk.gdk.color_parse('#EF2929') # red (from Tango style guide)
MEDIUM_COLOR = gtk.gdk.color_parse('#FCAF3E') # orange ("idem")
ALERT_COLOR = gtk.gdk.color_parse('#FCE94F') # yellow ("idem")
# FIXME: should these be configurable ?


class TaskListTreeView(BrowserTreeView):

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'changed': (gobject.SIGNAL_RUN_LAST, None, ()),
	}

	VIS_COL = 0 # visible
	PRIO_COL = 1
	TASK_COL = 2
	DATE_COL = 3
	PAGE_COL = 4
	ACT_COL = 5 # actionable - no children
	OPEN_COL = 6 # item not closed

	def __init__(self, ui, plugin):
		self.filter = None
		self.tag_filter = None
		self.real_model = gtk.TreeStore(bool, int, str, str, str, bool, bool)
			# VIS_COL, PRIO_COL, TASK_COL, DATE_COL, PAGE_COL, ACT_COL, OPEN_COL
		model = self.real_model.filter_new()
		model.set_visible_column(self.VIS_COL)
		model = gtk.TreeModelSort(model)
		model.set_sort_column_id(self.PRIO_COL, gtk.SORT_DESCENDING)
		BrowserTreeView.__init__(self, model)
		self.ui = ui
		self.plugin = plugin

		cell_renderer = gtk.CellRendererText()
		for name, i in (
			(_('Task'), self.TASK_COL), # T: Column header Task List dialog
			(_('Page'), self.PAGE_COL), # T: Column header Task List dialog
		):
			column = gtk.TreeViewColumn(name, cell_renderer, text=i)
			column.set_resizable(True)
			column.set_sort_column_id(i)
			if i == self.TASK_COL: column.set_expand(True)
			self.append_column(column)

		# Add some rendering for the Prio column
		def render_prio(col, cell, model, i):
			prio = model.get_value(i, self.PRIO_COL)
			cell.set_property('text', str(prio))
			if prio >= 3: color = HIGH_COLOR
			elif prio == 2: color = MEDIUM_COLOR
			elif prio == 1: color = ALERT_COLOR
			else: color = NORMAL_COLOR
			cell.set_property('cell-background-gdk', color)

		cell_renderer = gtk.CellRendererText()
		column = gtk.TreeViewColumn(_('Prio'), cell_renderer)
			# T: Column header Task List dialog
		column.set_cell_data_func(cell_renderer, render_prio)
		column.set_sort_column_id(self.PRIO_COL)
		self.insert_column(column, 0)

		# Rendering of the Date column
		today    = str( datetime.date.today() )
		tomorrow = str( datetime.date.today() + datetime.timedelta(days=1))
		dayafter = str( datetime.date.today() + datetime.timedelta(days=2))
		def render_date(col, cell, model, i):
			date = model.get_value(i, self.DATE_COL)
			if date == '9999':
				cell.set_property('text', '')
			else:
				cell.set_property('text', date)
				# TODO allow strftime here

			if date <= today: color = HIGH_COLOR
			elif date == tomorrow: color = MEDIUM_COLOR
			elif date == dayafter: color = ALERT_COLOR
			else: color = NORMAL_COLOR
			cell.set_property('cell-background-gdk', color)

		cell_renderer = gtk.CellRendererText()
		column = gtk.TreeViewColumn(_('Date'), cell_renderer)
			# T: Column header Task List dialog
		column.set_cell_data_func(cell_renderer, render_date)
		column.set_sort_column_id(self.DATE_COL)
		self.insert_column(column, 2)

		self.refresh()
		self.plugin.connect_object('tasklist-changed', self.__class__.refresh, self)

	def refresh(self):
		self.real_model.clear()
		paths = {}
		for row in self.plugin.list_tasks():
			if not row['source'] in paths:
				paths[row['source']] = self.plugin.get_path(row)
			path = paths[row['source']]
			modelrow = [False, row['prio'], row['description'], row['due'], path.name, row['actionable'], row['open']]
						# VIS_COL, PRIO_COL, TASK_COL, DATE_COL, PAGE_COL, ACT_COL, OPEN_COL
			modelrow[0] = self._filter_item(modelrow)
			self.real_model.append(None, modelrow)

		self.emit('changed')

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

	def get_tags(self):
		'''Returns list of all tags that are in use for tasks'''
		tags = set()

		def collect(model, path, iter):
			# also count hidden rows here
			desc = model[iter][self.TASK_COL].decode('utf-8')
			for match in tag_re.findall(desc):
				tags.add(match)

		self.real_model.foreach(collect)

		return tags

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
			self.tag_filter = ["@"+tag.lower() for tag in tags]
		else:
			self.tag_filter = None
		self._eval_filter()

	def _eval_filter(self):
		logger.debug('Filtering with tag: %s, filter: %s', self.tag_filter, self.filter)

		def filter(model, path, iter):
			visible = self._filter_item(model[iter])
			model[iter][self.VIS_COL] = visible

		self.real_model.foreach(filter)

	def _filter_item(self, modelrow):
		# This method filters case insensitive because both filters and
		# text are first converted to lower case text.
		visible = True

		if not (modelrow[self.ACT_COL] and modelrow[self.OPEN_COL]):
			visible = False

		description = modelrow[self.TASK_COL].lower()
		pagename = modelrow[self.PAGE_COL].lower()

		if visible and self.tag_filter:
			match = False
			for tag in self.tag_filter:
				if tag in description:
					match = True
					break
			if not match:
				visible = False

		if visible and self.filter:
			inverse, string = self.filter
			match = string in description or string in pagename
			if (not inverse and not match) or (inverse and match):
				visible = False

		return visible

	def do_row_activated(self, path, column):
		model = self.get_model()
		page = Path( model[path][self.PAGE_COL] )
		#~ task = ...
		self.ui.open_page(page)
		#~ self.ui.mainwindow.pageview.search(task) # FIXME

# Need to register classes defining gobject signals
gobject.type_register(TaskListTreeView)


# TODO this plugin should be ported to using a table in the index database
# needs to hook database init and page indexing
# Needs to re-build the database when preferences changed
# Needs statusbar or similar to notify when indexing still ongoing
# Separating database class and Treemodel will also allow better separation
# of data and interface code.
