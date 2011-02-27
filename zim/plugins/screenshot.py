# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import gtk
import time

from zim.fs import TmpFile
from zim.plugins import PluginClass
from zim.gui.widgets import ui_environment, Dialog, ErrorDialog
from zim.applications import Application

ui_xml = '''
<ui>
	<menubar name='menubar'>
		<menu action='insert_menu'>
			<placeholder name='plugin_items'>
				<menuitem action='insert_screenshot'/>
			</placeholder>
		</menu>
	</menubar>
</ui>
'''

ui_actions = (
	# name, stock id, label, accelerator, tooltip, read only
	('insert_screenshot', None, _('_Screenshot...'), '', '', False),
		# T: menu item for insert screenshot plugin
)

if ui_environment['platform'] == 'maemo':
	COMMAND = 'screenshot-tool'
else:
	COMMAND = 'scrot'


class InsertScreenshotPlugin(PluginClass):
	'''FIXME'''

	plugin_info = {
		'name': _('Insert Screenshot'), # T: plugin name
		'description': _('''\
This plugin  allows taking a screenshot and directly insert it
in a zim page.

This is a core plugin shipping with zim.
'''), # T: plugin description
		'author': 'Jaap Karssenberg',
		'help': 'Plugins:Insert Screenshot',
	}

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		if self.ui.ui_type == 'gtk':
			self.ui.add_actions(ui_actions, self)
			self.ui.add_ui(ui_xml, self)

	@classmethod
	def check_dependencies(klass):
		return [(COMMAND, Application((COMMAND,)).tryexec())]

	def insert_screenshot(self):
		dialog = InsertScreenshotDialog.unique(self, self.ui)
		dialog.show_all()


class InsertScreenshotDialog(Dialog):

	# TODO use uistate to save previous setting

	def __init__(self, ui):
		Dialog.__init__(self, ui, _('Insert Screenshot')) # T: dialog title
		if COMMAND == 'scrot':
			self.screen_radio = gtk.RadioButton(None, _('Capture whole screen')) # T: option in 'insert screenshot' dialog
			self.select_radio = gtk.RadioButton(self.screen_radio, _('Select window or region')) # T: option in 'insert screenshot' dialog
			self.vbox.add(self.screen_radio)
			self.vbox.add(self.select_radio)

		hbox = gtk.HBox()
		self.vbox.add(hbox)
		hbox.add(gtk.Label(_('Delay')+': ')) # T: input in 'insert screenshot' dialog
		self.time_spin = gtk.SpinButton()
		self.time_spin.set_range(0, 99)
		self.time_spin.set_increments(1, 5)
		hbox.add(self.time_spin)
		hbox.add(gtk.Label(' '+_('seconds'))) # T: label behind timer

	def do_response_ok(self):
		tmpfile = TmpFile('insert-screenshot.png')
		options = ()

		if COMMAND == 'scrot':
			if self.select_radio.get_active():
				options += ('--select', '--border')
				# Interactively select a window or rectangle with the mouse.
				# When selecting a window, grab wm border too
			else:
				options += ('--multidisp',)
				# For multiple heads, grab shot from each and join them together.

		delay = self.time_spin.get_value_as_int()
		if delay > 0:
			options += ('-d', str(delay))
			# Wait NUM seconds before taking a shot.

		helper = Application((COMMAND,) + options)

		def callback(status, tmpfile):
			if status == helper.STATUS_OK:
				name = time.strftime('screenshot_%Y-%m-%d-%H%M%S.png')
				page = self.ui.page
				dir = self.ui.notebook.get_attachments_dir(page)
				file = dir.new_file(name)
				tmpfile.rename(file)
				self.ui.mainwindow.pageview.insert_image(file, interactive=False)
			else:
				ErrorDialog(self.ui,
					_('Some error occured while running "%s"') % COMMAND).run()
					# T: Error message in "insert screenshot" dialog, %s will be replaced by aplication name

		tmpfile.dir.touch()
		helper.spawn((tmpfile,), callback, tmpfile)
		return True
