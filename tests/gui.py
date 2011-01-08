
from tests import TestCase, get_test_notebook, create_tmp_dir, MockObject

from zim.errors import Error
from zim.notebook import Path
from zim.fs import File, Dir

import zim.gui



class TestDialogs(TestCase):

	slowTest = True

	def runTest(self):
		'''Test input/output of various dialogs'''
		tmp_dir = create_tmp_dir('gui_testdialogs')
		ui = MockUI('Test:foo:bar')

		## Jump To Page dialog
		for name, path in (
			(':foo', ':foo'),
			('foo', ':Test:foo'),
			('baz', ':Test:foo:baz'),
			('+baz', ':Test:foo:bar:baz'),
		):
			dialog = zim.gui.OpenPageDialog(ui)
			dialog.form.widgets['page'].set_text(name)
			dialog.assert_response_ok()
			self.assertEqual(ui.mock_calls[-1], ('open_page', Path(path)))

		## New Page dialog
		for name, path in (
			(':new', ':new'),
			('foo:new', ':Test:foo:new'),
			('new', ':Test:foo:new'),
			('+new', ':Test:foo:bar:new'),
		):
			dialog = zim.gui.NewPageDialog(ui)
			dialog.form.widgets['page'].set_text(name)
			dialog.assert_response_ok()
			self.assertEqual(ui.mock_calls[-1], ('save_page',))
			self.assertEqual(ui.mock_calls[-2], ('open_page', Path(path)))
			page = ui.notebook.get_page(Path(path))
			self.assertTrue(page.exists())
			page.modified = False # HACK so we can clean up
			ui.notebook.delete_page(page)

		for name, path in (
			(':new', ':Test:foo:bar:new'),
			('foo:new', ':Test:foo:bar:foo:new'),
			('new', ':Test:foo:bar:new'),
			('+new', ':Test:foo:bar:new'),
		):
			dialog = zim.gui.NewPageDialog(ui, subpage=True)
			dialog.form.widgets['page'].set_text(name)
			dialog.assert_response_ok()
			self.assertEqual(ui.mock_calls[-1], ('save_page',))
			self.assertEqual(ui.mock_calls[-2], ('open_page', Path(path)))
			page = ui.notebook.get_page(Path(path))
			self.assertTrue(page.exists())
			page.modified = False # HACK so we can clean up
			ui.notebook.delete_page(page)

		dialog = zim.gui.NewPageDialog(ui)
		dialog.form.widgets['page'].set_text(':Test:foo')
		self.assertRaises(Error, dialog.assert_response_ok)

		## Save Copy dialog
		file = File((tmp_dir, 'save_copy.txt'))
		self.assertFalse(file.exists())
		dialog = zim.gui.SaveCopyDialog(ui)
		dialog.set_file(file)
		#~ dialog.assert_response_ok()
		#~ self.assertTrue(file.exists())

		## Import Page dialog
		file = File((tmp_dir, 'import_page.txt'))
		file.write('test 123\n')
		self.assertTrue(file.exists())
		ui = MockUI()
		dialog = zim.gui.ImportPageDialog(ui)
		dialog.set_file(file)
		#~ dialog.assert_response_ok()
		#~ self.assertEqual(ui.mock_calls[-1], ('open_page', Path(':import_page')))
		#~ self.assertTrue(ui.notebook.get_page(':import_page').exists())

		## Move Page dialog
		# Can't test much here except for the call to do_move_page
		ui.mock_method('do_move_page', True)

		dialog = zim.gui.MovePageDialog(ui, path=Path('Test:foo:bar'))
		self.assertTrue(dialog.form['update'])
		self.assertTrue(dialog.form.widgets['update'].get_sensitive())
		dialog.form['parent'] = Path('New')
		dialog.assert_response_ok()
		self.assertEqual(ui.mock_calls[-1],
			('do_move_page', Path('Test:foo:bar'), Path('New:bar'), True))

		dialog = zim.gui.MovePageDialog(ui, path=Path('New:bar'))
		self.assertFalse(dialog.form['update'])
		self.assertFalse(dialog.form.widgets['update'].get_sensitive())
		dialog.form['parent'] = Path('foo')
		dialog.assert_response_ok()
		self.assertEqual(ui.mock_calls[-1],
			('do_move_page', Path('New:bar'), Path('foo:bar'), False))

		## Rename Page dialog
		# Can't test much here except for the call to do_rename_page
		ui.mock_method('do_rename_page', True)

		dialog = zim.gui.RenamePageDialog(ui, path=Path('Test:foo:bar'))
		self.assertTrue(dialog.form['update'])
		self.assertTrue(dialog.form.widgets['update'].get_sensitive())
		self.assertTrue(dialog.form['head'])
		self.assertTrue(dialog.form.widgets['head'].get_sensitive())
		dialog.form['name'] = 'New'
		dialog.assert_response_ok()
		self.assertEqual(ui.mock_calls[-1],
			('do_rename_page', Path('Test:foo:bar'), 'New', True, True))

		dialog = zim.gui.RenamePageDialog(ui, path=Path('New:bar'))
		self.assertFalse(dialog.form['update'])
		self.assertFalse(dialog.form.widgets['update'].get_sensitive())
		self.assertFalse(dialog.form['head'])
		self.assertFalse(dialog.form.widgets['head'].get_sensitive())
		dialog.form['name'] = 'New'
		dialog.assert_response_ok()
		self.assertEqual(ui.mock_calls[-1],
			('do_rename_page', Path('New:bar'), 'New', False, False))

		## Delete Page dialog
		# just check inputs are OK - skip output
		dialog = zim.gui.DeletePageDialog(ui, path=Path('Test:foo:bar'))
		self.assertTrue(dialog.links_checkbox.get_active())
		self.assertTrue(dialog.links_checkbox.get_sensitive())

		dialog = zim.gui.DeletePageDialog(ui, path=Path('New'))
		self.assertFalse(dialog.links_checkbox.get_active())
		self.assertFalse(dialog.links_checkbox.get_sensitive())

		dialog.destroy()

		## Attach File dialog
		file = File((tmp_dir, 'file_to_be_attached'))
		file.write('Test 1 2 3\n')
		newfile = File((tmp_dir, 'attachments', 'Test', 'foo', 'file_to_be_attached'))
		self.assertTrue(file.exists())
		self.assertFalse(newfile.exists())

		store = ui.notebook.get_store(Path(':'))
		store.dir = Dir((tmp_dir, 'attachments')) # Fake dir based notebook
		dialog = zim.gui.AttachFileDialog(ui, path=Path('Test:foo'))
		dialog.set_file(file)
		#~ dialog.assert_response_ok()

		#~ self.assertTrue(file.exists()) # No move or delete happened
		#~ self.assertTrue(newfile.exists())
		#~ self.assertTrue(newfile.compare(file))
		del store.dir

		## Search dialog
		from zim.gui.searchdialog import SearchDialog
		ui = MockUI()
		ui.notebook = get_test_notebook()
		dialog = SearchDialog(ui)
		dialog.query_entry.set_text('Foo')
		dialog.query_entry.activate()
		model = dialog.results_treeview.get_model()
		self.assertTrue(len(model) > 3)

		ui.mainwindow = MockObject()
		ui.mainwindow.pageview = MockObject()
		col = dialog.results_treeview.get_column(0)
		dialog.results_treeview.row_activated((0,), col)

		## New Application dialog
		from zim.gui.applications import NewApplicationDialog
		ui = MockUI()
		dialog = NewApplicationDialog(ui, mimetype='text/plain')
		dialog.form['name'] = 'Foo'
		dialog.form['exec'] = 'foo %f'
		app = dialog.assert_response_ok()
		self.assertEqual(app.name, 'Foo')

		dialog = NewApplicationDialog(ui, type='web_browser')
		dialog.form['name'] = 'Foo'
		dialog.form['exec'] = 'foo %f'
		app = dialog.assert_response_ok()
		self.assertEqual(app.name, 'Foo')

		## Custom tool dialog
		from zim.gui.customtools import CustomToolManagerDialog
		dialog = CustomToolManagerDialog(ui)
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
		from zim.gui.customtools import EditCustomToolDialog
		dialog = EditCustomToolDialog(ui)
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

		## Properties dialog
		from zim.gui.propertiesdialog import PropertiesDialog
		ui = MockUI()
		dialog = PropertiesDialog(ui)
		dialog.assert_response_ok()


class MockUI(MockObject):

	def __init__(self, page=None):
		MockObject.__init__(self)

		if page and not isinstance(page, Path):
			self.page = Path(page)
		else:
			self.page = page

		self.mainwindow = None
		self.notebook = get_test_notebook()
