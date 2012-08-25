# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import gobject
import gtk

import re
import datetime
import locale

from zim.plugins import PluginClass
from zim.gui.widgets import ui_environment, Dialog, Button, LEFT_PANE, TOP, WIDGET_POSITIONS
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

date_path_re = re.compile(r'^(.*:)?\d{4}:\d{1,2}:\d{2}$')
week_path_re = re.compile(r'^(.*:)?\d{4}:Week \d{2}$')
month_path_re = re.compile(r'^(.*:)?\d{4}:\d{1,2}$')
year_path_re = re.compile(r'^(.*:)?\d{4}$')


# Initialize setting for first day of the week. This is locale
# dependent, and the gtk widget already has good code to find it out.
# TODO we might also add this as a user preference
SUNDAY = 'Sunday'
MONDAY = 'Monday'
if gtk.Calendar().get_display_options() \
 & gtk.CALENDAR_WEEK_START_MONDAY:
	FIRST_DAY_OF_WEEK = MONDAY
else:
	FIRST_DAY_OF_WEEK = SUNDAY


def dates_for_week(year, week):
	'''Returns the first and last day of the week for a given
	week number of a given year.
	@param year: year as int (e.g. 2012)
	@param week: week number as int (0 .. 53)
	@returns: a 2-tuple of:
	  - a C{datetime.date} object for the start date of the week
	  - a C{datetime.date} object for the end dateof the week

	@note: first day of the week can be either C{MONDAY} or C{SUNDAY},
	this is configured in C{FIRST_DAY_OF_WEEK} based on the locale.
	'''
	# Note that the weeknumber in the isocalendar does NOT depend on the
	# first day being Sunday or Monday, but on the first Thursday in the
	# new year. See datetime.isocalendar() for details.
	# If the year starts with e.g. a Friday, January 1st still belongs
	# to week 53 of the previous year.
	# Day of week in isocalendar starts with 1 for Mon and is 7 for Sun,
	# and week starts on Monday.

	jan1 = datetime.date(year, 1, 1)
	_, jan1_week, jan1_weekday = jan1.isocalendar()

	if FIRST_DAY_OF_WEEK == MONDAY:
		days = jan1_weekday - 1
		# if Jan 1 is a Monday, days is 0
	else:
		days = jan1_weekday
		# if Jan 1 is a Monday, days is 1
		# for Sunday it becomes 7 (or -1 week)

	if jan1_week == 1:
		weeks = week - 1
	else:
		# Jan 1st is still wk53 of the previous year
		weeks = week

	start = jan1 + datetime.timedelta(days=-days, weeks=weeks)
	end = start + datetime.timedelta(days=6)
	return start, end


def week_calendar(date):
	'''Get the year, week number and week day for a specific date.
	Like C{datetime.date.isocalendar()} but takes into account
	C{FIRST_DAY_OF_WEEK} correctly.
	@param date: a C{datetime.date} or C{datetime.datetime} object
	@returns: a year and a week number as integer
	'''
	# Both strftime %W and %U are not correct, they use differnt
	# week number count than the isocalendar. See datetime
	# module for details.
	# In short Jan 1st can still be week 53 of the previous year
	# So we can use isocalendar(), however this does not take
	# into accout FIRST_DAY_OF_WEEK, see comment in dates_for_week()
	year, week, weekday = date.isocalendar()
	if FIRST_DAY_OF_WEEK == SUNDAY and weekday == 7:
		# iso calendar gives us the week ending this sunday,
		# we want the next week
		monday = date + datetime.timedelta(days=1)
		year, week, weekday = monday.isocalendar()
	return year, week


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
		date, end_date = dates_for_week(year, week)
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
		return None # Not a calendar path
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

	global DAY, WEEK, MONTH, YEAR, SUNDAY, MONDAY # Hack - to make sure translation is loaded
	DAY = _('Day') # T: option value
	WEEK = _('Week') # T: option value
	MONTH = _('Month') # T: option value
	YEAR = _('Year') # T: option value

	SUNDAY = _('Sunday') # T: calendar day
	MONDAY = _('Monday') # T: calendar day

	plugin_preferences = (
		# key, type, label, default
		('embedded', 'bool', _('Show calendar in sidepane instead of as dialog'), False), # T: preferences option
		('pane', 'choice', _('Position in the window'), (LEFT_PANE, TOP), WIDGET_POSITIONS), # T: preferences option
		('granularity', 'choice', _('Use a page for each'), DAY, (DAY, WEEK, MONTH, YEAR)), # T: preferences option, values will be "Day", "Month", ...
		#~ ('week_start', 'choice', _('Week starts on'), FIRST_DAY_OF_WEEK, (MONDAY, SUNDAY)), # T: preferences option for first day of the week, options are Monday or Sunday
		('namespace', 'namespace', _('Namespace'), ':Calendar'), # T: input label
	)
	# TODO disable pane setting if not embedded

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		self.sidepane_widget = None # For the embedded version
		self.ui_id_show_dialog = None # For the 'show dialog' action
		self._set_template = None

	def initialize_ui(self, ui):
		if self.ui.ui_type == 'gtk':
			self.ui.add_actions(ui_actions, self)
			self.ui.add_ui(ui_xml, self)
			self.connectto(TemplateManager, 'process-page', self.on_process_page_template)
			self.connectto(self.ui, 'open-page')

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

	def on_open_page(self, ui, page, path):
		if self.sidepane_widget:
			self.sidepane_widget.set_page(path)
		# else dialog takes care of itself

	def connect_embedded_widget(self):
		if not self.sidepane_widget:
			self.sidepane_widget = CalendarPluginWidget(self)
		else:
			self.ui.mainwindow.remove(self.sidepane_widget)

		self.ui.mainwindow.add_widget(self.sidepane_widget, self.preferences['pane'])
		self.sidepane_widget.show_all()

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
			year, week = week_calendar(date)
			path = '%i:Week %02i' % (year, week)
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
		'''Returns the date for a specific path or C{None}'''
		dates = daterange_from_path(path)
		if dates:
			return dates[1]
		else:
			return None

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
		while next <= self.end:
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
				dates = daterange_from_path(path)
				if dates and dates[0] == 'day':
					calendar.mark_day(date[1].day)

	def set_page(self, page):
		dates = daterange_from_path(page)
		if dates and dates[0] != 'year':
			# Calendar is per month, so do not switch view for year page
			self.calendar.select_month(dates[1].month-1, dates[1].year)

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

		self.connectto(self.plugin.ui, 'open-page')

	def on_open_page(self, ui, page, path):
		self.calendar_widget.set_page(page)

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
