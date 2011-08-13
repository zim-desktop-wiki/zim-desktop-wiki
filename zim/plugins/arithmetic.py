
# Copyright 2011 Patricio Paez <pp@pp.com.mx>
#
# Plugin to use arithmetic in Zim wiki

from zim._lib.arithmetic import ParserGTK

from zim.plugins import PluginClass

ui_xml = '''
<ui>
<menubar name='menubar'>
	<menu action='tools_menu'>
		<placeholder name='plugin_items'>
			<menuitem action='calculate'/>
		</placeholder>
	</menu>
</menubar>
</ui>
'''

ui_actions = (
	# name, stock id, label, accelerator, tooltip, readonly
	('calculate', None, _('_Arithmetic'), 'F5', '', False), # T: menu item
)


class ArithmeticPlugin(PluginClass):

	plugin_info = {
		'name': _('Arithmetic'), # T: plugin name
		'description': _('''\
This plugin allows you to embed arithmetic calculations in zim.  You may use variables, %, x or * for multiplication.

This plugin is based on the arithmetic module from http://pp.com.mx/python/arithmetic.
'''), # T: plugin description
		'author': 'Patricio Paez',
		'help': 'Plugins:Arithmetic',
	}

	#~ plugin_preferences = (
		# key, type, label, default
	#~ )

	def initialize_ui(self, ui):
		if self.ui.ui_type == 'gtk':
			self.ui.add_actions(ui_actions, self)
			self.ui.add_ui(ui_xml, self)

	def calculate(self):
		"""Perform arithmetic operations"""

		# get the buffer
		buf = self.ui.mainwindow.pageview.view.get_buffer()

		# parse and return modified text
		parser = ParserGTK()
		parser.parse( buf )
