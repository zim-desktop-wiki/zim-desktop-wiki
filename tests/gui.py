
from __future__ import with_statement

from tests import TestCase, get_test_notebook, create_tmp_dir, MockObject
from tests.gtk import TestDialogContext

from zim.errors import Error
from zim.notebook import get_notebook_list, Path, NotebookInfo
from zim.fs import File, Dir
from zim.config import config_file

import zim.gui

from zim.gui.clipboard import *


class TestClipboard(TestCase):

	def runTest(self):
		'''Test clipboard interaction'''
		clipboard = Clipboard()
		notebook = get_test_notebook()
		tmp_dir = create_tmp_dir('gui_Clipboard')
		notebook.get_store(Path(':')).dir = Dir(tmp_dir) # fake source dir

		# tree roundtrip
		for pagename in ('Test:wiki', 'roundtrip'):
			page = notebook.get_page(Path(pagename))
			parsetree = page.get_parsetree()

			clipboard.set_parsetree(notebook, page, parsetree)
			newtree = clipboard.request_parsetree(None, notebook, block=True)
			self.assertEqual(newtree.tostring(), parsetree.tostring())

		# tree -> ...
		import zim.formats
		text = 'some **bold** text'
		parsetree = zim.formats.get_format('plain').Parser().parse(text.decode('utf-8'))
		clipboard.set_parsetree(notebook, page, parsetree)

		wanted = 'some **bold** text\n'
		text = clipboard.wait_for_text()
		self.assertEqualDiff(text, wanted)

		wanted = '''\
<html>
<head>
<meta http-equiv="Content-Type" content="text/html;charset=utf-8">
<meta name="Description" content="Copy-Paste Buffer">
<meta name="Generator" content="Zim">
</head>
<body>
<p>
some <strong>bold</strong> text<br>
</p>

</body>
</html>
'''
		selection = clipboard.wait_for_contents('text/html')
		self.assertEqualDiff(selection.data, wanted)

		wanted = '''\
Version:1.0\r
StartHTML:000000185\r
EndHTML:000000527\r
StartFragment:000000450\r
EndFragment:000000495\r
StartSelection:000000450\r
EndSelection:000000495\r
SourceURL:zim://copy-pase-buffer\r
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN"><HTML><HEAD><meta http-equiv="Content-Type" content="text/html;charset=utf-8">
<meta name="Description" content="Copy-Paste Buffer">
<meta name="Generator" content="Zim"></HEAD><BODY><!--StartFragment--><p>
some <strong>bold</strong> text<br>
</p>
<!--EndFragment--></BODY></HTML>'''
		selection = clipboard.wait_for_contents('HTML Format')
		self.assertEqualDiff(selection.data, wanted)


		# pagelink -> ..
		page = notebook.get_page(Path('Test:wiki'))
		clipboard.set_pagelink(notebook, page)

		selection = clipboard.wait_for_contents(INTERNAL_PAGELIST_TARGET_NAME)
		self.assertEqual(selection.data, 'Test:wiki\r\n')

		selection = clipboard.wait_for_contents(PAGELIST_TARGET_NAME)
		self.assertEqual(selection.data, 'Unnamed Notebook?Test:wiki\r\n')

		wanted = '''\
<?xml version=\'1.0\' encoding=\'utf-8\'?>\n<zim-tree><link href="Test:wiki">Test:wiki</link></zim-tree>'''
		newtree = clipboard.request_parsetree(None, notebook, page, block=True)
		self.assertEqual(newtree.tostring(), wanted)

		text = clipboard.wait_for_text()
		self.assertEqual(text, 'Test:wiki')


		# text -> tree
		wanted = '''\
<?xml version='1.0' encoding='utf-8'?>\n<zim-tree>some string</zim-tree>'''
		clipboard.set_text('some string')
		newtree = clipboard.request_parsetree(None, notebook, block=True)
		self.assertEqual(newtree.tostring(), wanted)


		# file -> tree
		page = notebook.get_page(Path('Test:wiki'))
		targets = [('text/uri-list', 0, 0)]

		def my_get_data(clipboard, selectiondata, id, file):
			selectiondata.set_uris([file.uri])

		def my_clear_data(*a):
			pass

		file = File('/foo/bar/baz.txt')
		clipboard.set_with_data(targets, my_get_data, my_clear_data, file)
		tree = clipboard.request_parsetree(None, notebook, page, block=True)
		img = tree.find('link')
		rel_path = img.get('href')
		self.assertEqual(notebook.resolve_file(rel_path, page), file)

		file = File('./data/zim.png')
		clipboard.set_with_data(targets, my_get_data, my_clear_data, file)
		tree = clipboard.request_parsetree(None, notebook, page, block=True)
		img = tree.find('img')
		file_obj = img.get('_src_file')
		self.assertEqual(file_obj, file)
		rel_path = img.get('src')
		self.assertEqual(notebook.resolve_file(rel_path, page), file)


		# image -> tree
		page = notebook.get_page(Path('Test:wiki'))
		targets = [('image/png', 0, 0)]

		def my_get_data(clipboard, selectiondata, id, file):
			pixbuf = gtk.gdk.pixbuf_new_from_file(file.path)
			selectiondata.set_pixbuf(pixbuf)

		def my_clear_data(*a):
			pass

		file = File('./data/zim.png')
		clipboard.set_with_data(targets, my_get_data, my_clear_data, file)
		tree = clipboard.request_parsetree(None, notebook, page, block=True)
		img = tree.find('img')
		file_obj = img.get('_src_file')
		self.assertFalse(file_obj == file)
		self.assertTrue(file_obj.exists())
		self.assertTrue(file_obj.isimage())
		self.assertTrue(file_obj.path.endswith('.png'))
		rel_path = img.get('src')
		self.assertEqual(notebook.resolve_file(rel_path, page), file_obj)


class TestDialogs(TestCase):

	slowTest = True

	def setUp(self):
		self.ui = MockUI('Test:foo:bar')

	def testOpenPageDialog(self):
		'''Test OpenPageDialog dialog (Jump To...)'''
		for name, path in (
			(':foo', ':foo'),
			('foo', ':Test:foo'),
			('baz', ':Test:foo:baz'),
			('+baz', ':Test:foo:bar:baz'),
		):
			dialog = zim.gui.OpenPageDialog(self.ui)
			dialog.form.widgets['page'].set_text(name)
			dialog.assert_response_ok()
			self.assertEqual(self.ui.mock_calls[-1], ('open_page', Path(path)))

	def testNewPageDialog(self):
		'''Test NewPageDialog'''
		for name, path in (
			(':new', ':new'),
			('foo:new', ':Test:foo:new'),
			('new', ':Test:foo:new'),
			('+new', ':Test:foo:bar:new'),
		):
			dialog = zim.gui.NewPageDialog(self.ui)
			dialog.form.widgets['page'].set_text(name)
			dialog.assert_response_ok()
			self.assertEqual(self.ui.mock_calls[-1], ('save_page',))
			self.assertEqual(self.ui.mock_calls[-2], ('open_page', Path(path)))
			page = self.ui.notebook.get_page(Path(path))
			self.assertTrue(page.exists())
			page.modified = False # HACK so we can clean up
			self.ui.notebook.delete_page(page)

		for name, path in (
			(':new', ':Test:foo:bar:new'),
			('foo:new', ':Test:foo:bar:foo:new'),
			('new', ':Test:foo:bar:new'),
			('+new', ':Test:foo:bar:new'),
		):
			dialog = zim.gui.NewPageDialog(self.ui, subpage=True)
			dialog.form.widgets['page'].set_text(name)
			dialog.assert_response_ok()
			self.assertEqual(self.ui.mock_calls[-1], ('save_page',))
			self.assertEqual(self.ui.mock_calls[-2], ('open_page', Path(path)))
			page = self.ui.notebook.get_page(Path(path))
			self.assertTrue(page.exists())
			page.modified = False # HACK so we can clean up
			self.ui.notebook.delete_page(page)

		dialog = zim.gui.NewPageDialog(self.ui)
		dialog.form.widgets['page'].set_text(':Test:foo')
		self.assertRaises(Error, dialog.assert_response_ok)

	def testSaveCopyDialog(self):
		'''Test SaveCopyDialog'''
		tmp_dir = create_tmp_dir('gui_SaveCopyDialog')
		file = File((tmp_dir, 'save_copy.txt'))
		self.assertFalse(file.exists())
		dialog = zim.gui.SaveCopyDialog(self.ui)
		dialog.set_file(file)
		#~ dialog.assert_response_ok()
		#~ self.assertTrue(file.exists())

	def testImportPageDialog(self):
		'''Test ImportPageDialog'''
		tmp_dir = create_tmp_dir('gui_ImportPageDialog')
		file = File((tmp_dir, 'import_page.txt'))
		file.write('test 123\n')
		self.assertTrue(file.exists())
		self.ui = MockUI()
		dialog = zim.gui.ImportPageDialog(self.ui)
		dialog.set_file(file)
		#~ dialog.assert_response_ok()
		#~ self.assertEqual(self.ui.mock_calls[-1], ('open_page', Path(':import_page')))
		#~ self.assertTrue(self.ui.notebook.get_page(':import_page').exists())

	def testMovePageDialog(self):
		'''Test MovePageDialog'''
		# Can't test much here except for the call to do_move_page
		self.ui.mock_method('do_move_page', True)

		dialog = zim.gui.MovePageDialog(self.ui, path=Path('Test:foo:bar'))
		self.assertTrue(dialog.form['update'])
		self.assertTrue(dialog.form.widgets['update'].get_property('sensitive'))
		dialog.form['parent'] = Path('New')
		dialog.assert_response_ok()
		self.assertEqual(self.ui.mock_calls[-1],
			('do_move_page', Path('Test:foo:bar'), Path('New:bar'), True))

		dialog = zim.gui.MovePageDialog(self.ui, path=Path('New:bar'))
		self.assertFalse(dialog.form['update'])
		self.assertFalse(dialog.form.widgets['update'].get_property('sensitive'))
		dialog.form['parent'] = Path('foo')
		dialog.assert_response_ok()
		self.assertEqual(self.ui.mock_calls[-1],
			('do_move_page', Path('New:bar'), Path('foo:bar'), False))

	def testRenamePageDialog(self):
		'''Test RenamePageDialog'''
		# Can't test much here except for the call to do_rename_page
		self.ui.mock_method('do_rename_page', True)

		dialog = zim.gui.RenamePageDialog(self.ui, path=Path('Test:foo:bar'))
		self.assertTrue(dialog.form['update'])
		self.assertTrue(dialog.form.widgets['update'].get_property('sensitive'))
		self.assertTrue(dialog.form['head'])
		self.assertTrue(dialog.form.widgets['head'].get_property('sensitive'))
		dialog.form['name'] = 'New'
		dialog.assert_response_ok()
		self.assertEqual(self.ui.mock_calls[-1],
			('do_rename_page', Path('Test:foo:bar'), 'New', True, True))

		dialog = zim.gui.RenamePageDialog(self.ui, path=Path('New:bar'))
		self.assertFalse(dialog.form['update'])
		self.assertFalse(dialog.form.widgets['update'].get_property('sensitive'))
		self.assertFalse(dialog.form['head'])
		self.assertFalse(dialog.form.widgets['head'].get_property('sensitive'))
		dialog.form['name'] = 'New'
		dialog.assert_response_ok()
		self.assertEqual(self.ui.mock_calls[-1],
			('do_rename_page', Path('New:bar'), 'New', False, False))

	def testDeletePageDialog(self):
		'''Test DeletePageDialog'''
		# just check inputs are OK - skip output
		dialog = zim.gui.DeletePageDialog(self.ui, path=Path('Test:foo:bar'))
		self.assertTrue(dialog.links_checkbox.get_active())
		self.assertTrue(dialog.links_checkbox.get_property('sensitive'))

		dialog = zim.gui.DeletePageDialog(self.ui, path=Path('New'))
		self.assertFalse(dialog.links_checkbox.get_active())
		self.assertFalse(dialog.links_checkbox.get_property('sensitive'))

		dialog.assert_response_ok()

	def testAttachFileDialog(self):
		'''Test AttachFileDialog'''
		tmp_dir = create_tmp_dir('gui_AttachFileDialog')
		file = File((tmp_dir, 'file_to_be_attached'))
		file.write('Test 1 2 3\n')
		newfile = File((tmp_dir, 'attachments', 'Test', 'foo', 'file_to_be_attached'))
		self.assertTrue(file.exists())
		self.assertFalse(newfile.exists())

		store = self.ui.notebook.get_store(Path(':'))
		store.dir = Dir((tmp_dir, 'attachments')) # Fake dir based notebook
		dialog = zim.gui.AttachFileDialog(self.ui, path=Path('Test:foo'))
		dialog.set_file(file)
		#~ dialog.assert_response_ok()

		#~ self.assertTrue(file.exists()) # No move or delete happened
		#~ self.assertTrue(newfile.exists())
		#~ self.assertTrue(newfile.compare(file))
		#~ del store.dir

	def testSearchDialog(self):
		'''Test SearchDialog'''
		from zim.gui.searchdialog import SearchDialog
		self.ui.notebook = get_test_notebook()
		dialog = SearchDialog(self.ui)
		dialog.query_entry.set_text('Foo')
		dialog.query_entry.activate()
		model = dialog.results_treeview.get_model()
		self.assertTrue(len(model) > 3)

		self.ui.mainwindow = MockObject()
		self.ui.mainwindow.pageview = MockObject()
		col = dialog.results_treeview.get_column(0)
		dialog.results_treeview.row_activated((0,), col)

	def testNewApplicationDialog(self):
		'''Test NewApplicationDialog'''
		from zim.gui.applications import NewApplicationDialog
		dialog = NewApplicationDialog(self.ui, mimetype='text/plain')
		dialog.form['name'] = 'Foo'
		dialog.form['exec'] = 'foo %f'
		app = dialog.assert_response_ok()
		self.assertEqual(app.name, 'Foo')

		dialog = NewApplicationDialog(self.ui, type='web_browser')
		dialog.form['name'] = 'Foo'
		dialog.form['exec'] = 'foo %f'
		app = dialog.assert_response_ok()
		self.assertEqual(app.name, 'Foo')

	def testCustomToolDialog(self):
		'''Test CustomTool dialogs'''
		from zim.gui.customtools import CustomToolManagerDialog
		from zim.gui.customtools import EditCustomToolDialog

		## CustomToolManager dialog
		dialog = CustomToolManagerDialog(self.ui)
		properties = {
			'Name': 'Foo',
			'Comment': 'Test Foo',
			'X-Zim-ExecTool': 'foo %u',
			'X-Zim-ReadOnly': False,
			'X-Zim-ShowInToolBar': False,

		}
		dialog.manager.create(**properties)
		dialog.listview.refresh()
		dialog.destroy()

		## Edit custom tool dialog
		dialog = EditCustomToolDialog(self.ui)
		input = {
			'Name': 'Foo',
			'Comment': 'Test Foo',
			'X-Zim-ExecTool': 'foo %u',
			'X-Zim-ReadOnly': False,
			'X-Zim-ShowInToolBar': False,

		}
		dialog.form.update(input)
		output = dialog.assert_response_ok()
		input['Icon'] = None
		self.assertEqual(output, input)

	def testPropertiesDialog(self):
		'''Test PropertiesDialog'''
		from zim.gui.propertiesdialog import PropertiesDialog
		self.ui.readonly = True
		dialog = PropertiesDialog(self.ui)
		dialog.assert_response_ok()

		from zim.config import ConfigDictFile
		notebook = self.ui.notebook
		file = notebook.dir.file('notebook.zim')
		notebook.config = ConfigDictFile(file)
		self.ui.readonly = False

		config1 = {
			'name': 'Notebook Foo',
			'home': 'Home',
			'icon': './icon.png',
			'document_root': '/foo',
			'shared': False,
		}
		config2 = {
			'name': 'Notebook Bar',
			'home': 'HomeSweetHome',
			'icon': './picture.png',
			'document_root': '/bar',
			'shared': True,
		}
		notebook.save_properties(**config1)
		self.assertEqual(notebook.config['Notebook'], config1)

		dialog = PropertiesDialog(self.ui)
		dialog.assert_response_ok()

		self.assertEqual(notebook.config['Notebook'], config1)
		self.assertEqual(notebook.name, config1['name'])
		self.assertEqual(notebook.get_home_page(), Path(config1['home']))
		self.assertEqual(notebook.icon, notebook.dir.file(config1['icon']).path)
		self.assertEqual(notebook.document_root, Dir(config1['document_root']))

		dialog = PropertiesDialog(self.ui)
		dialog.form.update(config2)
		dialog.assert_response_ok()

		self.assertEqual(notebook.config['Notebook'], config2)
		self.assertEqual(notebook.name, config2['name'])
		self.assertEqual(notebook.get_home_page(), Path(config2['home']))
		self.assertEqual(notebook.icon, notebook.dir.file(config2['icon']).path)
		self.assertEqual(notebook.document_root, Dir(config2['document_root']))


	def testPreferencesDialog(self):
		'''Test PreferencesDialog'''
		from zim.gui.preferencesdialog import PreferencesDialog, PluginConfigureDialog
		import zim.gui.pageview

		gui = zim.gui.GtkInterface()
		gui.register_preferences('GtkInterface', zim.gui.ui_preferences)
		gui.register_preferences('PageView', zim.gui.pageview.ui_preferences)
		self.ui.preferences_register = gui.preferences_register
		self.ui.preferences = gui.preferences
		self.ui.plugins = gui.plugins

		## Test get/set simple value
		self.assertEquals(self.ui.preferences['GtkInterface']['toggle_on_ctrlspace'], False)
		dialog = PreferencesDialog(self.ui)
		self.assertEquals(dialog.forms['Interface']['toggle_on_ctrlspace'], False)
		dialog.assert_response_ok()
		self.assertEquals(self.ui.preferences['GtkInterface']['toggle_on_ctrlspace'], False)

		dialog = PreferencesDialog(self.ui)
		dialog.forms['Interface']['toggle_on_ctrlspace'] = True
		dialog.assert_response_ok()
		self.assertEquals(self.ui.preferences['GtkInterface']['toggle_on_ctrlspace'], True)

		## Test font button
		zim.gui.pageview.PageView.style['TextView']['font'] = 'Sans 12'
		dialog = PreferencesDialog(self.ui)
		self.assertEquals(dialog.forms['Interface']['use_custom_font'], True)
		dialog.assert_response_ok()
		self.assertEqual(zim.gui.pageview.PageView.style['TextView']['font'], 'Sans 12')
		self.assertFalse(any(['use_custom_font' in d for d in self.ui.preferences.values()]))

		zim.gui.pageview.PageView.style['TextView']['font'] = 'Sans 12'
		dialog = PreferencesDialog(self.ui)
		self.assertEquals(dialog.forms['Interface']['use_custom_font'], True)
		dialog.forms['Interface']['use_custom_font'] = False
		dialog.assert_response_ok()
		self.assertEqual(zim.gui.pageview.PageView.style['TextView']['font'], None)
		self.assertFalse(any(['use_custom_font' in d for d in self.ui.preferences.values()]))

		## Plugin Config dialog
		from zim.plugins import get_plugin
		klass = get_plugin('calendar')
		pref_dialog = PreferencesDialog(self.ui)
		dialog = PluginConfigureDialog(pref_dialog, klass)
		dialog.assert_response_ok()


	# Test for ExportDialog can be found in test/export.py
	# Test for NotebookDialog is in separate class below


class TestGtkInterface(TestCase):

	slowTest = True

	def runTest(self):
		ui = zim.gui.GtkInterface()

		# test populating menus
		menu = gtk.Menu()
		ui.populate_popup('page_popup', menu)
		items = menu.get_children()
		self.assertTrue(len(items) > 3)


class TestNotebookDialog(TestCase):

	def setUp(self):
		list = config_file('notebooks.list')
		file = list.file
		if file.exists():
			file.remove()

	def runTest(self):
		from zim.gui.notebookdialog import prompt_notebook, \
			AddNotebookDialog, NotebookDialog

		tmpdir = create_tmp_dir('gui_TestNotebookDialog')
		dir1 = Dir(tmpdir + '/mynotebook1')
		dir2 = Dir(tmpdir + '/mynotebook2')

		# First time we get directly the AddNotebookDialog
		def doAddNotebook(dialog):
			self.assertTrue(isinstance(dialog, AddNotebookDialog))
			dialog.form['name'] = 'Foo'
			dialog.form['folder'] = dir1.path
			dialog.assert_response_ok()

		with TestDialogContext(doAddNotebook):
			self.assertEqual(prompt_notebook(), dir1.uri)

		# Second time we get the list
		def testNotebookDialog(dialog):
			self.assertTrue(isinstance(dialog, NotebookDialog))
			selection = dialog.treeview.get_selection()
			selection.select_path((0,)) # select first and only notebook
			dialog.assert_response_ok()

		with TestDialogContext(testNotebookDialog):
			self.assertEqual(prompt_notebook(), dir1.uri)

		# Third time we add a notebook and set the default
		def doAddNotebook(dialog):
			self.assertTrue(isinstance(dialog, AddNotebookDialog))
			dialog.form['name'] = 'Bar'
			dialog.form['folder'] = dir2.path
			dialog.assert_response_ok()

		def testAddNotebook(dialog):
			self.assertTrue(isinstance(dialog, NotebookDialog))

			with TestDialogContext(doAddNotebook):
				dialog.do_add_notebook()

			dialog.combobox.set_active(0)

			selection = dialog.treeview.get_selection()
			selection.select_path((1,)) # select newly added notebook
			dialog.assert_response_ok()

		with TestDialogContext(testAddNotebook):
			self.assertEqual(prompt_notebook(), dir2.uri)

		# Check the notebook exists and the notebook list looks like it should
		for dir in (dir1, dir2):
			self.assertTrue(dir.exists())
			self.assertTrue(dir.file('notebook.zim').exists())

		list = get_notebook_list()
		self.assertTrue(len(list) == 2)
		self.assertEqual(list[0], NotebookInfo(dir1.uri, name='Foo'))
		self.assertEqual(list[1], NotebookInfo(dir2.uri, name='Bar'))
		self.assertEqual(list.default, NotebookInfo(dir1.uri, name='Foo'))

		# Now unset the default and again check the notebook list
		def unsetDefault(dialog):
			self.assertTrue(isinstance(dialog, NotebookDialog))
			dialog.combobox.set_active(-1)
			selection = dialog.treeview.get_selection()
			selection.select_path((1,)) # select newly added notebook
			dialog.assert_response_ok()

		with TestDialogContext(unsetDefault):
			self.assertEqual(prompt_notebook(), dir2.uri)

		list = get_notebook_list()
		self.assertTrue(len(list) == 2)
		self.assertTrue(list.default is None)


class MockUI(MockObject):

	tmp_dir = create_tmp_dir('gui_MockUI')

	def __init__(self, page=None):
		MockObject.__init__(self)

		if page and not isinstance(page, Path):
			self.page = Path(page)
		else:
			self.page = page

		self.mainwindow = None
		self.notebook = get_test_notebook()
		self.notebook.dir = Dir(self.tmp_dir) # fake source dir
		self.notebook.get_store(Path(':')).dir = self.notebook.dir

