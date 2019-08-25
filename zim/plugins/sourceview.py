# -*- coding: UTF-8 -*-

# Copyright 2011 Jiří Janoušek <janousek.jiri@gmail.com>
# Copyright 2014-2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import logging

logger = logging.getLogger('zim.pugin.sourceview')


# This plugin can work without GUI for just the export
# Be nice about gtk, since it may not be present in a server CLI only version
try:
	from gi.repository import Gtk
	from gi.repository import Pango
except:
	Gtk = None

try:
	import gi
	gi.require_version('GtkSource', '3.0')
	from gi.repository import GtkSource
except:
	GtkSource = None

from zim.plugins import PluginClass, InsertedObjectTypeExtension
from zim.actions import action
from zim.utils import WeakSet
from zim.config import String, Boolean
from zim.formats.html import html_encode

from zim.gui.pageview import PageViewExtension
from zim.gui.widgets import Dialog, ScrolledWindow
from zim.gui.insertedobjects import InsertedObjectWidget, TextViewWidget


if GtkSource:
	lm = GtkSource.LanguageManager()
	lang_ids = lm.get_language_ids()
	lang_names = [lm.get_language(i).get_name() for i in lang_ids]

	LANGUAGES = dict((lm.get_language(i).get_name(), i) for i in lang_ids)
else:
	LANGUAGES = {}
#~ print LANGUAGES


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
		self._widgets = WeakSet()
		self.preferences = plugin.preferences
		InsertedObjectTypeExtension.__init__(self, plugin, objmap)
		self.connectto(self.preferences, 'changed', self.on_preferences_changed)

	def new_model_interactive(self, parent, notebook, page):
		lang, linenumbers = InsertCodeBlockDialog(parent).run()
		if lang is None:
			raise ValueError # dialog cancelled
		else:
			attrib = self.parse_attrib({'lang': lang, 'linenumbers': linenumbers})
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
		self.view.modify_font(Pango.FontDescription('monospace'))
		self.view.set_auto_indent(True)
		self.view.set_smart_home_end(True)
		self.view.set_highlight_current_line(True)
		self.view.set_right_margin_position(80)
		self.view.set_show_right_margin(True)
		self.view.set_tab_width(4)
		self.view.set_show_line_numbers(self.buffer.object_attrib['linenumbers'])

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
		self.view.set_auto_indent(preferences['auto_indent'])
		self.view.set_smart_home_end(preferences['smart_home_end'])
		self.view.set_highlight_current_line(preferences['highlight_current_line'])
		self.view.set_right_margin_position(preferences['right_margin_position'])
		self.view.set_show_right_margin(preferences['show_right_margin'])
		self.view.set_tab_width(preferences['tab_width'])

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
		self.result = (None, None)
		self.uistate.define(lang=String(None))
		self.uistate.define(line_numbers=Boolean(True))
		defaultlang = self.uistate['lang']

		menu = {}
		for l in sorted(LANGUAGES, key=lambda k: k.lower()):
			key = l[0].upper()
			if not key in menu:
				menu[key] = []
			menu[key].append(l)

		model = Gtk.TreeStore(str)
		defaultiter = None
		for key in sorted(menu):
			iter = model.append(None, [key])
			for lang in menu[key]:
				myiter = model.append(iter, [lang])
				if LANGUAGES[lang] == defaultlang:
					defaultiter = myiter

		hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
		hbox.set_spacing(5)
		label = Gtk.Label(_('Syntax') +':') # T: input label
		hbox.add(label)

		combobox = Gtk.ComboBox.new_with_model(model)
		renderer_text = Gtk.CellRendererText()
		combobox.pack_start(renderer_text, True)
		combobox.add_attribute(renderer_text, "text", 0)
		if defaultiter is not None:
			combobox.set_active_iter(defaultiter)
		hbox.add(combobox)
		self.combobox = combobox
		self.vbox.add(hbox)
		self.checkbox = Gtk.CheckButton(_('Display line numbers')) # T: input checkbox
		self.checkbox.set_active(self.uistate['line_numbers'])
		self.vbox.add(self.checkbox)

	def do_response_ok(self):
		model = self.combobox.get_model()
		iter = self.combobox.get_active_iter()

		if iter is not None:
			name = model[iter][0]
			self.uistate['lang'] = LANGUAGES[name]
			self.uistate['line_numbers'] = self.checkbox.get_active()
			self.result = (self.uistate['lang'], self.uistate['line_numbers'])
			return True
		else:
			return False # no syntax selected
