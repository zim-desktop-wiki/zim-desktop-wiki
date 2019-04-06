
# Copyright 2014-2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import tests

from tests.mainwindow import setUpMainWindow
from tests.pageview import setUpPageView

from zim.notebook import Path
from zim.formats import ParseTree, StubLinker
from zim.formats.html import Dumper as HtmlDumper

from zim.plugins import PluginManager
from zim.plugins.sourceview import *


def get_gtk_action(uimanager, name):
	for group in uimanager.get_action_groups():
		action = group.get_action(name)
		if action is not None:
			return action
	else:
		raise ValueError


@tests.skipIf(GtkSource is None, 'GtkSource not available')
class TestPageView(tests.TestCase):

	def setUp(self):
		PluginManager.load_plugin('sourceview')

	def testWidget(self):
		pageview = setUpPageView(
			self.setUpNotebook(),
			text='''\

{{{code: lang="python" linenumbers="true"
def dump():
		for i in range(1, 5):
				print i
}}}

'''	)
		# test widget loaded
		objects = list(pageview.textview._object_widgets) # XXX
		self.assertIsInstance(objects[0], SourceViewWidget)

		# test modify
		widget = objects[0]
		self.assertFalse(pageview.textview.get_buffer().get_modified())
		widget.buffer.set_text('some new code')
		self.assertTrue(pageview.textview.get_buffer().get_modified())

		# test modification ends up in page
		tree = pageview.get_parsetree()
		#print(tree.tostring())
		elt = tree.find('object')
		self.assertIsNotNone(elt)
		self.assertEqual(elt.attrib['type'], 'code')
		self.assertEqual(elt.gettext(), 'some new code\n')

	def testInsertCodeBlock(self):
		window = setUpMainWindow(self.setUpNotebook(content={'Test': 'Test 123'}), path='Test')
		action = get_gtk_action(window.uimanager, 'insert_code')

		def insert_code_block(dialog):
			self.assertIsInstance(dialog, InsertCodeBlockDialog)
			iter = dialog.combobox.get_model().get_iter('5:0')
			dialog.combobox.set_active_iter(iter)
			dialog.assert_response_ok()

		with tests.DialogContext(insert_code_block):
			action.activate()

		tree = window.pageview.get_parsetree()
		#print(tree.tostring())
		elt = tree.find('object')
		self.assertIsNotNone(elt)
		self.assertEqual(elt.attrib['type'], 'code')

		# Run a second time because it will excersize default language in uistate
		with tests.DialogContext(insert_code_block):
			action.activate()

	def testInsertCodeBlockCancel(self):
		window = setUpMainWindow(self.setUpNotebook(content={'Test': 'Test 123'}), path='Test')
		action = get_gtk_action(window.uimanager, 'insert_code')

		def cancel_dialog(dialog):
			self.assertIsInstance(dialog, InsertCodeBlockDialog)
			dialog.response(Gtk.ResponseType.CANCEL)

		with tests.DialogContext(cancel_dialog):
			action.activate()

		tree = window.pageview.get_parsetree()
		#print(tree.tostring())
		elt = tree.find('object')
		self.assertIsNone(elt)


@tests.skipIf(GtkSource is None, 'GtkSource not available')
class TestSourceViewObject(tests.TestCase):

	def setUp(self):
		PluginManager.load_plugin('sourceview')

	def testPreferencesChanged(self):
		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		obj = PluginManager.insertedobjects['code']
		model = obj.model_from_data(notebook, page, *obj.new_object())
		widget = obj.create_widget(model)
		self.assertTrue(widget.view.get_smart_home_end())
		obj.plugin.preferences['smart_home_end'] = False
		self.assertFalse(widget.view.get_smart_home_end())

	def testPopUp(self):
		notebook = self.setUpNotebook()
		page = notebook.get_page(Path('Test'))
		obj = PluginManager.insertedobjects['code']
		model = obj.model_from_data(notebook, page, *obj.new_object())
		widget = obj.create_widget(model)

		self.assertTrue(widget.view.get_show_line_numbers())
		menu = Gtk.Menu()
		widget.view.emit('populate-popup', menu)
		item = tests.gtk_get_menu_item(menu, 'Show Line Numbers')
		item.activate()
		self.assertFalse(widget.view.get_show_line_numbers())

		submenu = tests.gtk_get_menu_item(menu, 'Syntax')
		item = tests.gtk_get_menu_item(submenu.get_submenu(), 'Python')
		item.activate()
		self.assertEqual(widget.buffer.get_language().get_name(), 'Python')

	def testDumpHtml(self):
		xml = '''\
<?xml version='1.0' encoding='utf-8'?>
<zim-tree><object lang="python" linenumbers="false" type="code">
def foo(a, b):
	print "FOO", a >= b

</object></zim-tree>'''
		tree = ParseTree().fromstring(xml)
		dumper = HtmlDumper(StubLinker())
		html = dumper.dump(tree)
		#print('>>', html)
		self.assertIn(
			'<pre><code class="python">\ndef foo(a, b):\n\tprint "FOO", a &gt;= b\n\n</code></pre>',
			''.join(html)
		)
