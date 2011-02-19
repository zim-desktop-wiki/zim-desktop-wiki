# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains helper classes for running external applications.

Also see the module zim.gui.applications, which contains classes for
working with applications defined in desktop entry files.
'''

import os
import logging
import subprocess

import gobject

import zim.fs

logger = logging.getLogger('zim.applications')


class Application(object):

	STATUS_OK = 0

	def __init__(self, cmd, tryexeccmd=None):
		assert isinstance(cmd, (tuple, list))
		assert tryexeccmd is None or isinstance(tryexeccmd, basestring)
		self.cmd = tuple(cmd)
		self.tryexeccmd = tryexeccmd

	@property
	def name(self):
		return self.cmd[0]

	@staticmethod
	def _lookup(cmd):
		'''Lookup cmd in PATH'''
		if os.name == 'nt' and not '.' in cmd:
			cmd = cmd + '.exe'
			# Automagically convert command names on windows

		if zim.fs.isabs(cmd):
			if zim.fs.isfile(cmd):
				return cmd
			else:
				return None
		else:
			# lookup in PATH
			for dir in os.environ['PATH'].split(os.pathsep):
				file = os.sep.join((dir, cmd))
				if zim.fs.isfile(file):
					return file
			else:
				return None

	def _cmd(self, args):
		# substitute args in the command - to be overloaded by child classes
		if args:
			return self.cmd + tuple(map(unicode, args))
		else:
			return self.cmd

	def tryexec(self):
		'''Check if the executable exists without calling it. If no 'tryexec'
		parameter is defined for this application, the first parameter of
		the command list is used.
		'''
		cmd = self.tryexeccmd or self.cmd[0]
		return not self._lookup(cmd) is None

	def _checkargs(self, cwd, args):
		assert args is None or isinstance(args, (tuple, list))
		argv = [a.encode(zim.fs.ENCODING) for a in self._cmd(args)]
		if cwd:
			cwd = unicode(cwd).encode(zim.fs.ENCODING)
		return cwd, argv

	def run(self, args=None, cwd=None):
		'''Run application in the foreground and wait for it to return.
		An exception will be thrown if the application returns non-zero.
		'''
		cwd, argv = self._checkargs(cwd, args)
		logger.info('Running: %s (cwd: %s)', argv, cwd)
		subprocess.check_call(argv, cwd=cwd, stdout=open(os.devnull, 'w'))

	def pipe(self, args=None, cwd=None, input=None):
		'''Run application in the foreground and wait for it to return.
		This method returns stdout while logging stderr as warning.
		Output is returned as a list of lines.
		'''
		cwd, argv = self._checkargs(cwd, args)
		logger.info('Running: %s (cwd: %s)', argv, cwd)
		stdout, stderr = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE).communicate(input)

		if stderr:
			logger.warn(stderr)

		return [line + '\n' for line in stdout.splitlines()]
			# Explicit newline conversion, e.g. on windows \r\n -> \n

	def spawn(self, args=None, callback=None, data=None, cwd=None):
		'''Run application in the background and return immediatly.

		The optional callback can be used to trigger when the application
		exits. The signature is:

			callback(status)

		where 'status' is the exit status of the process. The application
		object provides a constant 'STATUS_OK' which can be used to test if
		the application was successful or not.
		'''
		# TODO: can we build this based on os.spawn ? - seems this method fails on win32
		cwd, argv = self._checkargs(cwd, args)
		opts = {}

		flags = gobject.SPAWN_SEARCH_PATH
		if callback:
			flags |= gobject.SPAWN_DO_NOT_REAP_CHILD
			# without this flag child is reaped autmatically -> no zombies

		logger.info('Spawning: %s (cwd: %s)', argv, cwd)
		try:
			pid, stdin, stdout, stderr = \
				gobject.spawn_async(argv, flags=flags, **opts)
		except gobject.GError:
			logger.exception('Failed running: %s', argv)
			name = self.name
			#~ ErrorDialog(None, _('Could not run application: %s') % name).run()
				#~ # T: error when application failed to start
			return None
		else:
			logger.debug('Process started with PID: %i', pid)
			if callback:
				# child watch does implicite reaping -> no zombies
				if data is None:
					gobject.child_watch_add(pid,
						lambda pid, status: callback(status))
				else:
					gobject.child_watch_add(pid,
						lambda pid, status, data: callback(status, data), data)
			return pid


class WebBrowser(Application):
	'''Wrapper for the webbrowser module with the Application API. Can be
	used as fallback if no webbrowser is configured.
	'''

	name = _('Default') + ' (webbrowser)' # T: label for default webbrowser
	key = 'webbrowser' # Used by zim.gui.applications

	def __init__(self):
		import webbrowser
		self.controller = None
		try:
			self.controller = webbrowser.get()
		except webbrowser.Error:
			pass # webbrowser throws an error when no browser is found

	def tryexec(self):
		return not self.controller is None

	def run(self, args):
		raise NotImplementedError, 'WebBrowser can not run in foreground'

	def spawn(self, args, callback=None):
		if callback:
			raise NotImplementedError, 'WebBrowser can not handle callback'

		for url in args:
			logger.info('Opening in webbrowser: %s', url)
			self.controller.open(url)


class StartFile(Application):
	'''Wrapper for os.startfile(). Usefull mainly on windows to open
	files with the default application.
	'''

	name = _('Default') + ' (os)' # T: label for default application
	key = 'startfile' # Used by zim.gui.applications

	def __init__(self):
		pass

	def tryexec(self):
		return hasattr(os, 'startfile')

	def run(self, args):
		raise NotImplementedError, 'StartFile can not run in foreground'

	def spawn(self, args, callback=None):
		if callback:
			logger.warn('os.startfile does not support a callback')

		for file in args:
			path = os.path.normpath(unicode(file))
			logger.info('Opening with os.startfile: %s', path)
			os.startfile(path)
