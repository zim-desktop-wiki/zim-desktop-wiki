# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import webbrowser

from zim.fs import *
from zim.plugins import PluginClass
import zim.templates

ui_xml = '''
<ui>
	<menubar name='menubar'>
		<menu action='file_menu'>
			<placeholder name='print_actions'>
				<menuitem action='print_to_browser'/>
			</placeholder>
		</menu>
	</menubar>
</ui>
'''

ui_actions = (
	# name, stock id, label, accelerator, tooltip
	('print_to_browser', 'gtk-print', '_Print to Browser', '<ctrl>P', 'Printto browser'),

)

class SpellPlugin(PluginClass):
	'''FIXME'''

	info = {
		'name': 'Print to Browser',
		'author': 'Jaap Karssenberg <pardus@cpan.org>',
		'description': 'FIXME',
	}

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		if self.ui.ui_type == 'gtk':
			self.ui.add_actions(ui_actions, self)
			self.ui.add_ui(ui_xml, self)

	def print_to_browser(self):
		file = '/tmp/pyzim-print-to-browser.html' # FIXME use proper interface to get tmp file
		#output = File(file)
		output = Buffer()
		template = zim.templates.get_template('html', 'Print')
		template.process(self.ui.notebook, self.ui.page, output)
		# TODO figure out why output directly to file doesn't work
		File(file).write(output.getvalue())
		webbrowser.open('file://%s' % file)
