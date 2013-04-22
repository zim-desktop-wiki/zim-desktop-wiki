# -*- coding: utf-8 -*-

# Copyright 2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import getopt
import logging

import zim

from zim.errors import Error


class UsageError(Error):
	'''Error raised when commands do not have correct
	number or type of arguments
	'''
	pass


class Command(object):
	'''Base class for commandline commands'''

	arguments = () #: Define arguments, e.g ('NOTEBOOK', '[PAGE]')

	options = () #: Define options by 3-tuple of long, short & description
		# e.g. ("foo=", "f", "set parameter for foo")

	default_options	 = (
		('verbose', 'V', 'Verbose output'),
		('debug', 'D', 'Debug output'),
	)

	def __init__(self, command, *args, **opts):
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

		optlist, args = getopt.gnu_getopt(args, options, long_options)
		self.args += args

		for o, a in optlist:
			key = o.strip('-')
			key = options_map.get(key, key)
			if a == '':
				self.opts[key] = True
			else:
				self.opts[key] = a

	def get_options(self, *names):
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

		logger = logging.getLogger() # root
		logger.setLevel(level)
		#~ logger.info('This is zim %s', zim.__version__)
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
