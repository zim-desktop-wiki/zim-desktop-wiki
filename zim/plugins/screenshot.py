# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import gtk
import time

from zim.plugins import PluginClass, WindowExtension, extends
from zim.actions import action
from zim.fs import TmpFile
from zim.applications import Application
from zim.gui.widgets import ui_environment, Dialog, ErrorDialog


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

	@classmethod
	def check_dependencies(klass):
		has_tool = Application((COMMAND,)).tryexec()
		return has_tool, [(COMMAND, has_tool, True)]


@extends('MainWindow')
class MainWindowExtension(WindowExtension):

	uimanager_xml = '''
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

	@action(_('_Screenshot...')) # T: menu item for insert screenshot plugin
	def insert_screenshot(self):
		notebook = self.window.ui.notebook # XXX
		page = self.window.ui.page # XXX
		dialog = InsertScreenshotDialog.unique(self, self.window, notebook, page)
			# XXX would like Dialog(pageview, page)
		dialog.show_all()


class InsertScreenshotDialog(Dialog):

	# TODO use uistate to save previous setting

	def __init__(self, window, notebook, page):
		Dialog.__init__(self, window, _('Insert Screenshot')) # T: dialog title
		if COMMAND == 'scrot':
			self.screen_radio = gtk.RadioButton(None, _('Capture whole screen')) # T: option in 'insert screenshot' dialog
			self.select_radio = gtk.RadioButton(self.screen_radio, _('Select window or region')) # T: option in 'insert screenshot' dialog
			self.vbox.add(self.screen_radio)
			self.vbox.add(self.select_radio)

		self.notebook = notebook
		self.page = page

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
				dir = self.notebook.get_attachments_dir(self.page)
				file = dir.new_file(name)
				tmpfile.rename(file)
				self.ui.pageview.insert_image(file, interactive=False) # XXX ui == window
			else:
				ErrorDialog(self.ui,
					_('Some error occurred while running "%s"') % COMMAND).run()
					# T: Error message in "insert screenshot" dialog, %s will be replaced by application name

		tmpfile.dir.touch()
		helper.spawn((tmpfile,), callback, tmpfile)
		return True
