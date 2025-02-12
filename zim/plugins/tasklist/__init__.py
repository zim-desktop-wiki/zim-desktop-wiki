
# Copyright 2009-2020 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# TODO: allow more complex queries for filter, in particular (NOT tag AND tag)
#       allow multiple tabs in dialog / side pane with configurable query
#
# TODO: add an interface for this plugin in the WWW frontend
#
# TODO: commandline option
# - open dialog
# - output to stdout with configurable format
# - force update, intialization


from zim.plugins import PluginClass, find_extension
from zim.actions import action
from zim.config import StringAllowEmpty
from zim.signals import DelayedCallback
from zim.notebook import NotebookExtension

from zim.gui.notebookview import NotebookViewExtension
from zim.gui.widgets import RIGHT_PANE, PANE_POSITIONS

from .indexer import TasksIndexer
from .gui import TaskListWindow, TaskListWidget


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
		('button_in_headerbar', 'bool', _('Show tasklist button in headerbar'), True),
			# T: preferences option
		('show_inbox_next', 'bool', _('Show "GTD-style" inbox & next actions lists'), False),
			# T: preferences option - "GTD" means "Getting Things Done" methodology
		('embedded', 'bool', _('Show tasklist in sidepane'), False),
			# T: preferences option
		('pane', 'choice', _('Position in the window'), RIGHT_PANE, PANE_POSITIONS),
			# T: preferences option
		('show_due_date_in_pane', 'bool', _('Show due date in sidepane'), False),
			# T: preferences option
		('show_start_date_in_pane', 'bool', _('Show start date in sidepane'), False),
			# T: preferences option
		('show_page_col_in_pane', 'bool', _('Show page column in the sidepane'), False),
			# T: preferences option
	)

	parser_properties = (
		# key, type, label, default
		('all_checkboxes', 'bool', _('Consider all checkboxes as tasks'), True),
			# T: label for plugin preferences dialog
		('labels', 'string', _('Labels marking tasks'), 'FIXME, TODO', StringAllowEmpty),
			# T: label for plugin preferences dialog - labels are e.g. "FIXME", "TODO"
		('waiting_labels', 'string', _('Labels for "waiting" tasks'), 'Waiting, Planned', StringAllowEmpty),
			# T: label for plugin preferences dialog - labels are e.g. "Waiting", "Planned"
		('nonactionable_tags', 'string', _('Tags for "waiting" tasks'), '@waiting, @planned', StringAllowEmpty),
			# T: label for plugin preferences dialog - tags are e.g. "@waiting", "@planned"
		('integrate_with_journal', 'choice', _('Use date from journal pages'), 'start', ( # T: label for preference with multiple options
			('none', _('do not use')),        # T: choice for "Use date from journal pages"
			('start', _('as start date for tasks')),  # T: choice for "Use date from journal pages"
			('due', _('as due date for tasks'))       # T: choice for "Use date from journal pages"
		)),
		('included_subtrees', 'string', _('Section(s) to index'), '', StringAllowEmpty),
			# T: Notebook sections to search for tasks - default is the whole tree (empty string means everything)
		('excluded_subtrees', 'string', _('Section(s) to ignore'), '', StringAllowEmpty),
			# T: Notebook sections to exclude when searching for tasks - default is none
	)

	view_properties = (
		('show_pages', 'bool', _('Show page names in selection pane'), True),
			# T: label for plugin preferences dialog
		('use_workweek', 'bool', _('Don\'t count Saturday and Sunday as working days'), False),
			# T: label for plugin preferences dialog
	)

	plugin_notebook_properties = parser_properties + view_properties


class TaskListNotebookExtension(NotebookExtension):

	__signals__ = {
		'tasklist-changed': (None, None, ()),
	}

	def __init__(self, plugin, notebook):
		NotebookExtension.__init__(self, plugin, notebook)

		self.properties = self.plugin.notebook_properties(notebook)
		self._parser_key = self._get_parser_key()

		self.index = notebook.index
		if self.index.get_property(TasksIndexer.PLUGIN_NAME) != TasksIndexer.PLUGIN_DB_FORMAT:
			self.index._db.executescript(TasksIndexer.TEARDOWN_SCRIPT) # XXX
			self.index.flag_reindex()

		self.indexer = None
		self._setup_indexer(self.index, self.index.update_iter)
		self.connectto(self.index, 'new-update-iter', self._setup_indexer)

		self.connectto(self.properties, 'changed', self.on_properties_changed)

	def _setup_indexer(self, index, update_iter):
		if self.indexer is not None:
			self.disconnect_from(self.indexer)
			self.indexer.disconnect_all()

		self.indexer = TasksIndexer.new_from_index(index, self.properties)
		update_iter.add_indexer(self.indexer)
		self.connectto(self.indexer, 'tasklist-changed')

	def on_properties_changed(self, properties):
		# Need to construct new parser, re-index pages
		if self._parser_key != self._get_parser_key():
			self._parser_key = self._get_parser_key()

			self.disconnect_from(self.indexer)
			self.indexer.disconnect_all()
			self.indexer = TasksIndexer.new_from_index(self.index, properties)
			self.index.flag_reindex()
			self.connectto(self.indexer, 'tasklist-changed')

	def on_tasklist_changed(self, indexer):
		self.emit('tasklist-changed')

	def _get_parser_key(self):
		return tuple(
			self.properties[t[0]]
				for t in self.plugin.parser_properties
		)

	def teardown(self):
		self.indexer.disconnect_all()
		self.notebook.index.update_iter.remove_indexer(self.indexer)
		self.index._db.executescript(TasksIndexer.TEARDOWN_SCRIPT) # XXX
		self.index.set_property(TasksIndexer.PLUGIN_NAME, None)


class TaskListNotebookViewExtension(NotebookViewExtension):

	def __init__(self, plugin, pageview):
		NotebookViewExtension.__init__(self, plugin, pageview)
		self._task_list_window = None
		self._widget = None
		self._widget_state = (
			plugin.preferences['show_inbox_next'],
		)
		self.on_preferences_changed(plugin.preferences)
		self.connectto(plugin.preferences, 'changed', self.on_preferences_changed)

	@action(_('Task List'), icon='task-list-symbolic', menuhints='view:headerbar') # T: menu item
	def show_task_list(self):
		# This action keeps a ref to present unique window. However using the
		# "popout" action from the side pane can create multiple windows by
		# directly calling ``_show_task_window()``

		# TODO: add check + dialog for index probably_up_to_date

		if self._task_list_window is None:
			self._task_list_window = self._show_task_window(selection_state=None, hide_on_close=True)
		else:
			self._task_list_window.present()

	def _show_task_window(self, selection_state, hide_on_close=False):
			notebook = self.pageview.notebook
			index = self.pageview.notebook.index
			navigation = self.pageview.navigation
			properties = self.plugin.notebook_properties(self.pageview.notebook)
			window = TaskListWindow(notebook, index, navigation, properties, self.plugin.preferences['show_inbox_next'], hide_on_close=True)
			window.connect_after('destroy', self._drop_task_list_window_ref)
			if selection_state:
				window._set_selection_state(selection_state)
			self._connect_tasklist_changed(window)
			window.show_all()
			return window

	def _drop_task_list_window_ref(self, *a):
		self._task_list_window = None

	def on_preferences_changed(self, preferences):
		if self._task_list_window:
			self._task_list_window.destroy() # make sure it gets refreshed with new settings

		if not preferences['embedded']:
			if self._widget:
				self.remove_sidepane_widget(self._widget)
				self._widget = None
		else:
			if self._widget and self._widget_state != (
				preferences['show_inbox_next'],
			):
				self.remove_sidepane_widget(self._widget)
				self._widget = None

			if not self._widget:
				self._init_widget()
				self.add_sidepane_widget(self._widget, 'pane')
			else:
				self._widget.reload_view()

			self._widget.tasklisttreeview.set_view_column_visible('due', preferences['show_due_date_in_pane'])
			self._widget.tasklisttreeview.set_view_column_visible('start', preferences['show_start_date_in_pane'])
			self._widget.tasklisttreeview.set_view_column_visible('page', preferences['show_page_col_in_pane'])

		self.set_action_in_headerbar(self.show_task_list, preferences['button_in_headerbar'])

	def _init_widget(self):
		index = self.pageview.notebook.index
		properties = self.plugin.notebook_properties(self.pageview.notebook)
		self._widget = TaskListWidget(index, self.navigation,
			properties, self.plugin.preferences['show_inbox_next'], self.uistate,
			self._show_task_window)
		self._widget_state = (
			self.plugin.preferences['show_inbox_next'],
		)
		self._connect_tasklist_changed(self._widget)

	def _connect_tasklist_changed(self, widget):
		callback = DelayedCallback(10, lambda o: widget.reload_view())
			# Don't really care about the delay, but want to
			# make it less blocking - now it is at least on idle
		nb_ext = find_extension(self.pageview.notebook, TaskListNotebookExtension)
		widget.connectto(nb_ext, 'tasklist-changed', callback)
