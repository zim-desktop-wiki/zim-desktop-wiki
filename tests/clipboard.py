
# Copyright 2012-2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

from gi.repository import Gtk
from gi.repository import Gdk

import zim.formats

from zim.gui.clipboard import *


def get_clipboard_contents(targetname):
	'''Convenience function to get data from clipboard'''
	myclipboard = Gtk.Clipboard.get(Gdk.SELECTION_PRIMARY)
	atom = Gdk.Atom.intern(targetname, False)
	selection = myclipboard.wait_for_contents(atom)
	assert selection is not None
	return selection.data


def set_clipboard_uris(*uris):
	'''Convenience function to put a file on the clipboard'''
	myclipboard = Gtk.Clipboard()
	targets = [('text/uri-list', 0, 0)]

	def my_get_data(clipboard, selectiondata, id, file):
		selectiondata.set_uris(uris)

	def my_clear_data(*a):
		pass

	myclipboard.set_with_data(targets, my_get_data, my_clear_data, file)


def set_clipboard_image(file):
	'''Convenience function to put image data on the clipboard'''
	myclipboard = Gtk.Clipboard()
	targets = [('image/png', 0, 0)]

	def my_get_data(clipboard, selectiondata, id, file):
		pixbuf = GdkPixbuf.Pixbuf.new_from_file(file.path)
		selectiondata.set_pixbuf(pixbuf)

	def my_clear_data(*a):
		pass

	myclipboard.set_with_data(targets, my_get_data, my_clear_data, file)


class TestClipboard(tests.TestCase):

	def setUp(self):
		self.notebook = self.setUpNotebook(content=('Test',))

	def testCopyPasteText(self):
		text = 'test **123** \u2022' # text with non-ascii character
		Clipboard.set_text(text)
		result = Clipboard.get_text()
		self.assertEqual(result, text)
		self.assertTrue(isinstance(result, str))

	def testCopyParseTreePasteAsParseTree(self):
		page = self.notebook.get_page(Path('Test'))
		parsetree = page.get_parsetree()
		Clipboard.set_parsetree(self.notebook, page, parsetree)
		newtree = Clipboard.get_parsetree(self.notebook)
		self.assertEqual(newtree.tostring(), parsetree.tostring())

	def testCopyParseTreePasteAsText(self):
		# setup parsetree
		page = self.notebook.get_page(Path('Test'))
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

	@tests.expectedFailure
	def testCopyParseTreePasteAsHTML(self):
		# setup parsetree
		page = self.notebook.get_page(Path('Test'))
		input = 'some **bold** text\n'
		parser = zim.formats.get_format('wiki').Parser()
		parsetree = parser.parse(input)
		Clipboard.set_parsetree(self.notebook, page, parsetree)

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

	def testCopyTextPasteAsParseTree(self):
		wanted = '''<?xml version='1.0' encoding='utf-8'?>\n<zim-tree partial="True">some string</zim-tree>'''
		Clipboard.set_text('some string')
		newtree = Clipboard.get_parsetree(self.notebook)
		self.assertEqual(newtree.tostring(), wanted)

	@tests.expectedFailure
	def testCopyFileURIPasteAsParseTree1(self):
		self._testCopyFileURIPasteAsParseTree(set_clipboard_uris)

	def testCopyFileURIPasteAsParseTree2(self):
		self._testCopyFileURIPasteAsParseTree(Clipboard.set_uri)

	def _testCopyFileURIPasteAsParseTree(self, set_func):
		page = self.notebook.get_page(Path('Test:wiki'))
		file = File('/foo/bar/baz.txt')
		set_func(file.uri)
		tree = Clipboard.get_parsetree(self.notebook, page)
		link = tree.find('link')
		rel_path = link.get('href')
		self.assertEqual(self.notebook.resolve_file(rel_path, page), file)

	@tests.expectedFailure
	def testCopyImageFileURIPasteAsParseTree1(self):
		self._testCopyImageFileURIPasteAsParseTree(set_clipboard_uris)

	def testCopyImageFileURIPasteAsParseTree2(self):
		self._testCopyImageFileURIPasteAsParseTree(Clipboard.set_uri)

	def _testCopyImageFileURIPasteAsParseTree(self, set_func):
		page = self.notebook.get_page(Path('Test:wiki'))
		file = File('./data/zim.png') # image file
		set_func(file.uri)
		tree = Clipboard.get_parsetree(self.notebook, page)
		img = tree.find('img')
		file_obj = img.get('_src_file')
		self.assertEqual(file_obj, file)
		rel_path = img.get('src')
		self.assertEqual(self.notebook.resolve_file(rel_path, page), file)

	@tests.expectedFailure
	def testCopyURIListPasteAsParseTree1(self):
		self._testCopyURIListPasteAsParseTree(set_clipboard_uris)

	def testCopyURIListPasteAsParseTree2(self):
		self._testCopyURIListPasteAsParseTree(Clipboard.set_uri)

	def _testCopyURIListPasteAsParseTree(self, set_func):
		set_func('http://cpan.org', 'ftp://foo@test.org', 'user@mail.com')
		page = self.notebook.get_page(Path('Test:wiki'))
		tree = Clipboard.get_parsetree(self.notebook, page)
		links = tree.findall('link')
		hrefs = [e.attrib['href'] for e in links]
		self.assertEqual(hrefs,
			['http://cpan.org', 'ftp://foo@test.org', 'user@mail.com'])

	@tests.expectedFailure
	def testCopyImagePasteAsParseTree(self):
		inner = self.notebook.get_attachments_dir
		self.notebook.get_attachments_dir = lambda p: LocalFolder(inner(p).path) # fixture to ensure local folder used

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

	def testCopyPageLinkPasteAsParseTree(self):
		page = self.notebook.get_page(Path('Test:wiki'))
		Clipboard.set_pagelink(self.notebook, page)
		wanted = '''<?xml version=\'1.0\' encoding=\'utf-8\'?>\n<zim-tree><link href="+wiki">+wiki</link></zim-tree>'''
		newtree = Clipboard.get_parsetree(self.notebook, Path('Test'))
		self.assertEqual(newtree.tostring(), wanted)

	def testCopyPageLinkPasteAsText(self):
		page = self.notebook.get_page(Path('Test:wiki'))
		Clipboard.set_pagelink(self.notebook, page)
		text = Clipboard.get_text()
		self.assertEqual(text, 'Test:wiki')

	#~ def testCopyPasteFile(self):
		#~ assert False

	#~ def testCopyPasteUrl(self):
		#~ assert False
