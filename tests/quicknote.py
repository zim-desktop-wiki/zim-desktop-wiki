# -*- coding: utf-8 -*-

# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement

import tests
from tests.gui import setupGtkInterface

import os

from zim.plugins.quicknote import *

from zim.fs import File, Dir
from zim.gui.clipboard import Clipboard, SelectionClipboard


@tests.skipIf(os.name == 'nt', 'QuickNote not supported on Windows')
class TestQuickNotePlugin(tests.TestCase):

	def testMain(self):
		def main(*args):
			cmd = QuickNotePluginCommand('quicknote')
			cmd.parse_options(*args)
			cmd.run()

		def has_text(text):
			# create the actual check function
			def my_has_text(dialog):
				self.assertIsInstance(dialog, QuickNoteDialog)
				buffer = dialog.textview.get_buffer()
				result = buffer.get_text(*buffer.get_bounds())
				self.assertTrue(text in result)

			return my_has_text

		# Text on commandline
		text = 'foo bar baz\ndus 123'
		with tests.DialogContext(has_text(text)):
			main('text=' + text)

		with tests.DialogContext(has_text(text)):
			main('--text', text)

		encoded = 'Zm9vIGJhciBiYXoKZHVzIDEyMwo='
		with tests.DialogContext(has_text(text)):
			main('--text', encoded, '--encoding', 'base64')

		encoded = 'foo%20bar%20baz%0Adus%20123'
		with tests.DialogContext(has_text(text)):
			main('--text', encoded, '--encoding', 'url')

		# Clipboard input
		text = 'foo bar baz\ndus 123'
		SelectionClipboard.clipboard.clear() # just to be sure
		Clipboard.set_text(text)
		with tests.DialogContext(has_text(text)):
			main('input=clipboard')

		with tests.DialogContext(has_text(text)):
			main('--input', 'clipboard')

		text = 'foo bar baz\ndus 456'
		SelectionClipboard.set_text(text)
		with tests.DialogContext(has_text(text)):
			main('input=clipboard')

		with tests.DialogContext(has_text(text)):
			main('--input', 'clipboard')

		# Template options
		cmd = QuickNotePluginCommand('quicknote')
		cmd.parse_options('option:url=foo')
		self.assertEqual(cmd.template_options, {'url': 'foo'})

		cmd = QuickNotePluginCommand('quicknote')
		cmd.parse_options('--option', 'url=foo')
		self.assertEqual(cmd.template_options, {'url': 'foo'})

	# TODO: other commandline args
	# TODO: widget interaction - autcomplete etc.

	@tests.slowTest
	def testUIInterface(self):
		# test ui.new_page_from_text()

		name = 'foo:new page quicknote'
		text = '''\
======= New Page =======
Test 1 2 3

attachment {{./zim16.png}}
'''
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><h level="1">New Page</h>
<p>Test 1 2 3
</p>
<p>attachment <img src="./zim16.png" />
</p></zim-tree>'''

		dirname = self.create_tmp_dir(name='import_source')
		File('./icons/zim16.png').copyto(Dir(dirname))

		ui = setupGtkInterface(self)
		path = ui.new_page_from_text(text, name, attachments=dirname)
		page = ui.notebook.get_page(path)
		attachments = ui.notebook.get_attachments_dir(path)

		self.assertEqual(page.get_parsetree().tostring(), wanted)
		self.assertIn('zim16.png', attachments.list())


	#~ @tests.slowTest
	#~ def testAppend(self):
		#~ # test ui.append_text_to_page()
		#~ pass
