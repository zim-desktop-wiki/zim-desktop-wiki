# -*- coding: UTF-8 -*-

# Copyright 2011 Jiří Janoušek <janousek.jiri@gmail.com>
# Copyright 2014-2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import logging

logger = logging.getLogger('zim.plugins.sourceview')

import weakref

# This plugin can work without GUI for just the export
# Be nice about gtk, since it may not be present in a server CLI only version
try:
	from gi.repository import Gtk
	from gi.repository import Pango
except:
	Gtk = None

try:
	import gi

	# Allow using GtkSourceView 4.x (requires Gtk 3.24) for systems that no
	# longer provide 3.x.
	try:
		gi.require_version('GtkSource', '3.0')
	except:
		gi.require_version('GtkSource', '4')

	from gi.repository import GtkSource
except:
	GtkSource = None

from zim.plugins import PluginClass, InsertedObjectTypeExtension, PLUGIN_FOLDER
from zim.actions import action
from zim.config import String, Boolean, ConfigManager
from zim.formats.html import html_encode

from zim.gui.widgets import Dialog, InputEntry, ScrolledWindow
from zim.gui.insertedobjects import TextViewWidget

if GtkSource:
	lm = GtkSource.LanguageManager()
	lang_ids = lm.get_language_ids()
	lang_names = [lm.get_language(i).get_name() for i in lang_ids]

	LANGUAGES = dict((lm.get_language(i).get_name(), i) for i in lang_ids)

	ssm = GtkSource.StyleSchemeManager()

	# add an optional path in PLUGIN_FOLDER  where the user can set his
	# custom styles
	plugin_name = __name__.split('.')[-1]
	ssm.append_search_path(PLUGIN_FOLDER.subdir(plugin_name).path)
	# ~ print(ssm.get_search_path())

	STYLES = ssm.get_scheme_ids()
	if not STYLES:
		logger.exception('Themes for the SourceView Plugin, normally in %s are not found', str(ssm.get_search_path()))
else:
	LANGUAGES = {}
#~ print LANGUAGES
	STYLES = []
# ~ print (STYLES)


class SourceViewPlugin(PluginClass):

	plugin_info = {
		'name': _('Source View'), # T: plugin name
		'description': _('''\
This plugin allows inserting 'Code Blocks' in the page. These will be
shown as embedded widgets with syntax highlighting, line numbers etc.
'''), # T: plugin description
		'author': 'Jiří Janoušek',
		'help': 'Plugins:Source View',
	}

	global WRAP_NONE, WRAP_WORD_CHAR, WRAP_CHAR, WRAP_WORD # Hack - to make sure translation is loaded
	WRAP_NONE = _('Never wrap lines') # T: option value
	WRAP_WORD_CHAR = _('Try wrap at word boundaries or character') # T: option value
	WRAP_CHAR = _('Always wrap at character') # T: option value
	WRAP_WORD = _('Always wrap at word boundaries') # T: option value

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
		('border_width', 'int', _('Border width'), 3, (1, 20)),
			# T: preference option for sourceview plugin
		('wrap_mode', 'choice', _('Text wrap mode'), WRAP_WORD_CHAR, (WRAP_NONE, WRAP_WORD_CHAR, WRAP_CHAR, WRAP_WORD)),
			# T: preference option for sourceview plugin
		('theme', 'choice', _('Theme'), STYLES[0] if STYLES else 'not found',
										STYLES if STYLES else ['not found']),
			# T: preference option for sourceview plugin
	)

	@classmethod
	def check_dependencies(klass):
		check = Gtk is None or not GtkSource is None
		return check, [('GtkSourceView', check, True)]


class SourceViewObjectType(InsertedObjectTypeExtension):

	name = 'code'

	label = _('Code Block') # T: menu item

	object_attr = {
		'lang': String(None),
		'linenumbers': Boolean(True),
	}

	def __init__(self, plugin, objmap):
		self._widgets = weakref.WeakSet()
		self.preferences = plugin.preferences
		super().__init__(plugin, objmap)
		self.connectto(self.preferences, 'changed', self.on_preferences_changed)

	def new_model_interactive(self, parent, notebook, page):
		id, lang, linenumbers = InsertCodeBlockDialog(parent).run()
		if lang is None:
			raise ValueError # dialog cancelled
		else:
			attrib = self.parse_attrib({
				'id': id,
				'lang': lang,
				'linenumbers': linenumbers
			})
			return SourceViewBuffer(attrib, '')

	def model_from_data(self, notebook, page, attrib, text):
		return SourceViewBuffer(attrib, text)

	def data_from_model(self, buffer):
		return buffer.get_object_data()

	def create_widget(self, buffer):
		widget = SourceViewWidget(buffer)
		widget.set_preferences(self.preferences)
		self._widgets.add(widget)
		return widget

	def on_preferences_changed(self, preferences):
		for widget in self._widgets:
			widget.set_preferences(preferences)

	def format_html(self, dumper, attrib, data):
		# to use highlight.js add the following to your template:
		#<link rel="stylesheet" href="http://cdnjs.cloudflare.com/ajax/libs/highlight.js/9.5.0/styles/default.min.css">
		#<script src="http://cdnjs.cloudflare.com/ajax/libs/highlight.js/9.5.0/highlight.min.js"></script>
		#<script>hljs.initHighlightingOnLoad();</script>
		#Map GtkSourceView language ids match with Highlight.js language ids.
		#http://packages.ubuntu.com/precise/all/libGtkSource.0-common/filelist
		#http://highlightjs.readthedocs.io/en/latest/css-classes-reference.html
		sh_map = {'dosbatch': 'dos'}
		sh_lang = sh_map[attrib['lang']] if attrib['lang'] in sh_map else attrib['lang']
		# TODO: some template instruction to be able to use other highlighters as well?
		output = ['<pre><code class="%s">' % html_encode(sh_lang)] # for syntaxhigligther
		#class="brush: language;" works with SyntaxHighlighter 2.0.278, 3 & 4
		#output = ['<pre class="brush: %s;">' % html_encode(sh_lang)] # for syntaxhigligther

		output.append(html_encode(data))
		output.append('</code></pre>\n')

		return output


if GtkSource is not None:
	_bufferclass = GtkSource.Buffer
else:
	_bufferclass = object # avoid import error


class SourceViewBuffer(_bufferclass):

	def __init__(self, attrib, text):
		#logger.debug("SourceViewBuffer attrib=%r", attrib)
		GtkSource.Buffer.__init__(self)
		self.set_highlight_matching_brackets(True)
		if attrib['lang']:
			self._set_language(attrib['lang'])

		self.object_attrib = attrib

		if text.endswith('\n'):
			text = text[:-1]
			# If we have trailing \n it looks like an extra empty line
			# in the buffer, so we default remove one
		self.set_text(text)

	def set_show_line_numbers(self, show_line_numbers):
		self.object_attrib['linenumbers'] = show_line_numbers
		self.emit('changed')

	def set_language(self, lang):
		self.object_attrib['lang'] = lang
		self._set_language(lang)
		self.emit('changed')

	def _set_language(self, lang):
		try:
			GtkSource.Buffer.set_language(self, lm.get_language(lang))
		except:
			logger.exception('Could not set language for sourceview: %s', lang)

	def get_object_data(self):
		start, end = self.get_bounds()
		text = start.get_text(end)
		text += '\n' # Make sure we always have a trailing \n
		return self.object_attrib, text


class SourceViewWidget(TextViewWidget):

	def _init_view(self):
		self.buffer.object_attrib.connect('changed', self.on_attrib_changed)

		self.view = GtkSource.View()
		self.view.set_buffer(self.buffer)
		self.view.set_auto_indent(True)
		self.view.set_smart_home_end(True)
		self.view.set_highlight_current_line(True)
		self.view.set_right_margin_position(80)
		self.view.set_show_right_margin(True)
		self.view.set_tab_width(4)
		self.view.set_show_line_numbers(self.buffer.object_attrib['linenumbers'])
		self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
		self.view.set_border_width(3)

		self.WRAP_MODE = {
			WRAP_NONE: Gtk.WrapMode.NONE,
			WRAP_WORD_CHAR: Gtk.WrapMode.WORD_CHAR,
			WRAP_CHAR: Gtk.WrapMode.CHAR,
			WRAP_WORD: Gtk.WrapMode.WORD,
		}

		text_style = ConfigManager.get_config_dict('style.conf')
		try:
			font = text_style['Tag code']['family']
		except KeyError:
			font = 'monospace'
		finally:
			self.view.modify_font(Pango.FontDescription(font))

		# simple toolbar
		#~ bar = Gtk.HBox() # FIXME: use Gtk.Toolbar stuff
		#~ lang_selector = Gtk.ComboBoxText()
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

		#~ line_numbers = Gtk.ToggleButton('Line numbers')
		#~ try:
			#~ line_numbers.set_active(self._attrib['linenumbers']=='true')
			#~ self.show_line_numbers(self._attrib['linenumbers'], False)
		#~ except (ValueError, KeyError):
			#~ line_numbers.set_active(True)
			#~ self.show_line_numbers(True, False)
		#~ line_numbers.connect('toggled', self.on_line_numbers_toggled)
		#~ bar.pack_start(line_numbers, False, False)
		#~ self.add_header(bar)

		# TODO: other toolbar options
		# TODO: autohide toolbar if textbuffer is not active

		win = ScrolledWindow(self.view, Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER, Gtk.ShadowType.NONE)
		self.add(win)

		self.view.connect('populate-popup', self.on_populate_popup)

	def set_preferences(self, preferences):

		# set the style scheme
		theme = preferences['theme']
		try:
			style_scheme = ssm.get_scheme(theme)
			self.buffer.set_style_scheme(style_scheme)
		except:
			logger.exception('Could not set theme for sourceview: %s', theme)

		# set other preferences
		self.view.set_auto_indent(preferences['auto_indent'])
		self.view.set_smart_home_end(preferences['smart_home_end'])
		self.view.set_highlight_current_line(preferences['highlight_current_line'])
		self.view.set_right_margin_position(preferences['right_margin_position'])
		self.view.set_show_right_margin(preferences['show_right_margin'])
		self.view.set_tab_width(preferences['tab_width'])
		self.view.set_border_width(preferences['border_width'])
		self.view.set_wrap_mode(self.WRAP_MODE[preferences['wrap_mode']])

	def on_attrib_changed(self, attrib):
		self.view.set_show_line_numbers(attrib['linenumbers'])

	def on_populate_popup(self, view, menu):
		menu.prepend(Gtk.SeparatorMenuItem())

		def activate_linenumbers(item):
			self.buffer.set_show_line_numbers(item.get_active())

		item = Gtk.CheckMenuItem(_('Show Line Numbers'))
			# T: preference option for sourceview plugin
		item.set_active(self.buffer.object_attrib['linenumbers'])
		item.set_sensitive(self.view.get_editable())
		item.connect_after('activate', activate_linenumbers)
		menu.prepend(item)

		def activate_lang(item):
			self.buffer.set_language(item.zim_sourceview_languageid)

		item = Gtk.MenuItem.new_with_mnemonic(_('Syntax'))
		item.set_sensitive(self.view.get_editable())
		submenu = Gtk.Menu()
		for lang in sorted(LANGUAGES, key=lambda k: k.lower()):
			langitem = Gtk.MenuItem.new_with_mnemonic(lang)
			langitem.connect('activate', activate_lang)
			langitem.zim_sourceview_languageid = LANGUAGES[lang]
			submenu.append(langitem)
		item.set_submenu(submenu)
		menu.prepend(item)

		menu.show_all()


class InsertCodeBlockDialog(Dialog):

	def __init__(self, parent):
		Dialog.__init__(self, parent, _('Insert Code Block')) # T: dialog title
		self.result = (None, None, None)
		self.uistate.define(id=String(None))
		self.uistate.define(lang=String(None))
		self.uistate.define(line_numbers=Boolean(True))

		grid = Gtk.Grid()
		grid.set_column_spacing(5)
		grid.set_row_spacing(5)

		label = Gtk.Label(_('Syntax') + ':') # T: input label
		grid.add(label)

		self.combobox = Gtk.ComboBox.new_with_model_and_entry(self.init_combobox_model())
		self.combobox.set_entry_text_column(0)
		entry = self.combobox.get_child()
		entry.set_activates_default(True)  # Pressing enter will activate the default button (here: ok-button)

		completion = Gtk.EntryCompletion()
		completion.set_model(self.init_autocomplete_model())
		completion.set_text_column(0)
		completion.set_minimum_key_length(0)
		entry.set_completion(completion)

		defaultlang = self.init_default_language()
		if defaultlang:
			entry.set_text(defaultlang)

		self.combobox.connect("changed", self.on_combobox_changed)

		grid.attach(self.combobox, 1, 0, 1, 1)

		label = Gtk.Label(_('Id') + ':') # T: input label for object ID
		grid.attach(label, 0, 1, 1, 1)
		self.entry = InputEntry()
		grid.attach(self.entry, 1, 1, 1, 1)

		self.checkbox = Gtk.CheckButton(_('Display line numbers')) # T: input checkbox
		self.checkbox.set_active(self.uistate['line_numbers'])
		grid.attach(self.checkbox, 1, 2, 1, 1)

		self.vbox.add(grid)

		# Set ok button as default.
		self.btn_ok = self.get_widget_for_response(response_id=Gtk.ResponseType.OK)
		self.btn_ok.set_can_default(True)
		self.btn_ok.grab_default()
		self.btn_ok.set_sensitive(defaultlang is not None)

	def init_default_language(self):
		for lang in sorted(LANGUAGES, key=lambda k: k.lower()):
			if LANGUAGES[lang] == self.uistate['lang']:
				return lang
		return None

	def init_combobox_model(self):
		menu = {}
		for l in sorted(LANGUAGES, key=lambda k: k.lower()):
			key = l[0].upper()
			if not key in menu:
				menu[key] = []
			menu[key].append(l)
		model = Gtk.TreeStore(str)
		for key in sorted(menu):
			iter = model.append(None, [key])
			for lang in menu[key]:
				model.append(iter, [lang])
		return model

	def init_autocomplete_model(self):
		store = Gtk.TreeStore(str)
		for lang in sorted(LANGUAGES, key=lambda k: k.lower()):
			store.append(None, [lang])
		return store

	def on_combobox_changed(self, widget):
		""" Checks whether the text entry in combobox is valid and enables/disables the ok-button. """
		self.btn_ok = self.get_widget_for_response(response_id=Gtk.ResponseType.OK)
		self.btn_ok.set_sensitive(widget.get_child().get_text() in LANGUAGES)

	def do_response_ok(self):
		if self.combobox.get_child().get_text() in LANGUAGES:
			self.uistate['lang'] = LANGUAGES[self.combobox.get_child().get_text()]
			self.uistate['id'] = self.entry.get_text()
			self.uistate['line_numbers'] = self.checkbox.get_active()
			self.result = (self.uistate['id'], self.uistate['lang'], self.uistate['line_numbers'])
			return True
		else:
			return False # no syntax selected
