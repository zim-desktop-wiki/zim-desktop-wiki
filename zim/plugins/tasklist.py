# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

import gobject
import gtk
import logging
import re
import datetime

from zim.parsing import parse_date
from zim.plugins import PluginClass
from zim.notebook import Path
from zim.gui.widgets import Dialog, Button, IconButton, BrowserTreeView, SingleClickTreeView
from zim.formats import UNCHECKED_BOX, CHECKED_BOX, XCHECKED_BOX


logger = logging.getLogger('zim.plugins.tasklist')


ui_actions = (
	# name, stock id, label, accelerator, tooltip, read only
	('show_task_list', 'zim-task-list', _('Task List'), '', _('Task List'), True),
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

# FUTURE: add an interface for this plugin in the WWW frontend

class TaskListPlugin(PluginClass):

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
		if ui.ui_type == 'gtk':
			ui.add_actions(ui_actions, self)
			ui.add_ui(ui_xml, self)

	def show_task_list(self):
		dialog = TaskListDialog.unique(self, plugin=self)
		dialog.present()


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
		self.task_list = TaskListTreeView(self.ui)
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
		self.task_list.connect('updated', set_statistics)

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

		self.on_update(task_list)
		task_list.connect('updated', self.on_update)

	def get_tags(self):
		'''Returns current selected tags, or None for all tags'''
		model, paths = self.get_selection().get_selected_rows()
		if not paths or (0,) in paths:
			return None
		else:
			return [model[path][0] for path in paths]

	def on_update(self, task_list):
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


style = gtk.Label().get_style() # HACK - how to get default style ?
NORMAL_COLOR = style.base[gtk.STATE_NORMAL]
HIGH_COLOR = gtk.gdk.color_parse('#EF2929') # red (from Tango style guide)
MEDIUM_COLOR = gtk.gdk.color_parse('#FCAF3E') # orange ("idem")
ALERT_COLOR = gtk.gdk.color_parse('#FCE94F') # yellow ("idem")
# FIXME: should these be configurable ?


class TaskListTreeView(BrowserTreeView):

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'updated': (gobject.SIGNAL_RUN_LAST, None, ()),
	}

	VIS_COL = 0 # visible
	PRIO_COL = 1
	TASK_COL = 2
	DATE_COL = 3
	PAGE_COL = 4
	ACT_COL = 5 # actionable - no children
	OPEN_COL = 6 # item not closed

	tag_re = re.compile(r'(?<!\S)@(\w+)\b', re.U)
	date_re = re.compile(r'\s*\[d:(.+)\]')

	def __init__(self, ui):
		self.filter = None
		self.tag_filter = None
		self.real_model = gtk.TreeStore(bool, int, str, str, str, bool, bool)
			# Vis, Prio, Task, Date, Page, Open, Act
		model = self.real_model.filter_new()
		model.set_visible_column(self.VIS_COL)
		model = gtk.TreeModelSort(model)
		model.set_sort_column_id(self.PRIO_COL, gtk.SORT_DESCENDING)
		BrowserTreeView.__init__(self, model)
		self.ui = ui
		self.total = 0
		self.tags = {} # dict mapping tag to ref count
		self.prio = {} # dict mapping tag to ref count
		self.maxprio = 0

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

		for page in ui.notebook.walk():
			self.index_page(page)
			# TODO do not hang here while indexing...
			# TODO cache this in database

		# TODO connect to notebok signals for updating ?

	#~ def show_closed(self, bool):
		# TODO - also show closed items

	#~ def show_tree(self, bool):
		# TODO - switch between tree view and list view

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
		return self.tags.keys()

	def get_statistics(self):
		highest = max([0] + self.prio.keys())
		stats = [self.prio.get(k, 0) for k in range(highest+1)]
		stats.reverse() # highest first
		return self.total, stats

	def set_tag_filter(self, tags):
		# TODO support multiple tags
		if tags:
			self.tag_filter = ["@"+tag.lower() for tag in tags]
		else:
			self.tag_filter = None
		self._eval_filter()

	def _eval_filter(self):
		logger.debug('Filtering with tag: %s, filter: %s', self.tag_filter, self.filter)
		self.real_model.foreach(self._filter_item)

	def _filter_item(self, model, path, iter):
		# This method filters case insensitive because both filters and
		# text are first converted to lower case text.
		visible = True

		if not (model[iter][self.ACT_COL] and model[iter][self.OPEN_COL]):
			visible = False

		description = model[iter][self.TASK_COL].lower()
		pagename = model[iter][self.PAGE_COL].lower()

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

		model[iter][self.VIS_COL] = visible

	def do_row_activated(self, path, column):
		model = self.get_model()
		page = Path( model[path][self.PAGE_COL] )
		#~ task = ...
		self.ui.open_page(page)
		#~ self.ui.mainwindow.pageview.search(task)

	def index_page(self, page):
		#~ self._delete_page(page)
		self._index_page(page)
		self.emit('updated')

	def _index_page(self, page):
		logger.debug('Task List indexing page: %s', page)
		tree = page.get_parsetree()
		if not tree:
			return

		for element in tree.getiterator('li'):
			bullet = element.get('bullet')
			if bullet in (UNCHECKED_BOX, CHECKED_BOX, XCHECKED_BOX):
				open = bullet == UNCHECKED_BOX
				self._add_task(page, element, open)

	def _add_task(self, page, node, open):
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

		text = self.date_re.sub(set_date, text)

		# TODO - determine if actionable or not
		# TODO - call _filter_item()
		self.real_model.append(None,
			(open, prio, text, date, page.name, True, open) )
			# Vis, Prio, Task, Date, Page, Act, Open

		if open:
			self.total += 1
			self.maxprio = max(self.maxprio, prio)
			if prio in self.prio:
				self.prio[prio] += 1
			else:
				self.prio[prio] = 1

		tags = set(self.tag_re.findall(text))
		for tag in tags:
			if tag in self.tags:
				self.tags[tag] += 1
			else:
				self.tags[tag] = 1

	def _flatten(self, node):
		text = node.text or ''
		for child in node.getchildren():
			if child.tag != 'li':
				text += self._flatten(child) # recurs
				text += child.tail or ''
		return text

# Need to register classes defining gobject signals
gobject.type_register(TaskListTreeView)


# TODO this plugin should be ported to using a table in the index database
# needs to hook database init and page indexing
# Needs to re-build the database when preferences changed
# Needs statusbar or similar to notify when indexing still ongoing
# Separating database class and Treemodel will also allow better separation
# of data and interface code.
