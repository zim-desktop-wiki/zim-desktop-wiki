# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement

import tests

import os
import gtk

from zim.errors import Error
from zim.notebook import get_notebook_list, Path, Page, NotebookInfo
from zim.formats import ParseTree
from zim.fs import File, Dir
from zim.config import config_file
from zim.gui.clipboard import Clipboard

import zim.gui


def setupGtkInterface(test, klass=None):
	'''Setup a new GtkInterface object for testing.
	Will have test notebook, and default preferences.
	@param test: the test that wants to use this ui object
	@param klass: the klass to use, defaults to L{GtkInterface}, but
	could be partially mocked subclass
	'''
	if klass is None:
		klass = zim.gui.GtkInterface

	# start filtering
	filter = FilterNoSuchImageWarning()
	filter.wrap_test(test)

	# flush preferences
	preferences = config_file('preferences.conf')
	preferences.file.remove()

	# create interface object with new notebook
	dirpath = test.get_tmp_name()
	notebook = tests.new_notebook(fakedir=dirpath)
	path = Path('Test:foo:bar')
	ui = klass(notebook=notebook, page=path)

	# finalize plugins
	for plugin in ui.plugins:
		plugin.finalize_ui(ui)

	ui.mainwindow.init_uistate()

	return ui


@tests.slowTest
class TestDialogs(tests.TestCase):

	def setUp(self):
		path = self.create_tmp_dir()
		self.ui = MockUI('Test:foo:bar', fakedir=path)

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
		self.ui.mainwindow = tests.MockObject()
		self.ui.mainwindow.pageview = tests.MockObject()

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
		tmp_dir = self.create_tmp_dir('testSaveCopyDialog')
		file = File((tmp_dir, 'save_copy.txt'))
		self.assertFalse(file.exists())
		dialog = zim.gui.SaveCopyDialog(self.ui)
		dialog.set_file(file)
		#~ dialog.assert_response_ok()
		#~ self.assertTrue(file.exists())

	def testImportPageDialog(self):
		'''Test ImportPageDialog'''
		tmp_dir = self.create_tmp_dir('testImportPageDialog')
		file = File((tmp_dir, 'import_page.txt'))
		file.write('test 123\n')
		self.assertTrue(file.exists())
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
		self.assertFalse(dialog.form['head']) # There is no heading
		self.assertTrue(dialog.form.widgets['head'].get_property('sensitive'))
		dialog.form['name'] = 'New'
		dialog.assert_response_ok()
		self.assertEqual(self.ui.mock_calls[-1],
			('do_rename_page', Path('Test:foo:bar'), 'New', False, True))

		dialog = zim.gui.RenamePageDialog(self.ui, path=Path('New:bar'))
		self.assertFalse(dialog.form['update'])
		self.assertFalse(dialog.form.widgets['update'].get_property('sensitive'))
		self.assertFalse(dialog.form['head'])
		self.assertFalse(dialog.form.widgets['head'].get_property('sensitive'))
		dialog.form['name'] = 'New'
		dialog.assert_response_ok()
		self.assertEqual(self.ui.mock_calls[-1],
			('do_rename_page', Path('New:bar'), 'New', False, False))

	def testRenamePageDialogWithHeadingChanges(self):
		'''Test RenamePageDialog's heading auto-change option depending on
		whether we have a changed heading or not.
		'''
		tree = ParseTree().fromstring('<zim-tree></zim-tree>')
		tree.set_heading("bar")
		self.ui.page = Page(Path("Test:foo:bar"), parsetree=tree)
		self.ui.notebook.get_page = lambda path: self.ui.page
		dialog = zim.gui.RenamePageDialog(self.ui, path=Path("Test:foo:bar"))
		self.assertTrue(dialog.form['head'])
		tree.set_heading("different")
		dialog = zim.gui.RenamePageDialog(self.ui, path=Path("Test:foo:bar"))
		self.assertFalse(dialog.form['head'])
	
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
		tmp_dir = self.create_tmp_dir('testAttachFileDialog')
		file = File((tmp_dir, 'file_to_be_attached'))
		file.write('Test 1 2 3\n')
		newfile = File((tmp_dir, 'attachments', 'Test', 'foo', 'file_to_be_attached'))
		self.assertTrue(file.exists())
		self.assertFalse(newfile.exists())

		dialog = zim.gui.AttachFileDialog(self.ui, path=Path('Test:foo'))
		dialog.set_file(file)
		#~ dialog.assert_response_ok()

		#~ self.assertTrue(file.exists()) # No move or delete happened
		#~ self.assertTrue(newfile.exists())
		#~ self.assertTrue(newfile.compare(file))

	def testSearchDialog(self):
		'''Test SearchDialog'''
		from zim.gui.searchdialog import SearchDialog
		self.ui.notebook = tests.new_notebook()
		dialog = SearchDialog(self.ui)
		dialog.query_entry.set_text('Foo')
		dialog.query_entry.activate()
		model = dialog.results_treeview.get_model()
		self.assertTrue(len(model) > 3)

		self.ui.mainwindow = tests.MockObject()
		self.ui.mainwindow.pageview = tests.MockObject()
		col = dialog.results_treeview.get_column(0)
		dialog.results_treeview.row_activated((0,), col)

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
			'interwiki': '',
			'home': 'Home',
			'icon': './icon.png',
			'document_root': File('/foo').path, # win32 save test
			'shared': False,
			'profile': '',
		}
		config2 = {
			'name': 'Notebook Bar',
			'interwiki': 'FooBar',
			'home': 'HomeSweetHome',
			'icon': './picture.png',
			'document_root': File('/bar').path, # win32 save test
			'shared': True,
			'profile': 'foo',
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
		with FilterFailedToLoadPlugin():
			# may miss dependencies for e.g. versioncontrol
			gui.load_plugins()
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

	def testTemplateEditorDialog(self):
		from zim.gui.templateeditordialog import TemplateEditorDialog
		dialog = TemplateEditorDialog(self.ui)
		# TODO what to test here ??
		dialog.assert_response_ok()

	# Test for ExportDialog can be found in test/export.py
	# Test for NotebookDialog is in separate class below



class FilterNoSuchImageWarning(tests.LoggingFilter):

	logger = 'zim.gui.pageview'
	message = 'No such image:'


class FilterFailedToLoadPlugin(tests.LoggingFilter):

	logger = 'zim'
	message = 'Failed to load plugin'


@tests.slowTest
class TestGtkInterface(tests.TestCase):

	def setUp(self):
		with FilterFailedToLoadPlugin():
			# may miss dependencies for e.g. versioncontrol
			self.ui = setupGtkInterface(self)

	def tearDown(self):
		self.ui.close()

	def testInitialization(self):
		'''Test Gtk interface initialization'''

		# start without notebook should not complain
		ui = zim.gui.GtkInterface()

		# now take ui with notebook
		ui = self.ui

		# test read only (starts readonly because notebook has no dir or file)
		self.assertTrue(ui.readonly)
		ui.set_readonly(False)
		self.assertFalse(ui.readonly)
		ui.set_readonly(True)
		self.assertTrue(ui.readonly)

		# TODO more tests for readonly pages etc.

		# test populating menus
		menu = gtk.Menu()
		ui.populate_popup('page_popup', menu)
		items = menu.get_children()
		self.assertGreater(len(items), 3)

		# open notebook (so the default plugins are loaded)
		nb = ui.notebook
		ui.notebook = None
		ui.open_notebook(nb)

		# remove plugins
		self.assertGreaterEqual(len(ui.plugins), 3) # default plugins without dependencies
		plugins = [p.plugin_key for p in ui.plugins]
		for name in plugins:
			ui.unload_plugin(name)
		self.assertEqual(len(ui.plugins), 0)

		# and add them again
		for name in plugins:
			ui.load_plugin(name)
		self.assertGreaterEqual(len(ui.plugins), 3) # default plugins without dependencies

		# check registering an URL handler
		func = tests.Counter(True)
		ui.register_url_handler('foo', func)
		ui.open_url('foo://bar')
		self.assertTrue(func.count == 1)
		ui.unregister_url_handler(func)

	def testMainWindow(self):
		'''Test main window'''
		path = Path('Test:foo:bar')
		window = self.ui.mainwindow

		self.assertTrue(window.uistate['show_menubar'])
		window.toggle_menubar()
		self.assertFalse(window.uistate['show_menubar'])
		window.toggle_menubar()
		self.assertTrue(window.uistate['show_menubar'])

		self.assertTrue(window.uistate['show_toolbar'])
		window.toggle_toolbar()
		self.assertFalse(window.uistate['show_toolbar'])
		window.toggle_toolbar()
		self.assertTrue(window.uistate['show_toolbar'])

		self.assertTrue(window.uistate['show_statusbar'])
		window.toggle_statusbar()
		self.assertFalse(window.uistate['show_statusbar'])
		window.toggle_statusbar()
		self.assertTrue(window.uistate['show_statusbar'])

		self.assertTrue(window.uistate['left_pane'][0])
		window.toggle_panes()
		self.assertFalse(window.uistate['left_pane'][0])
		window.toggle_panes()
		self.assertTrue(window.uistate['left_pane'][0])

		# note: focus starts at sidepane due to toggle_panes above
		self.assertEqual(window.get_focus(), window.pageindex.treeview)
		self.assertEqual(window.get_selected_path(), path)
		window.toggle_sidepane_focus()
		self.assertEqual(window.get_focus(), window.pageview.view)
		self.assertEqual(window.get_selected_path(), path)
		window.toggle_sidepane_focus()
		self.assertEqual(window.get_focus(), window.pageindex.treeview)
		# TODO also check this with "show_sidepane" off

		self.assertEqual(window.uistate['pathbar_type'], zim.gui.PATHBAR_RECENT)
		for style in (
			zim.gui.PATHBAR_NONE,
			zim.gui.PATHBAR_HISTORY,
			zim.gui.PATHBAR_PATH,
			zim.gui.PATHBAR_RECENT,
		):
			window.set_pathbar(style)
			self.assertEqual(window.uistate['pathbar_type'], style)
			# TODO specific test for pathbar to exercize history, add / move / remove pages etc.

		# note: no default style here - system default unknown
		for style in (
			zim.gui.TOOLBAR_ICONS_AND_TEXT,
			zim.gui.TOOLBAR_ICONS_ONLY,
			zim.gui.TOOLBAR_TEXT_ONLY,
		):
			window.set_toolbar_style(style)
			self.assertEqual(window.uistate['toolbar_style'], style)

		# note: no default style here - system default unknown
		for size in (
			zim.gui.TOOLBAR_ICONS_LARGE,
			zim.gui.TOOLBAR_ICONS_SMALL,
			zim.gui.TOOLBAR_ICONS_TINY,
		):
			window.set_toolbar_size(size)
			self.assertEqual(window.uistate['toolbar_size'], size)

		# FIXME: test fails because "readonly" not active because notebook was already readonly, so action never activatable
		#~ self.assertTrue(ui.readonly)
		#~ self.assertTrue(window.uistate['readonly'])
		#~ window.toggle_readonly()
		#~ self.assertFalse(ui.readonly)
		#~ self.assertFalse(window.uistate['readonly'])
		#~ window.toggle_readonly()
		#~ self.assertTrue(ui.readonly)
		#~ self.assertTrue(window.uistate['readonly'])

	def testNavigation(self):
		'''Test navigating the notebook with gtk interface'''

		# build up some history
		history = (
			Path('Test:foo:bar'),
			Path('Test:'),
			Path('Test:foo:'),
			Path('Test:foo:bar'),
		)
		for path in history:
			self.ui.open_page(path)
			self.assertEqual(self.ui.page, path)

		# check forward & backward
		for path in reversed(history[:-1]):
			self.assertTrue(self.ui.open_page_back())
			self.assertEqual(self.ui.page, path)
		self.assertFalse(self.ui.open_page_back())

		for path in history[1:]:
			self.assertTrue(self.ui.open_page_forward())
			self.assertEqual(self.ui.page, path)
		self.assertFalse(self.ui.open_page_forward())

		# check upward and downward
		for path in (Path('Test:foo:'), Path('Test:')):
			self.assertTrue(self.ui.open_page_parent())
			self.assertEqual(self.ui.page, path)
		self.assertFalse(self.ui.open_page_parent())

		for path in (Path('Test:foo:'), Path('Test:foo:bar')):
			self.assertTrue(self.ui.open_page_child())
			self.assertEqual(self.ui.page, path)
		self.assertFalse(self.ui.open_page_child())

		# previous and next
		self.assertTrue(self.ui.open_page_previous())
		self.assertTrue(self.ui.open_page_next())
		self.assertEqual(self.ui.page, Path('Test:foo:bar'))

	def testSave(self):
		'''Test saving a page from the interface'''
		self.ui.set_readonly(False)
		self.ui.open_page(Path('Non-exsiting:page'))
		self.assertFalse(self.ui.page.exists())
		self.assertTrue(self.ui.page.get_parsetree() is None)
		self.assertTrue(self.ui.mainwindow.pageview._showing_template) # check HACK
		self.ui.save_page()
		self.assertFalse(self.ui.page.get_parsetree() is None)

	def testPageMove(self):
		oldpath, newpath = Path('Movers:Stator:Mover'), Path('Movers:Mover')

		# Open page and process message queue to sync tree view
		indexpath = self.ui.notebook.index.lookup_path(oldpath)
		self.ui.open_page(indexpath)
		while gtk.events_pending():
			gtk.main_iteration(False)

		# Test actual moving
		page = self.ui.notebook.get_page(oldpath)
		text = page.dump('wiki')
		self.ui.notebook.index.ensure_update()
		self.ui.notebook.move_page(oldpath, newpath)
		self.ui.notebook.index.ensure_update()

		# newpath should exist and look like the old one
		page = self.ui.notebook.get_page(newpath)
		self.assertEqual(page.dump('wiki'), text)

		# oldpath should be deleted
		page = self.ui.notebook.get_page(oldpath)
		self.assertFalse(page.haschildren)
		self.assertFalse(page.hascontent)

	# TODO notebook manipulation (new (sub)page, rename, delete ..)
	# merge with tests for dialogs (?)

	def testClipboard(self):
		self.ui.copy_location()
		self.assertEqual(Clipboard.get_text(), 'Test:foo:bar')


@tests.slowTest
class TestClickLink(tests.TestCase):
	'''Test to check pageview and GtkInterface play together nicely when
	a link is clicked
	'''

	def setUp(self):
		class MyMock(zim.gui.GtkInterface, tests.MockObjectBase):

			def __init__(self, *arg, **kwarg):
				zim.gui.GtkInterface.__init__(self, *arg, **kwarg)
				tests.MockObjectBase.__init__(self)
				for method in (
					'open_notebook',
					'open_page',
					'open_file',
					'_open_with_emailclient',
					'_open_with_webbrowser',
					'_open_with_filebrowser',
					'_open_with',
				):
					self.mock_method(method, None)

		with FilterFailedToLoadPlugin():
			# may miss dependencies for e.g. versioncontrol
			self.ui = setupGtkInterface(self, klass=MyMock)

	def tearDown(self):
		self.ui.close()

	def runTest(self):
		self.assertRaises(AssertionError, self.ui.open_url, 'foo@bar.com')
			# this is not a URI, "mailto:foo@bar.com" is

		# Note: same list of test uris is testing in tests.parsing as well
		for href, type in (
			('zim+file://foo/bar?dus.txt', 'notebook'),
			('file:///foo/bar', 'file'),
			('http://foo/bar', 'http'),
			('http://192.168.168.100', 'http'),
			('file+ssh://foo/bar', 'file+ssh'),
			('mailto:foo@bar.com', 'mailto'),
			('mailto:foo.com', 'page'),
			('foo@bar.com', 'mailto'),
			('mailto:foo//bar@bar.com', 'mailto'), # is this a valid mailto uri ?
			('mid:foo@bar.org', 'mid'),
			('cid:foo@bar.org', 'cid'),
			('./foo/bar', 'file'),
			('/foo/bar', 'file'),
			('~/foo', 'file'),
			('C:\\foo', 'file'),
			('wp?foo', 'interwiki'),
			('http://foo?bar', 'http'),
			('\\\\host\\foo\\bar', 'smb'),
			('foo', 'page'),
			('foo:bar', 'page'),
		):
			#~ print ">> LINK %s (%s)" % (href, type)
			#~ self.ui.open_url(href)
			self.ui.mainwindow.pageview.do_link_clicked({'href': href})
			msg = "Clicked: \"%s\" resulted in: \"%s\"" % (href, self.ui.mock_calls[-1])
			if type == 'notebook':
				self.assertTrue(self.ui.mock_calls[-1][0] == 'open_notebook', msg=msg)
			elif type == 'page':
				self.assertTrue(self.ui.mock_calls[-1][0] == 'open_page', msg=msg)
			elif type == 'file':
				self.assertTrue(self.ui.mock_calls[-1][0] == 'open_file', msg=msg)
			elif type == 'mailto':
				self.assertTrue(self.ui.mock_calls[-1][0] in ('_open_with_emailclient', '_open_with'), msg=msg)
			elif type == 'smb' and os.name == 'nt':
				self.assertTrue(self.ui.mock_calls[-1][0] == '_open_with_filebrowser', msg=msg)
			else:
				self.assertTrue(self.ui.mock_calls[-1][0] in ('_open_with_webbrowser', '_open_with'), msg=msg)
			self.ui.mock_calls = [] # reset

		# Some more tests that may not be covered above
		for href, type in (
			('zim+file://foo/bar?dus.txt', 'notebook'),
			('file:///foo/bar', 'file'),
			('mailto:foo@bar.com', 'mailto'),
		):
			#~ print ">> OPEN_URL %s (%s)" % (href, type)
			self.ui.open_url(href)
			msg = "open_url('%s')\nResulted in: %s" % (href, self.ui.mock_calls[-1])
			if type == 'notebook':
				self.assertTrue(self.ui.mock_calls[-1][0] == 'open_notebook', msg=msg)
			elif type == 'file':
				self.assertTrue(self.ui.mock_calls[-1][0] == '_open_with_webbrowser', msg=msg)
			elif type == 'mailto':
				self.assertTrue(self.ui.mock_calls[-1][0] in ('_open_with_emailclient', '_open_with'), msg=msg)
			self.ui.mock_calls = [] # reset

		# TODO test plugin with custom handler


@tests.slowTest
class TestNotebookDialog(tests.TestCase):

	def setUp(self):
		list = config_file('notebooks.list')
		file = list.file
		if file.exists():
			file.remove()

	def runTest(self):
		from zim.gui.notebookdialog import prompt_notebook, \
			AddNotebookDialog, NotebookDialog

		tmpdir = self.create_tmp_dir()
		dir1 = Dir(tmpdir + '/mynotebook1')
		dir2 = Dir(tmpdir + '/mynotebook2')

		# First time we get directly the AddNotebookDialog
		def doAddNotebook(dialog):
			self.assertTrue(isinstance(dialog, AddNotebookDialog))
			dialog.form['name'] = 'Foo'
			dialog.form['folder'] = dir1.path
			dialog.assert_response_ok()

		with tests.DialogContext(doAddNotebook):
			self.assertEqual(prompt_notebook(), dir1.uri)

		# Second time we get the list
		def testNotebookDialog(dialog):
			self.assertTrue(isinstance(dialog, NotebookDialog))
			selection = dialog.treeview.get_selection()
			selection.select_path((0,)) # select first and only notebook
			dialog.assert_response_ok()

		with tests.DialogContext(testNotebookDialog):
			self.assertEqual(prompt_notebook(), dir1.uri)

		# Third time we add a notebook and set the default
		def doAddNotebook(dialog):
			self.assertTrue(isinstance(dialog, AddNotebookDialog))
			dialog.form['name'] = 'Bar'
			dialog.form['folder'] = dir2.path
			dialog.assert_response_ok()

		def testAddNotebook(dialog):
			self.assertTrue(isinstance(dialog, NotebookDialog))

			with tests.DialogContext(doAddNotebook):
				dialog.do_add_notebook()

			dialog.combobox.set_active(0)

			selection = dialog.treeview.get_selection()
			selection.select_path((1,)) # select newly added notebook
			dialog.assert_response_ok()

		with tests.DialogContext(testAddNotebook):
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

		with tests.DialogContext(unsetDefault):
			self.assertEqual(prompt_notebook(), dir2.uri)

		list = get_notebook_list()
		self.assertTrue(len(list) == 2)
		self.assertTrue(list.default is None)


class MockUI(tests.MockObject):

	def __init__(self, page=None, fakedir=None):
		tests.MockObject.__init__(self)

		self.tmp_dir = self.create_tmp_dir()

		if page and not isinstance(page, Path):
			self.page = Path(page)
		else:
			self.page = page

		self.mainwindow = None
		self.notebook = tests.new_notebook(fakedir=fakedir)
