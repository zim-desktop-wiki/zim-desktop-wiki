
# Copyright 2009-2024 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GdkPixbuf
from gi.repository import GObject
from gi.repository import Pango

import logging
import re

import zim.datetimetz as datetime
from zim.base.naturalsort import natural_sorted

from zim.notebook import Path
from zim.actions import toggle_action, initialize_actiongroup, PRIMARY_MODIFIER_MASK
from zim.signals import DelayedCallback, SIGNAL_AFTER, SignalHandler, ConnectorMixin
from zim.config import ConfigManager, ConfigDefinition
from zim.config.dicts import String
from zim.plugins import PluginManager, ExtensionBase, extendable
from zim.gui.widgets import \
	Dialog, WindowSidePaneWidget, InputEntry, \
	BrowserTreeView, SingleClickTreeView, ScrolledWindow, HPaned, StatusPage, \
	encode_markup_text, decode_markup_text, widget_set_css, \
	uistate_property
from zim.gui.actionextension import ActionExtensionBase, populate_toolbar_with_actions
from zim.gui.clipboard import Clipboard


logger = logging.getLogger('zim.plugins.tasklist')

from .indexer import AllTasks, ActiveTasks, InboxTasks, NextActionTasks, OpenProjectsTasks, WaitingTasks, \
	_MAX_DUE_DATE, _MIN_START_DATE, _NO_TAGS, _date_re, _tag_re, _parse_task_labels, _task_labels_re, \
	TASK_STATUS_OPEN, TASK_STATUS_CLOSED, TASK_STATUS_CANCELLED, TASK_STATUS_MIGRATED, TASK_STATUS_TRANSMIGRATED


# Selection lists
SELECTION_ALL = 'all'
SELECTION_ACTIVE = 'active'
SELECTION_INBOX = 'inbox'
SELECTION_NEXT = 'next'
SELECTION_PROJECTS = 'projects'
SELECTION_WAITING = 'waiting'

# Model Columns
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
STATUS_COL = 11
STATUS_ICON_NAME_COL = 12


class TaskStatusUIState(ConfigDefinition):
	'''Data type for selected task status list in uistate'''

	def check(self, value):
		# Valid data is sequence of integers for the TASK_STATUS_* constants
		if isinstance(value, str):
			try:
				value = [int(s) for s in value.split(',')]
			except:
				raise ValueError
		else:
			if not (
				isinstance(value, (list, tuple))
				and all(isinstance(v, int) for v in value)
			):
				raise ValueError

		if not all((v >= 0 and v <= 4) for v in value):
			# In range of TASK_STATUS_OPEN to TASK_STATUS_TRANSMIGRATED
			raise ValueError

		return value


class TaskListWidgetMixin(object):
	'''Common functions between side-pane widget and dialog'''

	SELECTION_MAP = { # Define in class to make sure translations are intialized
		SELECTION_ALL: (_('All Tasks'), AllTasks), # T: list with tasks
		SELECTION_ACTIVE: (_('Active'), ActiveTasks), # T: list with tasks
		SELECTION_INBOX: (' \u2012 ' + _('Inbox'), InboxTasks), # T: list with tasks (GTD style category)
		SELECTION_NEXT: (' \u2012 ' + _('Next Actions'), NextActionTasks), # T: list with tasks (GTD style category)
		SELECTION_PROJECTS: (' \u2012 ' + _('Projects'), OpenProjectsTasks), # T: list with tasks (GTD style category)
		SELECTION_WAITING: (_('Waiting'), WaitingTasks), # T: list with tasks (GTD style category)
	}

	taskselection_type = uistate_property('task_list', SELECTION_ALL, tuple(SELECTION_MAP.keys()))
	status = uistate_property('task_status', [TASK_STATUS_OPEN], TaskStatusUIState)

	def __init__(self, index, uistate, properties):
		self.index = index
		self.tasklisttreeview = None
		self.selection_list = None
		self.tag_list = None
		self._mbutton = None

		self.uistate = uistate
		self.uistate.setdefault('sort_column', 0)
		self.uistate.setdefault('sort_order', int(Gtk.SortType.DESCENDING))

		self.taskselection = self.SELECTION_MAP[self.taskselection_type][1].new_from_index(index)
		self.label_tag_filter = (None, None, None) # NOTE: Not taken from uistate since encoding&validation would be non-trivial

		self.connectto(properties, 'changed', self.on_properties_changed)

	def _init_selection_state(self):
		# Ensure widgets reflect selection
		state = self._get_selection_state()
		self._set_selection_state(state)

	def _get_selection_state(self):
		return (self.taskselection_type, self.status[:], self.label_tag_filter)

	def _set_selection_state(self, state):
		self.status = state[1]
		self.selection_list._select(state[0])
		self.tag_list._set_selected_labels_tags_pages(*state[2])

	def _create_tasklisttreeview(self, opener, properties):
		self.tasklisttreeview = TaskListTreeView(
			self.taskselection, opener,
			_parse_task_labels(properties['labels']),
			use_workweek=properties['use_workweek'],
			sort_column=self.uistate['sort_column'],
			sort_order=self.uistate['sort_order'],
		)
		stack = Gtk.Stack()
		for name, widget in (
			('treeview', ScrolledWindow(self.tasklisttreeview, shadow=Gtk.ShadowType.NONE)),
			('placeholder', StatusPage('task-list-closed-symbolic', _('No tasks'))), # T: placeholder label for sidepane
		):
			widget.show_all()
			stack.add_named(widget, name)

		def switch_placeholder(treeview, not_empty):
			if not_empty:
				stack.set_visible_child_name('treeview')
			else:
				stack.set_visible_child_name('placeholder')

		self.tasklisttreeview.connect('view-changed', switch_placeholder)
		stack.set_visible_child_name('treeview')

		return stack

	def _create_selection_menubutton(self, opener, properties, show_inbox_next):
		self._mbutton = Gtk.MenuButton()
		self._set_mbutton_label(self.SELECTION_MAP[SELECTION_ALL][0])
		popover = Gtk.Popover()
		self._mbutton.set_popover(popover)
		popover.add(self._create_selection_pane(properties, show_inbox_next))

		popout = Gtk.Button()
		icon = Gtk.Image.new_from_icon_name('window-pop-out-symbolic', Gtk.IconSize.SMALL_TOOLBAR)
		popout.add(icon)
		popout.set_tooltip_text(_('Show tasklist window')) # T: tooltip
		popout.set_alignment(0.5, 0.5)
		popout.set_relief(Gtk.ReliefStyle.NONE)
		popout.connect('clicked', lambda b: self._show_dialog_action(self._get_selection_state()))

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

		self.selection_list = ListSelectionView(show_inbox_next=show_inbox_next)
		self.selection_list.connect('row-activated', self.on_selection_activated)
		vbox1.add(self.selection_list)

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
		self.tasklisttreeview.update_properties(
			task_labels=task_labels,
			use_workweek=properties['use_workweek'],
		)
		self.tag_list.update_properties(
			task_labels=_parse_task_labels(properties['labels']),
			show_pages=properties['show_pages']
		)

	def reload_view(self):
		state = self._get_selection_state()
		for view in (self.tasklisttreeview, self.tag_list):
			if view is not None:
				view.refresh()
		self._set_selection_state(state)

	def on_selection_activated(self, listbox, boxrow):
		label = boxrow.get_children()[0]
		self.set_selection(label._zim_key)

	def set_selection(self, key):
		self.taskselection_type = key
		label, cls = self.SELECTION_MAP[key]
		self._set_mbutton_label(label)
		self.taskselection = cls.new_from_index(self.index)
		self.taskselection.set_status_included(*self.status)
		self.tasklisttreeview.set_taskselection(self.taskselection)
		self.tag_list.set_taskselection(self.taskselection)

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
		self.label_tag_filter = (labels, tags, pages)
		self.tasklisttreeview.set_label_tag_filter(labels, tags, pages)


class TaskListWidget(Gtk.VBox, TaskListWidgetMixin, WindowSidePaneWidget):

	title = _('Tas_ks') # T: tab label for side pane

	def __init__(self, index, opener, properties, show_inbox_next, uistate, show_dialog_action):
		GObject.GObject.__init__(self)
		TaskListWidgetMixin.__init__(self, index, uistate, properties)
		self._close_button = None
		self._show_dialog_action = show_dialog_action

		swindow = self._create_tasklisttreeview(opener, properties)
		self._header_hbox = self._create_selection_menubutton(opener, properties, show_inbox_next)
		self.pack_start(self._header_hbox, False, True, 0)
		self.pack_start(swindow, True, True, 0)

		self.tasklisttreeview.set_view_column_visible('status_icon', False) # no status toggle in this view
		self.tasklisttreeview.view_columns['task'].set_min_width(200) # don't let this column get too small

		filter_entry = self._create_filter_entry()
		self.pack_end(filter_entry, False, True, 0)

		self._init_selection_state()

	def set_embeded_closebutton(self, button):
		if self._close_button:
			self._header_hbox.remove(self._close_button)

		if button is not None:
			self._header_hbox.pack_end(button, False, True, 0)

		self._close_button = button
		return True


class TaskListWindowExtension(ActionExtensionBase):
	'''Base class for window extensions
	Actions can be defined using e.g. C{@action} decorator, see
	L{zim.actions}, and will automatically be added to the window on
	initialization.
	'''

	# TODO - should be generic base class for extending windows
	# TODO - remove actions on teardown !!!

	def __init__(self, plugin, window):
		ExtensionBase.__init__(self, plugin, window)
		self.window = window
		self.connectto(window, 'destroy')
		self._add_headerbar_actions()

	def on_destroy(self, dialog):
		self.destroy()


from zim.config import value_is_coord


@extendable(TaskListWindowExtension)
class TaskListWindow(TaskListWidgetMixin, ConnectorMixin, Gtk.Window):

	def __init__(self, notebook, index, navigation, properties, show_inbox_next, hide_on_close=True):
		Gtk.Window.__init__(self)
		self.uistate = notebook.state[self.__class__.__name__]
		defaultwindowsize=(550, 400)

		# Catching this signal prevents the window to actually be destroyed
		# when the user tries to close it. The action for close should either
		# hide or destroy the window.
		if hide_on_close:
			def do_delete_event(self, *a):
				logger.debug('Action: close tasklist window (delete-event)')
				self.save_uistate()
				self.hide()
				return True # Do not destroy - let close() handle it

			self.connect('delete-event', do_delete_event)
		else:
			self.connect('delete-event', self.save_uistate)

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

		TaskListWidgetMixin.__init__(self, index, self.uistate, properties)

		vbox = Gtk.VBox()
		self.add(vbox)

		if_prefs = ConfigManager.preferences['GtkInterface']
		# Normally would define the 'show_headerbar' pref here, but don't want
		# to overrule the definition in mainwindow. Therefore just using `get()`
		if if_prefs.get('show_headerbar', True):
			self._headerbar = Gtk.HeaderBar()
			self._headerbar.set_title(_('Tasks') + '  -  ' + notebook.name) # T: Window title for tasklist
			self._headerbar.set_show_close_button(True)
			self.set_titlebar(self._headerbar)
			self._toolbar = None
		else:
			self.set_title(_('Tasks') + '  -  ' + notebook.name) # T: Window title for tasklist
			self._headerbar = None
			self._toolbar = Gtk.Toolbar()
			vbox.pack_start(self._toolbar, False, False, 0)

			def on_extensions_changed(o, obj):
				if obj is self:
					self._update_toolbar()

			self.connectto(PluginManager, 'extensions-changed', on_extensions_changed)

		self.hpane = HPaned()
		self.uistate.setdefault('hpane_pos', 75)
		self.hpane.set_position(self.uistate['hpane_pos'])
		pane2_vbox = Gtk.VBox()
		self.hpane.pack2(pane2_vbox, resize=True)

		vbox.add(self.hpane)

		self._search_bar = Gtk.SearchBar()
		pane2_vbox.pack_start(self._search_bar, False, True, 0)
		self._filter_entry = self._create_filter_entry()
		self._filter_entry.set_size_request(400, -1) # FIXME, scale as percentage of window size / pane size ?
		self._search_bar.add(self._filter_entry)
		self._search_bar.connect_entry(self._filter_entry)
		self._filter_entry.show_all()
		self.connect('key-press-event', lambda o, e: self._search_bar.handle_event(e))
		self._search_bar.connect('notify::search-mode-enabled', lambda *a: self.show_search(active=self._search_bar.get_search_mode()))
			# make toggle button consistent when e.g. closing bar with <Escape> key binding

		swindow = self._create_tasklisttreeview(navigation, properties)
		pane2_vbox.pack_start(swindow, True, True, 0)

		self.tasklisttreeview.view_columns['task'].set_min_width(400) # don't let this column get too small

		self.hpane.pack1(self._create_selection_pane(properties, show_inbox_next, width=150), resize=False)

		self._init_count_label()
		self.tasklisttreeview.connect('view-changed', self._update_count_label)

		if self._headerbar:
			popover = self._create_menu()
			button = self._create_menu_button(popover)
			self._headerbar.pack_end(button)
			self._headerbar.pack_end(self.show_search.create_icon_button())
			self._headerbar.pack_end(self._count_label)
		else:
			assert self._toolbar is not None
			self._update_toolbar()

		self._init_selection_state()

		# Initialze actions
		initialize_actiongroup(self, 'win')

		# Hack to add Ctrl-F keybinding for the filter
		# FIXME: would prefer Window base class to handle actions out of the box
		group = Gtk.AccelGroup()
		group.connect( # <Primary><F>
			Gdk.unicode_to_keyval(ord('f')), PRIMARY_MODIFIER_MASK, Gtk.AccelFlags.VISIBLE,
			lambda *a: self.show_search() )
		self.add_accel_group(group)

	def _init_count_label(self):
		self._count_label = Gtk.Label()
		self._count_label.set_margin_start(12)
		self._count_label.set_margin_end(12)
		#context = self._count_label.get_style_context()
		#context.add_class(Gtk.STYLE_CLASS_SUBTITLE)
		model = self.tasklisttreeview.get_model()
		count = len(model) if model else 0
		self._update_count_label(None, count)

	def _update_count_label(self, view, count):
		self._count_label.set_text(_('%s shown') % str(count)) # T: number of tasks shown in tasklist window

	def _update_toolbar(self):
		for item in self._toolbar.get_children():
			self._toolbar.remove(item)

		populate_toolbar_with_actions(self._toolbar, self, include_headercontrols=True)

		space = Gtk.SeparatorToolItem()
		space.set_draw(False)
		space.set_expand(True)
		self._toolbar.insert(space, -1)

		item = Gtk.ToolItem()
		item.add(self._count_label)
		self._toolbar.insert(item, -1)

		item = self.show_search.create_tool_button(connect_button=False)
		item.set_action_name('win.show_search')
		self._toolbar.insert(item, -1)

		popover = self._create_menu()
		button = self._create_menu_toolbutton(popover)
		self._toolbar.insert(button, -1)

		self._toolbar.show_all()

	def _create_menu_button(self, popover):
		button = Gtk.MenuButton()
		button.set_direction(Gtk.ArrowType.NONE)
		button.set_popover(popover)
		button.show_all()
		return button

	def _create_menu_toolbutton(self, popover):
		button = Gtk.ToggleToolButton()
		button.set_icon_name('open-menu-symbolic')
		popover.set_relative_to(button)
		def toggle_popover(button):
			if button.get_active():
				popover.popup()
			else:
				popover.popdown()
		button.connect('toggled', toggle_popover)
		popover.connect('closed', lambda o: button.set_active(False))
		return button

	def _create_menu(self):
		popover = Gtk.Popover()

		vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
		for key, label in (
			(TASK_STATUS_OPEN, _('Show open tasks')), # T: selection menu option
			(TASK_STATUS_CLOSED, _('Show closed tasks')), # T: selection menu option
			(TASK_STATUS_CANCELLED, _('Show cancelled tasks')), # T: selection menu option
			(TASK_STATUS_MIGRATED, _('Show migrated tasks')), # T: selection menu option
			(TASK_STATUS_TRANSMIGRATED, _('Show trans-migrated tasks')) # T: selection menu option
		):
			checkbutton = Gtk.CheckButton.new_with_label(label)
			checkbutton.set_active(key in self.status)
			checkbutton.connect('toggled', self.on_status_checkbox_toggled, key)
			vbox.add(checkbutton)

		popover.add(vbox)
		vbox.show_all()
		return popover

	def on_status_checkbox_toggled(self, checkbox, key):
		self.status = [s for s in self.status if s != key]
		if checkbox.get_active():
			self.status.append(key)
		self.taskselection.set_status_included(*self.status)
		self.tasklisttreeview.refresh()
		self.tag_list.refresh()

	def present(self):
		Gtk.Window.present(self)
		self.reload_view() # Might be out of date when we are hidden

	def reload_view(self):
		# Overloaded to only run what visible, force refresh on present() above
		state = self._get_selection_state()
		for view in (self.tasklisttreeview, self.tag_list):
			if view is not None and view.is_visible():
				view.refresh()
		self._set_selection_state(state)

	def save_uistate(self, *a):
		self.uistate['hpane_pos'] = self.hpane.get_position()

		for column in self.tasklisttreeview.get_columns():
			if column.get_sort_indicator():
				self.uistate['sort_column'] = column.get_sort_column_id()
				self.uistate['sort_order'] = int(column.get_sort_order())
				break
		else:
			# if it is unsorted, just use the defaults
			self.uistate['sort_column'] = PRIO_COL
			self.uistate['sort_order'] = Gtk.SortType.ASCENDING

		try:
			x, y = self.get_position()
			self.uistate['_windowpos'] = (x, y)
			w, h = self.get_size()
			self.uistate['windowsize'] = (w, h)
		except:
			logger.exception('Exception in save_uistate')

	@toggle_action(_('_Search'), '<Primary>F', verb_icon='edit-find-symbolic') # T: Menu item
	def show_search(self, show):
		self._search_bar.set_search_mode(show)



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
			label.set_markup('<b>%s</b>' % _('Lists')) # T: Header for list selection in tasklist window
			row.set_header(label)

	def _select(self, key):
		for row in self.get_children():
			if row.get_child()._zim_key == key:
				self.select_row(row)
				self.emit('row-activated', row)
				return
		else:
			raise AssertionError("Could not find key: %s" % key)


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

	def _set_selected_labels_tags_pages(self, labels, tags, pages):
		selection = {'label': labels, 'tag': tags, 'page': pages}
		for row in self.get_children():
			myselection = selection[row._zim_type]
			if myselection is not None and row._zim_label in myselection:
					self.select_row(row)
			else:
				self.unselect_row(row)

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
				row = self._create_item(_('Untagged'), count, 'tag') # T: selection of tasks without tags
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


_cal_days_to_work_days = [
	# for each weekday 5 offsets used in algo below
	# represent weekends in a 14 day period starting at given weekday
	# first number is offset for weekend at start of the range
	# next 4 numbers are weekend days in the range
	None,
	[0, 5, 6, 12, 13], # monday
	[0, 4, 5, 11, 12], # tuesday
	[0, 3, 4, 10, 11], # wednesday
	[0, 2, 3,  9, 10], # thursday
	[0, 1, 2,  8,  9], # friday
	[1, 5, 6, 12, 13], # saturday
	[0, 6, 7, 13, 14], # sunday
]


def days_to_str(days, use_workweek, weekday):
	# days are calendar days, not working days
	# convert to working days if period is less than 2 weeks
	if days >= 300:
		return '%iy' % round(float(days) / 365) # round up to 1 year from ~10 months
	elif days >= 28:
		return '%im' % round(float(days) / 30) # round up to 1 year from 4 calendar weeks
	elif days >= 14:
		return '%iw' % round(float(days) / 7)
	elif use_workweek:
		offsets = _cal_days_to_work_days[weekday]
		days -= offsets[0]
		if days >= offsets[4]:
			days -= 4
		elif days == offsets[3]:
			days -= 3
		elif days >= offsets[2]:
			days -= 2
		elif days == offsets[1]:
			days -= 1
		return '%id' % days
	else:
		return '%id' % days


class TaskListTreeView(BrowserTreeView):

	# These default values are overwritten based on "styles.conf" configuration
	HIGH_COLOR = '#ef2929' # red (derived from Tango style guide)
	MEDIUM_COLOR = '#f57900' # orange
	ALERT_COLOR = '#fce947' # yellow

	PRIO_COLORS = [None, ALERT_COLOR, MEDIUM_COLOR, HIGH_COLOR] # index 0..3

	TAG_TEXT_COLOR = '#ce5c00'
	INACTIVE_TEXT_COLOR = 'darkgrey'

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'view-changed': (GObject.SignalFlags.RUN_LAST, None, (object,)),
	}

	def __init__(self,
		taskselection, opener,
		task_labels,
		use_workweek=False,
		sort_column=PRIO_COL, sort_order=Gtk.SortType.DESCENDING
	):
		self.text_style = ConfigManager.get_config_dict('style.conf')
		self.text_style['TaskList Prio High'].define({'background': String(self.HIGH_COLOR)})
		self.text_style['TaskList Prio Medium'].define({'background': String(self.MEDIUM_COLOR)})
		self.text_style['TaskList Prio Alert'].define({'background': String(self.ALERT_COLOR)})
		self.text_style['TaskList Inactive'].define({'foreground': String(self.INACTIVE_TEXT_COLOR)})
		self.text_style.connect('changed', lambda o: self.on_text_style_changed())
		self.on_text_style_changed()

		self.real_model = Gtk.TreeStore(bool, bool, int, str, str, object, str, str, int, int, str, int, str)
			# VIS_COL, ACT_COL, PRIO_COL, START_COL, DUE_COL, TAGS_COL, DESC_COL, PAGE_COL, TASKID_COL, PRIO_SORT_COL, PRIO_SORT_LABEL_COL, STATUS_COL, STATUS_ICON_NAME_COL
		model = self.real_model.filter_new()
		model.set_visible_column(VIS_COL)
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
		self.task_labels = task_labels
		self.use_workweek = use_workweek
		self._render_waiting_actionable = False
		self.view_columns = {}
		self._visible_columns = {}

		self._icon_names = {
			TASK_STATUS_OPEN: 'task-list-open-symbolic',
			TASK_STATUS_CLOSED: 'task-list-closed-symbolic',
			TASK_STATUS_CANCELLED: 'task-list-cancelled-symbolic',
			TASK_STATUS_MIGRATED: 'task-list-migrated-symbolic',
			TASK_STATUS_TRANSMIGRATED: 'task-list-transmigrated-symbolic',
		}

		# Status column
		cell_renderer = Gtk.CellRendererPixbuf()
		column = Gtk.TreeViewColumn(' ', cell_renderer)
		column.add_attribute(cell_renderer, 'icon-name', STATUS_ICON_NAME_COL)
		column.set_sort_column_id(STATUS_COL)
		self.append_column(column)
		self.view_columns['status_icon'] = column

		# Add some rendering for the Prio column
		def render_prio(col, cell, model, i, data):
			text = model.get_value(i, PRIO_SORT_LABEL_COL)
			if not model.get_value(i, ACT_COL):
				text = '<span color="%s">%s</span>' % (self.INACTIVE_TEXT_COLOR, text)
				bg = None
			else:
				prio = model.get_value(i, PRIO_COL)
				bg = self.PRIO_COLORS[min(prio, 3)]
			cell.set_property('markup', text)
			cell.set_property('cell-background', bg)

		cell_renderer = Gtk.CellRendererText()
		column = Gtk.TreeViewColumn('!', cell_renderer)
		column.set_cell_data_func(cell_renderer, render_prio)
		column.set_sort_column_id(PRIO_SORT_COL)
		self.append_column(column)
		self.view_columns['prio'] = column

		# Rendering for task description column
		cell_renderer = Gtk.CellRendererText()
		cell_renderer.set_property('ellipsize', Pango.EllipsizeMode.END)
		column = Gtk.TreeViewColumn(_('Task'), cell_renderer, markup=DESC_COL)
				# T: Column header Task List dialog
		column.set_resizable(True)
		column.set_sort_column_id(DESC_COL)
		column.set_expand(True)
		self.append_column(column)
		self.set_expander_column(column)
		self.view_columns['task'] = column

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
		def render_date(col, cell, model, i, model_col):
			date = model.get_value(i, model_col)
			if date in (_MAX_DUE_DATE, _MIN_START_DATE):
				cell.set_property('text', '')
			else:
				if not model.get_value(i, ACT_COL):
					date = '<span color="%s">%s</span>' % (self.INACTIVE_TEXT_COLOR, date)
				cell.set_property('markup', date)
				# TODO allow strftime here

			if model_col == DUE_COL:
				if date <= today:
					color = self.HIGH_COLOR
				elif date <= tomorrow:
					color = self.MEDIUM_COLOR
				elif date <= dayafter:
					# "<=" because tomorrow and/or dayafter can be after the weekend
					color = self.ALERT_COLOR
				else:
					color = None
				cell.set_property('cell-background', color)


		for key, col, label in (
			('due', DUE_COL, _('Due')), # T: Column header Task List dialog
			('start', START_COL, _('Start')), # T: Column header Task List dialog
		):
			cell_renderer = Gtk.CellRendererText()
			column = Gtk.TreeViewColumn(label, cell_renderer)
			column.set_cell_data_func(cell_renderer, render_date, col)
			column.set_sort_column_id(col)
			self.append_column(column)
			self.view_columns[key] = column

		# Rendering for page name column
		def render_page(col, cell, model, i, data):
			text = model.get_value(i, PAGE_COL)
			text = encode_markup_text(text)
			if not model.get_value(i, ACT_COL):
				text = '<span color="%s">%s</span>' % (self.INACTIVE_TEXT_COLOR, text)
			cell.set_property('markup', text)

		cell_renderer = Gtk.CellRendererText()
		column = Gtk.TreeViewColumn(_('Page'), cell_renderer)
				# T: Column header Task List dialog
		column.set_cell_data_func(cell_renderer, render_page)
		column.set_sort_column_id(PAGE_COL)
		self.append_column(column)
		self.view_columns['page'] = column

		# Finalize
		for key in self.view_columns:
			self._visible_columns[key] = True # Default all visible
		self.refresh()

		# HACK because we can not register ourselves :S
		self.connect('row_activated', self.__class__.do_row_activated)
		self.connect('focus-in-event', self.__class__.do_focus_in_event)

	def on_text_style_changed(self, *a):
		self.HIGH_COLOR = self.text_style['TaskList Prio High']['background']
		self.MEDIUM_COLOR = self.text_style['TaskList Prio Medium']['background']
		self.ALERT_COLOR = self.text_style['TaskList Prio Alert']['background']
		self.PRIO_COLORS = [None, self.ALERT_COLOR, self.MEDIUM_COLOR, self.HIGH_COLOR] # index 0..3

		self.TAG_TEXT_COLOR = self.text_style['Tag tag'].get('foreground', self.TAG_TEXT_COLOR)
		self.INACTIVE_TEXT_COLOR = self.text_style['TaskList Inactive']['foreground']

	def get_view_column_visible(self, key):
		assert key in self.view_columns
		return self.view_columns[key].get_visible()

	def set_view_column_visible(self, key, visible):
		assert key in self.view_columns
		self._visible_columns[key] = visible
		if self.taskselection.STYLE == 'inbox' and key in ('prio', 'due'):
			pass
		else:
			self.view_columns[key].set_visible(visible)

	def set_taskselection(self, taskselection):
		self.taskselection = taskselection

		if self.taskselection.STYLE == 'inbox':
			for key in ('prio', 'due'):
				self.view_columns[key].set_visible(False)
		else:
			for key in ('prio', 'due'):
				self.view_columns[key].set_visible(self._visible_columns[key])

		if self.taskselection.STYLE == 'waiting':
			self._render_waiting_actionable = True
		else:
			self._render_waiting_actionable = False

		self.refresh()

	def update_properties(self,
		task_labels=None,
		use_workweek=None,
	):
		if task_labels is not None:
			self.task_labels = task_labels

		if use_workweek is not None:
			self.use_workweek = use_workweek

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
		weekday = today.isoweekday()

		for prio_sort_int, row in enumerate(task_iter):
			path = Path(row['name'])
			tags = [t for t in row['tags'].split(',') if t]
			lowertags = [t.lower() for t in tags]
			actionable = self._render_waiting_actionable or not row['waiting']

			# Checkbox
			status = row['status']
			status_icon_name = self._icon_names[status]

			# Format label for "prio" column
			if status != TASK_STATUS_OPEN:
				prio_sort_label = '!' * min(row['prio'], 3)
			elif row['start'] > today_str:
				actionable = False
				y, m, d = row['start'].split('-')
				td = datetime.date(int(y), int(m), int(d)) - today
				prio_sort_label = '>' + days_to_str(td.days, self.use_workweek, weekday)
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
						prio_sort_label += days_to_str(td.days, self.use_workweek, weekday)
			else:
				prio_sort_label = '!' * min(row['prio'], 3)

			# Format description
			desc = _date_re.sub('', row['description'])
			desc = re.sub(r'\s*!+\s*', ' ', desc) # get rid of exclamation marks
			desc = encode_markup_text(desc)
			if actionable:
				desc = _tag_re.sub(r'<span color="%s">@\1</span>' % self.TAG_TEXT_COLOR, desc) # highlight tags
				desc = task_label_re.sub(r'<b>\1</b>', desc) # highlight labels
			else:
				desc = '<span color="%s">%s</span>' % (self.INACTIVE_TEXT_COLOR, desc)

			# Insert all columns
			modelrow = [False, actionable, row['prio'], row['start'], row['due'], tags, desc, path.name, row['id'], prio_sort_int, prio_sort_label, status, status_icon_name]
				# VIS_COL, ACT_COL, PRIO_COL, START_COL, DUE_COL, TAGS_COL, DESC_COL, PAGE_COL, TASKID_COL, PRIO_SORT_COL, PRIO_SORT_LABEL_COL, STATUS_COL, STATUS_ICON_NAME_COL
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
		if any((self.filter, self.tag_filter, self.label_filter, self.page_filter)):
			def filter(model, path, iter):
				visible = self._filter_item(model[iter])
				model[iter][VIS_COL] = visible
				if visible:
					parent = model.iter_parent(iter)
					while parent:
						model[parent][VIS_COL] = visible
						parent = model.iter_parent(parent)
		else:
			def filter(model, path, iter):
				model[iter][VIS_COL] = True

		self.real_model.foreach(filter)
		model = self.get_model()
		count = len(model) if model else 0
		self.emit('view-changed', count)
		self.expand_all()

	def _filter_item(self, modelrow):
		# This method filters case insensitive because both filters and
		# text are first converted to lower case text.
		visible = True

		pagename = modelrow[PAGE_COL].lower()
		description = modelrow[DESC_COL].lower()
		tags = [t.lower() for t in modelrow[TAGS_COL]]


		if visible and self.page_filter:
			pageparts = modelrow[PAGE_COL].split(':')
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
		page = Path(model[path][PAGE_COL])
		text = self._get_raw_text(model[path])

		pageview = self.opener.open_page(page)
		pageview.find(text)

	def _get_raw_text(self, task):
		id = task[TASKID_COL]
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

		task = model[iter][DESC_COL]
		start = model[iter][START_COL]
		due = model[iter][DUE_COL]
		page = model[iter][PAGE_COL]

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
		for indent, prio, desc, due_date, start_date, page in self.get_visible_data():
			prio = str(prio)
			desc = decode_markup_text(desc)
			desc = '"' + desc.replace('"', '""') + '"'
			text += ",".join((prio, desc, due_date, start_date, page)) + "\n"
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
<tr><th>Prio</th><th>Task</th><th>Due</th><th>Start</th><th>Page</th></tr>
''' % (self.HIGH_COLOR, self.MEDIUM_COLOR, self.ALERT_COLOR)

		today = str(datetime.date.today())
		tomorrow = str(datetime.date.today() + datetime.timedelta(days=1))
		dayafter = str(datetime.date.today() + datetime.timedelta(days=2))
		for indent, prio, desc, due_date, start_date, page in self.get_visible_data():
			if prio >= 3:
					prio = '<td class="high">%s</td>' % prio
			elif prio == 2:
					prio = '<td class="medium">%s</td>' % prio
			elif prio == 1:
					prio = '<td class="alert">%s</td>' % prio
			else:
					prio = '<td>%s</td>' % prio

			if due_date and due_date <= today:
					due_date = '<td class="high">%s</td>' % due_date
			elif due_date == tomorrow:
					due_date = '<td class="medium">%s</td>' % due_date
			elif due_date == dayafter:
					due_date = '<td class="alert">%s</td>' % due_date
			else:
					due_date = '<td>%s</td>' % due_date

			start_date = '<td>%s</td>' % start_date

			desc = '<td>%s%s</td>' % ('&nbsp;' * (4 * indent), desc)
			page = '<td>%s</td>' % page

			html += '<tr>' + prio + desc + due_date + start_date + page + '</tr>\n'

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
			prio = row[PRIO_COL]
			desc = row[DESC_COL]
			due_date = row[DUE_COL]
			start_date = row[START_COL]
			page = row[PAGE_COL]

			if due_date == _MAX_DUE_DATE:
				due_date = ''

			if start_date == _MIN_START_DATE:
				start_date = ''

			rows.append((indent, prio, desc, due_date, start_date, page))

		model = self.get_model()
		model.foreach(collect)

		return rows
