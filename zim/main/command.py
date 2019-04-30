
# Copyright 2013-2016 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''
This module is responsible for commandline parsing. It provides a base
class for the commandline commands defined in L{zim.main}
'''

import os

from getopt import gnu_getopt, GetoptError

import logging

logger = logging.getLogger('zim')


from zim.errors import Error


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

	default_options = (
		('verbose', 'V', 'Verbose output'),
		('debug', 'D', 'Debug output'),
	)

	def __init__(self, command, pwd=None):
		'''Constructor
		@param command: the command switch (first commandline argument)
		@param pwd: optional working directory path
		'''
		self.command = command
		self.args = []
		self.opts = {}
		self.pwd = pwd or os.getcwd()

	def parse_options(self, *args):
		'''Parse commandline options for this command
		Sets the attributes 'args' and 'opts' to a list of arguments
		and a dictionary of options respectively
		@param args: all remaining options to be parsed
		@raises GetOptError: when options are not correct
		'''
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
			raise UsageError('Command %s takes %i arguments' % (self.command, minimum))
		elif len(self.args) > len(self.arguments):
			raise UsageError('Command %s takes only %i arguments' % (self.command, len(self.args)))
		else:
			return tuple(self.args) \
				+ (None,) * (len(self.arguments) - len(self.args))

	def ignore_options(self, *options):
		for option in options:
			if self.opts.get(option) is not None:
				logger.warning('Option "%s" is ignored for this command', option)

	def run(self):
		'''Run the command
		@raises UsageError: when arguments are not correct
		@implementation: must be implemented by subclasses
		'''
		raise NotImplementedError


class GtkCommand(Command):
	'''Base class for commandline commands that result in a Gtk
	user interface being presented to the user or want to interact with the
	Gtk user interface.

	If the C{run()} method returns a window, it will be added to the
	application top level windows. And a C{Gtk.main} loop will run until
	all windows are destroyed.

	Commands derived from this class can be dispatched to the main application
	process. This is controlled by the C{standalone_process} property.

	NOTE: Do _not_ call C{Gtk.main} from the command, this will be
	done by the application object.
	'''

	default_options = Command.default_options + (
		('standalone', '', 'start a single instance, no background process'),
	)

	@property
	def standalone_process(self):
		return self.opts.get('standalone')

	def run_local(self):
		'''Method called in local process before we (try to) dispatch the
		command to the primary process. If it returns C{True} we assume the
		command is done and C{run()} is not called.
		If the command is called from the primary process directly, this method
		gets never called.
		'''
		return False
