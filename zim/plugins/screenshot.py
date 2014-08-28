# -*- coding: utf-8 -*-

# Copyright 2009-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>
# Copyright 2014 Andri Kusumah


import time
from platform import os

import gtk

from zim.plugins import PluginClass, WindowExtension, extends
from zim.actions import action
from zim.fs import TmpFile
from zim.applications import Application
from zim.gui.widgets import ui_environment, Dialog, ErrorDialog


PLATFORM = os.name
if ui_environment['platform'] == 'maemo':  # don't know what os.name return on maemo
	PLATFORM = 'maemo'

"""
TESTED:
	- import (imagemagick)
	- scrot
UNTESTED:
	- boxcutter (windows, http://keepnote.org/boxcutter/)
	- screenshot-tool (maemo)
"""
COMMAND = 'import'
SUPPORTED_COMMANDS_BY_PLATFORM = dict([
	('posix', ('import', 'scrot')),
	('nt', ('boxcutter',)),
	('maemo', ('screenshot-tool',)),
])
SUPPORTED_COMMANDS = SUPPORTED_COMMANDS_BY_PLATFORM[PLATFORM]
if len(SUPPORTED_COMMANDS):
	COMMAND = SUPPORTED_COMMANDS[0]  # set first available tool as default


class ScreenshotPicker(object):
	cmd_options = dict([
		('scrot', {
			'select': ('--select', '--border'),
			'full': ('--multidisp',),
			'delay': '-d',
		}),
		('import', {
			'select': ('-silent',),
			'full': ('-silent', '-window', 'root'),
			'delay': '-delay',
		}),
		('boxcutter', {
			'select': None,
			'full': ('--fullscreen',),
			'delay': None,
		}),
		('screenshot-tool', {
			'select': None,
			'full': (),
			'delay': '-d',
		})
	])
	cmd_default = COMMAND
	final_cmd_options = ()

	def __init__(self, cmd, select=False, delay=0):
		cmd = self.select_cmd(cmd)
		screenshot_mode = 'select' if select is True else 'full'
		self.final_cmd_options += self.cmd_options[cmd][screenshot_mode]

		if str(delay).isdigit() and int(delay) > 0 and self.cmd_options[cmd]['delay'] is not None:
			self.final_cmd_options += (self.cmd_options[cmd]['delay'], str(delay))

	@classmethod
	def select_cmd(cls, cmd=None):
		if cmd is None or cmd not in SUPPORTED_COMMANDS or cmd not in cls.cmd_options:
			cmd = cls.cmd_default
		return cmd

	@classmethod
	def get_cmd_options(cls, cmd=None, select=False, delay=0):
		cmd = cls.select_cmd(cmd)
		delay = delay if str(delay).isdigit() and int(delay) > 0 else 0
		me = cls(cmd, select, str(delay))
		return me.final_cmd_options

	@classmethod
	def has_delay_cmd(cls, cmd=None):
		cmd = cls.select_cmd(cmd)
		return True if cls.cmd_options[cmd]['delay'] is not None else False

	@classmethod
	def has_select_cmd(cls, cmd):
		cmd = cls.select_cmd(cmd)
		return True if cls.cmd_options[cmd]['select'] is not None else False


class InsertScreenshotPlugin(PluginClass):
	plugin_info = {
		'name': _('Insert Screenshot'),  # T: plugin name
		'description': _('''\
This plugin  allows taking a screenshot and directly insert it
in a zim page.

This is a core plugin shipping with zim.
'''),  # T: plugin description
		'author': 'Jaap Karssenberg',
		'help': 'Plugins:Insert Screenshot',
	}
	plugin_preferences = (
		# key, type, label, default
		('screenshot_command', 'choice', _('Screenshot Command'), COMMAND, SUPPORTED_COMMANDS), # T: plugin preference
	)
	screenshot_cmd = COMMAND

	def __init__(self, config=None):
		PluginClass.__init__(self, config)
		self.on_preferences_changed(self.preferences)
		self.preferences.connect('changed', self.on_preferences_changed)

	def on_preferences_changed(self, preferences):
		self.screenshot_cmd = preferences['screenshot_command']

	@classmethod
	def check_dependencies(cls):
		cmds = []
		is_ok = False
		if len(SUPPORTED_COMMANDS):
			for cmd in SUPPORTED_COMMANDS:
				has_tool = Application(cmd).tryexec()
				if has_tool:
					is_ok = True
					cmds.append((cmd, True, False))
				else:
					cmds.append((cmd, False, False))
		return is_ok, cmds


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
	screenshot_command = COMMAND
	plugin = None

	def __init__(self, plugin, window):
		WindowExtension.__init__(self, plugin, window)
		self.on_preferences_changed(plugin.preferences)
		self.connectto(plugin.preferences, 'changed', self.on_preferences_changed)
		self.plugin = plugin

	def on_preferences_changed(self, preferences):
		if preferences['screenshot_command']:
			self.screenshot_command = preferences['screenshot_command']

	@action(_('_Screenshot...'))  # T: menu item for insert screenshot plugin
	def insert_screenshot(self):
		notebook = self.window.ui.notebook  # XXX
		page = self.window.ui.page  # XXX
		dialog = InsertScreenshotDialog.unique(self, self.window, notebook, page,
											   self.plugin.preferences['screenshot_command'])
		dialog.show_all()


class InsertScreenshotDialog(Dialog):
	screenshot_command = COMMAND

	def __init__(self, window, notebook, page, screenshot_command):
		Dialog.__init__(self, window, _('Insert Screenshot'))  # T: dialog title
		self.screenshot_command = screenshot_command
		if ScreenshotPicker.has_select_cmd(self.screenshot_command):
			self.screen_radio = gtk.RadioButton(None,
												_('Capture whole screen'))  # T: option in 'insert screenshot' dialog
			self.select_radio = gtk.RadioButton(self.screen_radio,
												_('Select window or region'))  # T: option in 'insert screenshot' dialog
			self.vbox.add(self.screen_radio)
			self.vbox.add(self.select_radio)

		self.notebook = notebook
		self.page = page
		if ScreenshotPicker.has_delay_cmd(self.screenshot_command):
			hbox = gtk.HBox()
			self.vbox.add(hbox)
			hbox.add(gtk.Label(_('Delay') + ': '))  # T: input in 'insert screenshot' dialog
			self.time_spin = gtk.SpinButton()
			self.time_spin.set_range(0, 99)
			self.time_spin.set_increments(1, 5)
			self.time_spin.set_value(0)
			hbox.add(self.time_spin)
			hbox.add(gtk.Label(' ' + _('seconds')))  # T: label behind timer

	def do_response_ok(self):
		tmpfile = TmpFile('insert-screenshot.png')
		selection_mode = False
		delay = 0
		if ScreenshotPicker.has_select_cmd(self.screenshot_command) and self.select_radio.get_active():
			selection_mode = True

		if ScreenshotPicker.has_delay_cmd(self.screenshot_command):
			delay = self.time_spin.get_value_as_int()

		options = ScreenshotPicker.get_cmd_options(self.screenshot_command, selection_mode, str(delay))
		helper = Application((self.screenshot_command,) + options)

		def callback(status, tmpfile):
			if status == helper.STATUS_OK:
				name = time.strftime('screenshot_%Y-%m-%d-%H%M%S.png')
				imgdir = self.notebook.get_attachments_dir(self.page)
				imgfile = imgdir.new_file(name)
				tmpfile.rename(imgfile)
				pageview = self.ui.mainwindow.pageview
				pageview.insert_image(imgfile, interactive=False, force=True)
			else:
				ErrorDialog(self.ui,
							_('Some error occurred while running "%s"') % self.screenshot_command).run()
				# T: Error message in "insert screenshot" dialog, %s will be replaced by application name

		tmpfile.dir.touch()
		helper.spawn((tmpfile,), callback, tmpfile)
		return True
