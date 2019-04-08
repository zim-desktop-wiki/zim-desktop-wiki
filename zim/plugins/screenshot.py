
# Copyright 2009-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>
# Copyright 2014 Andri Kusumah


import time
from platform import os

from gi.repository import Gtk

from zim.plugins import PluginClass
from zim.actions import action
from zim.fs import TmpFile
from zim.applications import Application

from zim.gui.pageview import PageViewExtension
from zim.gui.widgets import Dialog, ErrorDialog


PLATFORM = os.name

"""
TESTED:
	- import (imagemagick)
	- scrot
	- spectacle
UNTESTED:
	- boxcutter (windows, http://keepnote.org/boxcutter/)
"""
COMMAND = 'import'
SUPPORTED_COMMANDS_BY_PLATFORM = dict([
	('posix', ('import', 'scrot', 'spectacle')),
	('nt', ('boxcutter',)),
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
		('spectacle', {
			'select': ('--background', '--region', '--output'),
			'full': ('--background', '--fullscreen'),
			'delay': '--delay',
			'delay_factor': 1000,
			'output': '--output',
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
	])
	cmd_default = COMMAND
	final_cmd_options = ()

	def __init__(self, cmd, select=False, delay=0):
		cmd = self.select_cmd(cmd)
		screenshot_mode = 'select' if select is True else 'full'
		self.final_cmd_options += self.cmd_options[cmd][screenshot_mode]

		if str(delay).isdigit() and int(delay) > 0 and self.cmd_options[cmd]['delay'] is not None:
			delay_factor = 1
			if 'delay_factor' in self.cmd_options[cmd]:
				delay_factor =  self.cmd_options[cmd]['delay_factor']
			self.final_cmd_options += (self.cmd_options[cmd]['delay'], str(int(delay) * int(delay_factor)))
		if 'output' in self.cmd_options[cmd]:
			self.final_cmd_options += (self.cmd_options[cmd]['output'], )

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
		('default_selection_mode', 'choice', _('Default choice'), 'Fullscreen', ['Fullscreen', 'Window or Region']),
		('default_delay', 'int', _('Default delay'), 0, (0,120)),
		('hide_dialog', 'bool', _('Hide options dialog'), False),
	)
	screenshot_cmd = COMMAND

	def __init__(self):
		PluginClass.__init__(self)
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


class ScreenshotPageViewExtension(PageViewExtension):

	screenshot_command = COMMAND
	plugin = None

	def __init__(self, plugin, pageview):
		PageViewExtension.__init__(self, plugin, pageview)
		self.on_preferences_changed(plugin.preferences)
		self.connectto(plugin.preferences, 'changed', self.on_preferences_changed)
		self.plugin = plugin

	def on_preferences_changed(self, preferences):
		if preferences['screenshot_command']:
			self.screenshot_command = preferences['screenshot_command']

	@action(_('_Screenshot...'), icon='gtk-fullscreen', menuhints='insert')  # T: menu item for insert screenshot plugin
	def insert_screenshot(self):
		self.notebook = self.pageview.notebook
		self.page = self.pageview.page

		if self.plugin.preferences['hide_dialog']:
			if self.plugin.preferences['default_selection_mode'] == 'Fullscreen':
				selection = False
			else:
				selection = True
			self.make_screenshot(selection, self.plugin.preferences['default_delay'])
		else:
			dialog = InsertScreenshotDialog.unique(self, self.pageview, self.notebook, self.page,
											   self.plugin.preferences['screenshot_command'], 
											   self.plugin.preferences['default_selection_mode'], self.make_screenshot)
			dialog.show_all()

	def make_screenshot(self, selection_mode, delay):
		tmpfile = TmpFile('insert-screenshot.png')
		options = ScreenshotPicker.get_cmd_options(self.screenshot_command, selection_mode, str(delay))
		cmd = (self.screenshot_command,) + options
		helper = Application(cmd)

		def callback(status, tmpfile):
					if status == helper.STATUS_OK:
						name = time.strftime('screenshot_%Y-%m-%d-%H%M%S.png')
						imgdir = self.notebook.get_attachments_dir(self.page)
						imgfile = imgdir.new_file(name)
						tmpfile.rename(imgfile)
						pageview = self.pageview
						pageview.insert_image(imgfile)
					else:
						ErrorDialog(self.ui, _('Some error occurred while running "%s"') % self.screenshot_command).run()
						# T: Error message in "insert screenshot" dialog, %s will be replaced by application name
		
		tmpfile.dir.touch()
		helper.spawn((tmpfile,), callback, tmpfile)
		return True
		

class InsertScreenshotDialog(Dialog):
	screenshot_command = COMMAND

	def __init__(self, pageview, notebook, page, screenshot_command, default_choice, cmd):
		Dialog.__init__(self, pageview, _('Insert Screenshot'))  # T: dialog title
		self.pageview = pageview
		self.screenshot_command = screenshot_command
		if ScreenshotPicker.has_select_cmd(self.screenshot_command):
			self.screen_radio = Gtk.RadioButton.new_with_mnemonic_from_widget(None,
												_('Capture whole screen'))  # T: option in 'insert screenshot' dialog
			self.select_radio = Gtk.RadioButton.new_with_mnemonic_from_widget(self.screen_radio,
												_('Select window or region'))  # T: option in 'insert screenshot' dialog
			self.vbox.add(self.screen_radio)
			self.vbox.add(self.select_radio)
			if default_choice == 'Fullscreen':
				self.screen_radio.set_active(True)
			else:
				self.select_radio.set_active(True)

		self.cmd = cmd 
		if ScreenshotPicker.has_delay_cmd(self.screenshot_command):
			hbox = Gtk.HBox()
			self.vbox.add(hbox)
			hbox.add(Gtk.Label(label=_('Delay') + ': '))  # T: input in 'insert screenshot' dialog
			self.time_spin = Gtk.SpinButton()
			self.time_spin.set_range(0, 99)
			self.time_spin.set_increments(1, 5)
			self.time_spin.set_value(0)
			hbox.add(self.time_spin)
			hbox.add(Gtk.Label(label=' ' + _('seconds')))  # T: label behind timer

	def do_response_ok(self):
		selection_mode = False
		delay = 0
		if ScreenshotPicker.has_select_cmd(self.screenshot_command) and self.select_radio.get_active():
			selection_mode = True

		if ScreenshotPicker.has_delay_cmd(self.screenshot_command):
			delay = self.time_spin.get_value_as_int()
		self.cmd(selection_mode, delay)
		return True
