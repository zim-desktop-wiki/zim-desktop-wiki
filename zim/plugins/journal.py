
# Copyright 2009-2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>


from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Gdk

import re

from functools import partial

import logging

from zim.plugins import PluginClass
from zim.actions import action
from zim.signals import SignalHandler, ConnectorMixin
import zim.datetimetz as datetime
from zim.datetimetz import dates_for_week, weekcalendar
from zim.notebook import Path, NotebookExtension
from zim.notebook.index import IndexNotFoundError
from zim.templates.expression import ExpressionFunction

from zim.gui.pageview import PageViewExtension
from zim.gui.widgets import ScrolledWindow, \
	WindowSidePaneWidget, LEFT_PANE, PANE_POSITIONS

from zim.plugins.pageindex import PageTreeStore, PageTreeView


logger = logging.getLogger('zim.plugins.journal')


# FUTURE: Use calendar.HTMLCalendar from core libs to render this plugin in www

# TODO: add extension
# - hook to the pageview end-of-word signal and link dates
#   add a preference for this
# - Overload the "Insert date" dialog by adding a 'link' option


KEYVALS_ENTER = list(map(Gdk.keyval_from_name, ('Return', 'KP_Enter', 'ISO_Enter')))
KEYVALS_SPACE = (Gdk.unicode_to_keyval(ord(' ')),)

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
		year, month, day = list(map(int, path.name.rsplit(':', 3)[-3:]))
		try:
			date = datetime.date(year, month, day)
		except ValueError:
			return None # not a valid date
		end_date = date
	elif week_path_re.match(path.name):
		type = 'week'
		year, week = path.name.rsplit(':', 2)[-2:]
		year, week = list(map(int, (year, week[5:]))) # Assumes "Week XX" string
		date, end_date = dates_for_week(year, week)
	elif month_path_re.match(path.name):
		type = 'month'
		year, month = list(map(int, path.name.rsplit(':', 2)[-2:]))
		try:
			date = datetime.date(year, month, 1)
		except ValueError:
			return None # not a valid month
		if month == 12:
			end_date = datetime.date(year, 12, 31)
		else:
			end_date = datetime.date(year, month + 1, 1) + datetime.timedelta(-1)
	elif year_path_re.match(path.name):
		type = 'year'
		year = int(path.name.rsplit(':', 1)[-1])
		date = datetime.date(year, 1, 1)
		end_date = datetime.date(year, 12, 31)
	else:
		return None # Not a journal path
	return type, date, end_date


class JournalPlugin(PluginClass):

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
		('pane', 'choice', _('Position in the window'), LEFT_PANE, PANE_POSITIONS), # T: preferences option
		('granularity', 'choice', _('Use a page for each'), DAY, (DAY, WEEK, MONTH, YEAR)), # T: preferences option, values will be "Day", "Month", ...
		('namespace', 'namespace', _('Section'), Path(':Journal')), # T: input label
		('auto_expand_in_index', 'bool', _('Expand journal page in index when opened'), True), # T: preferences option
	)

	def path_from_date(self, date):
		'''Returns the path for a journal page for a specific date'''
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


class CalendarNotebookExtension(NotebookExtension):
	'''Extend notebook by setting special page template for
	the journal namespace and by adding a hook to suggests links
	for dates.
	'''

	def __init__(self, plugin, notebook):
		NotebookExtension.__init__(self, plugin, notebook)
		self._initialized_namespace = None

		self.on_preferences_changed(plugin.preferences)
		self.connectto(plugin.preferences, 'changed', self.on_preferences_changed)

		self.connectto(notebook, 'suggest-link')
		self.connectto(notebook, 'new-page-template')

	def on_suggest_link(self, notebook, source, text):
		#~ if date_path_re.match(path.text):
		#~ 	return Path(text)
		if re.match(r'^\d{4}-\d{2}-\d{2}$', text):
			year, month, day = text.split('-')
			year, month, day = list(map(int, (year, month, day)))
			date = datetime.date(year, month, day)
			return self.plugin.path_from_date(date)
		# TODO other formats
		else:
			return None

	def on_new_page_template(self, notebook, path, template):
		daterange = daterange_from_path(path)
		if daterange:
			self.connectto(template, 'process',
				partial(
					self.on_process_new_page_template,
					daterange=daterange
				)
			)

	def on_process_new_page_template(self, template, output, context, daterange):
		'''Callback called when parsing a template, e.g. when exporting
		a page or when a new page is created.
		Sets parameters in the template dict to be used in the template.
		'''
		type, start, end = daterange
		context['journal_plugin'] = {
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
		self.notebook.namespace_properties[ns]['auto_expand_in_index'] = preferences['auto_expand_in_index']
		self._initialized_namespace = ns

	def teardown(self):
		if self._initialized_namespace:
			ns = self._initialized_namespace
			for key in ('template', 'auto_expand_in_index'):
				try:
					self.notebook.namespace_properties[ns].remove(key)
				except KeyError:
					pass
			self._initialized_namespace = None


class JournalPageViewExtension(PageViewExtension):
	'''Extension used to add calendar dialog to mainwindow'''

	def __init__(self, plugin, pageview):
		PageViewExtension.__init__(self, plugin, pageview)

		self.calendar_widget = CalendarWidget(plugin, pageview.notebook, plugin.config, self.navigation)
		self.connectto(pageview, 'page-changed', lambda o, p: self.calendar_widget.set_page(p))

		self.add_sidepane_widget(self.calendar_widget, 'pane')

	@action(_('To_day'), accelerator='<Alt>D', menuhints='go') # T: menu item
	def go_page_today(self):
		""" Opens the current day page in the Journal. If some text is selected,
			it is replaced with a link and moved at the end of today's page.
		"""
		today = datetime.date.today()
		path = self.plugin.path_from_date(today)

		contents = ""
		buffer = self.navigation.window.pageview.textview.get_buffer()
		if buffer.get_selection_bounds():
			contents = buffer.get_parsetree(buffer.get_selection_bounds())
			buffer.delete(*buffer.get_selection_bounds())  # cuts the moved text from the original page
			link = str(path)
			link = self.navigation.window.notebook.suggest_link(self.pageview.page, link) or link  # hope that suggest_link is implemented correctly
			buffer.insert_link_at_cursor(str(path), link)

		self.navigation.open_page(path)

		if contents:
			buffer = self.navigation.window.pageview.textview.get_buffer()
			buffer.insert_parsetree(buffer.get_end_iter(), contents)


class Calendar(Gtk.Calendar):
	'''Custom calendar widget class. Adds an 'activate' signal for when a
	date is selected explicitly by the user.
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'activate': (GObject.SignalFlags.RUN_LAST, None, ()),
	}

	def __init__(self):
		GObject.GObject.__init__(self)
		self.selected = False

	def do_key_press_event(self, event):
		handled = Gtk.Calendar.do_key_press_event(self, event)
		if handled and (event.keyval in KEYVALS_SPACE
		or event.keyval in KEYVALS_ENTER):
			self.emit('activate')
		return handled

	def do_button_press_event(self, event):
		handled = Gtk.Calendar.do_button_press_event(self, event)
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
		year, month, day = Gtk.Calendar.get_date(self)
		if day == 0:
			day = 1

		try:
			date = datetime.date(year, month + 1, day)
		except ValueError:
			# This error may mean that day number is higher than allowed.
			# If so, set date to the last day of the month.
			if day > 27:
				date = datetime.date(year, month + 2, 1) - datetime.timedelta(days = 1)
			else:
				raise
		return date


class CalendarWidget(Gtk.VBox, WindowSidePaneWidget):

	title = _('Journal') # T: side pane title

	def __init__(self, plugin, notebook, config, navigation):
		GObject.GObject.__init__(self)
		self.plugin = plugin
		self.navigation = navigation
		self.model = CalendarWidgetModel(plugin, notebook)

		self.label_box = Gtk.HBox()
		self.pack_start(self.label_box, False, True, 0)

		self.label = Gtk.Label()
		button = Gtk.Button()
		button.add(self.label)
		button.set_relief(Gtk.ReliefStyle.NONE)
		button.connect('clicked', lambda b: self.go_today())
		self.label_box.add(button)

		self._close_button = None

		self._refresh_label()
		self._timer_id = \
			GObject.timeout_add(300000, self._refresh_label)
			# 5 minute = 300_000 ms
			# Ideally we only need 1 timer per day at 00:00, but not
			# callback for that
		self.connect('destroy',
			lambda o: GObject.source_remove(o._timer_id))
			# Clear reference, else we get a new timer for every dialog

		self.calendar = Calendar()
		self.calendar.set_display_options(
			Gtk.CalendarDisplayOptions.SHOW_HEADING |
			Gtk.CalendarDisplayOptions.SHOW_DAY_NAMES |
			Gtk.CalendarDisplayOptions.SHOW_WEEK_NUMBERS
		)
		self.calendar.connect('activate', self.on_calendar_activate)
		self.calendar.connect('month-changed', self.on_month_changed)
		self.on_month_changed(self.calendar)
		self.pack_start(self.calendar, False, True, 0)

		index = notebook.index
		model = PageTreeStore(index, root=Path('Journal'), reverse=True)
		self.treeview = PageTreeView(notebook, config, navigation)
		self.treeview.set_model(model)
		self.pack_start(ScrolledWindow(self.treeview), True, True, 0)

	def go_today(self):
		self.calendar.select_date(datetime.date.today())
		self.calendar.emit('activate')

	def set_embeded_closebutton(self, button):
		if self._close_button:
			self.label_box.remove(self._close_button)

		if button is not None:
			self.label_box.pack_end(button, False, True, 0)

		self._close_button = button
		return True

	def _refresh_label(self, *a):
		#print "UPDATE LABEL %s" % id(self)
		format = _('%A %d %B %Y').replace(' 0', ' ')
			# T: strftime format for current date label
		text = datetime.strftime(format, datetime.date.today())
		self.label.set_text(text)
		return True # else timer is stopped

	def on_calendar_activate(self, calendar):
		date = calendar.get_date()
		path = self.plugin.path_from_date(date)
		self.navigation.open_page(path)

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
				cur_date = self.calendar.get_date()
				if cur_date < dates[1] or cur_date > dates[2]:
					self.calendar.select_date(dates[1])

			treepath = self.treeview.set_current_page(page, vivificate=True)
			if treepath:
				self.treeview.select_treepath(treepath)
		else:
			self.calendar.select_day(0)
			self.treeview.get_selection().unselect_all()


class CalendarWidgetModel(object):

	def __init__(self, plugin, notebook):
		self.plugin = plugin
		self.notebook = notebook

	def list_dates_for_month(self, date):
		namespace = self.plugin.path_for_month_from_date(date)
		try:
			for path in self.notebook.pages.list_pages(namespace):
				if date_path_re.match(path.name):
					dates = daterange_from_path(path)
					if dates and dates[0] == 'day':
						yield dates[1]
		except IndexNotFoundError:
			pass
