# -*- coding: utf-8 -*-

# Copyright 2011 Jiří Janoušek <janousek.jiri@gmail.com>

import gtk
import pango

try:
	import gtksourceview2
except:
	gtksourceview2 = None

from zim.plugins import PluginClass, WindowExtension, extends
from zim.actions import action
from zim.objectmanager import ObjectManager, CustomObjectClass
from zim.config import String
from zim.gui.widgets import Dialog
from zim.gui.pageview import CustomObjectBin, POSITION_BEGIN, POSITION_END
from zim.formats.html import html_encode

if gtksourceview2:
	lm = gtksourceview2.LanguageManager()
	lang_ids = lm.get_language_ids()
	lang_names = [lm.get_language(i).get_name() for i in lang_ids]

	LANGUAGES = dict((lm.get_language(i).get_name(), i) for i in lang_ids)
else:
	LANGUAGES = {}
#~ print LANGUAGES

OBJECT_TYPE = 'code'


class SourceViewPlugin(PluginClass):

	plugin_info = {
		'name': _('Source View'), # T: plugin name
		'description': _('''\
This plugin allows inserting 'Code Blocks' in the page. These will be
shown as emdedded widgets with syntax highlighting, line numbers etc.
'''), # T: plugin description
		'author': 'Jiří Janoušek',
		'help': 'Plugins:Source View',
		'object_types': (OBJECT_TYPE, ),
	}

	plugin_preferences = (
		# key, type, label, default
		('auto_indent', 'bool', _('Auto indenting'), True),
			# T: preference option for sourceview plugin
		('smart_home_end', 'bool', _('Smart Home key'), True),
			# T: preference option for sourceview plugin
		('highlight_current_line', 'bool', _('Highlight current line'), True),
			# T: preference option for sourceview plugin
		('show_right_margin', 'bool', _('Show right margin'), True),
			# T: preference option for sourceview plugin
		('right_margin_position', 'int', _('Right margin position'), 80, (1, 1000)),
			# T: preference option for sourceview plugin
		('tab_width', 'int', _('Tab width'), 4, (1, 80)),
			# T: preference option for sourceview plugin
	)

	@classmethod
	def check_dependencies(klass):
		check = not gtksourceview2 is None
		return check, [('gtksourceview2', check, True)]

	def __init__(self, config=None):
		PluginClass.__init__(self, config)
		self.connectto(self.preferences, 'changed', self.on_preferences_changed)

	def create_object(self, attrib, text, ui=None):
		'''Factory method for SourceViewObject objects'''
		obj = SourceViewObject(attrib, text, ui) # XXX
		obj.set_preferences(self.preferences)
		return obj

	def on_preferences_changed(self, preferences):
		'''Update preferences on open objects'''
		for obj in ObjectManager.get_active_objects(OBJECT_TYPE):
			obj.set_preferences(self.preferences)



@extends('MainWindow')
class MainWindowExtension(WindowExtension):

	uimanager_xml = '''
		<ui>
		<menubar name='menubar'>
			<menu action='insert_menu'>
				<placeholder name='plugin_items'>
					<menuitem action='insert_sourceview'/>
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
	def insert_sourceview(self):
		'''Inserts new SourceView'''
		lang = InsertCodeBlockDialog(self.window.ui).run() # XXX
		if not lang:
			return # dialog cancelled
		else:
			obj = SourceViewObject({'type': OBJECT_TYPE, 'lang': lang}, '', self.window.ui) # XXX
			pageview = self.window.pageview
			pageview.insert_object(pageview.view.get_buffer(), obj)


class InsertCodeBlockDialog(Dialog):

	def __init__(self, ui):
		Dialog.__init__(self, ui, _('Insert Code Block')) # T: dialog title
		names = sorted(LANGUAGES, key=lambda k: k.lower())
		self.add_form(
			(('lang', 'choice', _('Syntax'), names),) # T: input label
		)

		# Set previous used language
		self.uistate.define(lang=String(None))
		if 'lang' in self.uistate:
			for name, id in LANGUAGES.items():
				if self.uistate['lang'] == id:
					try:
						self.form['lang'] = name
					except ValueError:
						pass

					break

	def do_response_ok(self):
		name = self.form['lang']
		if name:
			self.result = LANGUAGES[name]
			self.uistate['lang'] = LANGUAGES[name]
		return True


class SourceViewObject(CustomObjectClass):

	def __init__(self, attrib, data, ui=None):
		if data.endswith('\n'):
			data = data[:-1]
			# If we have trailing \n it looks like an extra empty line
			# in the buffer, so we default remove one
		CustomObjectClass.__init__(self, attrib, data, ui)
		self.view = None

	def get_widget(self):
		if not self._widget:
			self._init_widget()
		return self._widget

	def _init_widget(self):
		from zim.gui.widgets import ScrolledWindow

		# SourceView scrolled window
		self.buffer = gtksourceview2.Buffer()
		self.buffer.set_text(self._data)
		self.buffer.connect('modified-changed', self.on_modified_changed)
		self.buffer.set_highlight_matching_brackets(True)
		self.buffer.set_modified(False)
		self._data = None
		self.view = gtksourceview2.View(self.buffer)
		self.view.modify_font(pango.FontDescription('monospace'))
		self.view.set_auto_indent(True)
		self.view.set_smart_home_end(True)
		self.view.set_highlight_current_line(True)
		self.view.set_right_margin_position(80)
		self.view.set_show_right_margin(True)
		self.view.set_tab_width(4)

		win = ScrolledWindow(self.view, gtk.POLICY_AUTOMATIC, gtk.POLICY_NEVER)
			# only horizontal scroll
		win.set_border_width(5)

		self._attrib.setdefault('lang', None)
		self._attrib.setdefault('linenumbers', 'true') # FIXME make boolean
		self.set_language(self._attrib['lang'], save=False)
		self.show_line_numbers(self._attrib['linenumbers'], save=False)

		self.view.connect('populate-popup', self.on_populate_popup)

		# simple toolbar
		#~ bar = gtk.HBox() # FIXME: use gtk.Toolbar stuff
		#~ lang_selector = gtk.combo_box_new_text()
		#~ lang_selector.append_text('(None)')
		#~ for l in lang_names: lang_selector.append_text(l)
		#~ try:
			#~ lang_selector.set_active(lang_ids.index(self._attrib['lang'])+1)
			#~ self.set_language(self._attrib['lang'] or None, False)
		#~ except (ValueError, KeyError):
			#~ lang_selector.set_active(0)
			#~ self.set_language(None, False)
		#~ lang_selector.connect('changed', self.on_lang_changed)
		#~ bar.pack_start(lang_selector, False, False)
	#~
		#~ line_numbers = gtk.ToggleButton('Line numbers')
		#~ try:
			#~ line_numbers.set_active(self._attrib['linenumbers']=='true')
			#~ self.show_line_numbers(self._attrib['linenumbers'], False)
		#~ except (ValueError, KeyError):
			#~ line_numbers.set_active(True)
			#~ self.show_line_numbers(True, False)
		#~ line_numbers.connect('toggled', self.on_line_numbers_toggled)
		#~ bar.pack_start(line_numbers, False, False)

		# TODO: other toolbar options
		# TODO: autohide toolbar if textbuffer is not active

		# Pack everything
		box = gtk.VBox()
		#~ box.pack_start(bar, False, False)
		box.pack_start(win)
		self._widget = CustomObjectBin()
		self._widget.set_has_cursor(True)
		self._widget.add(box)

		# Hook up integration with pageview cursor movement
		def on_grab_cursor(bin, position):
			begin, end = self.buffer.get_bounds()
			if position == POSITION_BEGIN:
				self.buffer.place_cursor(begin)
			else:
				self.buffer.place_cursor(end)
			self.view.grab_focus()

		def on_move_cursor(view, step_size, count, extend_selection):
			buffer = view.get_buffer()
			iter = buffer.get_iter_at_mark(buffer.get_insert())
			if (iter.is_start() or iter.is_end()) \
			and not extend_selection:
				if iter.is_start() and count < 0:
					self._widget.release_cursor(POSITION_BEGIN)
					return None
				elif iter.is_end() and count > 0:
					self._widget.release_cursor(POSITION_END)
					return None

			return None # let parent handle this signal

		self._widget.connect('grab-cursor', on_grab_cursor)
		self.view.connect('move-cursor', on_move_cursor)

		# Resize widget if parent TextView has been resized -- XXX
		self.ui.mainwindow.pageview.view.connect_after('size-allocate',
											self.on_parent_view_resized)

	def set_preferences(self, preferences):
		if self.view:
			self.view.set_auto_indent(preferences['auto_indent'])
			self.view.set_smart_home_end(preferences['smart_home_end'])
			self.view.set_highlight_current_line(preferences['highlight_current_line'])
			self.view.set_right_margin_position(preferences['right_margin_position'])
			self.view.set_show_right_margin(preferences['show_right_margin'])
			self.view.set_tab_width(preferences['tab_width'])

	def get_data(self):
		'''Returns data as text.'''
		if self._widget:
			buffer = self.view.get_buffer()
			bounds = buffer.get_bounds()
			text = buffer.get_text(bounds[0], bounds[1])
			text += '\n' # Make sure we always have a trailing \n
			return text
		return self._data

	def dump(self, format, dumper, linker=None):
		if format == "html":
			if 'lang' in self._attrib:
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
			if self._attrib['linenumbers'] == 'true':
				for i, l in enumerate(data.splitlines(1)):
					output.append('%i&nbsp;' % (i+1) + l)
			else:
				output.append(data)
			output.append('</pre>\n')
			return output
		return CustomObjectClass.dump(self, format, dumper, linker)

	def on_lang_changed(self, selector):
		'''Callback for language selector'''
		lang = selector.get_active()
		self.set_language(lang_ids[lang-1] if lang>0 else '')

	def set_language(self, lang, save=True):
		'''Set language in SourceView.'''
		if lang is None:
			self.buffer.set_language(None)
		else:
			self.buffer.set_language(lm.get_language(lang))
		if save:
			self._attrib['lang'] = lang
			self.set_modified(True)

	def on_line_numbers_toggled(self, button):
		'''Callback for toggling line numbers.'''
		self.show_line_numbers(button.get_active())

	def show_line_numbers(self, show, save=True):
		'''Toggles line numbers in SourceView.'''
		if isinstance(show, basestring): show = show == 'true'
		self.view.set_show_line_numbers(show)
		if save:
			self._attrib['linenumbers'] = 'true' if show else 'false'
			self.set_modified(True)

	def on_modified_changed(self, buffer):
		'''Requests saving date from TextBuffer.'''
		if buffer.get_modified():
			self.set_modified(True)
			buffer.set_modified(False)

	def on_parent_view_resized(self, view, size):
		'''Resizes widget if parent textview size has been changed.'''
		win = view.get_window(gtk.TEXT_WINDOW_TEXT)
		if win:

			vmargin =  2 * 5 + view.get_left_margin()+ view.get_right_margin() \
			+ 2 * self._widget.get_border_width()
			hmargin =  2 * 20 + 2 * self._widget.get_border_width()
			width, height = win.get_geometry()[2:4]
			#~ self._widget.set_size_request(width - vmargin, height - hmargin)
			self._widget.set_size_request(width - vmargin, -1)

	def on_populate_popup(self, view, menu):
		menu.prepend(gtk.SeparatorMenuItem())

		def activate_linenumbers(item):
			self.show_line_numbers(item.get_active())

		item = gtk.CheckMenuItem(_('Show Line Numbers'))
			# T: preference option for sourceview plugin
		item.set_active(self._attrib['linenumbers'] == 'true') # FIXME - make this attrib boolean
		item.connect_after('activate', activate_linenumbers)
		menu.prepend(item)


		def activate_lang(item):
			self.set_language(item.zim_sourceview_languageid)

		item = gtk.MenuItem(_('Syntax'))
		submenu = gtk.Menu()
		for lang in sorted(LANGUAGES, key=lambda k: k.lower()):
			langitem = gtk.MenuItem(lang)
			langitem.connect('activate', activate_lang)
			langitem.zim_sourceview_languageid = LANGUAGES[lang]
			submenu.append(langitem)
		item.set_submenu(submenu)
		menu.prepend(item)

		menu.show_all()

	# TODO: undo(), redo() stuff
