# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains helper classes for running external applications.

See L{zim.gui.applications} for classes with desktop integration for
applications defined in desktop entry files.
'''

import sys
import os
import logging
import subprocess

import gobject

import zim.fs
import zim.errors

logger = logging.getLogger('zim.applications')


class ApplicationError(zim.errors.Error):
	'''Error raises for error in sub process errors'''

	description = None

	def __init__(self, cmd, args, retcode, stderr):
		'''Constructor

		@param cmd: the application command as string
		@param args: tuple of arguments given to the command
		@param retcode: the return code of the command (non-zero!)
		@param stderr: the error output of the command
		'''
		self.msg = _('Failed to run application: %s') % cmd
		self.description = \
			_('%s\nreturned non-zero exit status %i') \
			% (cmd + ' "' + '" "'.join(args) + '"', retcode)

		if stderr:
			self.description += '\n\n' + stderr


class Application(object):
	'''Base class for objects representing an external application or
	command.

	@ivar name: the name of the command (default to first item of C{cmd})
	@ivar cmd: the command and arguments as a tuple
	@ivar tryexeccmd: the command to check in L{tryexec()}, if C{None}
	fall back to first item of C{cmd}
	'''

	STATUS_OK = 0 #: return code when the command executed succesfully

	def __init__(self, cmd, tryexeccmd=None):
		'''Constructor

		@param cmd: the command for the external application, either a
		string for the command, or a tuple or list with the command
		and arguments
		@param tryexeccmd: command to check in L{tryexec()} as string.
		If C{None} will default to C{cmd} or the first item of C{cmd}.
		'''
		if isinstance(cmd, basestring):
			cm = (cmd,)
		else:
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
		'''Check if the executable exists without calling it. This
		method is used e.g. to decide what applications to show in the
		gui. Uses the C{tryexeccmd}, or the first item of C{cmd} as the
		executable name.
		@returns: C{True} when the executable was found
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
		'''Run the application in a sub-process and wait for it to finish.
		Even when the application runs successfully, any message to stderr
		is logged as a warning by zim.
		@param args: additional arguments to give to the command as tuple or list
		@param cwd: the folder to set as working directory for the command
		@raises ApplicationError: if the sub-process returned an error.
		'''
		cwd, argv = self._checkargs(cwd, args)
		logger.info('Running: %s (cwd: %s)', argv, cwd)
		p = subprocess.Popen(argv, cwd=cwd, stdout=open(os.devnull, 'w'), stderr=subprocess.PIPE)
		p.wait()
		stderr = p.stderr.read()

		if not p.returncode == self.STATUS_OK:
			raise ApplicationError(argv[0], argv[1:], p.returncode, p.stderr.read())
		#~ elif stderr:
			#~ logger.warn(stderr)

	def pipe(self, args=None, cwd=None, input=None):
		'''Run the application in a sub-process and capture the output.
		Like L{run()}, but connects to stdin and stdout for the sub-process.

		@note: The data read is buffered in memory, so do not use this
		method if the data size is large or unlimited.

		@param args: additional arguments to give to the command as tuple or list
		@param cwd: the folder to set as working directory for the command
		@param input: input for the command as string

		@returns: output as a list of lines
		@raises ApplicationError: if the sub-process returned an error.
		'''
		cwd, argv = self._checkargs(cwd, args)
		logger.info('Running: %s (cwd: %s)', argv, cwd)
		p = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE)
		stdout, stderr = p.communicate(input)
		# TODO: handle ApplicationERror here as well ?

		#~ if not p.returncode == self.STATUS_OK:
			#~ raise ApplicationError(argv[0], argv[1:], p.returncode, stderr)
		#~ elif stderr:
		if stderr:
			logger.warn(stderr)

		return [line + '\n' for line in stdout.splitlines()]
			# Explicit newline conversion, e.g. on windows \r\n -> \n

	def spawn(self, args=None, callback=None, data=None, cwd=None):
		'''Start the application in the background and return immediately.
		This is used to start an external in parallel with zim that is
		not expected to exit immediatly, so we do not want to wait for
		it - e.g. a webbrowser to show an URL that was clicked.

		@param args: additional arguments to give to the command as tuple or list
		@param callback: optional callback can be used to trigger when
		the application exits. The signature is::

			callback(status, data)

		where 'C{status}' is the exit status of the process. The
		application object provides a constant 'C{STATUS_OK}' which can
		be used to test if the application was successful or not.
		@param data: additional data for the callback
		@param cwd: the folder to set as working directory for the command
		@returns: the PID for the new process
		'''
		cwd, argv = self._checkargs(cwd, args)
		# if it is a python script, insert interpreter as the executable
		if argv[0].endswith('.py'):
			argv.insert(0, sys.executable)
		opts = {}

		flags = gobject.SPAWN_SEARCH_PATH
		if callback:
			flags |= gobject.SPAWN_DO_NOT_REAP_CHILD
			# without this flag child is reaped automatically -> no zombies

		logger.info('Spawning: %s (cwd: %s)', argv, cwd)
		try:
			pid, stdin, stdout, stderr = \
				gobject.spawn_async(argv, flags=flags, **opts)
		except gobject.GError:
			logger.exception('Failed running: %s', argv)
			#~ name = self.name
			#~ ErrorDialog(None, _('Could not run application: %s') % name).run()
				#~ # T: error when application failed to start
			return None
		else:
			logger.debug('Process started with PID: %i', pid)
			if callback:
				# child watch does implicit reaping -> no zombies
				if data is None:
					gobject.child_watch_add(pid,
						lambda pid, status: callback(status))
				else:
					gobject.child_watch_add(pid,
						lambda pid, status, data: callback(status, data), data)
			return pid


class WebBrowser(Application):
	'''Application wrapper for the C{webbrowser} module. Can be used as
	fallback if no webbrowser is configured.
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
		'''This method is not supported by this class
		@raises NotImplementedError: always
		'''
		raise NotImplementedError, 'WebBrowser can not run in foreground'

	def spawn(self, args, callback=None):
		if callback:
			raise NotImplementedError, 'WebBrowser can not handle callback'

		for url in args:
			logger.info('Opening in webbrowser: %s', url)
			self.controller.open(url)


class StartFile(Application):
	'''Application wrapper for C{os.startfile()}. Can be used on
	windows to open files with the default application.
	'''

	name = _('Default') + ' (os)' # T: label for default application
	key = 'startfile' # Used by zim.gui.applications

	def __init__(self):
		pass

	def tryexec(self):
		return hasattr(os, 'startfile')

	def run(self, args):
		'''This method is not supported by this class
		@raises NotImplementedError: always
		'''
		raise NotImplementedError, 'StartFile can not run in foreground'

	def spawn(self, args, callback=None):
		if callback:
			logger.warn('os.startfile does not support a callback')

		for file in args:
			path = os.path.normpath(unicode(file))
			logger.info('Opening with os.startfile: %s', path)
			os.startfile(path)
