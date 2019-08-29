
# Copyright 2009-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import Pango

import logging
import re

from zim.plugins import find_extension

import zim.datetimetz as datetime
from zim.utils import natural_sorted

from zim.notebook import Path
from zim.gui.widgets import \
	Dialog, WindowSidePaneWidget, InputEntry, \
	BrowserTreeView, SingleClickTreeView, ScrolledWindow, HPaned, \
	encode_markup_text, decode_markup_text
from zim.gui.clipboard import Clipboard
from zim.signals import DelayedCallback, SIGNAL_AFTER
from zim.plugins import DialogExtensionBase, extendable

logger = logging.getLogger('zim.plugins.tasklist')

from .indexer import _MAX_DUE_DATE, _NO_TAGS, _date_re, _tag_re, _parse_task_labels, _task_labels_re


class TaskListWidgetMixin(object):

		def on_populate_popup(self, o, menu):
			sep = Gtk.SeparatorMenuItem()
			menu.append(sep)

			item = Gtk.CheckMenuItem(_('Show Tasks as Flat List'))
				# T: Checkbox in task list - hides parent items
			item.set_active(self.uistate['show_flatlist'])
			item.connect('toggled', self.on_show_flatlist_toggle)
			item.show_all()
			menu.append(item)

			item = Gtk.CheckMenuItem(_('Only Show Active Tasks'))
				# T: Checkbox in task list - this options hides tasks that are not yet started
			item.set_active(self.uistate['only_show_act'])
			item.connect('toggled', self.on_show_active_toggle)
			item.show_all()
			menu.append(item)

		def on_show_active_toggle(self, *a):
			active = not self.uistate['only_show_act']
			self.uistate['only_show_act'] = active
			self.task_list.set_filter_actionable(active)

		def on_show_flatlist_toggle(self, *a):
			active = not self.uistate['show_flatlist']
			self.uistate['show_flatlist'] = active
			self.task_list.set_flatlist(active)


class TaskListWidget(Gtk.VBox, TaskListWidgetMixin, WindowSidePaneWidget):

	title = _('Tasks') # T: tab label for side pane

	def __init__(self, tasksview, opener, properties, with_due, uistate):
		GObject.GObject.__init__(self)
		self.uistate = uistate
		self.uistate.setdefault('only_show_act', False)
		self.uistate.setdefault('show_flatlist', False)

		column_layout=TaskListTreeView.COMPACT_COLUMN_LAYOUT_WITH_DUE \
			if with_due else TaskListTreeView.COMPACT_COLUMN_LAYOUT
		self.task_list = TaskListTreeView(
			tasksview, opener,
			_parse_task_labels(properties['labels']),
			nonactionable_tags=_parse_task_labels(properties['nonactionable_tags']),
			filter_actionable=self.uistate['only_show_act'],
			tag_by_page=properties['tag_by_page'],
			use_workweek=properties['use_workweek'],
			column_layout=column_layout,
			flatlist=self.uistate['show_flatlist'],
		)
		self.task_list.connect('populate-popup', self.on_populate_popup)
		self.task_list.set_headers_visible(True)

		self.connectto(properties, 'changed', self.on_properties_changed)

		self.filter_entry = InputEntry(placeholder_text=_('Filter')) # T: label for filtering/searching tasks
		self.filter_entry.set_icon_to_clear()
		filter_cb = DelayedCallback(500,
			lambda o: self.task_list.set_filter(self.filter_entry.get_text()))
		self.filter_entry.connect('changed', filter_cb)

		self.pack_start(ScrolledWindow(self.task_list), True, True, 0)
		self.pack_end(self.filter_entry, False, True, 0)

	def on_properties_changed(self, properties):
		self.task_list.update_properties(
			task_labels=_parse_task_labels(properties['labels']),
			nonactionable_tags=_parse_task_labels(properties['nonactionable_tags']),
			tag_by_page=properties['tag_by_page'],
			use_workweek=properties['use_workweek'],
		)


class TaskListDialogExtension(DialogExtensionBase):
	pass

@extendable(TaskListDialogExtension)
class TaskListDialog(TaskListWidgetMixin, Dialog):

	def __init__(self, parent, tasksview, properties):
		Dialog.__init__(self, parent, _('Task List'), # T: dialog title
			buttons=Gtk.ButtonsType.CLOSE, help=':Plugins:Task List',
			defaultwindowsize=(550, 400))
		self.properties = properties
		self.tasksview = tasksview
		self.notebook = parent.notebook

		hbox = Gtk.HBox(spacing=5)
		self.vbox.pack_start(hbox, False, True, 0)
		self.hpane = HPaned()
		self.uistate.setdefault('hpane_pos', 75)
		self.hpane.set_position(self.uistate['hpane_pos'])
		self.vbox.pack_start(self.hpane, True, True, 0)

		# Task list
		self.uistate.setdefault('only_show_act', False)
		self.uistate.setdefault('show_flatlist', False)
		self.uistate.setdefault('sort_column', 0)
		self.uistate.setdefault('sort_order', int(Gtk.SortType.DESCENDING))

		opener = parent.navigation
		self.task_list = TaskListTreeView(
			self.tasksview, opener,
			_parse_task_labels(properties['labels']),
			nonactionable_tags=_parse_task_labels(properties['nonactionable_tags']),
			filter_actionable=self.uistate['only_show_act'],
			tag_by_page=properties['tag_by_page'],
			use_workweek=properties['use_workweek'],
			flatlist=self.uistate['show_flatlist'],
			sort_column=self.uistate['sort_column'],
			sort_order=self.uistate['sort_order']
		)
		self.task_list.set_headers_visible(True)
		self.task_list.connect('populate-popup', self.on_populate_popup)
		self.hpane.add2(ScrolledWindow(self.task_list))

		# Tag list
		self.tag_list = TagListTreeView(self.task_list)
		self.hpane.add1(ScrolledWindow(self.tag_list))

		self.connectto(properties, 'changed', self.on_properties_changed)

		# Filter input
		hbox.pack_start(Gtk.Label(_('Filter') + ': '), False, True, 0) # T: Input label
		filter_entry = InputEntry()
		filter_entry.set_icon_to_clear()
		hbox.pack_start(filter_entry, False, True, 0)
		filter_cb = DelayedCallback(500,
			lambda o: self.task_list.set_filter(filter_entry.get_text()))
		filter_entry.connect('changed', filter_cb)

		# TODO: use menu button here and add same options as in context menu
		#       for filtering the list
		def on_show_active_toggle(o):
			active = self.act_toggle.get_active()
			if self.uistate['only_show_act'] != active:
				self.uistate['only_show_act'] = active
				self.task_list.set_filter_actionable(active)

		self.act_toggle = Gtk.CheckButton.new_with_mnemonic(_('Only Show Active Tasks'))
			# T: Checkbox in task list - this options hides tasks that are not yet started
		self.act_toggle.set_active(self.uistate['only_show_act'])
		self.act_toggle.connect('toggled', on_show_active_toggle)
		self.uistate.connect('changed', lambda o: self.act_toggle.set_active(self.uistate['only_show_act']))
		hbox.pack_start(self.act_toggle, False, True, 0)

		# Statistics label
		self.statistics_label = Gtk.Label()
		hbox.pack_end(self.statistics_label, False, True, 0)

		def set_statistics():
			total = self.task_list.get_n_tasks()
			text = ngettext('%i open item', '%i open items', total) % total
				# T: Label for task List, %i is the number of tasks
			self.statistics_label.set_text(text)

		set_statistics()

		def on_tasklist_changed(o):
			self.task_list.refresh()
			self.tag_list.refresh(self.task_list)
			set_statistics()

		callback = DelayedCallback(10, on_tasklist_changed)
			# Don't really care about the delay, but want to
			# make it less blocking - should be async preferably
			# now it is at least on idle

		from . import TaskListNotebookExtension
		nb_ext = find_extension(self.notebook, TaskListNotebookExtension)
		self.connectto(nb_ext, 'tasklist-changed', callback)

	def on_properties_changed(self, properties):
		self.task_list.update_properties(
			task_labels=_parse_task_labels(properties['labels']),
			nonactionable_tags=_parse_task_labels(properties['nonactionable_tags']),
			tag_by_page=properties['tag_by_page'],
			use_workweek=properties['use_workweek'],
		)
		self.tag_list.refresh(self.task_list)

	def do_response(self, response):
		self.uistate['hpane_pos'] = self.hpane.get_position()

		for column in self.task_list.get_columns():
			if column.get_sort_indicator():
				self.uistate['sort_column'] = column.get_sort_column_id()
				self.uistate['sort_order'] = int(column.get_sort_order())
				break
		else:
			# if it is unsorted, just use the defaults
			self.uistate['sort_column'] = TaskListTreeView.PRIO_COL
			self.uistate['sort_order'] = Gtk.SortType.ASCENDING

		Dialog.do_response(self, response)


class TagListTreeView(SingleClickTreeView):
	'''TreeView with a single column 'Tags' which shows all tags available
	in a TaskListTreeView. Selecting a tag will filter the task list to
	only show tasks with that tag.
	'''

	_type_separator = 0
	_type_label = 1
	_type_tag = 2
	_type_untagged = 3

	def __init__(self, task_list):
		model = Gtk.ListStore(str, int, int, int) # tag name, number of tasks, type, weight
		SingleClickTreeView.__init__(self, model)
		self.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
		self.task_list = task_list

		column = Gtk.TreeViewColumn(_('Tags'))
			# T: Column header for tag list in Task List dialog
		column.set_expand(True)
		self.append_column(column)

		cr1 = Gtk.CellRendererText()
		cr1.set_property('ellipsize', Pango.EllipsizeMode.END)
		column.pack_start(cr1, True)
		column.set_attributes(cr1, text=0, weight=3) # tag name, weight

		column = Gtk.TreeViewColumn('')
		self.append_column(column)

		cr2 = self.get_cell_renderer_number_of_items()
		column.pack_start(cr2, False)
		column.set_attributes(cr2, text=1) # number of tasks

		self.set_row_separator_func(lambda m, i: m[i][2] == self._type_separator)

		self._block_selection_change = False
		self.get_selection().connect('changed', self.on_selection_changed)

		self.refresh(task_list)

	def get_tags(self):
		'''Returns current selected tags, or None for all tags'''
		tags = []
		for row in self._get_selected():
			if row[2] == self._type_tag:
				tags.append(row[0])
			elif row[2] == self._type_untagged:
				tags.append(_NO_TAGS)
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
			if not paths or any(p == Gtk.TreePath(0) for p in paths):
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
		if model is None:
				return
		model.clear()

		n_all = self.task_list.get_n_tasks()
		model.append((_('All Tasks'), n_all, self._type_label, Pango.Weight.BOLD)) # T: "tag" for showing all tasks

		used_labels = self.task_list.get_labels()
		for label in self.task_list.task_labels: # explicitly keep sorting from properties
			if label in used_labels:
				model.append((label, used_labels[label], self._type_label, Pango.Weight.BOLD))

		tags = self.task_list.get_tags()
		if _NO_TAGS in tags:
			n_untagged = tags.pop(_NO_TAGS)
			model.append((_('Untagged'), n_untagged, self._type_untagged, Pango.Weight.NORMAL))
			# T: label in tasklist plugins for tasks without a tag

		model.append(('', 0, self._type_separator, 0)) # separator

		for tag in natural_sorted(tags):
			model.append((tag, tags[tag], self._type_tag, Pango.Weight.NORMAL))

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
			self.task_list.set_tag_filter(tags, labels)


HIGH_COLOR = '#EF5151' # red (derived from Tango style guide - #EF2929)
MEDIUM_COLOR = '#FCB956' # orange ("idem" - #FCAF3E)
ALERT_COLOR = '#FCEB65' # yellow ("idem" - #FCE94F)
# FIXME: should these be configurable ?

COLORS = [None, ALERT_COLOR, MEDIUM_COLOR, HIGH_COLOR] # index 0..3

def days_to_str(days):
	if days > 290:
			return '%iy' % round(float(days) / 365) # round up to 1 year from ~10 months
	elif days > 25:
			return '%im' % round(float(days) / 30)
	elif days > 10:
			return '%iw' % round(float(days) / 7)
	else:
			return '%id' % days


class TaskListTreeView(BrowserTreeView):

	# idem for flat list vs tree

	VIS_COL = 0 # visible
	ACT_COL = 1 # actionable
	PRIO_COL = 2
	START_COL = 3
	DUE_COL = 4
	TAGS_COL = 5
	DESC_COL = 6
	PAGE_COL = 7
	TASKID_COL = 8
	PRIO_SORT_COL = 9
	PRIO_SORT_LABEL_COL = 10

	RICH_COLUMN_LAYOUT = 11
	COMPACT_COLUMN_LAYOUT = 12
	COMPACT_COLUMN_LAYOUT_WITH_DUE = 13

	def __init__(self,
		tasksview, opener,
		task_labels,
		nonactionable_tags=(),
		filter_actionable=False, tag_by_page=False, use_workweek=False,
		column_layout=RICH_COLUMN_LAYOUT, flatlist=False,
		sort_column=PRIO_COL, sort_order=Gtk.SortType.DESCENDING
	):
		self.real_model = Gtk.TreeStore(bool, bool, int, str, str, object, str, str, int, int, str)
			# VIS_COL, ACT_COL, PRIO_COL, START_COL, DUE_COL, TAGS_COL, DESC_COL, PAGE_COL, TASKID_COL, PRIO_SORT_COL, PRIO_SORT_LABEL_COL
		model = self.real_model.filter_new()
		model.set_visible_column(self.VIS_COL)
		model = Gtk.TreeModelSort(model)
		model.set_sort_column_id(sort_column, sort_order)
		BrowserTreeView.__init__(self, model)

		self.tasksview = tasksview
		self.opener = opener
		self.filter = None
		self.tag_filter = None
		self.label_filter = None
		self.filter_actionable = filter_actionable
		self.nonactionable_tags = tuple(t.strip('@').lower() for t in nonactionable_tags)
		self.tag_by_page = tag_by_page
		self.task_labels = task_labels
		self._tags = {}
		self._labels = {}
		self.flatlist = flatlist

		# Add some rendering for the Prio column
		def render_prio(col, cell, model, i, data):
			prio = model.get_value(i, self.PRIO_COL)
			text = model.get_value(i, self.PRIO_SORT_LABEL_COL)
			if text.startswith('>'):
				text = '<span color="darkgrey">%s</span>' % text
				bg = None
			else:
				bg = COLORS[min(prio, 3)]
			cell.set_property('markup', text)
			cell.set_property('cell-background', bg)

		cell_renderer = Gtk.CellRendererText()
		column = Gtk.TreeViewColumn('!', cell_renderer)
		column.set_cell_data_func(cell_renderer, render_prio)
		column.set_sort_column_id(self.PRIO_SORT_COL)
		self.append_column(column)

		# Rendering for task description column
		cell_renderer = Gtk.CellRendererText()
		cell_renderer.set_property('ellipsize', Pango.EllipsizeMode.END)
		column = Gtk.TreeViewColumn(_('Task'), cell_renderer, markup=self.DESC_COL)
				# T: Column header Task List dialog
		column.set_resizable(True)
		column.set_sort_column_id(self.DESC_COL)
		column.set_expand(True)
		if column_layout != self.RICH_COLUMN_LAYOUT:
			column.set_min_width(100)
		else:
			column.set_min_width(300) # don't let this column get too small
		self.append_column(column)
		self.set_expander_column(column)

		# custom tooltip
		self.props.has_tooltip = True
		self.connect("query-tooltip", self._query_tooltip_cb)

		# Rendering of the Date column
		day_of_week = datetime.date.today().isoweekday()
		if use_workweek and day_of_week == 4:
			# Today is Thursday - 2nd day ahead is after the weekend
			delta1, delta2 = 1, 3
		elif use_workweek and day_of_week == 5:
			# Today is Friday - next day ahead is after the weekend
			delta1, delta2 = 3, 4
		else:
			delta1, delta2 = 1, 2

		today = str(datetime.date.today())
		tomorrow = str(datetime.date.today() + datetime.timedelta(days=delta1))
		dayafter = str(datetime.date.today() + datetime.timedelta(days=delta2))
		def render_date(col, cell, model, i, data):
			date = model.get_value(i, self.DUE_COL)
			if date == _MAX_DUE_DATE:
				cell.set_property('text', '')
			else:
				cell.set_property('text', date)
				# TODO allow strftime here

			if date <= today:
					color = HIGH_COLOR
			elif date <= tomorrow:
					color = MEDIUM_COLOR
			elif date <= dayafter:
					color = ALERT_COLOR
				# "<=" because tomorrow and/or dayafter can be after the weekend
			else:
					color = None
			cell.set_property('cell-background', color)

		if column_layout != self.COMPACT_COLUMN_LAYOUT:
			cell_renderer = Gtk.CellRendererText()
			column = Gtk.TreeViewColumn(_('Date'), cell_renderer)
				# T: Column header Task List dialog
			column.set_cell_data_func(cell_renderer, render_date)
			column.set_sort_column_id(self.DUE_COL)
			self.append_column(column)

		# Rendering for page name column
		if column_layout == self.RICH_COLUMN_LAYOUT:
			cell_renderer = Gtk.CellRendererText()
			column = Gtk.TreeViewColumn(_('Page'), cell_renderer, text=self.PAGE_COL)
					# T: Column header Task List dialog
			column.set_sort_column_id(self.PAGE_COL)
			self.append_column(column)

		# Finalize
		self.refresh()

		# HACK because we can not register ourselves :S
		self.connect('row_activated', self.__class__.do_row_activated)
		self.connect('focus-in-event', self.__class__.do_focus_in_event)

	def update_properties(self,
		task_labels=None,
		nonactionable_tags=None,
		tag_by_page=None,
		use_workweek=None,
	):
		if task_labels is not None:
			self.task_labels = task_labels

		if nonactionable_tags is not None:
			self.nonactionable_tags = tuple(t.strip('@').lower() for t in nonactionable_tags)

		if tag_by_page is not None:
			self.tag_by_page = tag_by_page

		if use_workweek is not None:
			print("TODO udate_use_workweek rendering")

		self.refresh()

	def refresh(self):
		'''Refresh the model based on index data'''
		# Update data
		self._clear()
		self._append_tasks(None, None, {})
		self._today = datetime.date.today()

		# Make tags case insensitive
		tags = sorted((t.lower(), t) for t in self._tags)
			# tuple sorting will sort ("foo", "Foo") before ("foo", "foo"),
			# but ("bar", ..) before ("foo", ..)
		prev = ('', '')
		for tag in tags:
			if tag[0] == prev[0]:
				self._tags[prev[1]] += self._tags[tag[1]]
				self._tags.pop(tag[1])
			else:
				prev = tag

		# Set view
		self._eval_filter() # keep current selection
		self.expand_all()

	def _clear(self):
		self.real_model.clear() # flush
		self._tags = {}
		self._labels = {}

	def _append_tasks(self, task, iter, path_cache):
		task_label_re = _task_labels_re(self.task_labels)
		today = datetime.date.today()
		today_str = str(today)

		if self.flatlist:
			assert task is None
			tasks = self.tasksview.list_open_tasks_flatlist()
		else:
			tasks = self.tasksview.list_open_tasks(task)

		for prio_sort_int, row in enumerate(tasks):
			if row['source'] not in path_cache:
				# TODO: add pagename to list_open_tasks query - need new index
				path = self.tasksview.get_path(row)
				if path is None:
					# Be robust for glitches - filter these out
					continue
				else:
					path_cache[row['source']] = path

			path = path_cache[row['source']]

			# Update labels
			for label in task_label_re.findall(row['description']):
				self._labels[label] = self._labels.get(label, 0) + 1

			# Update tag count
			tags = [t for t in row['tags'].split(',') if t]
			if self.tag_by_page:
				tags = tags + path.parts

			if tags:
				for tag in tags:
					self._tags[tag] = self._tags.get(tag, 0) + 1
			else:
				self._tags[_NO_TAGS] = self._tags.get(_NO_TAGS, 0) + 1

			lowertags = [t.lower() for t in tags]
			actionable = not any(t in lowertags for t in self.nonactionable_tags)

			# Format label for "prio" column
			if row['start'] > today_str:
				actionable = False
				y, m, d = row['start'].split('-')
				td = datetime.date(int(y), int(m), int(d)) - today
				prio_sort_label = '>' + days_to_str(td.days)
				if row['prio'] > 0:
					prio_sort_label += ' ' + '!' * min(row['prio'], 3)
			elif row['due'] < _MAX_DUE_DATE:
				y, m, d = row['due'].split('-')
				td = datetime.date(int(y), int(m), int(d)) - today
				prio_sort_label = \
					'!' * min(row['prio'], 3) + ' ' if row['prio'] > 0 else ''
				if td.days < 0:
						prio_sort_label += '<b><u>OD</u></b>' # over due
				elif td.days == 0:
						prio_sort_label += '<u>TD</u>' # today
				else:
						prio_sort_label += days_to_str(td.days)
			else:
				prio_sort_label = '!' * min(row['prio'], 3)

			# Format description
			desc = _date_re.sub('', row['description'])
			desc = re.sub('\s*!+\s*', ' ', desc) # get rid of exclamation marks
			desc = encode_markup_text(desc)
			if actionable:
				desc = _tag_re.sub(r'<span color="#ce5c00">@\1</span>', desc) # highlight tags - same color as used in pageview
				desc = task_label_re.sub(r'<b>\1</b>', desc) # highlight labels
			else:
				desc = r'<span color="darkgrey">%s</span>' % desc

			# Insert all columns
			modelrow = [False, actionable, row['prio'], row['start'], row['due'], tags, desc, path.name, row['id'], prio_sort_int, prio_sort_label]
				# VIS_COL, ACT_COL, PRIO_COL, START_COL, DUE_COL, TAGS_COL, DESC_COL, PAGE_COL, TASKID_COL, PRIO_SORT_COL, PRIO_SORT_LABEL_COL
			modelrow[0] = self._filter_item(modelrow)
			myiter = self.real_model.append(iter, modelrow)

			if row['haschildren'] and not self.flatlist:
				self._append_tasks(row, myiter, path_cache) # recurs

	def set_filter_actionable(self, filter):
		'''Set filter state for non-actionable items
		@param filter: if C{False} all items are shown, if C{True} only actionable items
		'''
		self.filter_actionable = filter
		self._eval_filter()

	def set_flatlist(self, flatlist):
		self.flatlist = flatlist
		self.refresh()

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
			counter[0] += 1
		self.real_model.foreach(count)
		return counter[0]

	def set_tag_filter(self, tags=None, labels=None):
		if tags:
			self.tag_filter = [tag.lower() for tag in tags]
		else:
			self.tag_filter = None

		if labels:
			self.label_filter = [label.lower() for label in labels]
		else:
			self.label_filter = None

		self._eval_filter()

	def _eval_filter(self):
		#logger.debug('Filtering with labels: %s tags: %s, filter: %s', self.label_filter, self.tag_filter, self.filter)

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

		if not modelrow[self.ACT_COL] and self.filter_actionable:
			visible = False

		description = modelrow[self.DESC_COL].lower()
		pagename = modelrow[self.PAGE_COL].lower()
		tags = [t.lower() for t in modelrow[self.TAGS_COL]]

		if visible and self.label_filter:
			# Any labels need to be present
			for label in self.label_filter:
				if label in description:
					break
			else:
				visible = False # no label found

		if visible and self.tag_filter:
			# Any tag should match
			if (_NO_TAGS in self.tag_filter and not tags) \
			or any(tag in tags for tag in self.tag_filter):
				visible = True
			else:
				visible = False

		if visible and self.filter:
			# And finally the filter string should match
			# FIXME: we are matching against markup text here - may fail for some cases
			inverse, string = self.filter
			if string.startswith('@'):
				match = string[1:].lower() in [t.lower() for t in tags]
			else:
				match = string in description or string in pagename
			if (not inverse and not match) or (inverse and match):
				visible = False

		return visible

	def do_focus_in_event(self, event):
		#print ">>>", self._today, datetime.date.today()
		if self._today != datetime.date.today():
			self.refresh()

	def do_row_activated(self, path, column):
		model = self.get_model()
		page = Path(model[path][self.PAGE_COL])
		text = self._get_raw_text(model[path])

		pageview = self.opener.open_page(page)
		pageview.find(text)

	def _get_raw_text(self, task):
		id = task[self.TASKID_COL]
		row = self.tasksview.get_task(id)
		return row['description']

	def do_initialize_popup(self, menu):
		item = Gtk.MenuItem.new_with_mnemonic(_('_Copy')) # T: menu label
		item.connect('activate', self.copy_to_clipboard)
		menu.append(item)
		self.populate_popup_expand_collapse(menu)


	def _query_tooltip_cb(self, widget, x, y, keyboard_tip, tooltip):
		context = widget.get_tooltip_context(x, y, keyboard_tip)
		if not context:
			return False

		model, iter = context.model, context.iter
		if not (model and iter):
			return

		task = model[iter][self.DESC_COL]
		start = model[iter][self.START_COL]
		due = model[iter][self.DUE_COL]
		page = model[iter][self.PAGE_COL]

		today = str(datetime.date.today())

		text = [task, '\n']
		if start and start > today:
			text += ['<b>', _('Start'), ':</b> ', start, '\n'] # T: start date for task
		if due != _MAX_DUE_DATE:
			text += ['<b>', _('Due'), ':</b> ', due, '\n'] # T: due date for task

		text += ['<b>', _('Page'), ':</b> ', encode_markup_text(page)] # T: page label

		tooltip.set_markup(''.join(text))
		return True

	def copy_to_clipboard(self, *a):
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

		today = str(datetime.date.today())
		tomorrow = str(datetime.date.today() + datetime.timedelta(days=1))
		dayafter = str(datetime.date.today() + datetime.timedelta(days=2))
		for indent, prio, desc, date, page in self.get_visible_data():
			if prio >= 3:
					prio = '<td class="high">%s</td>' % prio
			elif prio == 2:
					prio = '<td class="medium">%s</td>' % prio
			elif prio == 1:
					prio = '<td class="alert">%s</td>' % prio
			else:
					prio = '<td>%s</td>' % prio

			if date and date <= today:
					date = '<td class="high">%s</td>' % date
			elif date == tomorrow:
					date = '<td class="medium">%s</td>' % date
			elif date == dayafter:
					date = '<td class="alert">%s</td>' % date
			else:
					date = '<td>%s</td>' % date

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
			desc = row[self.DESC_COL]
			date = row[self.DUE_COL]
			page = row[self.PAGE_COL]

			if date == _MAX_DUE_DATE:
				date = ''

			rows.append((indent, prio, desc, date, page))

		model = self.get_model()
		model.foreach(collect)

		return rows
