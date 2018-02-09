
# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>



import tests

import os

from zim.plugins.quicknote import *

from zim.fs import File, Dir
from zim.gui.clipboard import Clipboard, SelectionClipboard


@tests.skipIf(os.name == 'nt', 'QuickNote not supported on Windows')
class TestQuickNotePlugin(tests.TestCase):

	def assertRun(self, args, text):
		cmd = QuickNotePluginCommand('quicknote')
		cmd.parse_options(*args)
		dialog = cmd.run()

		self.assertIsInstance(dialog, QuickNoteDialog)
		buffer = dialog.textview.get_buffer()
		start, end = buffer.get_bounds()
		result = start.get_text(end)
		self.assertTrue(text in result)

	def testMain(self):
		# Text on commandline
		text = 'foo bar baz\ndus 123'
		self.assertRun(('text=' + text,), text)
		self.assertRun(('--text', text), text)

		encoded = 'Zm9vIGJhciBiYXoKZHVzIDEyMwo='
		self.assertRun(('--text', encoded, '--encoding', 'base64'), text)

		encoded = 'foo%20bar%20baz%0Adus%20123'
		self.assertRun(('--text', encoded, '--encoding', 'url'), text)

		# Clipboard input
		text = 'foo bar baz\ndus 123'
		SelectionClipboard.clipboard.clear() # just to be sure
		SelectionClipboard.clipboard.set_text('', -1) # HACK to clear it
		Clipboard.set_text(text)
		self.assertRun(('input=clipboard',), text)
		self.assertRun(('--input', 'clipboard',), text)

		text = 'foo bar baz\ndus 456'
		SelectionClipboard.set_text(text)
		self.assertRun(('input=clipboard',), text)
		self.assertRun(('--input', 'clipboard',), text)

		# Template options
		cmd = QuickNotePluginCommand('quicknote')
		cmd.parse_options('option:url=foo')
		self.assertEqual(cmd.template_options, {'url': 'foo'})

		cmd = QuickNotePluginCommand('quicknote')
		cmd.parse_options('--option', 'url=foo')
		self.assertEqual(cmd.template_options, {'url': 'foo'})

	# TODO: other commandline args
	# TODO: widget interaction - autcomplete etc.
