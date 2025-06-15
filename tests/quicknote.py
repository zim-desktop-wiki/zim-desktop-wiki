
# Copyright 2012,2024 Jaap Karssenberg <jaap.karssenberg@gmail.com>



import tests

import os

from zim.plugins.quicknote import *

from zim.gui.clipboard import Clipboard, SelectionClipboard


@tests.skipIf(os.name == 'nt', 'QuickNote not supported on Windows')
class TestQuickNotePlugin(tests.TestCase):

	def testMain(self):

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
