# -*- coding: utf-8 -*-

# Copyright 2013-2016 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains base classes for the application.
These are used in L{zim.main} to construct that behavior of the
zim application when called from the commandline.

This module is responsible for commandline parsing, setting up
application processes, and dispatching to the application specific
logic.

NOTE: For Gtk3 replace this by using GtkApplication / GApplication

'''


from getopt import gnu_getopt, GetoptError

import os
import sys

import logging

logger = logging.getLogger('zim')


from zim import __version__
from zim.errors import Error

import zim.newipc


class UsageError(Error):
	'''Error raised when commands do not have correct
	number or type of arguments
	'''
	pass


class Command(object):
	'''Base class for commandline commands, used by zim to abstract
	part of the C{main()} functionality and allow better testability
	of commandline arguments.

	Sub-classes can define the options and arguments that they require.
	Then only the C{run()} method needs to be defined to implement the
	actual command. In the C{run()} method C{self.opts} and C{self.args}
	can be accessed to get the commandline options (dict) and the
	commandline arguments (list) respectively.
	'''

	arguments = () #: Define arguments, e.g ('NOTEBOOK', '[PAGE]')

	options = () #: Define options by 3-tuple of long, short & description.
		#: E.g. ("foo=", "f", "set parameter for foo")
		#: For options that can appear multiple times,
		#: assign a list "[]" in "self.opts" before parse_options is called

	default_options	 = (
		('verbose', 'V', 'Verbose output'),
		('debug', 'D', 'Debug output'),
	)

	use_gtk = False #: Flag whether this command uses a graphical interface

	def __init__(self, command):
		'''Constructor
		@param command: the command switch (first commandline argument)
		@param args: positional commandline arguments
		@param opts: command options
		'''
		self.command = command
		self.commandline = ['--'+command]
		self.args = []
		self.opts = {}

	def parse_options(self, *args):
		'''Parse commandline options for this command
		Sets the attributes 'args' and 'opts' to a list of arguments
		and a dictionary of options respectively
		@param args: all remaining options to be parsed
		@raises GetOptError: when options are not correct
		'''
		self.commandline.extend(args)

		options = ''
		long_options = []
		options_map = {}
		for l, s, desc in self.default_options + self.options:
			long_options.append(l)
			if s and l.endswith('='):
				options += s + ':'
				options_map[s] = l.strip('=')
			elif s:
				options += s
				options_map[s] = l

		optlist, args = gnu_getopt(args, options, long_options)
		self.args += args

		for o, a in optlist:
			key = o.strip('-')
			key = options_map.get(key, key)
			if a == '':
				self.opts[key] = True
			elif key in self.opts and isinstance(self.opts[key], list):
				self.opts[key].append(a)
			else:
				self.opts[key] = a

	def get_options(self, *names):
		'''Retrieve a dict with a sub-set of the command options
		@param names: that options in the subset
		'''
		return dict((k, self.opts.get(k)) for k in names)

	def get_arguments(self):
		'''Get the arguments, to be used by the implementation of C{run()}
		@raises UsageError: when arguments are not correct
		@returns: tuple of arguments, padded with None to correct length
		'''
		minimum = len([a for a in self.arguments if not a.startswith('[')])
		if len(self.args) < minimum:
			raise UsageError, 'Command %s takes %i arguments' % (self.command, minimum)
		elif len(self.args) > len(self.arguments):
			raise UsageError, 'Command %s takes only %i arguments' % (self.command, len(self.args))
		else:
			return tuple(self.args) \
				+ (None,) * (len(self.arguments) - len(self.args))

	def ignore_options(self, *options):
		for option in options:
			if self.opts.get(option) is not None:
				logger.warning('Option "%s" is ignored for this command', option)

	def set_logging(self):
		'''Configure the logging module for output based on the
		default options -V and -D
		'''
		if self.opts.get('debug'):
			level = logging.DEBUG
		elif self.opts.get('verbose'):
			level = logging.INFO
		else:
			level = logging.WARN

		root = logging.getLogger() # root
		root.setLevel(level)

		logger = logging.getLogger('zim')
		logger.info('This is zim %s', __version__)
		if level == logging.DEBUG:
			import sys
			import os
			import zim.config

			logger.debug('Python version is %s', str(sys.version_info))
			logger.debug('Platform is %s', os.name)
			logger.debug(zim.get_zim_revision())
			zim.config.log_basedirs()

	def run(self):
		'''Run the command
		@raises UsageError: when arguments are not correct
		@implementation: must be implemented by subclasses
		'''
		raise NotImplementedError



class PluginCommand(Command):

	def __init__(self, command):
		self.command = command
		self.commandline = ['--plugin', command]
		self.args = []
		self.opts = {}


from zim.utils import WeakSet
assert hasattr(WeakSet, '_del'), 'assure hack remains working'

class InstancesSet(WeakSet):
	'''Overloaded to exit application when last instance is
	destroyed.
	'''

	def _del(self, ref):
		print ">>> DEL"
		import gtk

		WeakSet._del(self, ref)
		if not list(self) \
		and gtk.main_level() > 0:
			print ">>>>>>>> QUIT"
			gtk.main_quit()


_INSTANCES = WeakSet()  # Global / Sigleton per process


def run_in_main_process(function):
	'''Decorator that wraps ipc logic around a C{run()} method.
	Ensures either main process is contacten, or a new main process
	is started.
	Only if the command has set the option "standalone" this wrapper
	is ignorerd.

	In this wrapper an argument C{instances} is added that holds a
	set that can be used to store unique object instnaces within the
	main process.

	Finally this wrapper is also responsible for calling C{gtk.main},
	don't try to do this from the C{run()} method.

	@note: never pass on C{instances} to other objects, this would violate
	the design principle on the decentralized object structure!
	'''
	def wrapper(cmd):
		assert cmd.use_gtk # dispatch handler assumes use of gtk main loop
		if zim.newipc.get_in_main_process():
			function(cmd, _INSTANCES)
		elif cmd.opts.get('standalone'):
			logger.debug('Running standalone process')

			import gtk, gobject
			gobject.threads_init()

			function(cmd, _INSTANCES)

			gtk.main()
		else:
			if _try_dispatch(cmd.commandline):
				pass # we are done
			else:
				# we become the main process
				logger.debug('Starting primary process')
				import gtk, gobject
				gobject.threads_init()

				_daemonize()
				zim.newipc.start_listening()
				function(cmd, _INSTANCES)

				gtk.main()

	return wrapper


def _try_dispatch(argv):
	try:
		zim.newipc.dispatch(*argv)
	except IOError:
		return False
	except Exception:
		logger.exception('Got error in dispatch')
		return False
	else:
		logger.debug('Dispatched command')
		return True


def _daemonize():
	# Decouple from parent environment
	# and redirect standard file descriptors
	os.chdir("/")

	try:
		si = file(os.devnull, 'r')
		os.dup2(si.fileno(), sys.stdin.fileno())
	except:
		pass

	loglevel = logging.getLogger().getEffectiveLevel()
	if loglevel <= logging.INFO and sys.stdout.isatty() and sys.stderr.isatty():
		# more detailed logging has lower number, so WARN > INFO > DEBUG
		# log to file unless output is a terminal and logging <= INFO
		pass
	else:
		# Redirect output to file
		dir = zim.fs.get_tmpdir()
		err_stream = open(os.path.join(dir.path, "zim.log"), "w")

		# First try to dup handles for anyone who still has a reference
		# if that fails, just set them
		sys.stdout.flush()
		sys.stderr.flush()
		try:
			os.dup2(err_stream.fileno(), sys.stdout.fileno())
			os.dup2(err_stream.fileno(), sys.stderr.fileno())
		except:
			# Maybe stdout / stderr were not real files
			# in the first place..
			sys.stdout = err_stream
			sys.stderr = err_stream

		# Re-initialize logging handler, in case it keeps reference
		# to the old stderr object
		try:
			rootlogger = logging.getLogger()
			for handler in rootlogger.handlers:
				rootlogger.removeHandler(handler)

			handler = logging.StreamHandler()
			handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
			rootlogger.addHandler(handler)
		except:
			pass
