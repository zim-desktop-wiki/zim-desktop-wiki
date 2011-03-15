# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement

import gobject
import gtk
import pango
import logging
import re

import zim.datetimetz as datetime
from zim.parsing import parse_date
from zim.plugins import PluginClass
from zim.notebook import Path
from zim.gui.widgets import ui_environment, gtk_get_style,\
	Dialog, MessageDialog, \
	InputEntry, Button, IconButton, MenuButton, \
	BrowserTreeView, SingleClickTreeView
from zim.formats import get_format, UNCHECKED_BOX, CHECKED_BOX, XCHECKED_BOX
from zim.config import check_class_allow_empty


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
		('all_checkboxes', 'bool', _('Consider all checkboxes as tasks'), True),
			# T: label for plugin preferences dialog
		('tag_by_page', 'bool', _('Turn page name into tags for task items'), False),
			# T: label for plugin preferences dialog
		('labels', 'string', _('Labels marking tasks'), 'FIXME, TODO', check_class_allow_empty),
			# T: label for plugin preferences dialog - labels are e.g. "FIXME", "TODO", "TASKS"
	)
	_rebuild_on_preferences = ['all_checkboxes', 'labels']
		# Rebuild database table if any of these preferences changed.
		# But leave it alone if others change.

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
		regex = '(' + '|'.join(map(re.escape, self.task_labels)) + ')'
		self.task_label_re = re.compile(regex)

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
		tasks = self.extract_tasks(parsetree)
		if tasks:
			tasksfound = True

			# Much more efficient to do insert here at once for all tasks
			# rather than do it one by one while parsing the page.
			with self.index.db_commit:
				self.index.db.executemany(
					'insert into tasklist(source, parent, open, actionable, prio, due, description)'
					'values (%i, 0, ?, ?, ?, ?, ?)' % path.id,
					tasks
				)

		if tasksfound:
			self.emit('tasklist-changed')

	def extract_tasks(self, parsetree):
		'''Extract all tasks from a parsetree.
		Returns tuples for each tasks with following properties:
			(open, actionable, prio, due, description)
		'''
		tasks = []

		for node in parsetree.findall('p'):
			lines = self._flatten_para(node)
			# Check first line for task list header
			istasklist = False
			globaltags = []
			if len(lines) >= 2 \
			and isinstance(lines[0], basestring) \
			and isinstance(lines[1], tuple) \
			and self.task_labels and self.task_label_re.match(lines[0]):
				for word in lines[0].split()[1:]:
					if word.startswith('@'):
						globaltags.append(word)
					else:
						# not a header after all
						globaltags = []
						break
				else:
					# no break occured - all OK
					lines.pop(0)
					istasklist = True

			# Check line by line
			for item in lines:
				if isinstance(item, tuple):
					# checkbox
					if istasklist or self.preferences['all_checkboxes'] \
					or (self.task_labels and self.task_label_re.match(item[2])):
						open = item[0] == UNCHECKED_BOX
						tasks.append(self._parse_task(item[2], level=item[1], open=open, tags=globaltags))
				else:
					# normal line
					if self.task_labels and self.task_label_re.match(item):
						tasks.append(self._parse_task(item, tags=globaltags))

		return tasks

	def _flatten_para(self, para):
		# Returns a list which is a mix of normal lines of text and
		# tuples for checkbox items. Checkbox item tuples consist of
		# the checkbox type, the indenting level and the text.
		items = []

		text = para.text or ''
		for child in para.getchildren():
			if child.tag == 'strike':
				continue # Ignore strike out text
			elif child.tag == 'ul':
				if text:
					items += text.splitlines()
				items += self._flatten_list(child)
				text = child.tail or ''
			else:
				text += self._flatten(child)
				text += child.tail or ''

		if text:
			items += text.splitlines()

		return items

	def _flatten_list(self, list, list_level=0):
		# Handle bullet lists
		items = []
		for node in list.getchildren():
			if node.tag == 'ul':
				items += self._flatten_list(node, list_level+1) # recurs
			elif node.tag == 'li':
				bullet = node.get('bullet')
				text = self._flatten(node)
				if bullet in (UNCHECKED_BOX, CHECKED_BOX, XCHECKED_BOX):
					items.append((bullet, list_level, text))
				else:
					items.append(text)
			else:
				pass # should not occur - ignore silently
		return items

	def _flatten(self, node):
		# Just flatten everything to text
		text = node.text or ''
		for child in node.getchildren():
			text += self._flatten(child) # recurs
			text += child.tail or ''
		return text

	def _parse_task(self, text, level=0, open=True, tags=None):
		# TODO - determine if actionable or not
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

		if tags:
			for tag in tags:
				if not tag in text:
					text += ' ' + tag

		text = date_re.sub(set_date, text)
		return (open, True, prio, date, text)
			# (open, actionable, prio, due, description)


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
		self.task_list = TaskListTreeView(self.ui, plugin)
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
		tags = self._get_selected()
		for label in self.task_list.plugin.task_labels:
			if label in tags:
				tags.remove(label)
		return tags or None

	def get_labels(self):
		'''Returns current selected labels'''
		labels = []
		for tag in self._get_selected():
			if tag in self.task_list.plugin.task_labels:
				labels.append(tag)
		return labels or None

	def _get_selected(self):
		model, paths = self.get_selection().get_selected_rows()
		if not paths or (0,) in paths:
			return []
		else:
			return [model[path][0] for path in paths]

	def refresh(self, task_list):
		# FIXME make sure selection is not reset when refreshing
		model = self.get_model()
		model.clear()
		model.append((_('All'), False)) # T: "tag" for showing all tasks
		for label in task_list.plugin.task_labels:
			model.append((label, False))
		model.append(('', True)) # separator
		for tag in sorted(self.task_list.get_tags()):
			model.append((tag, False))

	def on_selection_changed(self, selection):
		tags = self.get_tags()
		labels = self.get_labels()
		self.task_list.set_tag_filter(tags)
		self.task_list.set_label_filter(labels)


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
		self.label_filter = None
		self.real_model = gtk.TreeStore(bool, int, str, str, str, bool, bool)
			# VIS_COL, PRIO_COL, TASK_COL, DATE_COL, PAGE_COL, ACT_COL, OPEN_COL
		model = self.real_model.filter_new()
		model.set_visible_column(self.VIS_COL)
		model = gtk.TreeModelSort(model)
		model.set_sort_column_id(self.PRIO_COL, gtk.SORT_DESCENDING)
		BrowserTreeView.__init__(self, model)
		self.ui = ui
		self.plugin = plugin

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
		self.append_column(column)

		# Rendering for task description column
		cell_renderer = gtk.CellRendererText()
		cell_renderer.set_property('ellipsize', pango.ELLIPSIZE_END)
		column = gtk.TreeViewColumn(_('Task'), cell_renderer, text=self.TASK_COL)
				# T: Column header Task List dialog
		column.set_resizable(True)
		column.set_sort_column_id(self.TASK_COL)
		column.set_expand(True)
		if ui_environment['platform'] == 'maemo':
			column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
			column.set_fixed_width(250)
			# FIXME probably should also limit the size of this
			# column on other platforms ...
		self.append_column(column)

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
		self.append_column(column)

		# Rendering for page name column
		cell_renderer = gtk.CellRendererText()
		column = gtk.TreeViewColumn(_('Page'), cell_renderer, text=self.PAGE_COL)
				# T: Column header Task List dialog
		column.set_resizable(True)
		column.set_sort_column_id(self.PAGE_COL)
		self.append_column(column)

		# Finalize
		self.refresh()
		self.plugin.connect_object('tasklist-changed', self.__class__.refresh, self)

	def refresh(self):
		self.real_model.clear() # flush

		# First cache + sort tasks to ensure stability of the list
		rows = list(self.plugin.list_tasks())
		paths = {}
		for row in rows:
			if not row['source'] in paths:
				paths[row['source']] = self.plugin.get_path(row)

		rows.sort(key=lambda r: paths[r['source']].name)

		for row in rows:
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
			row = model[iter]
			if not row[self.OPEN_COL]:
				return # only count open items

			desc = row[self.TASK_COL].decode('utf-8')
			for match in tag_re.findall(desc):
				tags.add(match)

			if self.plugin.preferences['tag_by_page']:
				name = row[self.PAGE_COL].decode('utf-8')
				for part in name.split(':'):
					tags.add(part)

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
			self.tag_filter = [tag.lower() for tag in tags]
		else:
			self.tag_filter = None
		self._eval_filter()

	def set_label_filter(self, labels):
		if labels:
			self.label_filter = labels
		else:
			self.label_filter = None
		self._eval_filter()

	def _eval_filter(self):
		logger.debug('Filtering with labels: %s tags: %s, filter: %s', self.label_filter, self.tag_filter, self.filter)

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

		if visible and self.label_filter:
			# Any labels need to be present
			description = modelrow[self.TASK_COL]
			for label in self.label_filter:
				if label in description:
					break
			else:
				visible = False # no label found

		description = modelrow[self.TASK_COL].lower()
		pagename = modelrow[self.PAGE_COL].lower()

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
			inverse, string = self.filter
			match = string in description or string in pagename
			if (not inverse and not match) or (inverse and match):
				visible = False

		return visible

	def do_row_activated(self, path, column):
		model = self.get_model()
		page = Path( model[path][self.PAGE_COL] )
		task = unicode(model[path][self.TASK_COL])
		self.ui.open_page(page)
		self.ui.mainwindow.pageview.find(task)

	def do_button_release_event(self, event):
		'''Handler for button-release-event, triggers popup menu'''
		if event.button == 3:
			self.emit('popup-menu')# FIXME do we need to pass x/y and button ?
			return True
		else:
			return BrowserTreeView.do_button_release_event(self, event)

	def do_popup_menu(self): # FIXME do we need to pass x/y and button ?
		menu = gtk.Menu()
		item = gtk.MenuItem(_("_Copy")) # T: menu item in context menu
		item.connect_object('activate', self.__class__.copy_to_clipboard, self)
		menu.append(item)
		menu.show_all()
		menu.popup(None, None, None, 3, 0)
		return True

	def copy_to_clipboard(self):
		'''Exports currently visable elements from the tasks list'''
		logger.debug('Exporting to clipboard current view of task list.')
		model = self.get_model()
		tasks = ""
		for row in model:
			# only open items
			if row[self.OPEN_COL]:
				tags = set()
				vis, prio, desc, due, path_name, actionable, opn = row
				if due == "9999": due = "-"
				for match in tag_re.findall(desc.decode("UTF-8")):
					tags.add(match)
					tasks += "Description: %s\nPriority: %s,  Actionable: %s,  Open: %s,  Due: %s\nPath: %s,  Tags: %s\n\n" % (desc, prio, actionable, opn, due, path_name, ", ".join(tags))
		tasks += "Number of tasks: %s. Exported: %s" \
				% (len(model), str(datetime.now()))
		#~ print tasks
		gtk.Clipboard().set_text(tasks.decode("UTF-8"))

# Need to register classes defining gobject signals
gobject.type_register(TaskListTreeView)


# TODO this plugin should be ported to using a table in the index database
# needs to hook database init and page indexing
# Needs to re-build the database when preferences changed
# Needs statusbar or similar to notify when indexing still ongoing
# Separating database class and Treemodel will also allow better separation
# of data and interface code.
