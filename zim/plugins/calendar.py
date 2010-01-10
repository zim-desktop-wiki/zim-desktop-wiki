# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

import gobject
import gtk

import re
from datetime import date as dateclass

from zim.plugins import PluginClass
from zim.gui import Dialog
from zim.gui.widgets import Button
from zim.notebook import Path


# FUTURE: Use calendar.HTMLCalendar from core libs to render this plugin in www

# TODO implement template for calendar pages
#  - take into account month and year nodes as well


ui_xml = '''
<ui>
<menubar name='menubar'>
	<menu action='go_menu'>
		<placeholder name='plugin_items'>
			<menuitem action='go_page_today'/>
		</placeholder>
	</menu>
</menubar>
</ui>
'''

ui_xml_show_dialog = '''
<ui>
<menubar name='menubar'>
	<menu action='view_menu'>
		<placeholder name='plugin_items'>
			<menuitem action='show_calendar'/>
		</placeholder>
	</menu>
</menubar>
<toolbar name='toolbar'>
	<placeholder name='tools'>
		<toolitem action='show_calendar'/>
	</placeholder>
</toolbar>
</ui>
'''

ui_actions = (
	# name, stock id, label, accelerator, tooltip, readonly
	('go_page_today', None, _('To_day'), '<Alt>D', '', True), # T: menu item
	('show_calendar', 'zim-calendar', _('Calen_dar'),  '', 'Show calendar', True), # T: menu item
)

KEYVALS_ENTER = map(gtk.gdk.keyval_from_name, ('Return', 'KP_Enter', 'ISO_Enter'))
KEYVALS_SPACE = (gtk.gdk.unicode_to_keyval(ord(' ')),)

date_path_re = re.compile(r'^(.*:)?\d{4}:\d{2}:\d{2}$')


class CalendarPlugin(PluginClass):

	plugin_info = {
		'name': _('Calendar'), # T: plugin name
		'description': _('''\
This plugin turns one namespace into a calendar
keeping one page per day. A dialog is added with a
month view of this special namespace.

This is a core plugin shipping with zim.
'''), # T: plugin description
		'author': 'Jaap Karssenberg',
		'help': 'Plugins:Calendar',
	}

	plugin_preferences = (
		# key, type, label, default
		('embedded', 'bool', _('Show calendar in sidepane instead of as dialog'), False), # T: preferences option
		('namespace', 'namespace', _('Namespace'), ':Calendar'), # T: input label
	)

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		self.sidepane_widget = None
		self.ui_id_show_dialog = None
		self._set_template = None
		if self.ui.ui_type == 'gtk':
			self.ui.add_actions(ui_actions, self)
			self.ui.add_ui(ui_xml, self)
			self.ui.connect_after('open-notebook', self.do_open_notebook)

	def do_open_notebook(self, ui, notebook):
		self.do_preferences_changed()
		notebook.register_hook('suggest_link', self.suggest_link)

	def disconnect(self):
		self.ui.notebook.unregister_hook('suggest_link', self.suggest_link)
		if self._set_template:
			ns = self._set_template
			try:
				self.ui.notebook.namespace_properties[ns].remove('template')
			except KeyError:
				pass
		PluginClass.disconnect(self)

	def do_preferences_changed(self):
		'''Switch between calendar in the sidepane or as a dialog'''
		if self._set_template:
			ns = self._set_template
			try:
				self.ui.notebook.namespace_properties[ns].remove('template')
			except KeyError:
				pass

		if isinstance(self.preferences['namespace'], Path):
			ns = self.preferences['namespace']
			self.preferences['namespace'] = ns.name
		else:
			self.preferences.setdefault('namespace', ':Calendar')
			ns = self.ui.notebook.resolve_path(self.preferences['namespace'])

		self.ui.notebook.namespace_properties[ns]['template'] = '_Calendar'
		self._set_template = ns

		sidepane = self.ui.mainwindow.sidepane
		if self.preferences['embedded']:
			if self.ui_id_show_dialog:
				self.ui.remove_ui(self, self.ui_id_show_dialog)
				self.ui_id_show_dialog = None

			self.sidepane_widget = CalendarPluginWidget(self)
			sidepane.pack_start(self.sidepane_widget, False)
			sidepane.reorder_child(self.sidepane_widget, 0)
			self.sidepane_widget.show_all()
		else:
			if self.sidepane_widget:
				sidepane.remove(self.sidepane_widget)
				self.sidepane_widget = None

			self.ui_id_show_dialog = self.ui.add_ui(ui_xml_show_dialog, self)

	def path_from_date(self, date):
		return Path(
			self.preferences['namespace'] + ':' + date.strftime('%Y:%m:%d') )

	def path_for_month_from_date(self, date):
		return Path(
			self.preferences['namespace'] + ':' + date.strftime('%Y:%m') )

	def date_from_path(self, path):
		assert date_path_re.match(path.name), 'Not an date path: %s' % path.name
		year, month, day = path.name.rsplit(':', 3)[-3:]
		year, month, day = map(int, (year, month, day))
		return dateclass(year, month, day)

	def suggest_link(self, source, text):
		#~ if date_path_re.match(path.text):
		#~ 	return Path(text)
		if re.match(r'^\d{4}-\d{2}-\d{2}$', text):
			year, month, day = text.split('-')
			year, month, day = map(int, (year, month, day))
			date = dateclass(year, month, day)
			return self.path_from_date(date)
		# TODO other formats
		else:
			return None

	def go_page_today(self):
		today = dateclass.today()
		path = self.path_from_date(today)
		self.ui.open_page(path)

	def show_calendar(self):
		dialog = CalendarDialog.unique(self, self)
		dialog.present()

	# TODO: hook to the pageview end-of-word signal and link dates
	#       add a preference for this
	# TODO: Overload the "Insert date" dialog by adding a 'link' option


class Calendar(gtk.Calendar):
	'''Custom calendar widget class. Adds an 'activate' signal for when a
	date is selected explicitly by the user.
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'activate': (gobject.SIGNAL_RUN_LAST, None, ()),
	}

	def do_key_press_event(self, event):
		handled = gtk.Calendar.do_key_press_event(self, event)
		if handled and (event.keyval in KEYVALS_SPACE
		or event.keyval in KEYVALS_ENTER):
			self.emit('activate')
		return handled

	def do_button_press_event(self, event):
		handled = gtk.Calendar.do_button_press_event(self, event)
		if event.button == 1:
			self.emit('activate')
		return handled

	def select_date(self, date):
		'''Set selected date using a datetime oject'''
		self.select_month(date.month - 1, date.year)
		self.select_day(date.day)

	def get_date(self):
		'''Get the datetime object for the selected date'''
		year, month, day = gtk.Calendar.get_date(self)
		return dateclass(year, month + 1, day)

# Need to register classes defining gobject signals
gobject.type_register(Calendar)


class CalendarPluginWidget(gtk.VBox):

	def __init__(self, plugin):
		gtk.VBox.__init__(self)
		self.plugin = plugin

		format = _('%A %d %B %Y').replace(' 0', ' ') # T: strftime format for current date label
		label = gtk.Label(dateclass.today().strftime(str(format)))
			# str() needed for python 2.5 compatibility
		self.pack_start(label, False)

		self.calendar = Calendar()
		self.calendar.display_options(
			gtk.CALENDAR_SHOW_HEADING |
			gtk.CALENDAR_SHOW_DAY_NAMES |
			gtk.CALENDAR_SHOW_WEEK_NUMBERS )
		self.calendar.connect('activate', self.on_calendar_activate)
		self.calendar.connect('month-changed', self.on_month_changed)
		self.on_month_changed(self.calendar)
		self.pack_start(self.calendar, False)

		self.plugin.ui.connect('open-page', self.on_open_page)

	def on_calendar_activate(self, calendar):
		path = self.plugin.path_from_date( calendar.get_date() )
		if path != self.plugin.ui.page:
			self.plugin.ui.open_page(path)

	def on_month_changed(self, calendar):
		calendar.clear_marks()
		namespace = self.plugin.path_for_month_from_date( calendar.get_date() )
		for path in self.plugin.ui.notebook.index.list_pages(namespace):
			date = self.plugin.date_from_path(path)
			calendar.mark_day(date.day)

	def on_open_page(self, ui, page, path):
		try:
			date = self.plugin.date_from_path(path)
			self.calendar.select_month(date.month-1, date.year)
		except AssertionError:
			pass

	def select_date(self, date):
		self.calendar.select_date(date)
		self.on_calendar_activate(self.calendar)


class CalendarDialog(Dialog):

	def __init__(self, plugin):
		Dialog.__init__(self, plugin.ui, _('Calendar'), buttons=None) # T: dialog title
		self.set_resizable(False)
		self.plugin = plugin

		self.calendar_widget = CalendarPluginWidget(plugin)
		self.vbox.add(self.calendar_widget)

		hbox = gtk.HBox()
		self.vbox.add(hbox)
		button = Button(_('_Today'), gtk.STOCK_JUMP_TO) # T: button label
		button.connect('clicked',
			lambda o: self.calendar_widget.select_date(dateclass.today()))
		hbox.pack_end(button, False)
