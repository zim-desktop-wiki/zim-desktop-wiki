# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# The Error class needed to be put in a separate file to avoid recursive
# imports.

'''This module contains the base class for all errors in zim'''

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

	def __init__(self, msg):
		self.msg = msg

	def __str__(self):
		msg = self.__unicode__()
		return msg.encode('utf-8')

	def __unicode__(self):
		msg = u'' + self.msg.strip()
		if self.description:
			msg += '\n\n' + self.description.strip() + '\n'
		return msg

	def __repr__(self):
		return '<%s>' % self.__class__.__name__


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
