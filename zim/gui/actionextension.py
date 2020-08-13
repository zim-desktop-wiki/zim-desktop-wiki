# Copyright 2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# This module exists to resolve import cycle between mainwindow and
# pageview modules

from zim.plugins import ExtensionBase
from zim.actions import get_actions, get_gtk_actiongroup, RadioActionMethod


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
		button = action.create_icon_button()
		headerbar = self.obj.get_toplevel().get_titlebar()
		if 'view' in action.menuhints:
			headerbar.pack_end(button)
		else:
			headerbar.pack_start(button)
		button.show_all()

	def remove_from_headerbar(self, action):
		# fails silently
		headerbar = self.obj.get_toplevel().get_titlebar()
		for button in action._proxies:
			try:
				headerbar.remove(button)
			except:
				pass

	def set_action_in_headerbar(self, action, visible):
		if visible:
			headerbar = self.obj.get_toplevel().get_titlebar()
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
