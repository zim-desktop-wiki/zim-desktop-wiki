#
# Copyright 2020 Thomas Engel <thomas.engel.web@gmail.de>
# License:  same as zim (gpl)
#
# DESCRIPTION:
#
# Zim plugin to search and execute menu entries via dialog.
#
# CHANGELOG:
#
# 2020-11-22 1st working version
# 2020-11-23 Improved usability
# 2020-12-13 Improved code and usability
# 2020-12-29 Added history support
# 2021-01-01 Improved usability
# 2021-01-03 Improved usability
# 2021-01-23 Limited history feature to only contain last entry
# 2021-01-23 Added ability to show keybindings in dialog
# 2021-02-18 Fixed display of keybindings
# 2021-03-13 Improved search ability
# 2021-04-16 Renamed project from "Zim Dash" to "Zim Command Palette" and changed keybinding from alt-x to ctrl-shift-p

import logging

import gi

gi.require_version('Gdk', '3.0')
gi.require_version('Gtk', '3.0')
from gi.repository import Gdk, Gtk

from zim.actions import action
from zim.config import String
from zim.gui.mainwindow import MainWindowExtension
from zim.gui.widgets import Dialog
from zim.plugins import PluginClass

logger = logging.getLogger('zim.plugins.command_palette')


class CommandPalettePlugin(PluginClass):
	plugin_info = {
		'name': _('Command Palette'),  # T: plugin name
		'description': _('This plugin opens a search dialog to allow quickly '
						 'executing menu entries.'),  # T: plugin description
		'author': 'Thomas Engel <thomas.engel.web@gmail.com>',
		'help': 'Plugins:CommandPalette',
	}


class CommandPaletteMainWindowExtension(MainWindowExtension):
	""" Listener for the show command palette dialog shortcut. """

	def __init__(self, plugin, window):
		MainWindowExtension.__init__(self, plugin, window)
		self.window = window

	def _init_store(self):
		""" Construct the store containing all menu-items and associated actions. """
		store = Gtk.ListStore(str, object, str)
		for label, item in ZimMenuBarCrawler().run(self.window.menubar).items():
			action = item[0]
			shortcut = item[1]
			store.append((label, action, shortcut))
		return store

	@action('', accelerator='<ctrl><shift>p', menuhints='accelonly')
	def do_show_command_palette_dialog(self):
		store = self._init_store()
		dialog = ZimCommandPaletteDialog(self.window, store, self.plugin.preferences)
		if dialog.run() == Gtk.ResponseType.OK:
			dialog.action()
			# The return value is only relevant for the on_key_press_event function and makes sure that the
			# pressed key is not processed any further.
			return True


class ZimMenuBarCrawler:
	""" Crawler for Gtk.MenuBar to return all item labels and associated actions in a dictionary. """

	# Separator ">>" used between menu item names e.g. "File >> New Page..."
	SEPARATOR = u'\u0020\u0020\u00BB\u0020\u0020'

	def run(self, menu_bar: Gtk.MenuBar):

		result = {}

		def crawl(container: Gtk.MenuItem, path: str):
			if container.get_submenu():
				for child in container.get_submenu():
					if hasattr(child, "get_label") and child.get_label():
						child_path = path + ZimMenuBarCrawler.SEPARATOR + child.get_label().replace("_", "")
						crawl(child, child_path)
			else:
				accel_name = None
				if container.get_accel_path():
					accel = Gtk.AccelMap.lookup_entry(container.get_accel_path())[1]
					accel_name = Gtk.accelerator_get_label(accel.accel_key, accel.accel_mods)
				result[path] = [container.activate, accel_name]

		for child in menu_bar:
			if hasattr(child, "get_label") and child.get_label():
				crawl(child, child.get_label().replace("_", ""))

		return result


class ZimCommandPaletteDialog(Dialog):
	""" A search dialog with auto-complete feature. """

	def __init__(self, parent, store, preferences):
		title = _('Command Palette')
		Dialog.__init__(self, parent, title)

		self.uistate.define(last_entry=String(None))
		self.action = None
		self.store = store
		self.entries = {item[0]: item[1] for item in self.store}  # { label: action }

		# Configure completion for search field.
		completion = Gtk.EntryCompletion()
		completion.set_model(store)

		cell_shortcut = Gtk.CellRendererText()
		completion.pack_end(cell_shortcut, False)
		completion.add_attribute(cell_shortcut, 'text', 2)

		completion.set_text_column(0)
		completion.set_minimum_key_length(0)
		completion.connect("match-selected", self.on_match_selected)

		def match_anywhere(_completion, _entrystr, _iter, _data):
			""" Match any part. """
			_modelstr = _completion.get_model()[_iter][0].lower()
			for part in _entrystr.split():
				if part not in _modelstr:
					return False
			return True

		completion.set_match_func(match_anywhere, None)

		self.hbox = Gtk.HBox()

		# Add search field.
		self.txt_search = Gtk.SearchEntry(hexpand=True, margin=2)
		self.txt_search.set_activates_default(True)  # Make ENTER key press trigger the OK button.
		self.txt_search.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, Gtk.STOCK_FIND)
		self.txt_search.set_placeholder_text("Search commands")
		self.txt_search.set_completion(completion)

		last_entry = self.init_last_entry()
		if last_entry:
			self.txt_search.set_text(last_entry)

		self.txt_search.connect('search-changed', self.do_validate, parent)
		self.txt_search.connect("key-press-event", self.on_key_pressed, parent)

		# Add ok button.
		self.btn_ok = self.get_widget_for_response(response_id=Gtk.ResponseType.OK)
		self.btn_ok.set_can_default(True)
		self.btn_ok.grab_default()
		self.btn_ok.set_sensitive(last_entry is not None)

		# Configure dialog.
		self.set_modal(True)
		self.set_default_size(380, 100)
		self.hbox.pack_start(self.txt_search, True, True, 0)
		self.vbox.pack_start(self.hbox, True, True, 0)

		# Set focus to search field
		self.txt_search.grab_focus()

	def init_last_entry(self):
		"""
		Returns either the entry which was selected by the user in the last dialog call or None, when there never was
		any selection at all or when the selected entry does not exist anymore (e.g. disabled plugin).
		"""
		if self.uistate['last_entry'] in self.entries:
			return self.uistate['last_entry']
		return None

	def on_key_pressed(self, widget, event, data=None):
		""" Listener for gtk.Entry key press events. """
		if event.keyval == Gdk.KEY_Up or event.keyval == Gdk.KEY_Down:
			# Open popup-menu with suggestions when pressing arrow-up/arrow-down key.
			#
			# Note: The popup-menu is only shown when the text field contains at least one character. This bypasses
			#       a bug which appears when the text field is empty in which case the entries shown in the popup menu
			#       can't be selected by pressing the ENTER key.
			if len(self.txt_search.get_text()) > 0:
				self.txt_search.emit('changed')
			return True
		elif event.keyval == Gdk.KEY_Escape:
			self.close()
			return True
		return False

	def on_match_selected(self, completion, model, iter):
		""" Directly close dialog when selecting an entry in the completion list. """
		logger.debug("ZimCommandPalettePlugin: Match selected from popup menu: {}".format(model[iter][0]))
		self.txt_search.set_text(model[iter][0])
		if self.do_response_ok():
			self.close()

	def do_validate(self, entry, data):
		""" Validating selected text entry and enable/disable ok button. """
		self.btn_ok.set_sensitive(entry.get_text() in self.entries)

	def do_response_ok(self):
		""" Finishing up when activating the ok button. """
		if self.txt_search.get_text() in self.entries:
			self.action = self.entries[self.txt_search.get_text()]
			self.uistate['last_entry'] = self.txt_search.get_text()
			self.result = Gtk.ResponseType.OK
			return True
		else:
			logger.error("ZimCommandPalettePlugin: Aborting, invalid entry selected: {}".format(self.txt_search.get_text()))
