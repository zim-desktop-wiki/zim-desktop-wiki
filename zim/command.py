# -*- coding: utf-8 -*-

# Copyright 2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>


from getopt import gnu_getopt, GetoptError

import logging

logger = logging.getLogger('zim')


from zim import __version__
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

	default_options	 = (
		('verbose', 'V', 'Verbose output'),
		('debug', 'D', 'Debug output'),
	)

	use_gtk = False #: Flag whether this command uses a graphical interface

	def __init__(self, command, *args, **opts):
		'''Constructor
		@param command: the command switch (first commandline argument)
		@param args: positional commandline arguments
		@param opts: command options
		'''
		self.command = command
		self.args = list(args)
		self.opts = opts

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
