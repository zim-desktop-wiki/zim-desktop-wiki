# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

from zim.plugins import PluginClass

ui_xml = '''
<ui>
	<menubar name='menubar'>
		<menu action='view_menu'>
			<placeholder name='plugin_items'>
				<menuitem action='toggle_readonly'/>
			</placeholder>
		</menu>
	</menubar>
	<toolbar name='toolbar'>
		<placeholder name='tools'>
			<toolitem action='toggle_readonly'/>
		</placeholder>
	</toolbar>
</ui>
'''

ui_toggle_actions = (
	# name, stock id, label, accelerator, tooltip, initial state, readonly
	('toggle_readonly', 'gtk-edit', _('Page Editable'), '', _('Toggle Page Editable'), True, True), # T: menu item
)

class ToggleReadOnlyPlugin(PluginClass):

	plugin_info = {
		'name': _('Toggle ReadOnly'), # T: plugin name
		'description': _('''\
This plugin allows you to temporarily switch the
notebook to a read-only state. This means it is
locked and can not be editted by accident.

This is a core plugin shipping with zim.
'''), # T: plugin description
		'author': 'Jaap Karssenberg',
		'help': 'Plugins:Toggle ReadOnly',
	}

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		if self.ui.ui_type == 'gtk':
			self.ui.add_toggle_actions(ui_toggle_actions, self)
			self.ui.add_ui(ui_xml, self)
			self.uistate.setdefault('readonly', False)
			self.ui.connect_after('open-notebook', self.do_open_notebook)
			if self.ui.notebook:
				self.do_open_notebook(self.ui, self.ui.notebook)

	def do_open_notebook(self, ui, notebook):
		if notebook.readonly:
			self.toggle_readonly(readonly=True)
			self.actiongroup.get_action('toggle_readonly').set_sensitive(False)
		else:
			self.toggle_readonly(readonly=self.uistate['readonly'])

	def toggle_readonly(self, readonly=None):
		active = not readonly
		self.toggle_action('toggle_readonly', active)

	def do_toggle_readonly(self, active=None):
		if active is None:
			active = self.actiongroup.get_action('toggle_readonly').get_active()
		readonly = not active
		self.ui.set_readonly(readonly)
		self.uistate['readonly'] = readonly

# TODO: set toggle insensitive when notebook is readlonly
# TODO: set toggle insensitive when page is readonly
