# -*- coding: utf-8 -*-

# Copyright 2015 Tobias Haupenthal <thaupenthal@xdn.de>

import gtk
import gtksourceview2
import pango
import logging

logger = logging.getLogger('zim.plugin.tableeditor')

from zim.plugins import PluginClass, WindowExtension, extends
from zim.actions import action
from zim.utils import WeakSet
from zim.objectmanager import ObjectManager, CustomObjectClass
from zim.config import String, Boolean
from zim.gui.widgets import Dialog, ScrolledWindow
from zim.gui.objectmanager import CustomObjectWidget, TextViewWidget, TableViewWidget
from zim.formats.html import html_encode

OBJECT_TYPE = 'table'

if gtksourceview2:
	lm = gtksourceview2.LanguageManager()
	lang_ids = lm.get_language_ids()
	lang_names = [lm.get_language(i).get_name() for i in lang_ids]

	LANGUAGES = dict((lm.get_language(i).get_name(), i) for i in lang_ids)
else:
	LANGUAGES = {}


class TableEditorPlugin(PluginClass):

	plugin_info = {
		'name': _('Table Editor'), # T: plugin name
		'description': _('''\
**IN DEVELOPMENT**
This plugin allows inserting 'Tables' in the page. These will be shown as TreeGrid widgets.
Exporting them to various formats (i.e. HTML/LaTeX) completes the feature set.
'''), # T: plugin description
		'object_types': (OBJECT_TYPE, ),
		'help': 'Plugins:Table Editor',
		'author': 'Tobias Haupenthal',
	}

	plugin_preferences = (
		# key, type, label, default
		('auto_indent', 'bool', _('Auto indenting'), True),
			# T: preference option for sourceview plugin
		('smart_home_end', 'bool', _('Smart Home key'), True),
			# T: preference option for sourceview plugin
		('highlight_current_line', 'bool', _('Highlight current line'), False),
			# T: preference option for sourceview plugin
		('show_right_margin', 'bool', _('Show right margin'), False),
			# T: preference option for sourceview plugin
		('right_margin_position', 'int', _('Right margin position'), 72, (1, 1000)),
			# T: preference option for sourceview plugin
		('tab_width', 'int', _('Tab width'), 4, (1, 80)),
			# T: preference option for sourceview plugin
	)

	def __init__(self, config=None):
		PluginClass.__init__(self, config)
		self.connectto(self.preferences, 'changed', self.on_preferences_changed)

	def create_object(self, attrib, text):
		'''Factory method for SourceViewObject objects'''
		obj = TableViewObject(attrib, text, self.preferences)
		return obj

	def on_preferences_changed(self, preferences):
		'''Update preferences on open objects'''
		for obj in ObjectManager.get_active_objects(OBJECT_TYPE):
			obj.preferences_changed()


@extends('MainWindow')
class MainWindowExtension(WindowExtension):

	uimanager_xml = '''
		<ui>
		<menubar name='menubar'>
			<menu action='insert_menu'>
				<placeholder name='plugin_items'>
					<menuitem action='insert_table'/>
				</placeholder>
			</menu>
		</menubar>
		</ui>
	'''

	def __init__(self, plugin, window):
		WindowExtension.__init__(self, plugin, window)
		ObjectManager.register_object(OBJECT_TYPE, self.plugin.create_object)
			# XXX use pageview attribute instead of singleton

	def teardown(self):
		ObjectManager.unregister_object(OBJECT_TYPE)

	@action(_('Code Block'), readonly=False) # T: menu item
	def insert_table(self):
		'''Inserts new SourceView'''
		logger.fatal("InsertCodeBlockDialog")
		#lang = InsertCodeBlockDialog(self.window.ui).run() # XXX
		lang = "php"
		if not lang:
			return # dialog cancelled
		else:
			obj = self.plugin.create_object({'type': OBJECT_TYPE, 'lang': lang}, '')
			pageview = self.window.pageview
			pageview.insert_object_at_cursor(obj)


class TableViewObject(CustomObjectClass):

	OBJECT_ATTR = {
		'type': String('table'),
		'lang': String(None),
		'linenumbers': Boolean(True),
	}

	def __init__(self, attrib, data, preferences):
		if data.endswith('\n'):
			data = data[:-1]
			# If we have trailing \n it looks like an extra empty line
			# in the buffer, so we default remove one
		CustomObjectClass.__init__(self, attrib, data)
		self.preferences = preferences
		self.buffer = None
		self._widgets = WeakSet()

	def get_widget(self):
		if not self.buffer:
			self.buffer = gtksourceview2.Buffer()
			self.buffer.set_text(self._data)
			self.buffer.connect('modified-changed', self.on_modified_changed)
			self.buffer.set_highlight_matching_brackets(True)
			self.buffer.set_modified(False)
			self._data = None

			try:
				if self._attrib['lang']:
					self.buffer.set_language(lm.get_language(self._attrib['lang']))
			except:
				logger.exception('Could not set language for sourceview: %s', lang)

		widget = TableViewWidget(self, self.buffer)
		self._widgets.add(widget)

		widget.view.set_show_line_numbers(self._attrib['linenumbers'])
		widget.set_preferences(self.preferences)
		return widget

	def preferences_changed(self):
		for widget in self._widgets:
			widget.set_preferences(self.preferences)

	def on_modified_changed(self, buffer):
		# Sourceview changed, set change on oject, reset state of
		# sourceview buffer so we get a new signal with next change
		if buffer.get_modified():
			self.set_modified(True)
			buffer.set_modified(False)

	def get_data(self):
		'''Returns data as text.'''
		if self.buffer:
			bounds = self.buffer.get_bounds()
			text = self.buffer.get_text(bounds[0], bounds[1])
			text += '\n' # Make sure we always have a trailing \n
			return text
		else:
			return self._data

	def dump(self, format, dumper, linker=None):
		if format == "html":
			if self._attrib['lang']:
				# class="brush: language;" works with SyntaxHighlighter 2.0.278
				# by Alex Gorbatchev <http://alexgorbatchev.com/SyntaxHighlighter/>
				# TODO: not all GtkSourceView language ids match with SyntaxHighlighter
				# language ids.
				# TODO: some template instruction to be able to use other highlighters as well?
				output = ['<pre class="brush: %s;">\n' % html_encode(self._attrib['lang'])]
			else:
				output = ['<pre>\n']
			data = self.get_data()
			data = html_encode(data) # XXX currently dumper gives encoded lines - NOK
			if self._attrib['linenumbers']:
				for i, l in enumerate(data.splitlines(1)):
					output.append('%i&nbsp;' % (i+1) + l)
			else:
				output.append(data)
			output.append('</pre>\n')
			return output
		return CustomObjectClass.dump(self, format, dumper, linker)

	def set_language(self, lang):
		'''Set language in SourceView.'''
		self._attrib['lang'] = lang
		self.set_modified(True)

		if self.buffer:
			if lang is None:
				self.buffer.set_language(None)
			else:
				self.buffer.set_language(lm.get_language(lang))

	def show_line_numbers(self, show):
		'''Toggles line numbers in SourceView.'''
		self._attrib['linenumbers'] = show
		self.set_modified(True)

		for widget in self._widgets:
			widget.view.set_show_line_numbers(show)
