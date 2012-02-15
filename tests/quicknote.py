# -*- coding: utf-8 -*-

# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement

import tests

import os

from zim.plugins.quicknote import *
from zim.gui.clipboard import Clipboard, SelectionClipboard


@tests.skipIf(os.name == 'nt', 'QuickNote not supported on Windows')
class TestQuickNotePlugin(tests.TestCase):

	def testMain(self):
		def has_text(text):
			# create the actual check function
			def my_has_text(dialog):
				assert isinstance(dialog, QuickNoteDialog)
				buffer = dialog.textview.get_buffer()
				result = buffer.get_text(*buffer.get_bounds())
				#~ print result
				self.assertTrue(text in result)

			return my_has_text

		# Text on commandline
		text = 'foo bar baz\ndus 123'
		with tests.DialogContext(has_text(text)):
			main(None, 'text=' + text)

		# Clipboard input
		text = 'foo bar baz\ndus 123'
		SelectionClipboard.clipboard.clear() # just to be sure
		Clipboard.set_text(text)
		with tests.DialogContext(has_text(text)):
			main(None, 'input=clipboard')

		text = 'foo bar baz\ndus 456'
		SelectionClipboard.set_text(text)
		with tests.DialogContext(has_text(text)):
			main(None, 'input=clipboard')


	# TODO: other commandline args
	# TODO: widget interaction - autcomplete etc.
