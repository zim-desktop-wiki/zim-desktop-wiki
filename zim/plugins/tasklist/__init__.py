
# Copyright 2009-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# TODO: allow more complex queries for filter, in particular (NOT tag AND tag)
#       allow multiple tabs in dialog / side pane with configurable query
#
# TODO: add an interface for this plugin in the WWW frontend
#
# TODO: commandline option
# - open dialog
# - output to stdout with configurable format
# - force update, intialization

# TODO: test coverage for the start date label (and due with "<")
# TODO: test coverage for start / due date from journal page
# TODO: test coverage for sorting in list_open_tasks
# TODO: test coverage include / exclude sections
# TODO: update manual



from zim.plugins import PluginClass, find_extension
from zim.actions import action
from zim.config import StringAllowEmpty
from zim.signals import DelayedCallback
from zim.notebook import NotebookExtension

from zim.gui.pageview import PageViewExtension
from zim.gui.widgets import RIGHT_PANE, PANE_POSITIONS

from .indexer import TasksIndexer, TasksView
from .gui import TaskListDialog, TaskListWidget


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
		('embedded', 'bool', _('Show tasklist in sidepane'), False),
			# T: preferences option
		('pane', 'choice', _('Position in the window'), RIGHT_PANE, PANE_POSITIONS),
			# T: preferences option
		('with_due', 'bool', _('Show due date in sidepane'), False),
			# T: preferences option
	)

	parser_preferences = (
		# key, type, label, default
		('all_checkboxes', 'bool', _('Consider all checkboxes as tasks'), True),
			# T: label for plugin preferences dialog
		('labels', 'string', _('Labels marking tasks'), 'FIXME, TODO', StringAllowEmpty),
			# T: label for plugin preferences dialog - labels are e.g. "FIXME", "TODO"
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

	plugin_notebook_properties = parser_preferences + (
		('nonactionable_tags', 'string', _('Tags for non-actionable tasks'), '', StringAllowEmpty),
			# T: label for plugin preferences dialog
		('tag_by_page', 'bool', _('Turn page name into tags for task items'), False),
			# T: label for plugin preferences dialog
		('use_workweek', 'bool', _('Flag tasks due on Monday or Tuesday before the weekend'), False),
			# T: label for plugin preferences dialog
	)

	hide_preferences = ('nonactionable_tags', 'tag_by_page', 'use_workweek')
		# These are deprecated, but I don't dare to remove them yet
		# so hide them in the configuration dialog instead


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
				for t in self.plugin.parser_preferences
		)

	def teardown(self):
		self.indexer.disconnect_all()
		self.notebook.index.update_iter.remove_indexer(self.indexer)
		self.index._db.executescript(TasksIndexer.TEARDOWN_SCRIPT) # XXX
		self.index.set_property(TasksIndexer.PLUGIN_NAME, None)


class TaskListPageViewExtension(PageViewExtension):

	def __init__(self, plugin, pageview):
		PageViewExtension.__init__(self, plugin, pageview)
		self._widget = None
		self.currently_with_due = plugin.preferences['with_due']
		self.on_preferences_changed(plugin.preferences)
		self.connectto(plugin.preferences, 'changed', self.on_preferences_changed)

	@action(_('Task List'), icon='zim-task-list', menuhints='view') # T: menu item
	def show_task_list(self):
		# TODO: add check + dialog for index probably_up_to_date

		index = self.pageview.notebook.index
		tasksview = TasksView.new_from_index(index)
		properties = self.plugin.notebook_properties(self.pageview.notebook)
		dialog = TaskListDialog.unique(self, self.pageview, tasksview, properties)
		dialog.present()

	def on_preferences_changed(self, preferences):
		reset_widget = self.currently_with_due != preferences['with_due']
		self.currently_with_due = preferences['with_due']
		if self._widget and (not preferences['embedded'] or reset_widget):
			self.remove_sidepane_widget(self._widget)
			self._widget = None
		if preferences['embedded'] or reset_widget:
			if self._widget is None:
				self._init_widget()
				self.add_sidepane_widget(self._widget, 'pane')
			else:
				self._widget.task_list.refresh()

	def _init_widget(self):
		index = self.pageview.notebook.index
		tasksview = TasksView.new_from_index(index)
		properties = self.plugin.notebook_properties(self.pageview.notebook)
		self._widget = TaskListWidget(tasksview, self.navigation,
			properties, self.plugin.preferences['with_due'], self.uistate)

		def on_tasklist_changed(o):
			self._widget.task_list.refresh()

		callback = DelayedCallback(10, on_tasklist_changed)
			# Don't really care about the delay, but want to
			# make it less blocking - now it is at least on idle

		nb_ext = find_extension(self.pageview.notebook, TaskListNotebookExtension)
		self.connectto(nb_ext, 'tasklist-changed', callback)
