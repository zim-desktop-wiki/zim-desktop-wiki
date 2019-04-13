
# Copyright 2009-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>



import tests

from zim.fs import TmpFile
from zim.notebook import Path

from zim.gui.customtools import *


def clear_customtools():
	listfile = XDG_CONFIG_HOME.file('zim/customtools/customtools.list')
	folder = XDG_CONFIG_HOME.subdir('zim/customtools/')
	assert 'tests/tmp' in listfile.path.replace('\\', '/')
	assert 'tests/tmp' in folder.path.replace('\\', '/')
	listfile.remove()
	folder.remove_children()


class MockStubPageView(StubPageView):

	def get_word(self, format=None):
		if format:
			return '**FooBar**'
		else:
			return 'FooBar'


@tests.slowTest
class TestCustomTools(tests.TestCase):

	mockConfigManager = False  # breaks hack in customtools

	def setUp(self):
		clear_customtools()

	def testManager(self):
		'''Test CustomToolManager API'''
		# initialize the list
		manager = CustomToolManager()
		self.assertEqual(list(manager), [])
		self.assertEqual(list(manager._names), [])

		# add a tool
		properties = {
			'Name': 'Foo',
			'Comment': 'Test 1 2 3',
			'Icon': '',
			'X-Zim-ExecTool': 'foo %t "quoted"',
			'X-Zim-ReadOnly': False,
			'X-Zim-ShowInToolBar': True,
		}
		tool = manager.create(**properties)
		self.assertEqual(list(manager), [tool])
		self.assertEqual(list(manager._names), ['foo-usercreated'])

		self.assertTrue(tool.isvalid)
		self.assertEqual(tool.name, 'Foo')
		self.assertEqual(tool.comment, 'Test 1 2 3')
		self.assertFalse(tool.isreadonly)
		self.assertTrue(tool.showintoolbar)
		self.assertTrue(tool.get_pixbuf(Gtk.IconSize.MENU))
		self.assertEqual(tool.showincontextmenu, 'Text') # Auto generated

		# test file saved correctly
		#~ from pprint import pprint
		#~ pprint(tool)
		lines = tool.dump()
		self.assertTrue(len(lines) > 5)
		lines = tool.file.readlines()
		self.assertTrue(len(lines) > 5)

		# refresh list
		manager = CustomToolManager()
		self.assertEqual(list(manager), [tool])
		self.assertEqual(list(manager._names), ['foo-usercreated'])

		# add a second tool
		tool1 = tool
		properties = {
			'Name': 'Foo',
			'Comment': 'Test 1 2 3',
			'Icon': None,
			'X-Zim-ExecTool': 'foo %f',
			'X-Zim-ReadOnly': False,
			'X-Zim-ShowInToolBar': True,
		}
		tool = manager.create(**properties)
		self.assertEqual(list(manager), [tool1, tool])
		self.assertEqual(list(manager._names), ['foo-usercreated', 'foo-usercreated-1'])

		self.assertTrue(tool.isvalid)
		self.assertEqual(tool.name, 'Foo')
		self.assertEqual(tool.comment, 'Test 1 2 3')
		self.assertFalse(tool.isreadonly)
		self.assertTrue(tool.showintoolbar)
		self.assertTrue(tool.get_pixbuf(Gtk.IconSize.MENU))
		self.assertEqual(tool.showincontextmenu, 'Page') # Auto generated

		# switch order
		i = manager.index(tool)
		self.assertTrue(i == 1)
		manager.reorder(tool, 0)
		i = manager.index(tool)
		self.assertTrue(i == 0)
		self.assertEqual(list(manager._names), ['foo-usercreated-1', 'foo-usercreated'])

		# delete
		file = tool1.file
		self.assertTrue(file.exists())
		manager.delete(tool1)
		self.assertEqual(list(manager._names), ['foo-usercreated-1'])
		self.assertFalse(file.exists())

	def testParseExec(self):
		'''Test parsing of custom tool Exec strings'''
		# %f for source file as tmp file current page
		# %d for attachment directory
		# %s for real source file (if any)
		# %p for the page name
		# %n for notebook location (file or directory)
		# %D for document root
		# %t for selected text or word under cursor
		# %T for selected text or word under cursor with wiki format

		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test:Foo'))
		pageview = MockStubPageView(notebook, page)
		args = (notebook, page, pageview)

		tmpfile = TmpFile('tmp-page-source.txt').path

		tool = CustomToolDict()
		tool.update({
			'Name': 'Test',
			'Comment': 'Test 1 2 3',
			'X-Zim-ExecTool': 'foo',
		})
		for cmd, wanted in (
			('foo %f', ('foo', tmpfile)),
			('foo %d', ('foo', notebook.folder.folder('Test/Foo').path)),
			('foo %s', ('foo', page.source.path)),
			('foo %p', ('foo', 'Test:Foo')),
			('foo %n', ('foo', notebook.folder.path)),
			('foo %D', ('foo', '')), # no document root
			('foo %t', ('foo', 'FooBar')),
			('foo %T', ('foo', '**FooBar**')),
		):
			#~ print('>>>', cmd)
			tool['Desktop Entry']['X-Zim-ExecTool'] = cmd
			self.assertEqual(tool.parse_exec(args), wanted)


class TestCustomToolsUI(tests.TestCase):

	mockConfigManager = False  # breaks hack in customtools

	def setUp(self):
		clear_customtools()

		notebook = self.setUpNotebook(content=('test',))
		page = notebook.get_page(Path('test'))

		self.uimanager = Gtk.UIManager()
		group = Gtk.ActionGroup('test')
		group.add_actions([('tools_menu', None, '_Tools')])
		self.uimanager.insert_action_group(group)


		self.pageview = StubPageView(notebook, page)
		self.customtoolsui = CustomToolManagerUI(self.uimanager, self.pageview)

	def get_action(self, name):
		for group in self.uimanager.get_action_groups():
			action = group.get_action(name)
			if action:
				return action
		else:
			raise ValueError

	def testMenuUpdatedWhenToolAdded(self):
		# Key in this test is that the changes happens via a different instance
		# of the manager - demonstrating the singleton-like behavior
		self.assertNotIn('edit-usercreated', self.uimanager.get_ui())
		mymanager = CustomToolManager()
		mytool = {
			'Name': 'Edit',
			'Comment': 'Test Edit',
			'X-Zim-ExecTool': 'edit %f',
		}
		mymanager.create(**mytool)
		self.assertIn('edit-usercreated', self.uimanager.get_ui())

	def testMenuUpdatedWhenToolChanges(self):
		# Key in this test is that the changes happens via a different instance
		# of the manager - demonstrating the singleton-like behavior
		mymanager = CustomToolManager()
		mytool = {
			'Name': 'Edit',
			'Comment': 'Test Edit',
			'X-Zim-ExecTool': 'edit %f',
		}
		mymanager.create(**mytool)
		self.assertIn('edit-usercreated', self.uimanager.get_ui())
		action = self.get_action('edit-usercreated')
		self.assertEqual(action.get_property('label'), 'Edit')

		tool = mymanager.get_tool('Edit')
		tool.update({'Name': 'My Editting tool'})
		tool.write()
		self.assertIn('edit-usercreated', self.uimanager.get_ui())
		action = self.get_action('edit-usercreated')
		self.assertEqual(action.get_property('label'), 'My Editting tool')

	def testExecuteCustomToolAction(self):
		mymanager = CustomToolManager()
		mytool = {
			'Name': 'Edit',
			'Comment': 'Test Edit',
			'X-Zim-ExecTool': 'edit %f',
		}
		mymanager.create(**mytool)
		action = self.get_action('edit-usercreated')

		def tool_run(args):
			self.assertIn(args[0], ('edit', b'edit'))

		with tests.ApplicationContext(tool_run):
			action.activate()

	def testExecuteCustomToolActionModifyPage(self):
		mymanager = CustomToolManager()
		mytool = {
			'Name': 'Edit',
			'Comment': 'Test Edit',
			'X-Zim-ExecTool': 'edit %s',
			'X-Zim-ReadOnly': False,
		}
		mymanager.create(**mytool)
		action = self.get_action('edit-usercreated')

		def tool_run(args):
			self.assertIn(args[0], ('edit', b'edit'))
			self.pageview.page.source_file.write('test 123')

		with tests.ApplicationContext(tool_run):
			action.activate()

	def testExecuteCustomToolActionReplaceSelection(self):
		mymanager = CustomToolManager()
		mytool = {
			'Name': 'Edit',
			'Comment': 'Test Edit',
			'X-Zim-ExecTool': 'edit %f',
			'X-Zim-ReplaceSelection': True,
		}
		tool = mymanager.create(**mytool)
		self.assertTrue(tool.replaceselection)
		action = self.get_action('edit-usercreated')

		got = []
		self.pageview.replace_selection = lambda *a, **kwa: got.append(a)

		def tool_run(args):
			self.assertIn(args[0], ('edit', b'edit'))
			return "TEST 123"

		with tests.ApplicationContext(tool_run):
			action.activate()

		self.assertEqual(got, [('TEST 123',)])

class TestCustomToolDialog(tests.TestCase):

	mockConfigManager = False  # breaks hack in customtools

	def setUp(self):
		clear_customtools()

	def testAddCustomTool(self):
		manager = CustomToolManager()
		mytool = {
			'Name': 'Add',
			'Comment': 'Test Add',
			'X-Zim-ExecTool': 'add %f',
			'X-Zim-ReadOnly': False,
			'X-Zim-ShowInToolBar': False,
			'X-Zim-ReplaceSelection': False,
		}

		self.assertIsNone(manager.get_tool('Add'))

		def add_tool(dialog):
			dialog.set_input(**mytool)
			dialog.assert_response_ok()

		dialog = CustomToolManagerDialog(None)
		with tests.DialogContext(add_tool):
			dialog.on_add()
			dialog.assert_response_ok()

		# XXX listview intialization fails in test ???
		#model = dialog.listview.get_model()
		#self.assertIn('Add', [r[CustomToolList.NAME_COL] for r in model])

		tool = manager.get_tool('Add')
		self.assertIsNotNone(tool)
		for key, value in list(mytool.items()):
			self.assertEqual(tool['Desktop Entry'][key], value)

	@tests.expectedFailure # Fails because of select_by_name fails - listview initialized ?
	def testEditCustomTool(self):
		manager = CustomToolManager()
		mytool = {
			'Name': 'Edit',
			'Comment': 'Test Edit',
			'X-Zim-ExecTool': 'edit %f',
		}
		manager.create(**mytool)
		self.assertIsNotNone(manager.get_tool('Edit'))

		def edit_tool(dialog):
			dialog.set_input(Comment='Editted Comment')
			dialog.assert_response_ok()

		dialog = CustomToolManagerDialog(None)
		#model = dialog.listview.get_model()
		#self.assertIn('Edit', [r[CustomToolList.NAME_COL] for r in model])
		with tests.DialogContext(edit_tool):
			dialog.listview.select_by_name('Edit')
			dialog.on_edit()
			dialog.assert_response_ok()

		tool = manager.get_tool('Edit')
		self.assertEqual(tool.comment, 'Editted Comment')

	@tests.expectedFailure
	def testRemoveCustomTool(self):
		# Need initialized listview
		raise NotImplementedError

	@tests.expectedFailure
	def testMovePositionInList(self):
		# Need initialized listview
		raise NotImplementedError
