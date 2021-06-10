
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
		wanted = '''<?xml version='1.0' encoding='utf-8'?>\n<zim-tree partial="True">some **string**</zim-tree>'''
		Clipboard.set_text('some **string**')
		newtree = Clipboard.get_parsetree(self.notebook)
		self.assertEqual(newtree.tostring(), wanted)

	def testCopyTextPasteAsParseTreeWiki(self):
		wanted = '''<?xml version='1.0' encoding='utf-8'?>\n<zim-tree partial="True"><p>some <strong>string</strong></p></zim-tree>'''
		Clipboard.set_text('some **string**')
		newtree = Clipboard.get_parsetree(self.notebook, text_format='wiki')
		self.assertEqual(newtree.tostring(), wanted)

	def testCopyTextPasteAsParseTreeVerbatim(self):
		wanted = '''<?xml version='1.0' encoding='utf-8'?>\n<zim-tree partial="True"><pre>some **string**</pre></zim-tree>'''
		Clipboard.set_text('some **string**')
		newtree = Clipboard.get_parsetree(self.notebook, text_format='verbatim-pre')
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
			'<link href="+Foo#anchor">+Foo#anchor</link>\n'
			'</p></zim-tree>'
		) # No need to update the link

	def testCopyPasteParseTreeWithLinkInDifferentPage(self):
		page = self.notebook.get_page(Path('Test'))
		page.parse('wiki', '[[+Foo]]\n[[+Foo|Foo]]\n[[+Foo|my foo link]]\n[[+Foo#anchor]]')
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
			'</p></zim-tree>'
		) # Link updated to point to same target from new location

	def testCopyPasteParseTreeWithLinkInDifferentNotebook(self):
		page = self.notebook.get_page(Path('Test'))
		page.parse('wiki', '[[+Foo]]\n[[+Foo|my foo link]]\n[[+Foo#anchor]]')
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
			'</p></zim-tree>'
		) # Link updated to point to same target from new location

	def testCopyPasteParseTreeWithFileLinkInSamePage(self):
		page = self.notebook.get_page(Path('Test'))
		page.parse('wiki', '[[./attachment.pdf]]\n[[./attachment.pdf|my attachment]]')
		parsetree = page.get_parsetree()
		Clipboard.set_parsetree(self.notebook, page, parsetree)

		newtree = Clipboard.get_parsetree(self.notebook, page)
		self.assertEqual(newtree.tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
			'<zim-tree><p>'
			'<link href="./attachment.pdf">./attachment.pdf</link>\n'
			'<link href="./attachment.pdf">my attachment</link>\n'
			'</p></zim-tree>'
		) # No need to update the link

	def testCopyPasteParseTreeWithFileLinkInDifferentPage(self):
		page = self.notebook.get_page(Path('Test'))
		page.parse('wiki', '[[./attachment.pdf]]\n[[./attachment.pdf|my attachment]]')
		parsetree = page.get_parsetree()
		Clipboard.set_parsetree(self.notebook, page, parsetree)

		newtree = Clipboard.get_parsetree(self.notebook, Path('OtherPage'))
		self.assertEqual(newtree.tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
			'<zim-tree><p>'
			'<link href="../Test/attachment.pdf">../Test/attachment.pdf</link>\n'
			'<link href="../Test/attachment.pdf">my attachment</link>\n'
			'</p></zim-tree>'
		) # Link updated to point to same target from new location

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
			'<link href="%(file_uri)s">my attachment</link>\n'
			'</p></zim-tree>' % {'file_uri': file_uri}
		) # Link updated to point to same target from new location

	def testCopyPasteParseTreeWithImageInSamePage(self):
		page = self.notebook.get_page(Path('Test'))
		page.parse('wiki', '{{./attachment.png}}\n{{../OtherPage/otherimage.png}}')
		parsetree = page.get_parsetree()
		Clipboard.set_parsetree(self.notebook, page, parsetree)

		newtree = Clipboard.get_parsetree(self.notebook, page)
		self.assertEqual(newtree.tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
			'<zim-tree><p>'
			'<img src="./attachment.png" />\n'
			'<img src="../OtherPage/otherimage.png" />\n'
			'</p></zim-tree>'
		) # No need to update the images

	def testCopyPasteParseTreeWithImageInDifferentPage(self):
		self.notebook = self.setUpNotebook(name='first notebook', content=('Test',), mock=tests.MOCK_ALWAYS_REAL)

		page = self.notebook.get_page(Path('Test'))
		page.parse('wiki', '{{./attachment.png}}\n{{../OtherPage/otherimage.png}}')
		page.attachments_folder.file('attachment.png').touch()

		newpage = self.notebook.get_page(Path('OtherPage'))
		newfile = newpage.attachments_folder.file('attachment.png')
		self.assertFalse(newfile.exists())

		parsetree = page.get_parsetree()
		Clipboard.set_parsetree(self.notebook, page, parsetree)

		newtree = Clipboard.get_parsetree(self.notebook, Path('OtherPage'))
		self.assertEqual(newtree.tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
			'<zim-tree><p>'
			'<img src="./attachment.png" />\n'
			'<img src="./otherimage.png" />\n'
			'</p></zim-tree>'
		)
		# No update on first image, *but* file is copied
		# Second image is not copied, but src is updates
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
			'<img src="./attachment.png" />\n'
			'<img src="./otherimage.png" />\n'
			'</p></zim-tree>'
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
			'<object src="./foo.png" type="image+equation" />\n'
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
		newpage.attachments_folder.file('foo001.tex').touch() # Let file exist already
		newfile_1 = newpage.attachments_folder.file('foo002.png')
		newfile_2 = newpage.attachments_folder.file('foo002.tex')
		self.assertFalse(newfile_1.exists())
		self.assertFalse(newfile_2.exists())

		parsetree = page.get_parsetree()
		Clipboard.set_parsetree(self.notebook, page, parsetree)

		newtree = Clipboard.get_parsetree(self.notebook, Path('OtherPage'))
		self.assertEqual(newtree.tostring(),
			'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n'
			'<zim-tree><p>'
			'<object src="./foo002.png" type="image+equation" />\n'
			'</p></zim-tree>'
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
			'<object src="./foo.png" type="image+equation" />\n'
			'</p></zim-tree>'
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
			'<link href="wp?Foo">wikipedia Foo</link>\n'
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
			'<link href="wp?Foo">wikipedia Foo</link>\n'
			'</p></zim-tree>'
		) # Does not need update - check it is left alone
