# -*- coding: utf-8 -*-

# Copyright 2011 Jiří Janoušek <janousek.jiri@gmail.com>

import gtk
import pango

try:
	import gtksourceview2
except:
	gtksourceview2 = None

from zim.plugins import PluginClass
from zim.objectmanager import ObjectManager, CustomObjectClass
from zim.gui.widgets import Dialog, CustomObjectBin
from zim.formats.html import html_encode


lm = gtksourceview2.LanguageManager()
lang_ids = lm.get_language_ids()
lang_names = [lm.get_language(i).get_name() for i in lang_ids]

LANGUAGES = dict((lm.get_language(i).get_name(), i) for i in lang_ids)
#~ print LANGUAGES

OBJECT_TYPE = 'code'

ui_xml = '''
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

ui_actions = (
	# name, stock id, label, accelerator, tooltip, readonly
	('insert_sourceview', None, _('Code Block'), None, '', False), # T: menu item
)



class SourceViewObject(CustomObjectClass):

	def __init__(self, attrib, data, ui=None):
		CustomObjectClass.__init__(self, attrib, data, ui)
		if self.ui and self.ui.ui_type == 'gtk':
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
			win = gtk.ScrolledWindow()
			win.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_NEVER) # only H scroll
			win.set_shadow_type(gtk.SHADOW_ETCHED_IN)
			win.add(self.view)
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
			self._widget.add(box)

			# Resize widget if parent TextView has been resized
			self.ui.mainwindow.pageview.view.connect_after('size-allocate',
												self.on_parent_view_resized)
		else:
			self.view = None

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
			return buffer.get_text(bounds[0], bounds[1])
		return self._data

	def dump(self, format, dumper, linker=None):
		if format == "html":
			if 'lang' in self._attrib:
				# class="brush: language;" works with SyntaxHighlighter 2.0.278
				# by Alex Gorbatchev <http://alexgorbatchev.com/SyntaxHighlighter/>
				# TODO: not all GtkSourceView language ids match with SyntaxHighlighter
				# language ids.
				output = ['<pre class="brush: %s;">\n' % html_encode(self._attrib['lang'])]
			else:
				output = ['<pre>\n']
			output.append(html_encode(self.get_data()))
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
		('smart_home_end', 'bool', _('Smart Home key'), True),
		('highlight_current_line', 'bool', _('Highlight current line'), True),
		('show_right_margin', 'bool', _('Show right margin'), True),
		('right_margin_position', 'int', _('Right margin position'), 80, (1, 1000)),
		('tab_width', 'int', _('Tab width'), 4, (1, 80)),
	)

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		ObjectManager.register_object(OBJECT_TYPE, self.create_object)

	def create_object(self, attrib, text, ui=None):
		'''Factory method for SourceViewObject objects'''
		obj = SourceViewObject(attrib, text, ui)
		obj.set_preferences(self.preferences)
		return obj

	def do_preferences_changed(self):
		'''Update preferences on open objects'''
		for obj in ObjectManager.get_active_objects(OBJECT_TYPE):
			obj.set_preferences(self.preferences)

	def initialize_ui(self, ui):
		if self.ui.ui_type == 'gtk':
			self.ui.add_actions(ui_actions, self)
			self.ui.add_ui(ui_xml, self)

	#def finalize_ui(self, ui):
	#	if self.ui.ui_type == 'gtk':
	#		pass

	def disconnect(self):
		ObjectManager.unregister_object('source')
		PluginClass.disconnect(self)

	def insert_sourceview(self):
		'''Inserts new SourceView'''
		lang = InsertCodeBlockDialog(self.ui).run()
		if not lang:
			return # dialog cancelled
		else:
			obj = SourceViewObject({'type': OBJECT_TYPE, 'lang': lang}, '', self.ui)
			pageview = self.ui.mainwindow.pageview
			pageview.insert_object(pageview.view.get_buffer(), obj)

	@classmethod
	def check_dependencies(klass):
		check = not gtksourceview2 is None
		return check, [('gtksourceview2', check, True)]


class InsertCodeBlockDialog(Dialog):

	def __init__(self, ui):
		Dialog.__init__(self, ui, _('Insert Code Block')) # T: dialog title
		names = sorted(LANGUAGES, key=lambda k: k.lower())
		self.add_form(
			(('lang', 'choice', _('Syntax'), names),) # T: input label
		)

		# Set previous used language
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
		self.result = LANGUAGES[name]
		self.uistate['lang'] = LANGUAGES[name]
		return True
