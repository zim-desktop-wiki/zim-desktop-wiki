# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import gobject
import gtk

import re
import datetime

from zim.plugins import PluginClass
from zim.gui.widgets import ui_environment, Dialog, Button
from zim.notebook import Path
from zim.templates import TemplateManager, TemplateFunction


# FUTURE: Use calendar.HTMLCalendar from core libs to render this plugin in www


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
week_path_re = re.compile(r'^(.*:)?\d{4}:Week \d{2}$')
month_path_re = re.compile(r'^(.*:)?\d{4}:\d{2}$')
year_path_re = re.compile(r'^(.*:)?\d{4}$')

def daterange_from_path(path):
	'''Determine the calendar dates mapped by a specific page
	@param path: a L{Path} object
	@returns: a 3-tuple of:
	  - the page type (one of "C{day}", "C{week}", "C{month}", or "C{year}")
	  - a C{datetime.date} object for the start date
	  - a C{datetime.date} object for the end date
	or C{None} when the page does not map a date
	'''
	if date_path_re.match(path.name):
		type = 'day'
		year, month, day = map(int, path.name.rsplit(':', 3)[-3:])
		date = datetime.date(year, month, day)
		end_date = date
	elif week_path_re.match(path.name):
		type = 'week'
		year, week = path.name.rsplit(':', 2)[-2:]
		year, week = map(int, (year, week[5:])) # Assumes "Week XX" string
		date = datetime.date(year, 1, 1)
		if week > 0:
			date = date + datetime.timedelta(week*7 - datetime.date(year, 1, 1).weekday() - 1)
			end_date = date + datetime.timedelta(6)
		else:
			end_date = date + datetime.timedelta(6 - datetime.date(year, 1, 1).weekday() - 1)
	elif month_path_re.match(path.name):
		type = 'month'
		year, month = map(int, path.name.rsplit(':', 2)[-2:])
		date = datetime.date(year, month, 1)
		if month == 12:
			end_date = datetime.date(year, 12, 31)
		else:
			end_date = datetime.date(year, month+1, 1) + datetime.timedelta(-1)
	elif year_path_re.match(path.name):
		type = 'year'
		year = int(path.name.rsplit(':', 1)[-1])
		date = datetime.date(year, 1, 1)
		end_date = datetime.date(year, 12, 31)
	else:
		return None# Not a calendar path
	return type, date, end_date


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

	global DAY, WEEK, MONTH, YEAR # Hack
	DAY = _('Day') # T: option value
	WEEK = _('Week') # T: option value
	MONTH = _('Month') # T: option value
	YEAR = _('Year') # T: option value

	plugin_preferences = (
		# key, type, label, default
		('embedded', 'bool', _('Show calendar in sidepane instead of as dialog'), False), # T: preferences option
		('granularity', 'choice', _('Use a page for each'), DAY, [DAY, WEEK, MONTH, YEAR]), # T: preferences option, values will be "Day", "Month", ...
		('namespace', 'namespace', _('Namespace'), ':Calendar'), # T: input label
	)

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		self.sidepane_widget = None # For the embedded version
		self.ui_id_show_dialog = None # For the 'show dialog' action
		self._set_template = None

	def initialize_ui(self, ui):
		if self.ui.ui_type == 'gtk':
			self.ui.add_actions(ui_actions, self)
			self.ui.add_ui(ui_xml, self)
			TemplateManager.connect('process-page', self.on_process_page_template)

	def finalize_notebook(self, notebook):
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
		self.disconnect_embedded_widget()
		PluginClass.disconnect(self)

	def connect_embedded_widget(self):
		from zim.gui.widgets import LEFT_PANE, TOP
		if not self.sidepane_widget:
			self.sidepane_widget = CalendarPluginWidget(self)
			self.sidepane_widget.show_all()
			self.ui.mainwindow.add_widget(self.sidepane_widget, LEFT_PANE, TOP)

	def disconnect_embedded_widget(self):
		if self.sidepane_widget:
			self.ui.mainwindow.remove(self.sidepane_widget)
			self.sidepane_widget.destroy()
			self.sidepane_widget = None

	def do_preferences_changed(self):
		'''Switch between calendar in the sidepane or as a dialog'''
		if self.ui.notebook:
			if self._set_template:
				ns = self._set_template
				try:
					self.ui.notebook.namespace_properties[ns].remove('template')
				except KeyError:
					pass

			if isinstance(self.preferences['namespace'], Path):
				ns = self.preferences['namespace'].name
				self.preferences['namespace'] = ns
			else:
				self.preferences.setdefault('namespace', ':Calendar')
				ns = self.preferences['namespace']
				ns = self.ui.notebook.resolve_path(ns)
				ns = ns.name
				self.preferences['namespace'] = ns

			self.ui.notebook.namespace_properties[ns]['template'] = 'Calendar'
			self._set_template = ns

		if self.ui.ui_type == 'gtk':
			if self.preferences['embedded']:
				if self.ui_id_show_dialog:
					self.ui.remove_ui(self, self.ui_id_show_dialog)
					self.ui_id_show_dialog = None

				self.connect_embedded_widget()
			else:
				self.disconnect_embedded_widget()

				if not self.ui_id_show_dialog:
					self.ui_id_show_dialog = \
						self.ui.add_ui(ui_xml_show_dialog, self)

	def path_from_date(self, date):
		'''Returns the path for a calendar page for a specific date'''
		if self.preferences['granularity'] == DAY:
			path = date.strftime('%Y:%m:%d')
		elif self.preferences['granularity'] == WEEK:
			path = date.strftime('%Y:Week %U') # FIXME - should this be translated ??
		elif self.preferences['granularity'] == MONTH:
			path = date.strftime('%Y:%m')
		elif self.preferences['granularity'] == YEAR:
			path = date.strftime('%Y')
		return Path( self.preferences['namespace'] + ':' + path )

	def path_for_month_from_date(self, date):
		'''Returns the namespace path for a certain month'''
		return Path( self.preferences['namespace']
						+ ':' + date.strftime('%Y:%m') )

	def date_from_path(self, path):
		'''Returns a datetime.date object for a calendar page'''
		dates = daterange_from_path(path)
		assert dates, 'Not a date path: %s' % path.name
		return dates[1]

	def on_process_page_template(self, manager, template, page, dict):
		'''Callback called when parsing a template, e.g. when exposing a page
		or for the template used to create a new page. Will set parameters in
		the template dict to be used in the template.
		'''
		daterange = daterange_from_path(page)
		if daterange:
			type, start, end = daterange
			dict['calendar_plugin'] = {
				'page_type': type,
				'date': start,
				'start_date': start,
				'end_date': end,
				'days': DateRangeTemplateFunction(start, end),
			}

	def suggest_link(self, source, text):
		#~ if date_path_re.match(path.text):
		#~ 	return Path(text)
		if re.match(r'^\d{4}-\d{2}-\d{2}$', text):
			year, month, day = text.split('-')
			year, month, day = map(int, (year, month, day))
			date = datetime.date(year, month, day)
			return self.path_from_date(date)
		# TODO other formats
		else:
			return None

	def go_page_today(self):
		today = datetime.date.today()
		path = self.path_from_date(today)
		self.ui.open_page(path)

	def show_calendar(self):
		dialog = CalendarDialog.unique(self, self)
		dialog.present()

	# TODO: hook to the pageview end-of-word signal and link dates
	#       add a preference for this
	# TODO: Overload the "Insert date" dialog by adding a 'link' option


class DateRangeTemplateFunction(TemplateFunction):
	'''Function to be used in templates to iterate a range of dates'''

	def __init__(self, start, end):
		self.start = start
		self.end = end

	def __call__(self, dict):
		oneday = datetime.timedelta(days=1)
		yield self.start
		next = self.start + oneday
		while next < self.end:
			yield next
			next += oneday


class Calendar(gtk.Calendar):
	'''Custom calendar widget class. Adds an 'activate' signal for when a
	date is selected explicitly by the user.
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'activate': (gobject.SIGNAL_RUN_LAST, None, ()),
	}
	def __init__(self):
		gtk.Calendar.__init__(self)
		self.selected = False

	def do_key_press_event(self, event):
		handled = gtk.Calendar.do_key_press_event(self, event)
		if handled and (event.keyval in KEYVALS_SPACE
		or event.keyval in KEYVALS_ENTER):
			self.emit('activate')
		return handled

	def do_button_press_event(self, event):
		handled = gtk.Calendar.do_button_press_event(self, event)
		if event.button == 1 and self.selected:
			self.selected = False
			self.emit('activate')
		return handled

	def do_day_selected(self):
		self.selected = True

	def select_date(self, date):
		'''Set selected date using a datetime oject'''
		self.select_month(date.month - 1, date.year)
		self.select_day(date.day)

	def get_date(self):
		'''Get the datetime object for the selected date'''
		year, month, day = gtk.Calendar.get_date(self)
		return datetime.date(year, month + 1, day)

# Need to register classes defining gobject signals
gobject.type_register(Calendar)


class CalendarPluginWidget(gtk.VBox):

	def __init__(self, plugin):
		gtk.VBox.__init__(self)
		self.plugin = plugin

		self.label = gtk.Label()
		self.pack_start(self.label, False)
		self._refresh_label()
		self._timer_id = \
			gobject.timeout_add(300000, self._refresh_label)
			# 5 minute = 300_000 ms
			# Ideally we only need 1 timer per day at 00:00, but not
			# callback for that
		self.connect('destroy',
			lambda o: gobject.source_remove(o._timer_id) )
			# Clear reference, else we get a new timer for every dialog

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
		self._select_date_cb = None

	def _refresh_label(self, *a):
		#print "UPDATE LABEL %s" % id(self)
		format = _('%A %d %B %Y').replace(' 0', ' ')
			# T: strftime format for current date label
		text = datetime.date.today().strftime(str(format))
			# str() needed for python 2.5 compatibility strftime
		self.label.set_text(text)
		return True # else timer is stopped

	def set_select_date_callback(self, func):
		self._select_date_cb = func

	def on_calendar_activate(self, calendar):
		path = self.plugin.path_from_date( calendar.get_date() )
		if path != self.plugin.ui.page:
			self.plugin.ui.open_page(path)
		if callable(self._select_date_cb):
			self._select_date_cb(calendar.get_date())

	def on_month_changed(self, calendar):
		calendar.clear_marks()
		namespace = self.plugin.path_for_month_from_date( calendar.get_date() )
		for path in self.plugin.ui.notebook.index.list_pages(namespace):
			if date_path_re.match(path.name):
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
		Dialog.__init__(self, plugin.ui, _('Calendar'), buttons=gtk.BUTTONS_CLOSE) # T: dialog title
		self.set_resizable(False)
		self.plugin = plugin

		self.calendar_widget = CalendarPluginWidget(plugin)
		self.calendar_widget.set_select_date_callback(self.on_select_date)
		self.vbox.add(self.calendar_widget)

		button = Button(_('_Today'), gtk.STOCK_JUMP_TO) # T: button label
		button.connect('clicked', self.do_today )
		self.action_area.add(button)
		self.action_area.reorder_child(button, 0)
		self.dateshown = datetime.date.today()

	def on_select_date(self, date):
		if ui_environment['platform'] == 'maemo':
			# match the user usage pattern
			# close the dialog once a explicit selection is made
			# since it is modal and the mainwindow can't be reached
			if (date.month != self.dateshown.month) or (date.year != self.dateshown.year):
				self.dateshown = date
			else:
				self.emit('close')

	def do_today(self, event):
		self.calendar_widget.select_date(datetime.date.today())
