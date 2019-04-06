
# Copyright 2009-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>



import tests

from gi.repository import Gtk

from zim.newfs import LocalFolder, LocalFile
from zim.config import XDG_DATA_HOME

from zim.gui.applications import ApplicationManager
from zim.gui.templateeditordialog import TemplateEditorDialog, TemplateListView

BASENAME_COL = TemplateListView.BASENAME_COL


def list_all(model):
	rows = []
	model.foreach(lambda m, p, i: rows.append(m[p]))
	return rows

def find_all(model):
	rows = []
	model.foreach(lambda m, p, i: rows.append((p, m[p])))
	return rows

def select_by_name(view, name):
	for path, row in find_all(view.get_model()):
		if row[BASENAME_COL] == name:
			return view.select(path)


@tests.slowTest
class TestTemplateEditor(tests.TestCase):

	def setUp(self):
		folder = LocalFolder(XDG_DATA_HOME.subdir('zim/templates').path)
		assert 'tests/tmp' in folder.path.replace('\\', '/')
		if folder.exists():
			folder.remove_children()
		for name, content in (
			('html/foo_test.html', 'Test 123\n'),
			('html/bar_test.html', 'Test 123\n'),
		):
			folder.file(name).write(content)

		manager = ApplicationManager()
		entry = manager.create('text/plain', 'test', 'test')
		manager.set_default_application('text/plain', entry)

	def testTemplateList(self):
		dialog = TemplateEditorDialog(None)
		model = dialog.view.get_model()
		self.assertIn('foo_test', [r[BASENAME_COL] for r in list_all(model)])

	def testViewTemplate(self):
		dialog = TemplateEditorDialog(None)
		select_by_name(dialog.view, 'foo_test')

		def open_file(args):
			got = LocalFile(args[-1])
			want = LocalFile(XDG_DATA_HOME.file('zim/templates/html/foo_test.html').path)
			self.assertEqual(got, want)

		with tests.ApplicationContext(open_file):
			dialog.on_view()

	def testEditTemplate(self):
		dialog = TemplateEditorDialog(None)
		select_by_name(dialog.view, 'foo_test')

		def open_file(args):
			got = LocalFile(args[-1])
			want = LocalFile(XDG_DATA_HOME.file('zim/templates/html/foo_test.html').path)
			self.assertEqual(got, want)

		with tests.DialogContext(Gtk.MessageDialog):
			with tests.ApplicationContext(open_file):
				dialog.on_edit()

	def testCopyTemplate(self):
		dialog = TemplateEditorDialog(None)
		select_by_name(dialog.view, 'foo_test')

		def do_copy(dialog):
			dialog.set_input(name='new_foo_test')
			dialog.assert_response_ok()

		with tests.DialogContext(do_copy):
			dialog.on_copy()

		file = LocalFile(XDG_DATA_HOME.file('zim/templates/html/new_foo_test.html').path)
		self.assertTrue(file.exists())


	def testRemoveTemplate(self):
		dialog = TemplateEditorDialog(None)
		select_by_name(dialog.view, 'foo_test')
		file = LocalFile(XDG_DATA_HOME.file('zim/templates/html/foo_test.html').path)
		self.assertTrue(file.exists())
		dialog.on_delete()
		self.assertFalse(file.exists())


	def testBrowseTemplates(self):
		dialog = TemplateEditorDialog(None)

		def open_folder(args):
			got = LocalFolder(args[-1])
			want = LocalFolder(XDG_DATA_HOME.subdir('zim/templates').path)
			self.assertEqual(got, want)

		with tests.ApplicationContext(open_folder):
			dialog.on_browse()
