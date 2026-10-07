# Copyright 2026 Self-Perfection <alexander.s.m@gmail.com>


import sys

from gi.repository import Gtk

import tests

from tests.mainwindow import setUpMainWindow

import zim.plugins.trayicon

from zim.plugins.trayicon import StatusIconTrayIcon, TrayIconPlugin, TrayIconMainWindowExtension


@tests.skipIf(sys.platform == 'darwin', 'Gtk.StatusIcon crashes the test process on macOS')
class TestStatusIconTrayIcon(tests.TestCase):

	def runTest(self):
		# "do_popup_menu" is the default handler for the "popup-menu"
		# signal of Gtk.StatusIcon - if it is connected to the signal as
		# well, the menu shows up twice for a single click
		class MyStatusIconTrayIcon(StatusIconTrayIcon):

			def __init__(self):
				self.menus = []
				StatusIconTrayIcon.__init__(self)

			def do_popup_menu(self, button=3, activate_time=0):
				# Build the menu, but don't show it during tests
				self.menus.append(self.get_trayicon_menu())

		icon = MyStatusIconTrayIcon()
		icon.emit('popup-menu', 3, 0)
		self.assertEqual(len(icon.menus), 1)
		icon.destroy()


@tests.skipIf(sys.platform == 'darwin', 'Gtk.StatusIcon crashes the test process on macOS')
class TestTrayIconMainWindowExtension(tests.TestCase):

	def runTest(self):
		# When the plugin is enabled from the preferences dialog the window is
		# already part of the application - the extension must be able to set up
		# in that state as well. Else it is never registered and "teardown()"
		# does not run when the plugin is disabled again, leaving a tray icon
		# for a disabled plugin and a window that keeps hiding itself on close.
		application = Gtk.Application()
		application.register(None) # else windows are not accepted
		window = setUpMainWindow(self.setUpNotebook())
		application.add_window(window)
		self.assertIsNotNone(window.get_application())

		plugin = TrayIconPlugin()
		extension = TrayIconMainWindowExtension(plugin, window)
		self.assertIsNotNone(zim.plugins.trayicon.GLOBAL_TRAYICON)
		self.assertTrue(window.hideonclose)

		extension.teardown()
		self.assertIsNone(zim.plugins.trayicon.GLOBAL_TRAYICON)
		self.assertFalse(window.hideonclose)
