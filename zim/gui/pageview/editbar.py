# Copyright 2020 - 2022 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from gi.repository import Gtk
from gi.repository import Pango
from gi.repository import Gio

import logging

from zim.plugins import PluginManager, list_actions
from zim.signals import ConnectorMixin


logger = logging.getLogger('zim.gui.pageview')


class EditActionMixin(object):
	'''Base class for EditBar and ToolBar implementations that want to include
	formatting actions
	'''

	def __init__(self, pageview):
		self.pageview = pageview
		self.edit_format_actions = (
			pageview.toggle_format_strong,
			pageview.toggle_format_emphasis,
			pageview.toggle_format_mark,
			pageview.toggle_format_strike,
			pageview.toggle_format_code,
			pageview.toggle_format_sub,
			pageview.toggle_format_sup,
		)
		self.edit_menus = (
			('_List', 'view-list-symbolic', self._create_list_menu()),
			('_Heading', 'format-text-heading-symbolic', self._create_head_menu()),
			('_Insert', 'insert-image-symbolic', self._create_insert_menu()),
		)
		self.edit_clear_action = pageview.clear_formatting

		def on_extensions_changed(o, obj):
			if obj in (pageview, PluginManager.insertedobjects):
				self._update_insert_menu()

		PluginManager.connect('extensions-changed', on_extensions_changed)

	def _create_list_menu(self):
		menu = Gio.Menu()
		section = Gio.Menu()
		menu.append_section(None, section)

		pageview = self.pageview
		for action in (
			pageview.apply_format_bullet_list,
			pageview.apply_format_numbered_list,
			pageview.apply_format_checkbox_list,
			'----',
			pageview.clear_list_format,
		):
			if action == '----':
				section = Gio.Menu()
				menu.append_section(None, section)
			else:
				section.append(action.label, 'pageview.' + action.name)

		return menu

	def _create_head_menu(self):
		menu = Gio.Menu()
		section = Gio.Menu()
		menu.append_section(None, section)

		pageview = self.pageview
		for action in (
			pageview.apply_format_h1,
			pageview.apply_format_h2,
			pageview.apply_format_h3,
			pageview.apply_format_h4,
			pageview.apply_format_h5,
			'----',
			pageview.clear_heading_format,
		):
			if action == '----':
				section = Gio.Menu()
				menu.append_section(None, section)
			else:
				section.append(action.label, 'pageview.' + action.name)

		return menu

	def _create_insert_menu(self):
		menu = Gio.Menu()
		self._insert_menu = menu
		return menu

	def _update_insert_menu(self):
		menu = self._insert_menu
		menu.remove_all()

		section = Gio.Menu()
		menu.append_section(None, section)

		plugin_section = None
		seen = set((
			'insert_bullet_list',
			'insert_numbered_list',
			'insert_checkbox_list',
		)) # Ignore these 3 even if they have "insert" menuhint
		pageview = self.pageview
		for action in (
			pageview.attach_file,
			'----',
			pageview.show_insert_image,
			pageview.insert_text_from_file,
			'----',
			'<plugins>',
			'----',
			pageview.insert_date,
			pageview.insert_line,
			pageview.insert_link,
		):
			if action == '----':
				section = Gio.Menu()
				menu.append_section(None, section)
			elif action == '<plugins>':
				plugin_section = section
			else:
				section.append(action.label, 'pageview.' + action.name)
				seen.add(action.name)

		for name, action in list_actions(pageview):
			if action.menuhints[0] == 'insert' and not action.name in seen:
				plugin_section.append(action.label, 'pageview.' + action.name)
				seen.add(action.name)


class EditBar(EditActionMixin, Gtk.ActionBar):

	def __init__(self, pageview):
		Gtk.ActionBar.__init__(self)
		EditActionMixin.__init__(self, pageview)

		def _grab_focus_on_click(button):
			# Need additional check for has_focus, else this grab will happen
			# for every state change of the underlying action
			if button.has_focus():
				pageview.grab_focus()

		for action in self.edit_format_actions:
			button = action.create_icon_button()
			# MGB: Commented this out because it prevents my Expander object from retaining focus 
			# after a EditBar button is clicked. Testing shows taking focus is not necessary.
			# button.connect('clicked', _grab_focus_on_click)
			self.pack_start(button)

		for label, icon_name, menu in self.edit_menus:
			button = self._create_menu_button(label, icon_name, menu)
			self.pack_start(button)

		clear_button = self.edit_clear_action.create_icon_button()
		# MGB: Commented this out because it prevents my Expander object from retaining focus 
		# after a EditBar button is clicked. Testing shows taking focus is not necessary.
		#clear_button.connect('clicked', lambda o: pageview.grab_focus())
		self.pack_end(clear_button)

		self.insert_state_label = Gtk.Label()
		self.insert_state_label.set_sensitive(False)
		self.pack_end(self.insert_state_label)
		textview = pageview.textview
		self.on_textview_toggle_overwrite(textview)
		textview.connect_after(
			'toggle-overwrite', self.on_textview_toggle_overwrite)

		self.style_info_label = Gtk.Label()
		self.style_info_label.set_sensitive(False)
		self.style_info_label.set_ellipsize(Pango.EllipsizeMode.END)
		self.pack_end(self.style_info_label)
		pageview.connect(
			'textstyle-changed', self.on_textview_textstyle_changed)

	def _create_menu_button(self, label, icon_name, menu):
		button = Gtk.MenuButton()
		hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
		label = Gtk.Label.new_with_mnemonic(label)
		label.set_ellipsize(Pango.EllipsizeMode.END)
		hbox.add(label)
		hbox.add(Gtk.Image.new_from_icon_name('pan-down-symbolic', Gtk.IconSize.BUTTON))
		button.add(hbox)

		popover = Gtk.Popover()
		popover.bind_model(menu)
		popover.connect('closed', lambda o: self.pageview.grab_focus())
		button.set_popover(popover)

		return button

	def on_textview_toggle_overwrite(self, textview):
		text = 'OVR' if textview.get_overwrite() else 'INS'
		self.insert_state_label.set_text(text + '  ')

	def on_textview_textstyle_changed(self, pageview, styles):
		label = ", ".join([s.title() for s in styles if s]) if styles else ''
		self.style_info_label.set_text(label)


class ToolBarEditBarManager(EditActionMixin, ConnectorMixin):

	def __init__(self, pageview, toolbar):
		self.pageview = pageview
		self.toolbar = toolbar
		EditActionMixin.__init__(self, pageview)
		toolbar.insert_action_group('pageview', pageview.get_action_group('pageview'))

		self._formatting_items = []
		self.on_readonly_changed(self.pageview, self.pageview.readonly)
		self.connectto(self.pageview, 'readonly-changed')

	def on_readonly_changed(self, pageview, readonly):
		for item in self._formatting_items:
			item.set_sensitive(not readonly)

	def populate_toolbar(self, toolbar):
		assert toolbar == self.toolbar

		self._formatting_items = []

		for action in self.edit_format_actions:
			item = action.create_tool_button(connect_button=False)
			item.set_action_name('pageview.' + action.name)
			toolbar.insert(item, -1)
			self._formatting_items.append(item)

		for label, icon_name, menu in self.edit_menus:
			button = self._create_menu_button(label, icon_name, menu)
			button.set_is_important(True) # Ensure text is shown by default
			toolbar.insert(button, -1)
			self._formatting_items.append(button)

		toolbar.insert(Gtk.SeparatorToolItem(), -1)

	def _create_menu_button(self, label, icon_name, menu):
		button = Gtk.ToggleToolButton()
		button.set_label(label+'...')
		button.set_use_underline(True)
		button.set_tooltip_text(label.replace('_', '')+'...') # icon button should always have tooltip
		button.set_icon_name(icon_name)

		popover = Gtk.Popover()
		popover.bind_model(menu)
		popover.set_relative_to(button)
		def toggle_popover(button):
			if button.get_active():
				popover.popup()
			else:
				popover.popdown()
		button.connect('toggled', toggle_popover)
		popover.connect('closed', lambda o: button.set_active(False))
		# MGB: Commented this out because it prevents my Expander object from retaining focus 
		# after a EditBar button is clicked. Testing shows taking focus is not necessary.
		#popover.connect('closed', lambda o: self.pageview.grab_focus())

		return button
