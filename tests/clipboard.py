# -*- coding: utf-8 -*-

# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>

#~ from __future__ import with_statement

import tests

import gtk
import zim.formats

from zim.gui.clipboard import *


def get_clipboard_contents(format):
	'''Convenience function to get data from clipboard'''
	myclipboard = gtk.Clipboard()
	selection = myclipboard.wait_for_contents(format)
	return selection.data


def set_clipboard_uris(*uris):
	'''Convenience function to put a file on the clipboard'''
	myclipboard = gtk.Clipboard()
	targets = [('text/uri-list', 0, 0)]

	def my_get_data(clipboard, selectiondata, id, file):
		selectiondata.set_uris(uris)

	def my_clear_data(*a):
		pass

	myclipboard.set_with_data(targets, my_get_data, my_clear_data, file)


def set_clipboard_image(file):
	'''Convenience function to put image data on the clipboard'''
	myclipboard = gtk.Clipboard()
	targets = [('image/png', 0, 0)]

	def my_get_data(clipboard, selectiondata, id, file):
		pixbuf = gtk.gdk.pixbuf_new_from_file(file.path)
		selectiondata.set_pixbuf(pixbuf)

	def my_clear_data(*a):
		pass

	myclipboard.set_with_data(targets, my_get_data, my_clear_data, file)


class TestClipboard(tests.TestCase):

	def setUp(self):
		path = self.get_tmp_name()
		self.notebook = tests.new_notebook(fakedir=path)

	def testCopyPasteText(self):
		text = u'test **123** \u2022' # text with non-ascii character
		Clipboard.set_text(text)
		result = Clipboard.get_text()
		self.assertEqual(result, text)
		self.assertTrue(isinstance(result, unicode))

	def testCopyPasteFromParseTree(self):
		# parsetree -> parsetree
		for pagename in ('Test:wiki', 'roundtrip'):
			page = self.notebook.get_page(Path(pagename))
			parsetree = page.get_parsetree()

			Clipboard.set_parsetree(self.notebook, page, parsetree)
			newtree = Clipboard.get_parsetree(self.notebook)
			self.assertEqual(newtree.tostring(), parsetree.tostring())

		# setup parsetree
		input = 'some **bold** text\n'
		parser = zim.formats.get_format('wiki').Parser()
		parsetree = parser.parse(input)
		Clipboard.set_parsetree(self.notebook, page, parsetree)

		# parsetree -> text (plain & wiki preference)
		# Note that pasting partial text (without newline) is tested
		# in the pageview test.
		wanted = 'some bold text\n'
		text = Clipboard.get_text()
		self.assertEqual(text, wanted)

		Clipboard.set_parsetree(self.notebook, page, parsetree, format='wiki')
		wanted = 'some **bold** text\n'
		text = Clipboard.get_text()
		self.assertEqual(text, wanted)

		# parsetree -> html (unix & windows)
		wanted = '''\
<html>
<head>
<meta http-equiv="Content-Type" content="text/html;charset=utf-8">
<meta name="Description" content="Copy-Paste Buffer">
<meta name="Generator" content="Zim">
</head>
<body>
<p>
some <b>bold</b> text
</p>

</body>
</html>
'''
		self.assertEqual(get_clipboard_contents('text/html'), wanted)

		wanted = '''\
Version:1.0\r
StartHTML:000000185\r
EndHTML:000000513\r
StartFragment:000000450\r
EndFragment:000000481\r
StartSelection:000000450\r
EndSelection:000000481\r
SourceURL:zim://copy-pase-buffer\r
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN"><HTML><HEAD><meta http-equiv="Content-Type" content="text/html;charset=utf-8">
<meta name="Description" content="Copy-Paste Buffer">
<meta name="Generator" content="Zim"></HEAD><BODY><!--StartFragment--><p>
some <b>bold</b> text
</p>
<!--EndFragment--></BODY></HTML>'''
		self.assertEqual(get_clipboard_contents('HTML Format'), wanted)

		# Test clear
		Clipboard.clear()
		self.assertTrue(Clipboard.get_parsetree() is None)


	def testCopyPasteToParseTree(self):
		# text -> tree
		wanted = '''<?xml version='1.0' encoding='utf-8'?>\n<zim-tree partial="True">some string</zim-tree>'''
		Clipboard.set_text('some string')
		newtree = Clipboard.get_parsetree(self.notebook)
		self.assertEqual(newtree.tostring(), wanted)

		# file link -> tree
		page = self.notebook.get_page(Path('Test:wiki'))

		file = File('/foo/bar/baz.txt')
		set_clipboard_uris(file.uri)
		tree = Clipboard.get_parsetree(self.notebook, page)
		link = tree.find('link')
		rel_path = link.get('href')
		self.assertEqual(self.notebook.resolve_file(rel_path, page), file)

		file = File('./data/zim.png') # image file
		set_clipboard_uris(file.uri)
		tree = Clipboard.get_parsetree(self.notebook, page)
		img = tree.find('img')
		file_obj = img.get('_src_file')
		self.assertEqual(file_obj, file)
		rel_path = img.get('src')
		self.assertEqual(self.notebook.resolve_file(rel_path, page), file)

		# uri list (could also be file list) -> tree
		set_clipboard_uris('http://cpan.org', 'ftp://foo@test.org', 'user@mail.com')
		tree = Clipboard.get_parsetree(self.notebook, page)
		links = tree.findall('link')
		hrefs = [e.attrib['href'] for e in links]
		self.assertEqual(hrefs,
			['http://cpan.org', 'ftp://foo@test.org', 'user@mail.com'])

		# image data -> tree
		page = self.notebook.get_page(Path('Test:wiki'))
		file = File('./data/zim.png')
		set_clipboard_image(file)
		tree = Clipboard.get_parsetree(self.notebook, page)
		img = tree.find('img')
		file_obj = img.get('_src_file')
		self.assertFalse(file_obj == file)
		self.assertTrue(file_obj.exists())
		self.assertTrue(file_obj.isimage())
		self.assertTrue(file_obj.path.endswith('.png'))
		rel_path = img.get('src')
		self.assertEqual(self.notebook.resolve_file(rel_path, page), file_obj)

	def testCopyPastePageLink(self):
		# pagelink -> uri list
		page = self.notebook.get_page(Path('Test:wiki'))
		Clipboard.set_pagelink(self.notebook, page)

		data = get_clipboard_contents(INTERNAL_PAGELIST_TARGET_NAME)
		self.assertEqual(data, 'Test:wiki\r\n')

		data = get_clipboard_contents(PAGELIST_TARGET_NAME)
		self.assertEqual(data, 'Unnamed Notebook?Test:wiki\r\n')

		# pagelink -> parsetree
		wanted = '''<?xml version=\'1.0\' encoding=\'utf-8\'?>\n<zim-tree><link href="+wiki">+wiki</link></zim-tree>'''
		newtree = Clipboard.get_parsetree(self.notebook, Path('Test'))
		self.assertEqual(newtree.tostring(), wanted)

		# pagelink -> text
		text = Clipboard.get_text()
		self.assertEqual(text, 'Test:wiki')

	#~ def testCopyPasteFile(self):
		#~ assert False

	#~ def testCopyPasteUrl(self):
		#~ assert False

# ClipboardManager.set_store
# ClipboardStore read / write / list
# ClipboardItem get / set / make permanent / drop
#
# Manager should be able to do paste-as, switching from plain text to wiki
# Distinguishe between cut and copied items
#
# LP #XXX: selection gone from clipboard when leaving page
#
# HTML -> parsetree (need import)



