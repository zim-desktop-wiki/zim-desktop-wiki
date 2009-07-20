# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Plugin to serve as work-around for the lack of printing support'''

import gobject
import gtk

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
	<menu action='view_menu'>
		<placeholder name='plugin_items'>
			<menuitem action='show_calendar'/>
		</placeholder>
	</menu>
	<menu action='go_menu'>
		<placeholder name='plugin_items'>
			<menuitem action='go_page_today'/>
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
	# name, stock id, label, accelerator, tooltip
	('go_page_today', None, _('To_day'), '<ctrl>D', ''), # T: menu item
)

ui_toggle_actions = (
	# name, stock id, label, accelerator, tooltip, None, initial state
	('show_calendar', 'zim-calendar', _('Calen_dar'),  '', '', None, False), # T: menu item
)

KEYVALS_ENTER = map(gtk.gdk.keyval_from_name, ('Return', 'KP_Enter', 'ISO_Enter'))
KEYVALS_SPACE = (gtk.gdk.unicode_to_keyval(ord(' ')),)


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
	}

	plugin_preferences = (
		# key, type, label, default
		('namespace', 'namespace', _('Namespace'), ':Calendar'), # T: input label
	)

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		if self.ui.ui_type == 'gtk':
			self.ui.add_actions(ui_actions, self)
			self.ui.add_toggle_actions(ui_toggle_actions, self)
			self.ui.add_ui(ui_xml, self)

	def path_from_date(self, date):
		return Path(
			self.preferences['namespace'] + ':' + date.strftime('%Y:%m:%d') )

	def date_from_path(self, path):
		_, year, month, day = path.name.rsplit(':', 3)
		year, month, day = map(int, (year, month, day))
		return dateclass(year, month, day)

	def go_page_today(self):
		today = dateclass.today()
		path = self.path_from_date(today)
		self.ui.open_page(path)

	def show_calendar(self, show=None):
		self.toggle_action('show_calendar', active=show)

	def do_show_calendar(self, show=None):
		if show is None:
			show = self.actiongroup.get_action('show_calendar').get_active()

		dialog = CalendarDialog.unique(self, self)
		if show:
			dialog.show_all()
		else:
			dialog.hide_all()

	# TODO: hook to the pageview end-of-word signal and link dates
	#       add a preference for this
	# TODO: Overload the "Insert date" dialog by adding a 'link' option

class CalendarDialog(Dialog):

	# TODO: add this method to the dialog base class..
	@classmethod
	def unique(klass, handler, *args, **opts):
		import weakref
		attr = '_unique_dialog_%s' % klass.__name__
		dialog = None

		if hasattr(handler, attr):
			ref = getattr(handler, attr)
			dialog = ref()

		if dialog is None or dialog.destroyed:
			dialog = klass(*args, **opts)

		setattr(handler, attr, weakref.ref(dialog))
		return dialog

	def __init__(self, plugin):
		Dialog.__init__(self, plugin.ui, _('Calendar'), buttons=None) # T: dialog title
		self.set_resizable(False)
		self.plugin = plugin

		format = _('%A %d %B %Y').replace(' 0', ' ') # T: strftime format for current date label
		label = gtk.Label(dateclass.today().strftime(format))
		self.vbox.add(label)

		self.calendar = Calendar()
		self.calendar.display_options(
			gtk.CALENDAR_SHOW_HEADING |
			gtk.CALENDAR_SHOW_DAY_NAMES |
			gtk.CALENDAR_SHOW_WEEK_NUMBERS )
		self.calendar.connect('activate', self.on_calendar_activate)
		self.vbox.add(self.calendar)

		hbox = gtk.HBox()
		self.vbox.add(hbox)
		button = Button(_('_Today'), gtk.STOCK_JUMP_TO) # T: button label
		button.connect_object('clicked', self.__class__.select_today, self)
		hbox.pack_end(button, False)

	def do_response(self, response):
		self.plugin.show_calendar(False)
		self.destroy()

	def on_calendar_activate(self, calendar):
		path = self.plugin.path_from_date( calendar.get_date() )
		if path != self.ui.page:
			self.ui.open_page(path)

	def select_today(self):
		self.calendar.select_date(dateclass.today())

	# TODO: synchronize with page loaded if it matches a date page
	# TODO: on month changed signal mark days that actually have a page


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
