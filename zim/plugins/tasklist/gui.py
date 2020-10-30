
# Copyright 2009-2020 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GObject
from gi.repository import Pango

import logging
import re

import zim.datetimetz as datetime
from zim.utils import natural_sorted

from zim.notebook import Path
from zim.gui.widgets import \
	Dialog, WindowSidePaneWidget, InputEntry, \
	BrowserTreeView, SingleClickTreeView, ScrolledWindow, HPaned, \
	encode_markup_text, decode_markup_text, widget_set_css
from zim.gui.clipboard import Clipboard
from zim.signals import DelayedCallback, SIGNAL_AFTER, SignalHandler, ConnectorMixin
from zim.plugins import ExtensionBase, extendable

logger = logging.getLogger('zim.plugins.tasklist')

from .indexer import AllTasks, ActiveTasks, InboxTasks, NextActionTasks, OpenProjectsTasks, WaitingTasks, \
	_MAX_DUE_DATE, _NO_TAGS, _date_re, _tag_re, _parse_task_labels, _task_labels_re, \
	TASK_STATUS_OPEN, TASK_STATUS_CLOSED, TASK_STATUS_CANCELLED, TASK_STATUS_MIGRATED


SELECTION_ALL = 'all'
SELECTION_ACTIVE = 'active'
SELECTION_INBOX = 'inbox'
SELECTION_NEXT = 'next'
SELECTION_PROJECTS = 'projects'
SELECTION_WAITING = 'waiting'


class TaskListWidgetMixin(object):
	'''Common functions between side-pane widget and dialog'''

	SELECTION_MAP = { # Define in class to make sure translations are intialized
		SELECTION_ALL: (_('All Tasks'), AllTasks),
		SELECTION_ACTIVE: (_('Active'), ActiveTasks),
		SELECTION_INBOX: (' \u2012 ' + _('Inbox'), InboxTasks),
		SELECTION_NEXT: (' \u2012 ' + _('Next Actions'), NextActionTasks),
		SELECTION_PROJECTS: (' \u2012 ' + _('Projects'), OpenProjectsTasks),
		SELECTION_WAITING: (_('Waiting'), WaitingTasks),
	}

	def __init__(self, index, uistate, properties):
		self.index = index
		self.taskselection = AllTasks.new_from_index(index)
		self.status = [TASK_STATUS_OPEN]

		self.tasklisttreeview = None
		self.tag_list = None
		self._mbutton = None

		self.uistate = uistate
		self.uistate.setdefault('sort_column', 0)
		self.uistate.setdefault('sort_order', int(Gtk.SortType.DESCENDING))

		self.connectto(properties, 'changed', self.on_properties_changed)

	def _create_tasklisttreeview(self, opener, properties, column_layout):
		self.tasklisttreeview = TaskListTreeView(
			self.taskselection, opener,
			_parse_task_labels(properties['labels']),
			nonactionable_tags=_parse_task_labels(properties['nonactionable_tags']),
			use_workweek=properties['use_workweek'],
			sort_column=self.uistate['sort_column'],
			sort_order=self.uistate['sort_order'],
			column_layout=column_layout,
		)
		return ScrolledWindow(self.tasklisttreeview)

	def _create_selection_menubutton(self, opener, properties, show_inbox_next):
		self._mbutton = Gtk.MenuButton()
		self._set_mbutton_label(self.SELECTION_MAP[SELECTION_ALL][0])
		popover = Gtk.Popover()
		self._mbutton.set_popover(popover)
		popover.add(self._create_selection_pane(properties, show_inbox_next))

		popout = Gtk.Button()
		icon = Gtk.Image.new_from_icon_name('window-pop-out-symbolic', Gtk.IconSize.SMALL_TOOLBAR)
		popout.add(icon)
		popout.set_tooltip_text(_('Show tasklist window'))
		popout.set_alignment(0.5, 0.5)
		popout.set_relief(Gtk.ReliefStyle.NONE)
		popout.connect('clicked', lambda b: self._show_dialog_action())

		hbox = Gtk.HBox()
		hbox.set_border_width(3)
		hbox.set_spacing(5)
		hbox.pack_start(self._mbutton, True, True, 0)
		hbox.pack_start(popout, False, True, 0)

		return hbox

	def _create_selection_pane(self, properties, show_inbox_next, width=300):
		vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
		vbox1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
		vbox1.set_border_width(5) # Else scrollbar overlays numbers

		selectionlist = ListSelectionView(show_inbox_next=show_inbox_next)
		selectionlist.connect('row-activated', self.on_selection_activated)
		vbox1.add(selectionlist)

		self.tag_list = LabelAndTagView(self.taskselection, self, _parse_task_labels(properties['labels']), properties['show_pages'])
		vbox1.add(self.tag_list)

		swindow = ScrolledWindow(vbox1, shadow=Gtk.ShadowType.NONE)
		swindow.set_size_request(width, 500)
		vbox.pack_start(swindow, True, True, 0)
		vbox.pack_end(self._create_clear_tags_button(), False, False, 0)
		vbox.show_all()
		return vbox

	def _create_clear_tags_button(self):
		button = Gtk.Button('Clear selection')
		button.connect('clicked', lambda o: self.tag_list.unselect_all())

		def update_button(tag_list):
			selected = tag_list.get_selected_rows()
			button.set_sensitive(bool(selected))

		update_button(self.tag_list)
		self.tag_list.connect('selected-rows-changed', update_button)
		return button

	def _create_filter_entry(self):
		filter_entry = InputEntry(placeholder_text=_('Filter tasks')) # T: label for filtering/searching tasks
		filter_entry.set_icon_to_clear()
		filter_cb = DelayedCallback(500,
			lambda o: self.on_filter_changed(filter_entry.get_text()))
		filter_entry.connect('changed', filter_cb)
		return filter_entry

	def on_filter_changed(self, text):
		self.tasklisttreeview.set_filter(text)

	def on_properties_changed(self, properties):
		task_labels = _parse_task_labels(properties['labels'])
		nonactionable_tags = _parse_task_labels(properties['nonactionable_tags'])
		self.tasklisttreeview.update_properties(
			task_labels=task_labels,
			nonactionable_tags=nonactionable_tags,
			use_workweek=properties['use_workweek'],
		)
		self.tag_list.update_properties(
			task_labels=_parse_task_labels(properties['labels']),
			show_pages=properties['show_pages']
		)

	def reload_view(self):
		for view in (self.tasklisttreeview, self.tag_list):
			if view is not None:
				view.refresh()

	def on_selection_activated(self, listbox, boxrow):
		label = boxrow.get_children()[0]
		self.set_selection(label._zim_key)

	def set_selection(self, key):
		label, cls = self.SELECTION_MAP[key]
		self._set_mbutton_label(label)
		taskselection = cls.new_from_index(self.index)
		taskselection.set_status_included(*self.status)

		if key == SELECTION_INBOX:
			style = TaskListTreeView.STYLE_INBOX
		elif key == SELECTION_WAITING:
			style = TaskListTreeView.STYLE_WAITING
		else:
			style = TaskListTreeView.STYLE_DEFAULT

		self.tasklisttreeview.set_taskselection(taskselection, style)
		self.tag_list.set_taskselection(taskselection)

	def _set_mbutton_label(self, text):
		if self._mbutton is None:
			return

		child = self._mbutton.get_children()[0]
		self._mbutton.remove(child)

		hbox = Gtk.HBox()
		label = Gtk.Label(text)
		label.set_alignment(0.1, 0.5)
		hbox.add(label)
		hbox.pack_end(Gtk.Image.new_from_icon_name('pan-down-symbolic', Gtk.IconSize.MENU), False, False, 0)
		hbox.show_all()
		self._mbutton.add(hbox)

	def set_label_tag_filter(self, labels, tags, pages):
		self.tasklisttreeview.set_label_tag_filter(labels, tags, pages)


class TaskListWidget(Gtk.VBox, TaskListWidgetMixin, WindowSidePaneWidget):

	title = _('Tas_ks') # T: tab label for side pane

	def __init__(self, index, opener, properties, show_due_date, show_inbox_next, uistate, show_dialog_action):
		GObject.GObject.__init__(self)
		TaskListWidgetMixin.__init__(self, index, uistate, properties)
		self._close_button = None
		self._show_dialog_action = show_dialog_action

		column_layout=TaskListTreeView.COMPACT_COLUMN_LAYOUT_WITH_DUE \
			if show_due_date else TaskListTreeView.COMPACT_COLUMN_LAYOUT

		swindow = self._create_tasklisttreeview(opener, properties, column_layout)
		self._header_hbox = self._create_selection_menubutton(opener, properties, show_inbox_next)
		self.pack_start(self._header_hbox, False, True, 0)
		self.pack_start(swindow, True, True, 0)

		filter_entry = self._create_filter_entry()
		self.pack_end(filter_entry, False, True, 0)

	def set_embeded_closebutton(self, button):
		if self._close_button:
			self._header_hbox.remove(self._close_button)

		if button is not None:
			self._header_hbox.pack_end(button, False, True, 0)

		self._close_button = button
		return True

from zim.actions import get_actions, RadioActionMethod
class TaskListWindowExtension(ExtensionBase):
	'''Base class for window extensions
	Actions can be defined using e.g. C{@action} decorator, see
	L{zim.actions}, and will automatically be added to the window on
	initialization.
	'''

	# TODO - remove actions on teardown !!!

	def __init__(self, plugin, window):
		ExtensionBase.__init__(self, plugin, window)
		self.window = window
		self.connectto(window, 'destroy')

		for name, action in get_actions(self):
			self.add_action(action)

	def on_destroy(self, dialog):
		self.destroy()

	def add_action(self, action):
		if isinstance(action, RadioActionMethod):
			raise NotImplementedError

		if 'headerstart' in action.menuhints:
			button = action.create_button()
			headerbar = self.window.get_titlebar()
			headerbar.pack_start(button)
			button.show_all()
		else:
			raise NotImplementedError


@extendable(TaskListWindowExtension)
class TaskListWindow(TaskListWidgetMixin, ConnectorMixin, Gtk.Window):

	def __init__(self, notebook, index, navigation, properties, show_inbox_next):
		Gtk.Window.__init__(self)
		self.uistate = notebook.state[self.__class__.__name__]
		#Dialog.__init__(self, parent, _('Task List'), # T: dialog title
		#	buttons=Gtk.ButtonsType.CLOSE, help=':Plugins:Task List',
		defaultwindowsize=(550, 400)
		from zim.config import value_is_coord

		# note: _windowpos is defined with a leading "_" so it is not
		# persistent across instances, this is intentional to avoid
		# e.g. messy placement for seldom used dialogs
		self.uistate.setdefault('_windowpos', None, check=value_is_coord)
		if self.uistate['_windowpos'] is not None:
			x, y = self.uistate['_windowpos']
			self.move(x, y)

		self.uistate.setdefault('windowsize', defaultwindowsize, check=value_is_coord)
		if self.uistate['windowsize'] is not None:
			w, h = self.uistate['windowsize']
			self.set_default_size(w, h)

		self.connect('delete-event', self.save_uistate)

		TaskListWidgetMixin.__init__(self, index, self.uistate, properties)

		headerbar = Gtk.HeaderBar()
		headerbar.set_title(_('Tasks') + '  -  ' + notebook.name)
		headerbar.set_show_close_button(True)
		self.set_titlebar(headerbar)

		self.hpane = HPaned()
		self.uistate.setdefault('hpane_pos', 75)
		self.hpane.set_position(self.uistate['hpane_pos'])
		pane2_vbox = Gtk.VBox()
		self.hpane.add2(pane2_vbox)

		column_layout = TaskListTreeView.RICH_COLUMN_LAYOUT
		swindow = self._create_tasklisttreeview(navigation, properties, column_layout)
		self.add(self.hpane)
		pane2_vbox.pack_start(swindow, True, True, 0)

		filter_entry = self._create_filter_entry()
		pane2_vbox.pack_start(filter_entry, False, True, 0)

		self.hpane.add1(self._create_selection_pane(properties, show_inbox_next, width=150))

		self._create_menu()

	def _create_menu(self):
		button = Gtk.MenuButton()
		button.set_direction(Gtk.ArrowType.NONE)
		popover = Gtk.Popover()
		button.set_popover(popover)

		vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
		for key, label in (
			(TASK_STATUS_OPEN, _('Show open tasks')),
			(TASK_STATUS_CLOSED, _('Show closed tasks')),
			(TASK_STATUS_CANCELLED, _('Show cancelled tasks')),
			(TASK_STATUS_MIGRATED, _('Show migrated tasks'))
		):
			checkbutton = Gtk.CheckButton.new_with_label(label)
			checkbutton.set_active(key in self.status)
			checkbutton.connect('toggled', self.on_status_checkbox_toggled, key)
			vbox.add(checkbutton)

		popover.add(vbox)
		button.show_all()
		vbox.show_all()

		#headerbar = self.get_titlebar()
		#headerbar.pack_end(button)

	def on_status_checkbox_toggled(self, checkbox, key):
		if checkbox.get_active():
			self.status.append(key)
		else:
			self.status = [s for s in self.status if s != key]
		self.taskselection.set_status_included(*self.status)
		self.tasklisttreeview.refresh()

	def save_uistate(self, *a):
		self.uistate['hpane_pos'] = self.hpane.get_position()

		for column in self.tasklisttreeview.get_columns():
			if column.get_sort_indicator():
				self.uistate['sort_column'] = column.get_sort_column_id()
				self.uistate['sort_order'] = int(column.get_sort_order())
				break
		else:
			# if it is unsorted, just use the defaults
			self.uistate['sort_column'] = TaskListTreeView.PRIO_COL
			self.uistate['sort_order'] = Gtk.SortType.ASCENDING

		try:
			x, y = self.get_position()
			self.uistate['_windowpos'] = (x, y)
			w, h = self.get_size()
			self.uistate['windowsize'] = (w, h)
		except:
			logger.exception('Exception in save_uistate')


class ListSelectionView(Gtk.ListBox):

	def __init__(self, show_inbox_next=False):
		Gtk.ListBox.__init__(self)
		if show_inbox_next:
			lists = (
				SELECTION_ALL,
				SELECTION_ACTIVE,
				SELECTION_INBOX,
				SELECTION_NEXT,
				SELECTION_PROJECTS,
				SELECTION_WAITING,
			)
		else:
			lists = (
				SELECTION_ALL,
				SELECTION_ACTIVE,
				SELECTION_WAITING,
			)

		for key in lists:
			mylabel = Gtk.Label(TaskListWidgetMixin.SELECTION_MAP[key][0])
			mylabel.set_alignment(0.0, 0.5)
			mylabel._zim_key = key
			self.insert(mylabel, -1)

		widget_set_css(self, self.__class__.__name__, 'background-color: rgba(0.0, 0.0, 0.0, 0.0)')
			# Removing white background for listbox

		self.set_header_func(self._update_header_func)

	def _update_header_func(self, row, before):
		# Only set header once on first row
		if before is None and not row.get_header():
			label = Gtk.Label()
			label.set_markup('<b>%s</b>' % _('Lists'))
			row.set_header(label)


class LabelAndTagView(Gtk.ListBox):

	def __init__(self, taskselection, tasklist_widget, task_labels, show_pages=True):
		Gtk.ListBox.__init__(self)

		self.taskselection = taskselection
		self.tasklist_widget = tasklist_widget
		self.task_labels = task_labels
		self.show_pages = show_pages

		widget_set_css(self, self.__class__.__name__, 'background-color: rgba(0.0, 0.0, 0.0, 0.0)')
			# Removing white background for listbox

		self.set_selection_mode(Gtk.SelectionMode.MULTIPLE)

		self.set_header_func(self._update_header_func)
		self.set_filter_func(self._filter_func)
		self.refresh()

	def update_properties(self, show_pages, task_labels):
		self.show_pages = show_pages
		self.task_labels = task_labels
		self.refresh()

	def do_button_release_event(self, event):
		# Implement behavior for de-selecting rows
		if event.type == Gdk.EventType.BUTTON_RELEASE \
		and event.button == 1 and not event.get_state() & (Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.META_MASK):
			x, y = list(map(int, event.get_coords()))
			row = self.get_row_at_y(y)
			if row and row.is_selected():
				self.unselect_row(row)
				return True

		return Gtk.ListBox.do_button_release_event(self, event)

	def do_selected_rows_changed(self):
		labels, tags, pages = self._get_selected_labels_tags_pages()
		self.tasklist_widget.set_label_tag_filter(labels, tags, pages)
		self.update()

	def _get_selected_labels_tags_pages(self):
		labels, tags, pages = [], [], []
		for row in self.get_selected_rows():
			if row._zim_type == 'label':
				labels.append(row._zim_label)
			elif row._zim_type == 'tag':
				tags.append(row._zim_label)
			else: # 'page'
				pages.append(row._zim_label)
		return labels, tags, pages

	def set_taskselection(self, taskselection):
		self.taskselection = taskselection
		self.refresh()

	def refresh(self):
		for child in self.get_children():
			self.remove(child)

		labels, tags, pages = self.taskselection.count_labels_and_tags_pages(self.task_labels)

		for label in self.task_labels: # Keep original order
			count = labels.get(label, 0)
			self.add(self._create_item(label, count, 'label'))

		for tag in natural_sorted(tags.keys()):
			count = tags[tag]
			if tag == _NO_TAGS:
				row = self._create_item(_('Untagged'), count, 'tag')
				row._zim_label = _NO_TAGS
				self.add(row)
			else:
				self.add(self._create_item(tag, count, 'tag'))

		if self.show_pages:
			for name in natural_sorted(pages.keys()):
				count = pages[name]
				self.add(self._create_item(name, count, 'page'))

		self.show_all()

	def update(self):
		intersect = self._get_selected_labels_tags_pages()
		labels, tags, pages = self.taskselection.count_labels_and_tags_pages(self.task_labels, intersect)
		tags = {k.lower(): c for k, c in tags.items()} # Convert to lower because potential case mismatch with labels
		for row in self.get_children():
			if row._zim_type == 'label':
				count = labels.get(row._zim_label, 0)
			elif row._zim_type == 'tag':
				count = tags.get(row._zim_label.lower(), 0)
			else: #'page'
				count = pages.get(row._zim_label, 0)
			hbox = row.get_child()
			count_label = hbox.get_children()[-1]
			count_label.set_text(str(count))
			row._zim_count = count
			row.changed()

	def _create_item(self, label, count, type):
		hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
		glabel = Gtk.Label(label)
		glabel.set_alignment(0.0, 0.5)
		glabel.set_ellipsize(Pango.EllipsizeMode.END)
		countlabel = Gtk.Label(str(count))
		countlabel.set_sensitive(False) # Lighter color compared to main label
		hbox.pack_start(glabel, True, True, 0)
		hbox.pack_start(countlabel, False, False, 0)

		row = Gtk.ListBoxRow()
		row.add(hbox)
		row._zim_type = type
		row._zim_label = label
		row._zim_count = count
		row.set_activatable(False)
		return row

	def _filter_func(self, row):
		return row._zim_count > 0

	def _update_header_func(self, row, before):
		if before is None or before._zim_type != row._zim_type:
			if not row.get_header():
				if row._zim_type == 'label':
					text = _('Labels') # T: header in selection drop down
				elif row._zim_type == 'tag':
					text = _('Tags') # T: header in selection drop down
				else: # 'page'
					text = _('Page') # T: header in selection drop down
				label = Gtk.Label()
				label.set_markup('<b>%s</b>' % text)
				row.set_header(label)
		else:
			if row.get_header():
				row.set_header(None)


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

	STYLE_DEFAULT = 0
	STYLE_INBOX = 1
	STYLE_WAITING = 2

	def __init__(self,
		taskselection, opener,
		task_labels,
		nonactionable_tags=(),
		use_workweek=False,
		column_layout=RICH_COLUMN_LAYOUT,
		sort_column=PRIO_COL, sort_order=Gtk.SortType.DESCENDING
	):
		self.real_model = Gtk.TreeStore(bool, bool, int, str, str, object, str, str, int, int, str)
			# VIS_COL, ACT_COL, PRIO_COL, START_COL, DUE_COL, TAGS_COL, DESC_COL, PAGE_COL, TASKID_COL, PRIO_SORT_COL, PRIO_SORT_LABEL_COL
		model = self.real_model.filter_new()
		model.set_visible_column(self.VIS_COL)
		model = Gtk.TreeModelSort(model)
		model.set_sort_column_id(sort_column, sort_order)
		BrowserTreeView.__init__(self, model)
		self.set_headers_visible(True)

		self.taskselection = taskselection
		self.opener = opener
		self.filter = None
		self.tag_filter = None
		self.label_filter = None
		self.page_filter = None
		self.nonactionable_tags = tuple(t.strip('@').lower() for t in nonactionable_tags)
		self.task_labels = task_labels
		self._render_waiting_actionable = False

		# Add some rendering for the Prio column
		def render_prio(col, cell, model, i, data):
			text = model.get_value(i, self.PRIO_SORT_LABEL_COL)
			if not model.get_value(i, self.ACT_COL):
				text = '<span color="darkgrey">%s</span>' % text
				bg = None
			else:
				prio = model.get_value(i, self.PRIO_COL)
				bg = COLORS[min(prio, 3)]
			cell.set_property('markup', text)
			cell.set_property('cell-background', bg)

		cell_renderer = Gtk.CellRendererText()
		column = Gtk.TreeViewColumn('!', cell_renderer)
		column.set_cell_data_func(cell_renderer, render_prio)
		column.set_sort_column_id(self.PRIO_SORT_COL)
		self.append_column(column)
		self._prio_column = column

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
				if not model.get_value(i, self.ACT_COL):
					date = '<span color="darkgrey">%s</span>' % date
				cell.set_property('markup', date)
				# TODO allow strftime here

			if date <= today:
				color = HIGH_COLOR
			elif date <= tomorrow:
				color = MEDIUM_COLOR
			elif date <= dayafter:
				# "<=" because tomorrow and/or dayafter can be after the weekend
				color = ALERT_COLOR
			else:
				color = None
			cell.set_property('cell-background', color)

		if column_layout != self.COMPACT_COLUMN_LAYOUT:
			cell_renderer = Gtk.CellRendererText()
			column = Gtk.TreeViewColumn(_('Due'), cell_renderer)
				# T: Column header Task List dialog
			column.set_cell_data_func(cell_renderer, render_date)
			column.set_sort_column_id(self.DUE_COL)
			self.append_column(column)
			self._due_column = column
		else:
			self._due_column = None

		# Rendering for page name column
		def render_page(col, cell, model, i, data):
			text = model.get_value(i, self.PAGE_COL)
			text = encode_markup_text(text)
			if not model.get_value(i, self.ACT_COL):
				text = '<span color="darkgrey">%s</span>' % text
			cell.set_property('markup', text)

		if column_layout == self.RICH_COLUMN_LAYOUT:
			cell_renderer = Gtk.CellRendererText()
			column = Gtk.TreeViewColumn(_('Page'), cell_renderer)
					# T: Column header Task List dialog
			column.set_cell_data_func(cell_renderer, render_page)
			column.set_sort_column_id(self.PAGE_COL)
			self.append_column(column)

		# Finalize
		self.refresh()

		# HACK because we can not register ourselves :S
		self.connect('row_activated', self.__class__.do_row_activated)
		self.connect('focus-in-event', self.__class__.do_focus_in_event)

	def set_taskselection(self, taskselection, style=None):
		self.taskselection = taskselection

		if style == self.STYLE_INBOX:
			self._prio_column.set_visible(False)
			if self._due_column:
				self._due_column.set_visible(False)
		else:
			self._prio_column.set_visible(True)
			if self._due_column:
				self._due_column.set_visible(True)

		if style == self.STYLE_WAITING:
			self._render_waiting_actionable = True
		else:
			self._render_waiting_actionable = False

		self.refresh()

	def update_properties(self,
		task_labels=None,
		nonactionable_tags=None,
		use_workweek=None,
	):
		if task_labels is not None:
			self.task_labels = task_labels

		if nonactionable_tags is not None:
			self.nonactionable_tags = tuple(t.strip('@').lower() for t in nonactionable_tags)

		if use_workweek is not None:
			print("TODO udate_use_workweek rendering")

		self.refresh()

	def refresh(self):
		'''Refresh the model based on index data'''
		self.real_model.clear() # flush
		self._append_tasks(self.taskselection.list_tasks(), None)

		self._today = datetime.date.today()
		self._eval_filter() # keep current selection
		self.expand_all()

	def _append_tasks(self, task_iter, parent_tree_iter):
		task_label_re = _task_labels_re(self.task_labels)
		today = datetime.date.today()
		today_str = str(today)

		for prio_sort_int, row in enumerate(task_iter):
			path = Path(row['name'])
			tags = [t for t in row['tags'].split(',') if t]
			lowertags = [t.lower() for t in tags]
			if self._render_waiting_actionable:
				actionable = not (
					any(t in lowertags for t in self.nonactionable_tags)
				)
			else:
				actionable = not (
					row['waiting'] or
					any(t in lowertags for t in self.nonactionable_tags)
				)

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
			myiter = self.real_model.append(parent_tree_iter, modelrow)

			if row['haschildren']:
				child_tasks = self.taskselection.list_tasks(row)
				self._append_tasks(child_tasks, myiter) # recurs

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

	def set_label_tag_filter(self, labels=None, tags=None, pages=None):
		if tags:
			self.tag_filter = [tag.lower() for tag in tags]
		else:
			self.tag_filter = None

		if labels:
			self.label_filter = [label.lower() for label in labels]
		else:
			self.label_filter = None

		if pages:
			self.page_filter = pages
		else:
			self.page_filter = None

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

		pagename = modelrow[self.PAGE_COL].lower()
		description = modelrow[self.DESC_COL].lower()
		tags = [t.lower() for t in modelrow[self.TAGS_COL]]


		if visible and self.page_filter:
			pageparts = modelrow[self.PAGE_COL].split(':')
			visible = any(p in pageparts for p in self.page_filter)

		if visible and self.label_filter:
			# Any labels need to be present
			# (all does not make sense as they are mutual exclusive)
			for label in self.label_filter:
				if label in description:
					break
			else:
				visible = False # no label found

		if visible and self.tag_filter:
			# All tag should match
			if (_NO_TAGS in self.tag_filter and not tags) \
				or all(tag in tags for tag in self.tag_filter):
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
		row = self.taskselection.get_task(id)
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
		<title>Tasks</title>
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

<h1>Tasks</h1>

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
