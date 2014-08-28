# -*- coding: utf-8 -*-

# Copyright 2009-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement

import gobject
import gtk

import re

import logging

from zim.plugins import PluginClass, extends, ObjectExtension, WindowExtension
from zim.actions import action
from zim.signals import SignalHandler
import zim.datetimetz as datetime
from zim.datetimetz import dates_for_week, weekcalendar
from zim.gui.widgets import ui_environment, Dialog, Button, \
	WindowSidePaneWidget, LEFT_PANE, TOP, WIDGET_POSITIONS
from zim.notebook import Path
from zim.templates.expression import ExpressionFunction

logger = logging.getLogger('zim.plugins.calendar')


# FUTURE: Use calendar.HTMLCalendar from core libs to render this plugin in www


KEYVALS_ENTER = map(gtk.gdk.keyval_from_name, ('Return', 'KP_Enter', 'ISO_Enter'))
KEYVALS_SPACE = (gtk.gdk.unicode_to_keyval(ord(' ')),)

date_path_re = re.compile(r'^(.*:)?\d{4}:\d{1,2}:\d{2}$')
week_path_re = re.compile(r'^(.*:)?\d{4}:Week \d{2}$')
month_path_re = re.compile(r'^(.*:)?\d{4}:\d{1,2}$')
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
		'name': _('Journal'), # T: plugin name
		'description': _('''\
This plugin turns one section of the notebook into a journal
with a page per day, week or month.
Also adds a calendar widget to access these pages.
'''),
		# T: plugin description
		'author': 'Jaap Karssenberg',
		'help': 'Plugins:Journal',
	}

	global DAY, WEEK, MONTH, YEAR # Hack - to make sure translation is loaded
	DAY = _('Day') # T: option value
	WEEK = _('Week') # T: option value
	MONTH = _('Month') # T: option value
	YEAR = _('Year') # T: option value

	plugin_preferences = (
		# key, type, label, default
		('embedded', 'bool', _('Show calendar in sidepane instead of as dialog'), False), # T: preferences option
		('pane', 'choice', _('Position in the window'), (LEFT_PANE, TOP), WIDGET_POSITIONS), # T: preferences option
		('granularity', 'choice', _('Use a page for each'), DAY, (DAY, WEEK, MONTH, YEAR)), # T: preferences option, values will be "Day", "Month", ...
		('namespace', 'namespace', _('Section'), Path(':Journal')), # T: input label
	)
	# TODO disable pane setting if not embedded

	def __init__(self, config=None):
		PluginClass.__init__(self, config)
		self.preferences.connect('changed', self.on_preferences_changed)
		self.on_preferences_changed(self.preferences)

	def on_preferences_changed(self, preferences):
		if preferences['embedded']:
			self.set_extension_class('MainWindow', MainWindowExtensionEmbedded)
		else:
			self.set_extension_class('MainWindow', MainWindowExtensionDialog)

	def path_from_date(self, date):
		'''Returns the path for a calendar page for a specific date'''
		if self.preferences['granularity'] == DAY:
			path = date.strftime('%Y:%m:%d')
		elif self.preferences['granularity'] == WEEK:
			year, week, day = weekcalendar(date)
			path = '%i:Week %02i' % (year, week)
		elif self.preferences['granularity'] == MONTH:
			path = date.strftime('%Y:%m')
		elif self.preferences['granularity'] == YEAR:
			path = date.strftime('%Y')

		return self.preferences['namespace'].child(path)

	def path_for_month_from_date(self, date):
		'''Returns the namespace path for a certain month'''
		return self.preferences['namespace'].child(date.strftime('%Y:%m'))

	def date_from_path(self, path):
		'''Returns the date for a specific path or C{None}'''
		dates = daterange_from_path(path)
		if dates:
			return dates[1]
		else:
			return None


def dateRangeTemplateFunction(start, end):
	'''Returns a function to be used in templates to iterate a range of dates'''

	@ExpressionFunction
	def date_range_function():
		oneday = datetime.timedelta(days=1)
		yield start
		next = start + oneday
		while next <= end:
			yield next
			next += oneday

	return date_range_function


@extends('Notebook')
class NotebookExtension(ObjectExtension):
	'''Extend notebook by setting special page template for
	the calendar namespace and by adding a hook to suggests links
	for dates.
	'''

	def __init__(self, plugin, notebook):
		self.plugin = plugin
		self.notebook = notebook
		self._set_template = None

		self.on_preferences_changed(plugin.preferences)
		self.connectto(plugin.preferences, 'changed', self.on_preferences_changed)

		self.connectto(notebook, 'suggest-link')
		self.connectto(notebook, 'new-page-template')

	def on_suggest_link(self, notebook, source, text):
		#~ if date_path_re.match(path.text):
		#~ 	return Path(text)
		if re.match(r'^\d{4}-\d{2}-\d{2}$', text):
			year, month, day = text.split('-')
			year, month, day = map(int, (year, month, day))
			date = datetime.date(year, month, day)
			return self.plugin.path_from_date(date)
		# TODO other formats
		else:
			return None

	def on_new_page_template(self, notebook, path, template):
		daterange = daterange_from_path(path)
		if daterange:
			self.connectto(template, 'process',
				self.on_process_new_page_template,
				userdata=daterange
			)

	def on_process_new_page_template(self, template, output, context, daterange):
		'''Callback called when parsing a template, e.g. when exporting
		a page or when a new page is created.
		Sets parameters in the template dict to be used in the template.
		'''
		type, start, end = daterange
		context['calendar_plugin'] = {
			'page_type': type,
			'date': start,
			'start_date': start,
			'end_date': end,
			'days': dateRangeTemplateFunction(start, end),
		}

	def on_preferences_changed(self, preferences):
		self.teardown()
		ns = preferences['namespace'].name
		self.notebook.namespace_properties[ns]['template'] = 'Journal'
		self._set_template = ns

	def teardown(self):
		if self._set_template:
			ns = self._set_template
			try:
				self.notebook.namespace_properties[ns].remove('template')
			except KeyError:
				pass
			self._set_template = None


class MainWindowExtension(WindowExtension):
	'''Base class for our mainwindow extensions'''

	@action(_('To_day'), accelerator='<Alt>D') # T: menu item
	def go_page_today(self):
		today = datetime.date.today()
		path = self.plugin.path_from_date(today)
		self.window.ui.open_page(path) # XXX

	# TODO: hook to the pageview end-of-word signal and link dates
	#       add a preference for this
	# TODO: Overload the "Insert date" dialog by adding a 'link' option


@extends('MainWindow', autoload=False)
class MainWindowExtensionDialog(MainWindowExtension):
	'''Extension used to add calendar dialog to mainwindow'''

	uimanager_xml = '''
	<ui>
	<menubar name='menubar'>
		<menu action='go_menu'>
			<placeholder name='plugin_items'>
				<menuitem action='go_page_today'/>
			</placeholder>
		</menu>
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

	@action(_('Calen_dar'), stock='zim-calendar', tooltip=_('Show calendar')) # T: menu item
	def show_calendar(self):
		dialog = CalendarDialog.unique(self, self.plugin, self.window)
		dialog.present()


@extends('MainWindow', autoload=False)
class MainWindowExtensionEmbedded(MainWindowExtension):
	'''Extension used for calendar widget embedded in side pane'''

	uimanager_xml = '''
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

	def __init__(self, plugin, window):
		WindowExtension.__init__(self, plugin, window)
		self.opener = window.get_resource_opener()

		notebook = window.ui.notebook # XXX
		model = CalendarWidgetModel(self.plugin, notebook)
		self.widget = CalendarWidget(model)

		self.on_preferences_changed(plugin.preferences)
		self.connectto(plugin.preferences, 'changed', self.on_preferences_changed)

		self.connectto(self.widget, 'date-activated')
		self.connectto(self.window.ui, 'open-page') # XXX

	def on_preferences_changed(self, preferences):
		if self.widget is None:
			return

		try:
			self.window.remove(self.widget)
		except ValueError:
			pass
		self.window.add_widget(self.widget, preferences['pane'])
		self.widget.show_all()

	@SignalHandler
	def on_open_page(self, ui, page, path):
		self.widget.set_page(path)

	def on_date_activated(self, widget, date):
		path = self.plugin.path_from_date(date)
		with self.on_open_page.blocked():
			self.opener.open_page(path)

	def teardown(self):
		self.window.remove(self.widget)
		self.widget = None


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


class CalendarWidget(gtk.VBox, WindowSidePaneWidget):

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'date-activated': (gobject.SIGNAL_RUN_LAST, None, (object,)),
	}

	def __init__(self, model):
		gtk.VBox.__init__(self)
		self.model = model

		self.label_box = gtk.HBox()
		self.pack_start(self.label_box, False)

		self.label = gtk.Label()
		self.label_box.add(self.label)
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

	def embed_closebutton(self, button):
		if button:
			self.label_box.pack_end(button, False)
		else:
			for widget in self.label_box.get_children():
				if not widget == self.label:
					self.label_box.remove(widget)
		return True

	def _refresh_label(self, *a):
		#print "UPDATE LABEL %s" % id(self)
		format = _('%A %d %B %Y').replace(' 0', ' ')
			# T: strftime format for current date label
		text = datetime.date.today().strftime(str(format))
			# str() needed for python 2.5 compatibility strftime
		self.label.set_text(text)
		return True # else timer is stopped

	def on_calendar_activate(self, calendar):
		date = calendar.get_date()
		self.emit('date-activated', date)

	def on_month_changed(self, calendar):
		calendar.clear_marks()
		for date in self.model.list_dates_for_month(self.calendar.get_date()):
			calendar.mark_day(date.day)

	def set_page(self, page):
		dates = daterange_from_path(page)
		if dates:
			if dates[0] == 'year':
				# Calendar is per month, so do not switch view for year page
				pass
			else:
				self.calendar.select_date(dates[1])
		else:
			self.calendar.select_day(0)

	def select_date(self, date):
		self.calendar.select_date(date)

# Need to register classes defining gobject signals
gobject.type_register(CalendarWidget)


class CalendarWidgetModel(object):

	def __init__(self, plugin, notebook):
		self.plugin = plugin
		self.notebook = notebook

	def list_dates_for_month(self, date):
		namespace = self.plugin.path_for_month_from_date(date)
		for path in self.notebook.index.list_pages(namespace):
			if date_path_re.match(path.name):
				dates = daterange_from_path(path)
				if dates and dates[0] == 'day':
					yield dates[1]


class CalendarDialog(Dialog):

	def __init__(self, plugin, window):
		Dialog.__init__(self, window, _('Calendar'), buttons=gtk.BUTTONS_CLOSE) # T: dialog title
		self.set_resizable(False)
		self.plugin = plugin
		self.opener = window.get_resource_opener()

		notebook = window.ui.notebook # XXX
		model = CalendarWidgetModel(self.plugin, notebook)
		self.calendar_widget = CalendarWidget(model)
		self.vbox.add(self.calendar_widget)

		button = Button(_('_Today'), gtk.STOCK_JUMP_TO) # T: button label
		button.connect('clicked', self.do_today )
		self.action_area.add(button)
		self.action_area.reorder_child(button, 0)
		self.dateshown = datetime.date.today()

		self.connectto(self.calendar_widget, 'date-activated')
		self.connectto(window.ui, 'open-page') # XXX

	def on_date_activated(self, widget, date):
		path = self.plugin.path_from_date(date)
		with self.on_open_page.blocked():
			self.opener.open_page(path)

	@SignalHandler
	def on_open_page(self, ui, page, path):
		self.calendar_widget.set_page(page)

	def do_today(self, event):
		self.calendar_widget.select_date(datetime.date.today())
