# Copyright 2018-2022 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# This module exists to resolve import cycle between mainwindow and
# pageview modules

import os
import sys

from zim.plugins import ExtensionBase, list_actions
from zim.actions import get_actions, get_gtk_actiongroup, RadioActionMethod
from zim.gui.customtools import CustomToolManager

try:
	from gi.repository import Gtk
except ImportError:
	Gtk = None


if sys.platform == "darwin" or os.name == 'nt':
	# default headerbar off on Windows and macOS, see issue #2007
	os_default_headerbar = False
else:
	os_default_headerbar = True


def populate_toolbar_with_actions(toolbar, *extendables, include_headercontrols=False, include_customtools=False):
	'''Populate a C{Gtk.Toolbar} with actions from extendable objects
	Default includes actions that have the 'tools' or 'view' menuhints set.
	@param toolbar: a C{Gtk.Toolbar} to populate
	@param *extendables: list of object that have actions and extensions with actions, e.g. 'mainwindow', 'pageview'
	@param include_headercontrols: include tools with the 'headerbar' menuhint as well
	@param include_customtools: include custom tools as well
	'''
	viewitems, toolitems = [], []
	for o in extendables:
		for name, action in list_actions(o):
			if 'headerbar' in action.menuhints and not include_headercontrols:
				pass
			elif ('toolbar' in action.menuhints or 'headerbar' in action.menuhints) \
				or (action.hasicon and ('view' in action.menuhints or 'tools' in action.menuhints)):
					button = action.create_tool_button(fallback_icon='system-run')
					if 'is_important' in action.menuhints:
						button.set_is_important(True) # Ensure text is shown by default

					if 'view' in action.menuhints:
						viewitems.append(button)
					else:
						toolitems.append(button)

	if viewitems and toolitems:
		viewitems.append(Gtk.SeparatorToolItem())

	for item in viewitems + toolitems:
		toolbar.insert(item, -1)

	if not include_customtools:
		return

	customtools = CustomToolManager()
	customtoolitems = []
	icon_size = toolbar.get_icon_size()
	for tool in customtools:
		if tool.showintoolbar:
			button = Gtk.ToolButton()
			button.set_label(tool.name)
			button.set_icon_widget(Gtk.Image.new_from_pixbuf(tool.get_pixbuf(icon_size)))
			button.set_tooltip_text(tool.comment) # icon button should always have tooltip
			button.connect('clicked', customtools.run_custom_tool, tool)
			customtoolitems.append(button)

	if toolitems and customtoolitems:
		toolbar.insert(Gtk.SeparatorToolItem(), -1)

	for item in customtoolitems:
		toolbar.insert(item, -1)


class ActionExtensionBase(ExtensionBase):
	'''Common functions between MainWindowExtension and PageViewExtension
	do not use directly in plugins.
	'''

	def __init__(*a):
		raise AssertionError('Do not use this base directly')

	def _add_actions(self, uimanager):
		actions = get_actions(self)
		if actions:
			self._uimanager = uimanager
			actiongroup = get_gtk_actiongroup(self)
			uimanager.insert_action_group(actiongroup, 0)
			self._uimanager_ids = []
			for name, action in actions:
				xml = self._uimanager_xml(action, actiongroup, 'tools')
				if xml is not None:
					self._uimanager_ids.append(
						uimanager.add_ui_from_string(xml)
					)

				if 'headerbar' in action.menuhints:
					self.add_to_headerbar(action)

	def _add_headerbar_actions(self):
		headerbar = self.obj.get_toplevel().get_titlebar()
		if not headerbar:
			return

		for name, action in get_actions(self):
			if 'headerbar' in action.menuhints:
				self.add_to_headerbar(action)

	def teardown(self):
		if hasattr(self, '_uimanager_ids'):
			for ui_id in self._uimanager_ids:
				self._uimanager.remove_ui(ui_id)
			self._uimanager_ids = []

		if hasattr(self, 'actiongroup') and self.actiongroup is not None:
			self._uimanager.remove_action_group(self.actiongroup)
			self.actiongroup = None

		for name, action in get_actions(self):
			if 'headerbar' in action.menuhints:
				self.remove_from_headerbar(action)

	def add_to_headerbar(self, action):
		headerbar = self.obj.get_toplevel().get_titlebar()
		if not headerbar:
			return

		if action.hasicon and not 'is_important' in action.menuhints:
			button = action.create_icon_button()
		else:
			button = action.create_button()

		if 'view' in action.menuhints:
			headerbar.pack_end(button)
		else:
			headerbar.pack_start(button)
		button.show_all()

	def remove_from_headerbar(self, action):
		# fails silently
		headerbar = self.obj.get_toplevel().get_titlebar()
		if not headerbar:
			return

		for button in action._proxies:
			try:
				headerbar.remove(button)
			except:
				pass

	def set_action_in_headerbar(self, action, visible):
		if visible:
			headerbar = self.obj.get_toplevel().get_titlebar()
			if not headerbar:
				return

			children = headerbar.get_children()
			for button in action._proxies:
				if button in children:
					return
			else:
				self.add_to_headerbar(action)
		else:
			self.remove_from_headerbar(action)

	@staticmethod
	def _uimanager_xml(action, actiongroup, defaultmenu):
		menuhint = defaultmenu
		if action.menuhints:
			if 'accelonly' in action.menuhints:
				return '<ui><accelerator action=\'%s\'/></ui>' % action.name
			elif action.menuhints[0] in \
				('notebook', 'page', 'edit', 'insert', 'view', 'tools', 'go'):
					menuhint = action.menuhints[0]

		if menuhint in ('notebook', 'page'):
			menu_name = 'file_menu'
			placeholder_name = menuhint + '_plugin_items'
		else:
			menu_name = menuhint + '_menu'
			placeholder_name = 'plugin_items'

		if isinstance(action, RadioActionMethod):
			submenu_name = action.name + '_menu'
			submenu_label = action.menulabel
			actiongroup.add_actions(((submenu_name, None, submenu_label),))
			item_names = [e[0] for e in action._entries]
			item = '\n'.join(
				['<menu action=\'%s\'>' % submenu_name] +
				[
					'<menuitem action=\'%s\'/>' % n for n in item_names
				] +
				['</menu>']
			)
		else:
			item = '<menuitem action=\'%s\'/>' % action.name

		ui = '''\
		<ui>
		<menubar name='menubar'>
			<menu action='%s'>
				<placeholder name='%s'>
				%s
				</placeholder>
			</menu>
		</menubar>
		</ui>
		''' % (menu_name, placeholder_name, item)

		return ui
