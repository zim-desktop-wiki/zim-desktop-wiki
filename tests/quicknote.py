
# Copyright 2012,2024 Jaap Karssenberg <jaap.karssenberg@gmail.com>



import tests

import os

from zim.plugins.quicknote import *

from zim.gui.clipboard import Clipboard, SelectionClipboard


@tests.skipIf(os.name == 'nt', 'QuickNote not supported on Windows')
class TestQuickNotePlugin(tests.TestCase):

	def assertRun(self, args, text):
		# Bootstrap via "handle_local_commandline" to emulate
		# how application will handle this
		cmd = QuickNotePluginCommand('quicknote')
		cmd.parse_options(*args)
		args = cmd.handle_local_commandline(list(args))

		cmd = QuickNotePluginCommand('quicknote')
		cmd.parse_options(*args)
		dialog = cmd.run()

		self.assertIsInstance(dialog, QuickNoteDialog)
		buffer = dialog.textview.get_buffer()
		start, end = buffer.get_bounds()
		result = start.get_text(end)
		self.assertIn(text, result)

	def testMain(self):
		# Text on commandline
		text = 'foo bar baz\ndus 123'
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
		self.assertRun(('--input', 'clipboard',), text)

		text = 'foo bar baz\ndus 456'
		SelectionClipboard.set_text(text)
		self.assertRun(('--input', 'clipboard',), text)

		# Template options
		cmd = QuickNotePluginCommand('quicknote')
		cmd.parse_options('--option', 'url=foo')
		self.assertEqual(cmd.template_options, {'url': 'foo'})
		
		# Field assignments.
		cmd = QuickNotePluginCommand('quicknote')
		cmd.parse_options('--section', 'TheSection', '--title', 'TheTitle')
		self.assertEqual(cmd.opts['namespace'], 'TheSection')
		self.assertEqual(cmd.opts['basename'], 'TheTitle')
		
		# Field assignments.
		cmd = QuickNotePluginCommand('quicknote')
		cmd.parse_options('--namespace', 'TheSection', '--basename', 'TheTitle')
		self.assertEqual(cmd.opts['namespace'], 'TheSection')
		self.assertEqual(cmd.opts['basename'], 'TheTitle')
		
		# Field assignments, new options should override the deprecated ones.
		cmd = QuickNotePluginCommand('quicknote')
		cmd.parse_options('--namespace', 'TheNamespace', '--basename', 'Thebasename', '--section', 'TheSection', '--title', 'TheTitle')
		self.assertEqual(cmd.opts['namespace'], 'TheSection')
		self.assertEqual(cmd.opts['basename'], 'TheTitle')
		
		# Field assignments, interpret boolean flags correctly.
		cmd = QuickNotePluginCommand('quicknote')
		cmd.parse_options('--append', 'true', '--open', 'true')
		self.assertTrue(cmd.opts['append'])
		self.assertTrue(cmd.opts['open'])
		
		# Field assignments, interpret boolean flags correctly.
		cmd = QuickNotePluginCommand('quicknote')
		cmd.parse_options('--append', 'false', '--open', 'false')
		self.assertFalse(cmd.opts['append'])
		self.assertFalse(cmd.opts['open'])

	# TODO: other commandline args
	# TODO: widget interaction - autcomplete etc.
	# TODO: cursor placement by template instruction
