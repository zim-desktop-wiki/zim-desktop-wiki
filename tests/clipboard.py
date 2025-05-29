
# Copyright 2012-2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

from tests import os_native_path

import os

from gi.repository import Gtk
from gi.repository import Gdk

import zim.formats

from zim.newfs import LocalFile

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
		self.notebook = self.setUpNotebook(name='first notebook', content=('Test',))

	def testCopyPasteText(self):
		text = 'test **123** \u2022' # text with non-ascii character
		Clipboard.set_text(text)
		result = Clipboard.get_text()
		self.assertEqual(result, text)
		self.assertTrue(isinstance(result, str))

	def testCopyParseTreePasteAsParseTree(self):
		page = self.notebook.get_page(Path('Test'))
		parsetree = page.get_parsetree()
		Clipboard.set_parsetree(self.notebook, page, parsetree.copy())
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
		wanted = '''<?xml version='1.0' encoding='utf-8'?>\n<zim-tree>some **string**</zim-tree>'''
		Clipboard.set_text('some **string**')
		newtree = Clipboard.get_parsetree(self.notebook)
		self.assertEqual(newtree.tostring(), wanted)

	def testCopyTextPasteAsParseTreeWiki(self):
		wanted = '''<?xml version='1.0' encoding='utf-8'?>\n<zim-tree><p>some <strong>string</strong></p></zim-tree>'''
		Clipboard.set_text('some **string**')
		newtree = Clipboard.get_parsetree(self.notebook, text_format='wiki')
		self.assertEqual(newtree.tostring(), wanted)

	def testCopyTextPasteAsParseTreeVerbatim(self):
		wanted = '''<?xml version='1.0' encoding='utf-8'?>\n<zim-tree><pre>some **string**</pre></zim-tree>'''
		Clipboard.set_text('some **string**')
		newtree = Clipboard.get_parsetree(self.notebook, text_format='verbatim-pre')
		self.assertEqual(newtree.tostring(), wanted)

	def testCopyURLasTextPasteAsParseTree(self):
		# Special case, e.g. copy URL from browser address bar as text
		wanted = '''<?xml version='1.0' encoding='utf-8'?>\n<zim-tree><link href="https://localhost">https://localhost</link></zim-tree>'''
		Clipboard.set_text('https://localhost')
		newtree = Clipboard.get_parsetree(self.notebook)
		self.assertEqual(newtree.tostring(), wanted)

	@tests.expectedFailure
	def testCopyFileURIPasteAsParseTree1(self):
		self._testCopyFileURIPasteAsParseTree(set_clipboard_uris)

	def testCopyFileURIPasteAsParseTree2(self):
		self._testCopyFileURIPasteAsParseTree(Clipboard.set_uri)

	def _testCopyFileURIPasteAsParseTree(self, set_func):
		page = self.notebook.get_page(Path('Test:wiki'))
		file = LocalFile(os_native_path('/foo/bar/baz.txt'))
		set_func(file.uri)
		tree = Clipboard.get_parsetree(self.notebook, page)
		link = tree.find_element('link')
		rel_path = link.attrib.get('href')
		self.assertEqual(self.notebook.resolve_file(rel_path, page), file)

	@tests.expectedFailure
	def testCopyImageFileURIPasteAsParseTree1(self):
		self._testCopyImageFileURIPasteAsParseTree(set_clipboard_uris)

	def testCopyImageFileURIPasteAsParseTree2(self):
		self._testCopyImageFileURIPasteAsParseTree(Clipboard.set_uri)

	def _testCopyImageFileURIPasteAsParseTree(self, set_func):
		page = self.notebook.get_page(Path('Test:wiki'))
		file = tests.ZIM_DATA_FOLDER.file('./zim.png') # image file
		set_func(file.uri)
		tree = Clipboard.get_parsetree(self.notebook, page)
		img = tree.find_element('img')
		rel_path = img.attrib.get('src')
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
		hrefs = [e.attrib['href'] for e in tree.iter_elements('link')]
		self.assertEqual(hrefs,
			['http://cpan.org', 'ftp://foo@test.org', 'user@mail.com'])

	@tests.expectedFailure
	def testCopyImagePasteAsParseTree(self):
		inner = self.notebook.get_attachments_dir
		self.notebook.get_attachments_dir = lambda p: LocalFolder(inner(p).path) # fixture to ensure local folder used

		page = self.notebook.get_page(Path('Test:wiki'))
		file = tests.ZIM_DATA_FOLDER.file('./data/zim.png')
		set_clipboard_image(file)
		tree = Clipboard.get_parsetree(self.notebook, page)
		img = tree.find_element('img')
		rel_path = img.attrib.get('src')
		self.assertEqual(self.notebook.resolve_file(rel_path, page), file)

	def testCopyPageLinkPasteAsParseTree(self):
		page = self.notebook.get_page(Path('Test:wiki'))
		Clipboard.set_pagelink(self.notebook, page)
		wanted = '''<?xml version=\'1.0\' encoding=\'utf-8\'?>\n<zim-tree><link href="+wiki">+wiki</link></zim-tree>'''
		newtree = Clipboard.get_parsetree(self.notebook, Path('Test'))
		self.assertEqual(newtree.tostring(), wanted)

	def testCopyPageLinkPasteAsParseTreeInSamePage(self):
		page = self.notebook.get_page(Path('Test:wiki'))
		Clipboard.set_pagelink(self.notebook, page)
		wanted = '''<?xml version=\'1.0\' encoding=\'utf-8\'?>\n<zim-tree><link href="wiki">wiki</link></zim-tree>'''
		newtree = Clipboard.get_parsetree(self.notebook, page)
		self.assertEqual(newtree.tostring(), wanted)

	def testCopyPageLinkPasteAsParseTreeWithShortName(self):
		self.notebook.config['Notebook']['short_links'] = True
		page = self.notebook.get_page(Path('Test:wiki:Foo'))
		Clipboard.set_pagelink(self.notebook, page)
		wanted = '''<?xml version=\'1.0\' encoding=\'utf-8\'?>\n<zim-tree><link href="+wiki:Foo">Foo</link></zim-tree>'''
		newtree = Clipboard.get_parsetree(self.notebook, Path('Test'))
		self.assertEqual(newtree.tostring(), wanted)

	def testCopyPageLinkWithAnchorPasteAsParseTree(self):
		page = self.notebook.get_page(Path('Test:wiki'))
		Clipboard.set_pagelink(self.notebook, page, 'anchor')
		wanted = '''<?xml version=\'1.0\' encoding=\'utf-8\'?>\n<zim-tree><link href="+wiki#anchor">+wiki#anchor</link></zim-tree>'''
		newtree = Clipboard.get_parsetree(self.notebook, Path('Test'))
		self.assertEqual(newtree.tostring(), wanted)

	def testCopyPageLinkWithAnchorPasteAsParseTreeInSamePage(self):
		page = self.notebook.get_page(Path('Test:wiki'))
		Clipboard.set_pagelink(self.notebook, page, 'anchor')
		wanted = '''<?xml version=\'1.0\' encoding=\'utf-8\'?>\n<zim-tree><link href="#anchor">#anchor</link></zim-tree>'''
		newtree = Clipboard.get_parsetree(self.notebook, page)
		self.assertEqual(newtree.tostring(), wanted)

	def testCopyPageLinkWithAnchorAndTextPasteAsParseTree(self):
		page = self.notebook.get_page(Path('Test:wiki'))
		Clipboard.set_pagelink(self.notebook, page, 'anchor', 'My anchor')
		wanted = '''<?xml version=\'1.0\' encoding=\'utf-8\'?>\n<zim-tree><link href="+wiki#anchor">My anchor</link></zim-tree>'''
		newtree = Clipboard.get_parsetree(self.notebook, Path('Test'))
		self.assertEqual(newtree.tostring(), wanted)

	def testCopyPageLinkPasteAsText(self):
		page = self.notebook.get_page(Path('Test:wiki'))
		Clipboard.set_pagelink(self.notebook, page)
		text = Clipboard.get_text()
		self.assertEqual(text, 'Test:wiki')

	def testCopyPasteLinkInDifferentNotebook(self):
		othernotebook = self.setUpNotebook(name="othernotebook", content=('Test',))
		page = self.notebook.get_page(Path('Test:wiki'))
		Clipboard.set_pagelink(self.notebook, page)
		wanted = '''<?xml version=\'1.0\' encoding=\'utf-8\'?>\n<zim-tree><link href="first_notebook?Test:wiki">first_notebook?Test:wiki</link></zim-tree>'''
		newtree = Clipboard.get_parsetree(othernotebook, Path('Test'))
		self.assertEqual(newtree.tostring(), wanted)

	def testCopyPasteParseTreeWithLinkInSamePage(self):
		page = self.notebook.get_page(Path('Test'))
		page.parse('wiki', '[[+Foo]]\n[[+Foo|my foo link]]\n[[+Foo#anchor]]')
		parsetree = page.get_parsetree()
		Clipboard.set_parsetree(self.notebook, page, parsetree)

		newtree = Clipboard.get_parsetree(self.notebook, page)
		self.assertEqual(newtree.tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
			'<zim-tree><p>'
			'<link href="+Foo">+Foo</link>\n'
			'<link href="+Foo">my foo link</link>\n'
			'<link href="+Foo#anchor">+Foo#anchor</link>'
			'</p></zim-tree>'
		) # No need to update the link

	def testCopyPasteParseTreeWithLinkInDifferentPage(self):
		page = self.notebook.get_page(Path('Test'))
		page.parse('wiki', '[[+Foo]]\n[[+Foo|Foo]]\n[[+Foo|my foo link]]\n[[+Foo#anchor]]\n[[#anchor]]')
		parsetree = page.get_parsetree()
		Clipboard.set_parsetree(self.notebook, page, parsetree)

		newtree = Clipboard.get_parsetree(self.notebook, Path('OtherPage'))
		self.assertEqual(newtree.tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
			'<zim-tree><p>'
			'<link href="Test:Foo">Test:Foo</link>\n'
			'<link href="Test:Foo">Foo</link>\n'
			'<link href="Test:Foo">my foo link</link>\n'
			'<link href="Test:Foo#anchor">Test:Foo#anchor</link>\n'
			'<link href="Test#anchor">Test#anchor</link>'
			'</p></zim-tree>'
		) # Link updated to point to same target from new location

	def testCopyPasteParseTreeWithLinkInDifferentNotebook(self):
		page = self.notebook.get_page(Path('Test'))
		page.parse('wiki', '[[+Foo]]\n[[+Foo|my foo link]]\n[[+Foo#anchor]]\n[[#anchor]]')
		parsetree = page.get_parsetree()
		Clipboard.set_parsetree(self.notebook, page, parsetree)

		othernotebook = self.setUpNotebook(name="othernotebook", content=('Test',))
		newtree = Clipboard.get_parsetree(othernotebook, Path('OtherPage'))
		self.assertEqual(newtree.tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
			'<zim-tree><p>'
			'<link href="first_notebook?Test:Foo">first_notebook?Test:Foo</link>\n'
			'<link href="first_notebook?Test:Foo">my foo link</link>\n'
			'<link href="first_notebook?Test:Foo#anchor">first_notebook?Test:Foo#anchor</link>\n'
			'<link href="first_notebook?Test#anchor">first_notebook?Test#anchor</link>'
			'</p></zim-tree>'
		) # Link updated to point to same target from new location

	def testCopyPasteParseTreeWithFileLinkInSamePage(self):
		page = self.notebook.get_page(Path('Test'))
		page.parse('wiki', '[[./attachment.pdf]]\n[[./attachment.pdf|my attachment]]\n[[file://host/file]]')
		parsetree = page.get_parsetree()
		Clipboard.set_parsetree(self.notebook, page, parsetree)

		with tests.LoggingFilter('zim.notebook', 'Could not resolve filename'):
			newtree = Clipboard.get_parsetree(self.notebook, page)
		self.assertEqual(newtree.tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
			'<zim-tree><p>'
			'<link href="./attachment.pdf">./attachment.pdf</link>\n'
			'<link href="./attachment.pdf">my attachment</link>\n'
			'<link href="file://host/file">file://host/file</link>'
			'</p></zim-tree>'
		) # No need to update the link - file uri to external host untouched

	def testCopyPasteParseTreeWithFileLinkInDifferentPage(self):
		page = self.notebook.get_page(Path('Test'))
		page.parse('wiki', '[[./attachment.pdf]]\n[[./attachment.pdf|my attachment]]\n[[file://host/file]]')
		parsetree = page.get_parsetree()
		Clipboard.set_parsetree(self.notebook, page, parsetree)

		with tests.LoggingFilter('zim.notebook', 'Could not resolve filename'):
			newtree = Clipboard.get_parsetree(self.notebook, Path('OtherPage'))
		self.assertEqual(newtree.tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
			'<zim-tree><p>'
			'<link href="%s">%s</link>\n'
			'<link href="%s">my attachment</link>\n'
			'<link href="file://host/file">file://host/file</link>'
			'</p></zim-tree>' % (
				os_native_path('../Test/attachment.pdf'),
				os_native_path('../Test/attachment.pdf'),
				os_native_path('../Test/attachment.pdf')
			)
		) # Link updated to point to same target from new location - file uri to external host untouched

	def testCopyPasteParseTreeWithFileLinkInDifferentNotebook(self):
		# NOTE: no proper syntax for this type of link - just abs file link
		#       should be improved - e.g. path:./file style links like in docuwiki

		page = self.notebook.get_page(Path('Test'))
		page.parse('wiki', '[[./attachment.pdf]]\n[[./attachment.pdf|my attachment]]')
		parsetree = page.get_parsetree()
		Clipboard.set_parsetree(self.notebook, page, parsetree)

		file_uri = page.attachments_folder.file('attachment.pdf').uri
		othernotebook = self.setUpNotebook(name="othernotebook", content=('Test',))
		newtree = Clipboard.get_parsetree(othernotebook, Path('OtherPage'))
		self.assertEqual(newtree.tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
			'<zim-tree><p>'
			'<link href="%(file_uri)s">%(file_uri)s</link>\n'
			'<link href="%(file_uri)s">my attachment</link>'
			'</p></zim-tree>' % {'file_uri': file_uri}
		) # Link updated to point to same target from new location

	def testCopyPasteParseTreeWithImageInSamePage(self):
		page = self.notebook.get_page(Path('Test'))
		page.parse('wiki', '{{./attachment.png}}\n{{../OtherPage/otherimage.png}}\n{{./broken_image.png}}')
		parsetree = page.get_parsetree()
		Clipboard.set_parsetree(self.notebook, page, parsetree)

		newtree = Clipboard.get_parsetree(self.notebook, page)
		self.assertEqual(newtree.tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
			'<zim-tree><p>'
			'<img src="./attachment.png" />\n'
			'<img src="../OtherPage/otherimage.png" />\n'
			'<img src="./broken_image.png" />'
			'</p></zim-tree>'
		) # No need to update the images

	def testCopyPasteParseTreeWithImageInDifferentPage(self):
		self.notebook = self.setUpNotebook(name='first notebook', content=('Test',), mock=tests.MOCK_ALWAYS_REAL)

		page = self.notebook.get_page(Path('Test'))
		page.parse('wiki', '{{./attachment1.png}}\n{{attachment2.png}}\n{{../OtherPage/otherimage.png}}\n{{./../OtherPage/otherimage.png}}\n{{./broken_image.png}}')
		page.attachments_folder.file('attachment1.png').touch()
		page.attachments_folder.file('attachment2.png').touch()

		newpage = self.notebook.get_page(Path('OtherPage'))
		for name in ('attachment1.png', 'attachment2.png'):
			newfile = newpage.attachments_folder.file(name)
			self.assertFalse(newfile.exists())

		self.assertFalse(page.attachments_folder.file('broken_image.png').exists())

		parsetree = page.get_parsetree()
		Clipboard.set_parsetree(self.notebook, page, parsetree)

		with tests.LoggingFilter('zim.notebook.updater', 'File not found:'):
			newtree = Clipboard.get_parsetree(self.notebook, Path('OtherPage'))
		self.assertEqual(newtree.tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
			'<zim-tree><p>'
			'<img src="%s" />\n'
			'<img src="%s" />\n'
			'<img src="%s" />\n'
			'<img src="%s" />\n'
			'<img src="%s" />'
			'</p></zim-tree>' % (
				os_native_path('./attachment1.png'),
				os_native_path('./attachment2.png'),
				os_native_path('./otherimage.png'),
				os_native_path('./otherimage.png'),
				os_native_path('./broken_image.png'),
			)
		)
		# No update on two attachments, *but* file is copied
		# External images are not copied, but src is updates
		for name in ('attachment1.png', 'attachment2.png'):
			newfile = newpage.attachments_folder.file(name)
			self.assertTrue(newfile.exists())

	def testCopyPasteParseTreeWithImageInDifferentNotebook(self):
		self.notebook = self.setUpNotebook(name='first notebook', content=('Test',), mock=tests.MOCK_ALWAYS_REAL)

		page = self.notebook.get_page(Path('Test'))
		page.parse('wiki', '{{./attachment.png}}\n{{../OtherPage/otherimage.png}}')
		page.attachments_folder.file('attachment.png').touch()
		self.notebook.folder.file('OtherPage/otherimage.png').touch()

		parsetree = page.get_parsetree()
		Clipboard.set_parsetree(self.notebook, page, parsetree)

		othernotebook = self.setUpNotebook(name="othernotebook", content=('Test',), mock=tests.MOCK_ALWAYS_REAL)
		newpage = othernotebook.get_page(Path('OtherPage'))
		newfile_1 = newpage.attachments_folder.file('attachment.png')
		newfile_2 = newpage.attachments_folder.file('otherimage.png')
		self.assertFalse(newfile_1.exists())
		self.assertFalse(newfile_2.exists())

		newtree = Clipboard.get_parsetree(othernotebook, Path('OtherPage'))
		self.assertEqual(newtree.tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
			'<zim-tree><p>'
			'<img src="%s" />\n'
			'<img src="%s" />'
			'</p></zim-tree>' % (
				os_native_path('./attachment.png'),
				os_native_path('./otherimage.png')
			)
		) # For cross-notebook copy, copy update both images
		self.assertTrue(newfile_1.exists())
		self.assertTrue(newfile_2.exists())

	def testCopyPasteParseTreeWithEquationFileInSamePage(self):
		page = self.notebook.get_page(Path('Test'))
		page.parse('wiki', '{{./foo.png?type=equation}}')
		parsetree = page.get_parsetree()
		Clipboard.set_parsetree(self.notebook, page, parsetree)

		newtree = Clipboard.get_parsetree(self.notebook, page)
		self.assertEqual(newtree.tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
			'<zim-tree><p>'
			'<object src="./foo.png" type="image+equation" />'
			'</p></zim-tree>'
		) # No need to update the images

	def testCopyPasteParseTreeWithEquationFileInDifferentPage(self):
		self.notebook = self.setUpNotebook(name='first notebook', content=('Test',), mock=tests.MOCK_ALWAYS_REAL)

		page = self.notebook.get_page(Path('Test'))
		page.parse('wiki', '{{./foo.png?type=equation}}')
		page.attachments_folder.file('foo.png').touch()
		page.attachments_folder.file('foo.tex').touch()

		newpage = self.notebook.get_page(Path('OtherPage'))
		newpage.attachments_folder.file('foo.png').touch() # Let file exist already
		newpage.attachments_folder.file('foo-001.tex').touch() # Let file exist already
		newfile_1 = newpage.attachments_folder.file('foo-002.png')
		newfile_2 = newpage.attachments_folder.file('foo-002.tex')
		self.assertFalse(newfile_1.exists())
		self.assertFalse(newfile_2.exists())

		parsetree = page.get_parsetree()
		Clipboard.set_parsetree(self.notebook, page, parsetree)

		newtree = Clipboard.get_parsetree(self.notebook, Path('OtherPage'))
		self.assertEqual(newtree.tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
			'<zim-tree><p>'
			'<object src="%s" type="image+equation" />'
			'</p></zim-tree>' % os_native_path('./foo-002.png')
		) # Sources are copied and number is added due to existing files
		self.assertTrue(newfile_1.exists())
		self.assertTrue(newfile_2.exists())

	def testCopyPasteParseTreeWithEquationFileInDifferentNotebook(self):
		self.notebook = self.setUpNotebook(name='first notebook', content=('Test',), mock=tests.MOCK_ALWAYS_REAL)

		page = self.notebook.get_page(Path('Test'))
		page.parse('wiki', '{{./foo.png?type=equation}}')
		page.attachments_folder.file('foo.png').touch()
		page.attachments_folder.file('foo.tex').touch()

		othernotebook = self.setUpNotebook(name="othernotebook", content=('Test',), mock=tests.MOCK_ALWAYS_REAL)
		newpage = othernotebook.get_page(Path('OtherPage'))
		newfile_1 = newpage.attachments_folder.file('foo.png')
		newfile_2 = newpage.attachments_folder.file('foo.tex')
		self.assertFalse(newfile_1.exists())
		self.assertFalse(newfile_2.exists())

		parsetree = page.get_parsetree()
		Clipboard.set_parsetree(self.notebook, page, parsetree)

		newtree = Clipboard.get_parsetree(othernotebook, Path('OtherPage'))
		self.assertEqual(newtree.tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
			'<zim-tree><p>'
			'<object src="%s" type="image+equation" />'
			'</p></zim-tree>' % os_native_path('./foo.png')
		) # Sources are copied and number is added due to existing files
		self.assertTrue(newfile_1.exists())
		self.assertTrue(newfile_2.exists())

	def testCopyPasteParseTreeWithInterwikiLinkInDifferentPage(self):
		# Does not need update - check it is left alone
		page = self.notebook.get_page(Path('Test'))
		page.parse('wiki', '[[wp?Foo]]\n[[wp?Foo|wikipedia Foo]]')
		parsetree = page.get_parsetree()
		Clipboard.set_parsetree(self.notebook, page, parsetree)

		newtree = Clipboard.get_parsetree(self.notebook, Path('OtherPage'))
		self.assertEqual(newtree.tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
			'<zim-tree><p>'
			'<link href="wp?Foo">wp?Foo</link>\n'
			'<link href="wp?Foo">wikipedia Foo</link>'
			'</p></zim-tree>'
		) # Does not need update - check it is left alone

	def testCopyPasteParseTreeWithInterwikiLinkInDifferentNotebook(self):
		# Does not need update - check it is left alone

		page = self.notebook.get_page(Path('Test'))
		page.parse('wiki', '[[wp?Foo]]\n[[wp?Foo|wikipedia Foo]]')
		parsetree = page.get_parsetree()
		Clipboard.set_parsetree(self.notebook, page, parsetree)

		othernotebook = self.setUpNotebook(name="othernotebook", content=('Test',))
		newtree = Clipboard.get_parsetree(othernotebook, Path('OtherPage'))
		self.assertEqual(newtree.tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
			'<zim-tree><p>'
			'<link href="wp?Foo">wp?Foo</link>\n'
			'<link href="wp?Foo">wikipedia Foo</link>'
			'</p></zim-tree>'
		) # Does not need update - check it is left alone


class TestURIData(tests.TestCase):

	def runTest(self):
		someobject = tests.MockObject()
		someobject.uri = "file:///foo"

		file1 = LocalFile(os_native_path("/foo"))
		file2 = LocalFile("~/foo")
		assert file2.userpath.startswith('~')
		for (input, uris, text) in (
			((file1,), (file1.uri,), file1.path),
			((file2,), (file2.uri,), file2.userpath),
			(("file:///foo",), ("file:///foo",), "file:///foo"),
			((someobject,), ("file:///foo",), "file:///foo"),
			(("file:///foo", "file:///bar"), ("file:///foo", "file:///bar"), "file:///foo file:///bar"),
		):
			data = UriData(*input)
			self.assertEqual(data.get_data_as(URI_TARGET_ID), uris)
			self.assertEqual(data.get_data_as(TEXT_TARGET_ID), text)
