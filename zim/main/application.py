# Copyright 2013-2024 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# This class is in a seperate module to avoid Gtk imports in the main module
# imports are a bit circular

import os
import logging
import signal
from typing import List, Optional

logger = logging.getLogger('zim')

import zim.errors

from gi.repository import Gio
from gi.repository import Gtk

from . import _application_startup, build_command, UsageError


class ZimGtkApplication(Gtk.Application):
	
	APPLICATION_ID = 'org.zim_wiki.Zim' # For practical reasons use "_" instead of "-"
	
	def __init__(self, non_unique=False, standalone=False):
		'''Constructor
		@param non_unique: do not attempt to run a unique process but start a new process here
		@param standalone: in standalone mode, each notebook is opened in it's own process, 
		this implies C{non_unique}
		'''
		Gtk.Application.__init__(self)
		self.set_application_id(self.APPLICATION_ID)
		self.standalone = standalone
		if standalone or non_unique:
			self.set_flags(Gio.ApplicationFlags.HANDLES_COMMAND_LINE|Gio.ApplicationFlags.NON_UNIQUE)
		else:
			self.set_flags(Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
		self.connect('startup', self.__class__._do_startup) # Hack to avoid bug in python-gtk interaction
		self.connect('shutdown', self.__class__._do_shutdown)

	def _do_startup(self):
		_application_startup()

		def handle_sigterm(signal, frame):
			logger.info('Got SIGTERM, quit')
			self.quit()

		signal.signal(signal.SIGTERM, handle_sigterm)

		from zim.gui.widgets import gtk_window_set_default_icon
		gtk_window_set_default_icon()

		zim.errors.set_use_gtk(True)

	def _do_shutdown(self):
		# MainWindow implements saving in the destroy method
		for window in self.get_windows():
			window.destroy()

	def do_command_line(self, gcommandline):
		# Handler in primary process to process commandline and start application
		# if started from remote process, the exit code is given back to that process
		# and it exits while primary process keeps running as long as there are windows
		args = gcommandline.get_arguments()
		if 'python' in os.path.basename(args[0]):
			args = args[2:] # strip python interpreter and zim script name
		else:
			args = args[1:] # strip zim executable name
		return self.run_commandline(args, gcommandline.get_cwd())

	def run_commandline(self, args: List[str], pwd: Optional[str] = None) -> int:
		'''Run a commandline in the current process
		@param args: the commandline options
		@param pwd: the working directory as string path
		@returns: exit value as integer, 0 is OK, other values for errors
		'''
		try:
			args = [a for a in args if a is not None]
			cmd = build_command(args, pwd=pwd)
			window = cmd.run()
		except Exception as err:
			import sys
			print(err, file=sys.stderr)
			return 1
		else:
			if window and isinstance(window, Gtk.Window):
				self.add_window(window)
				window.present()
			elif window:
				# E.g. trayicon, not a window, but we need to hold application
				self.hold()
				window.connect('destroy', lambda *a: self.release())

			return 0

	def open_notebook(self, location, pagelink=None):
		'''Open a notebook either in an existing or a new window
		@param location: notebook location as uri or object with "uri" attribute like C{File}, C{Notebook}, or C{NotebookInfo}
		@param pagelink: optional page link (including optional anchor ID) as string or C{Path} object
		'''
		uri = location if isinstance(location, str) else location.uri
		pagelink = pagelink if isinstance(pagelink, (str, type(None))) else pagelink.name

		if self.standalone:
			self._spawn_new_instance('--gui', uri, pagelink)
		else:
			self.run_commandline(['--gui', uri, pagelink])

	def open_manual(self, pagelink=None):
		'''Open the manual either in an existing or a new window
		@param pagelink: optional page link (including optional anchor ID) as string or C{Path} object
		'''
		pagelink = pagelink if isinstance(pagelink, (str, type(None))) else pagelink.name

		if self.standalone:
			self._spawn_new_instance('--manual', pagelink)
		else:
			self.run_commandline(['--manual', pagelink])

	def _spawn_new_instance(self, *arg):
		# This method forces a new zim process to be run
		# used for "standalone" mode where each notebook gets
		# it's own process
		from zim import ZIM_EXECUTABLE
		from zim.applications import Application

		args = [ZIM_EXECUTABLE] + [a for a in arg if a is not None]
		if not '--standalone' in args:
			args.append('--standalone')

		# more detailed logging has lower number, so WARN > INFO > DEBUG
		loglevel = logging.getLogger().getEffectiveLevel()
		if loglevel <= logging.DEBUG:
			args.append('-D',)
		elif loglevel <= logging.INFO:
			args.append('-V',)

		Application(args).spawn()
