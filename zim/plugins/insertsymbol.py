
# Copyright 2010 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from gi.repository import Gtk
import logging

from zim.plugins import PluginClass
from zim.actions import action
from zim.config import ConfigManager

from zim.gui.pageview import PageViewExtension
from zim.gui.widgets import Dialog, InputEntry, ScrolledWindow
from zim.gui.applications import edit_config_file

logger = logging.getLogger('zim.plugins.insertsymbol')


VERBATIM = 'code'
VERBATIM_BLOCK = 'pre'


class InsertSymbolPlugin(PluginClass):

	plugin_info = {
		'name': _('Insert Symbol'), # T: plugin name
		'description': _('''\
This plugin adds the 'Insert Symbol' dialog and allows
auto-formatting typographic characters.

This is a core plugin shipping with zim.
'''), # T: plugin description
		'author': 'Jaap Karssenberg',
		'help': 'Plugins:Insert Symbol',
	}

	def __init__(self):
		PluginClass.__init__(self)
		self.symbols = {}
		self.symbol_order = []

	def load_file(self):
		self.symbols = {}
		self.symbol_order = []
		file = ConfigManager.get_config_file('symbols.list')
		for line in file.readlines():
			line = line.strip()
			if not line or line.startswith('#'):
				continue
			try:
				if '#' in line:
					line, _ = line.split('#', 1)
					line = line.strip()
				shortcut, code = line.split()
				symbol = chr(int(code))
				if not shortcut in self.symbols:
					self.symbols[shortcut] = symbol
					self.symbol_order.append(shortcut)
				else:
					logger.exception('Shortcut defined twice: %s', shortcut)
			except:
				logger.exception('Could not parse symbol: %s', line)

	def get_symbols(self):
		for shortcut in self.symbol_order:
			symbol = self.symbols[shortcut]
			yield symbol, shortcut


class InsertSymbolPageViewExtension(PageViewExtension):

	def __init__(self, plugin, pageview):
		PageViewExtension.__init__(self, plugin, pageview)
		self.connectto(pageview.textview, 'end-of-word')
		if not plugin.symbols:
			plugin.load_file()

	@action(_('Sy_mbol...'), menuhints='insert') # T: menu item
	def insert_symbol(self):
		'''Run the InsertSymbolDialog'''
		InsertSymbolDialog(self.pageview, self.plugin, self.pageview).run()

	def on_end_of_word(self, textview, start, end, word, char, editmode):
		'''Handler for the end-of-word signal from the textview'''
		# We check for non-space char because e.g. typing "-->" will
		# emit end-of-word with "--" as word and ">" as character.
		# This should be distinguished from the case when e.g. typing
		# "-- " emits end-of-word with "--" as word and " " (space) as
		# the char.
		if VERBATIM in editmode \
		or VERBATIM_BLOCK in editmode \
		or not (char.isspace() or char == ';'):
			return

		symbol = self.plugin.symbols.get(word)
		if not symbol and word.count('\\') == 1:
			# do this after testing the whole word, we have e.g. "=\="
			# also avoid replacing end of e.g. "C:\foo\bar\left",
			# so match exactly one "\"
			prefix, key = word.split('\\', 1)
			symbol = self.plugin.symbols.get('\\' + key)
			if symbol:
				start.forward_chars(len(prefix))

		if not symbol:
			return

		# replace word with symbol
		buffer = textview.get_buffer()
		mark = buffer.create_mark(None, end, left_gravity=False)
		if char == ';':
			end = end.copy()
			end.forward_char() # include the ';' in the delete
			buffer.delete(start, end)
		else:
			buffer.delete(start, end)
		iter = buffer.get_iter_at_mark(mark)
		buffer.insert(iter, symbol)
		buffer.delete_mark(mark)

		# block other handlers
		textview.stop_emission('end-of-word')


class InsertSymbolDialog(Dialog):

	def __init__(self, parent, plugin, pageview):
		Dialog.__init__(
			self,
			parent,
			_('Insert Symbol'), # T: Dialog title
			button=_('_Insert'),  # T: Button label
			defaultwindowsize=(350, 400)
		)
		self.plugin = plugin
		self.pageview = pageview
		if not plugin.symbols:
			plugin.load_file()

		self.textentry = InputEntry()
		self.vbox.pack_start(self.textentry, False, True, 0)

		model = Gtk.ListStore(str, str) # text, shortcut
		self.iconview = Gtk.IconView(model)
		self.iconview.set_text_column(0)
		self.iconview.set_column_spacing(0)
		self.iconview.set_row_spacing(0)
		self.iconview.set_property('has-tooltip', True)
		self.iconview.set_property('activate-on-single-click', True)
		self.iconview.connect('query-tooltip', self.on_query_tooltip)
		self.iconview.connect('item-activated', self.on_activated)

		swindow = ScrolledWindow(self.iconview)
		self.vbox.pack_start(swindow, True, True, 0)

		button = Gtk.Button.new_with_mnemonic(_('_Edit')) # T: Button label
		button.connect('clicked', self.on_edit)
		self.action_area.add(button)
		self.action_area.reorder_child(button, 0)

		self.load_symbols()

	def load_symbols(self):
		model = self.iconview.get_model()
		model.clear()
		for symbol, shortcut in self.plugin.get_symbols():
			model.append((symbol, shortcut))

	def on_query_tooltip(self, iconview, x, y, keyboard, tooltip):
		if keyboard:
			return False

		x, y = iconview.convert_widget_to_bin_window_coords(x, y)
		path = iconview.get_path_at_pos(x, y)
		if path is None:
			return False

		model = iconview.get_model()
		iter = model.get_iter(path)
		text = model.get_value(iter, 1)
		if not text:
			return False

		tooltip.set_text(text)
		return True

	def on_activated(self, iconview, path):
		model = iconview.get_model()
		iter = model.get_iter(path)
		text = model.get_value(iter, 0)
		pos = self.textentry.get_position()
		self.textentry.insert_text(text, pos)
		self.textentry.set_position(pos + len(text))

	def on_edit(self, button):
		file = ConfigManager.get_config_file('symbols.list')
		if edit_config_file(self, file):
			self.plugin.load_file()
			self.load_symbols()

	def run(self):
		self.iconview.grab_focus()
		Dialog.run(self)

	def do_response_ok(self):
		text = self.textentry.get_text()
		textview = self.pageview.textview
		buffer = textview.get_buffer()
		buffer.insert_at_cursor(text)
		return True
