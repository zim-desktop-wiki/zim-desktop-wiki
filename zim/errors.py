# -*- coding: utf-8 -*-

# Copyright 2009-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# The Error class needed to be put in a separate file to avoid recursive
# imports.

'''This module contains the base class for all errors in zim'''

import sys
import logging

logger = logging.getLogger('zim')


use_gtk_errordialog = False

def set_use_gtk(use_gtk):
	'''Set whether or not L{show_error} and L{exception_handler}
	shold use the L{ErrorDialog} or not.
	@param use_gtk: set C{True} for interactive gui, C{False} for
	terminal mode
	'''
	global use_gtk_errordialog
	use_gtk_errordialog = use_gtk


def get_error_msg(error):
	'''Returns the message to show for an error
	@param error: error object or string
	@returns: 2-tuple of: message string and a boolean
	whether a traceback should be shown or not
	'''
	if isinstance(error, Error):
		# An "expected" error
		return error.msg, False

	elif isinstance(error, EnvironmentError):
		# Normal error, e.g. OSError or IOError
		msg = error.strerror
		if hasattr(error, 'filename') and error.filename:
			msg += ': ' + error.filename
		return msg, False

	else:
		# An unexpected error, all other Exception's
		msg = _('Looks like you found a bug') # T: generic error dialog
		return msg, True


def log_error(error, debug=None):
	'''Log error and traceback
	@param error: error as understood by L{get_error_msg()}
	@param debug: optional debug message, defaults to the error itself
	'''
	msg, show_trace = get_error_msg(error)
	if debug is None:
		debug = msg

	if show_trace:
		# unexpected error - will be logged with traceback
		logger.exception(debug)
	else:
		# expected error - log trace to debug
		logger.debug(debug, exc_info=1)
		logger.error(msg)


def _run_error_dialog(error):
	#~ try:
	from zim.gui.widgets import ErrorDialog
	ErrorDialog(None, error, do_logging=False).run()
	#~ except:
		#~ logger.error('Failed to run error dialog')


def show_error(error):
	'''Show an error by calling L{log_error()} and when running
	interactive also calling L{ErrorDialog}.
	@param error: the error object
	'''
	log_error(error)
	if use_gtk_errordialog:
		_run_error_dialog(error)


def exception_handler(debug):
	'''Like C{show_error()} but with debug message instead of the actual
	error. Intended to be used in C{except} blocks as a catch-all for
	both intended and unintended errors.
	@param debug: debug message for logging
	'''
	# We use debug as log message, rather than the error itself
	# the error itself shows up in the traceback anyway
	exc_info = sys.exc_info()
	error = exc_info[1]
	del exc_info # recommended by manual

	log_error(error, debug=debug)
	if use_gtk_errordialog:
		_run_error_dialog(error)


class Error(Exception):
	'''Base class for all errors in zim.

	This class is intended for application and usage errors, these will
	be caught in the user interface and presented as error dialogs.
	In contrast and Exception that does I{not} derive from this base
	class will result in a "You found a bug" dialog. Do not use this
	class e.g. to catch programming errors.

	Subclasses should define two attributes. The first is 'msg', which is
	the short description of the error. Typically this gives the specific
	input / page / ... which caused the error. In there should be an attribute
	'description' (either as class attribute or object attribute) with a verbose
	description. This description can be less specific but should explain
	the error in a user friendly way. The default behavior is to take 'msg' as
	the single argument for the constructor. So a minimal subclass only needs
	to define a class attribute 'description'.

	For a typical error dialog in the Gtk interface the short string from 'msg'
	will be shown as the title in bold letters while the longer 'description'
	is shown below it in normal letters. As a guideline error classes that are
	used in the gui or that can be e.g. be raised on invalid input from the
	user should be translated.
	'''

	description = ''
	msg = '<Unknown Error>'
		# in case subclass does not define instance attribute

	def __init__(self, msg, description=None):
		self.msg = msg
		if description:
			self.description = description
			# else use class attribute

	def __str__(self):
		msg = self.__unicode__()
		return msg.encode('utf-8')

	def __unicode__(self):
		msg = u'' + self.msg.strip()
		if self.description:
			msg += '\n\n' + self.description.strip() + '\n'
		return msg

	def __repr__(self):
		return '<%s: %s>' % (self.__class__.__name__, self.msg)


# Defined here because these errors are not specific to files, but can
# occur in different storage models as well

class TrashNotSupportedError(Error):
	'''Error raised when trashing is not supported and delete should
	be used instead
	'''
	pass

class TrashCancelledError(Error):
	'''Error raised when a trashign operation is cancelled. (E.g. on
	windows the system will prompt the user with a confirmation
	dialog which has a Cancel button.)
	'''
	pass
