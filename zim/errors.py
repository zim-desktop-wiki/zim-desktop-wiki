# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# The Error class needed to be put in a separate file to avoid recusive
# imports.

class Error(Exception):
	'''Base class for all errors in zim.

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


class TrashNotSupportedError(Error):
	# Defined here because this is not specific to files, but can occur
	# in different storage models as well
	pass
