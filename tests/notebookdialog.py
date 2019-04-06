
# Copyright 2009-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>



import tests

import os

from zim.fs import Dir

from zim.config import ConfigManager
from zim.notebook import NotebookInfo, get_notebook_list

from zim.gui.notebookdialog import NotebookComboBox, NotebookTreeModel


def U(uri):
	if os.name == 'nt':
		return 'file:///C:/' + uri[8:]
	else:
		return uri


class TestNotebookComboBox(tests.TestCase):

	def runTest(self):
		class MyList(list):
			pass

		notebooklist = MyList([
			NotebookInfo(U('file:///test/foo'), name='Foo'),
			NotebookInfo(U('file:///test/bar'), name='Bar')
		])
		notebooklist.default = notebooklist[1]
		notebooklist.write = lambda: None

		model = NotebookTreeModel(notebooklist)

		combobox = NotebookComboBox(model)
		self.assertEqual(combobox.get_notebook(), notebooklist[1].uri) # default

		combobox.set_active(-1)
		self.assertEqual(combobox.get_notebook(), None)

		combobox.set_notebook(notebooklist[0].uri)
		self.assertEqual(combobox.get_notebook(), notebooklist[0].uri)

		combobox.set_notebook(U('file:///yet/another/notebook'))
		self.assertEqual(combobox.get_notebook(), None)

		combobox.set_notebook(U('file:///yet/another/notebook'), append=True)
		self.assertEqual(combobox.get_notebook(), U('file:///yet/another/notebook'))


@tests.slowTest
class TestNotebookDialog(tests.TestCase):

	def setUp(self):
		config = ConfigManager()
		list = config.get_config_file('notebooks.list')
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
			info = prompt_notebook()
			self.assertIsNotNone(info)
			self.assertEqual(info.uri, dir1.uri)

		# Second time we get the list
		def testNotebookDialog(dialog):
			self.assertTrue(isinstance(dialog, NotebookDialog))
			selection = dialog.treeview.get_selection()
			selection.select_path((0,)) # select first and only notebook
			dialog.assert_response_ok()

		with tests.DialogContext(testNotebookDialog):
			info = prompt_notebook()
			self.assertIsNotNone(info)
			self.assertEqual(info.uri, dir1.uri)

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
			info = prompt_notebook()
			self.assertIsNotNone(info)
			self.assertEqual(info.uri, dir2.uri)

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
			info = prompt_notebook()
			self.assertIsNotNone(info)
			self.assertEqual(info.uri, dir2.uri)

		list = get_notebook_list()
		self.assertTrue(len(list) == 2)
		self.assertTrue(list.default is None)
