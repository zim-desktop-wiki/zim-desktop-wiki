
# Copyright 2009,2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains helper classes for running external applications.

See L{zim.gui.applications} for classes with desktop integration for
applications defined in desktop entry files.
'''

import sys
import os
import re
import logging
import subprocess
import locale

from gi.repository import GObject
from gi.repository import GLib

import zim.errors

from zim.fs import adapt_from_oldfs
from zim.newfs import SEP, is_abs_filepath, FilePath, LocalFile
from zim.parsing import is_uri_re, is_win32_path_re


logger = logging.getLogger('zim.applications')


TEST_MODE = False
TEST_MODE_RUN_CB = None

_ENCODING = locale.getpreferredencoding()

def _decode(data):
	# Since we do not know for sure what encoding other processes will use
	# for output, we need to guess :(
	try:
		return data.decode('UTF-8')
	except UnicodeDecodeError:
		return data.decode(_ENCODING)


_FLATPAK_HOSTCOMMAND_PREFIX = ("flatpak-spawn", "--host")

def _check_flatpak_host_command():
	# Detect whether we are running in Flatpak and can call HostCommand
	if os.path.exists("/.flatpak-info"):
		try:
			subprocess.check_call(_FLATPAK_HOSTCOMMAND_PREFIX + ("which", "which"), stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
			return True
		except subprocess.CalledProcessError:
			pass  # Not privileged to call host command or "which" not found in the host
		except OSError:
			pass  # Failed to execute flatpak-spawn
	return False

_CAN_CALL_FLATPAK_HOST_COMMAND = _check_flatpak_host_command()

def _main_is_frozen():
	# Detect whether we are running py2exe compiled version
	return hasattr(sys, 'frozen') and sys.frozen


def _split_environ_list(value):
	if isinstance(value, str):
		return value.split(os.pathsep)
	elif value is None:
		return []
	else:
		raise ValueError



_word_re = re.compile(r'''
	(
		"(\\"|[^"])*" |  # double quoted word
		[^\s"]+          # word without spaces
	)''', re.X)


def split_quoted_strings(string):
	'''Split a word list respecting quotes according to XDG desktop entry spec

	Only supports double quotes as specified in the spec

	This function always expect full words to be quoted, even if quotes
	appear in the middle of a word, they are considered word
	boundries.

	( XDG Desktop Entry spec says full words must be quoted and
	quotes in a word escaped, but doesn't specify what to do with
	loose quotes in a string. Also this spec does not allow single
	quote quotes)
	'''
	string = string.strip()
	words = []
	m = _word_re.match(string)
	while m:
		w = m.group(0)

		words.append(w)
		i = m.end()
		string = string[i:].lstrip()
		m = _word_re.match(string)

	if string:
		words += string.split() # unmatched quote ?

	return [_unescape_quoted_string(w) for w in words if w]


def _unescape_quoted_string(string):
	# XDG Desktop entry spec says:"If an argument contains a reserved character
	# the argument *must* be quoted."
	# Therefore, unquoted arguments with backslash are invalid. However on
	# Windows we may have created these, so for backward compatibility pass
	# them through without unescaping.
	# Unescaping here does not target \n etc. but \" and other reserved characters
	# avoid touching alphabetic chars in case there are invalid paths in the string
	if string[0] == '"' and string[-1] == '"':
		return re.sub(r'\\(\W)', '\\1', string[1:-1])
	else:
		return string


class ApplicationLookUpError(zim.errors.Error):
	'''Error raised when an application is not found'''

	description = None

	def __init__(self, cmd):
		self.msg = _('Cound not find application: %s') % cmd
			# T: Error message when external application could not be found, %s is the command


class ApplicationError(zim.errors.Error):
	'''Error raised for errors in the sub process'''

	description = None

	def __init__(self, cmd, args, retcode, stderr):
		'''Constructor

		@param cmd: the application command as string
		@param args: tuple of arguments given to the command
		@param retcode: the return code of the command (non-zero!)
		@param stderr: the error output of the command
		'''
		self.msg = _('Failed to run application: %s') % cmd
			# T: Error message when external application failed, %s is the command
		self.description = \
			_('%(cmd)s\nreturned non-zero exit status %(code)i') \
			% {'cmd': cmd + ' "' + '" "'.join(args) + '"', 'code': retcode}
			# T: Error message when external application failed, %(cmd)s is the command, %(code)i the exit code

		if stderr:
			self.description += '\n\n' + stderr


class Application(object):
	'''Base class for objects representing an external application or
	command.

	@ivar name: the name of the command (default to first item of C{cmd})
	@ivar cmd: the command and arguments as a tuple or a string
	(when given as a string it will be parsed for quoted arguments)
	@ivar tryexeccmd: the command to check in L{tryexec()}, if C{None}
	fall back to first item of C{cmd}
	'''

	STATUS_OK = 0 #: return code when the command executed successfullly

	def __init__(self, cmd, tryexeccmd=None):
		'''Constructor

		@param cmd: the command for the external application, either a
		string for the command, or a tuple or list with the command
		and arguments
		@param tryexeccmd: command to check in L{tryexec()} as string.
		If C{None} will default to C{cmd} or the first item of C{cmd}.
		'''
		if isinstance(cmd, str):
			cmd = split_quoted_strings(cmd)
		else:
			assert isinstance(cmd, (tuple, list))
		assert tryexeccmd is None or isinstance(tryexeccmd, str)
		self.cmd = tuple(cmd)
		self.tryexeccmd = tryexeccmd

	def __eq__(self, other):
		if isinstance(other, Application):
			return (self.cmd, self.tryexeccmd) == (other.cmd, other.tryexeccmd)
		else:
			return False

	def __repr__(self):
		if hasattr(self, 'key'):
			return '<%s: %s>' % (self.__class__.__name__, self.key)
		elif hasattr(self, 'cmd'):
			return '<%s: %s>' % (self.__class__.__name__, self.cmd)
		else:
			return '<%s: %s>' % (self.__class__.__name__, self.name)

	@property
	def name(self):
		return self.cmd[0]

	@staticmethod
	def _lookup(cmd):
		'''Lookup cmd in PATH'''
		if is_abs_filepath(cmd):
			if os.path.isfile(cmd):
				return cmd
			else:
				return None
		elif os.name == 'nt':
			# Check executable extensions from windows environment
			extensions = _split_environ_list(os.environ.get('PATHEXT', '.com;.exe;.bat;.cmd'))
			for dir in _split_environ_list(os.environ.get('PATH')):
				for ext in extensions:
					file = SEP.join((dir, cmd + ext))
					if os.path.isfile(file) and os.access(file, os.X_OK):
						return file
			else:
				return None
		else:
			# On POSIX no extension is needed to make scripts executable
			for dir in _split_environ_list(os.environ.get('PATH')):
				file = SEP.join((dir, cmd))
				if os.path.isfile(file) and os.access(file, os.X_OK):
					return file
			else:
				if _CAN_CALL_FLATPAK_HOST_COMMAND:
					try:
						file = subprocess.check_output(_FLATPAK_HOSTCOMMAND_PREFIX + ("which", cmd), stderr=subprocess.DEVNULL)
						return file
					except subprocess.CalledProcessError:
						pass
				return None

	def _cmd(self, args):
		# substitute args in the command - to be overloaded by child classes
		if args:
			return self.cmd + tuple(map(str, args))
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
		argv = self._cmd(args)

		# Expand home dir
		if argv[0].startswith('~'):
			cmd = LocalFile(argv[0]).path
			argv = list(argv)
			argv[0] = cmd

		# if it is a python script, insert interpreter as the executable
		if argv[0].endswith('.py') and not _main_is_frozen():
			argv = list(argv)
			argv.insert(0, sys.executable)
		# TODO: consider an additional commandline arg to re-use compiled python interpreter

		if hasattr(cwd, 'path'):
			cwd = cwd.path

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
		logger.info('Running: %r (cwd: %r)', argv, cwd)
		if TEST_MODE:
			TEST_MODE_RUN_CB(argv)
			return None

		if os.name == 'nt':
			# http://code.activestate.com/recipes/409002/
			info = subprocess.STARTUPINFO()
			try:
				info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
			except AttributeError:
				info.dwFlags |= 1 # STARTF_USESHOWWINDOW = 0x01

			p = subprocess.Popen(argv,
				cwd=cwd,
				stdout=subprocess.DEVNULL,
				stderr=subprocess.PIPE,
				startupinfo=info,
				bufsize=4096,
				#~ close_fds=True
			)
		else:
			try:
				p = subprocess.Popen(argv,
					cwd=cwd,
					stdout=subprocess.DEVNULL,
					stderr=subprocess.PIPE,
					bufsize=4096,
					close_fds=True
				)
			except OSError:
				if _CAN_CALL_FLATPAK_HOST_COMMAND:
					p = subprocess.Popen(_FLATPAK_HOSTCOMMAND_PREFIX + argv,
						cwd=cwd,
						stdout=subprocess.DEVNULL,
						stderr=subprocess.PIPE,
						bufsize=4096,
						close_fds=True
					)
				else:
					raise
		stdout, stderr = p.communicate()

		if not p.returncode == self.STATUS_OK:
			raise ApplicationError(argv[0], argv[1:], p.returncode, _decode(stderr))
		#~ elif stderr:
			#~ logger.warn(_decode(stderr))

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
		logger.info('Running: %r (cwd: %r)', argv, cwd)
		if TEST_MODE:
			return TEST_MODE_RUN_CB(argv)

		startupinfo = None
		if os.name == 'nt':
			startupinfo = subprocess.STARTUPINFO()
			startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
			startupinfo.wShowWindow = subprocess.SW_HIDE
		try:
			p = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
		except OSError:
			if _CAN_CALL_FLATPAK_HOST_COMMAND:
				p = subprocess.Popen(_FLATPAK_HOSTCOMMAND_PREFIX + argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
			else:
				raise
		if input is None:
			stdout, stderr = p.communicate()
		else:
			data = input if isinstance(input, bytes) else str(input).encode('UTF-8')
				# No way to know what encoding the process accepts, so UTF-8 is as good as any
			stdout, stderr = p.communicate(data)

		#~ if not p.returncode == self.STATUS_OK:
			#~ raise ApplicationError(argv[0], argv[1:], p.returncode, stderr)
		#~ elif stderr:
		if stderr:
			logger.warning(_decode(stderr))
			# TODO: allow user to get this error as well - e.g. for logging image generator cmd

		text = _decode(stdout).replace('\r\n', '\n').splitlines(keepends=True)
		return text

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

		flags = GObject.SPAWN_SEARCH_PATH
		if callback:
			flags |= GObject.SPAWN_DO_NOT_REAP_CHILD
			# without this flag child is reaped automatically -> no zombies

		if cwd is None:
			cwd = os.getcwd()

		logger.info('Spawning: %s (cwd: %s)', argv, cwd)
		if TEST_MODE:
			TEST_MODE_RUN_CB(argv)
			return None

		# https://github.com/zim-desktop-wiki/zim-desktop-wiki/issues/1697
		def _callback_wrapper(pid, *args):
			GLib.spawn_close_pid(pid)
			callback(*args)

		try:
			try:
				pid, stdin, stdout, stderr = \
					GObject.spawn_async(argv, flags=flags, working_directory=cwd)
			except (GObject.GError, GLib.Error):
				if _CAN_CALL_FLATPAK_HOST_COMMAND:
					pid, stdin, stdout, stderr = \
						GObject.spawn_async(_FLATPAK_HOSTCOMMAND_PREFIX + argv, flags=flags, working_directory=cwd)
				else:
					raise
		except (GObject.GError, GLib.Error):
			from zim.gui.widgets import ErrorDialog
			ErrorDialog(None, _('Failed running: %s') % argv[0]).run()
				#~ # T: error when application failed to start
			return None
		else:
			logger.debug('Process started with PID: %i', pid)
			if callback:
				# child watch does implicit reaping -> no zombies
				if data is None:
					GObject.child_watch_add(pid,
						lambda _, status: _callback_wrapper(pid, status))
				else:
					GObject.child_watch_add(pid,
						lambda _, status, data: _callback_wrapper(pid, status, data), data)
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

	def __eq__(self, other):
		return isinstance(other, self.__class__)

	def tryexec(self):
		return not self.controller is None

	def run(self, args):
		'''This method is not supported by this class
		@raises NotImplementedError: always
		'''
		raise NotImplementedError('WebBrowser can not run in foreground')

	def spawn(self, args, callback=None):
		if callback:
			raise NotImplementedError('WebBrowser can not handle callback')

		for url in args:
			if hasattr(url, 'uri'):
				url = url.uri
			logger.info('Opening in webbrowser: %s', url)

			if TEST_MODE:
				TEST_MODE_RUN_CB((self.__class__.__name__, url))
			else:
				self.controller.open(url)


class StartFile(Application):
	'''Application wrapper for C{os.startfile()}. Can be used on
	windows to open files and URLs with the default application.
	'''

	name = _('Default') + ' (os)' # T: label for default application
	key = 'startfile' # Used by zim.gui.applications

	def __init__(self):
		pass

	def __eq__(self, other):
		return isinstance(other, self.__class__)

	def tryexec(self):
		return hasattr(os, 'startfile')

	def run(self, args):
		'''This method is not supported by this class
		@raises NotImplementedError: always
		'''
		raise NotImplementedError('StartFile can not run in foreground')

	def spawn(self, args, callback=None):
		if callback:
			raise NotImplementedError('os.startfile does not support a callback')

		for arg in args:
			arg = adapt_from_oldfs(arg)
			if hasattr(arg, 'path'):
				path = os.path.normpath(arg.path).replace('/', SEP) # msys can use '/' instead of '\\'
			elif is_uri_re.match(arg) and not is_win32_path_re.match(arg) and not arg.startswith('file://'):
				# URL or e.g. mailto: or outlook: URI
				path = str(arg)
			else:
				# must be file as string
				try:
					arg = FilePath(arg).path
				except ValueError:
					pass

				path = os.path.normpath(str(arg)).replace('/', SEP) # msys can use '/' instead of '\\'

			logger.info('Opening with os.startfile: %s', path)
			if TEST_MODE:
				TEST_MODE_RUN_CB((self.__class__.__name__, path))
			else:
				os.startfile(path)
