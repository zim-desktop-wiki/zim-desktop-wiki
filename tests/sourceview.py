
# Copyright 2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>



import tests

from tests.mainwindow import setUpMainWindow
from tests.pageview import setUpPageView

from zim.formats import ParseTree, StubLinker
from zim.formats.html import Dumper as HtmlDumper

from zim.plugins.sourceview import *


@tests.skipIf(GtkSource is None, 'GtkSource not available')
class TestPageViewExtension(tests.TestCase):

	def setUp(self):
		self.plugin = SourceViewPlugin()

	def tearDown(self):
		self.plugin.destroy()

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
		extension = SourceViewPageViewExtension(self.plugin, window.pageview)

		def insert_code_block(dialog):
			self.assertIsInstance(dialog, InsertCodeBlockDialog)
			iter = dialog.combobox.get_model().get_iter('5:0')
			dialog.combobox.set_active_iter(iter)
			dialog.assert_response_ok()

		with tests.DialogContext(insert_code_block):
			extension.insert_sourceview()

		tree = window.pageview.get_parsetree()
		#print(tree.tostring())
		elt = tree.find('object')
		self.assertIsNotNone(elt)
		self.assertEqual(elt.attrib['type'], 'code')

		# Run a second time because it will excersize default language in uistate
		with tests.DialogContext(insert_code_block):
			extension.insert_sourceview()

	def testInsertCodeBlockCancel(self):
		window = setUpMainWindow(self.setUpNotebook(content={'Test': 'Test 123'}), path='Test')
		extension = SourceViewPageViewExtension(self.plugin, window.pageview)

		def cancel_dialog(dialog):
			self.assertIsInstance(dialog, InsertCodeBlockDialog)
			dialog.response(Gtk.ResponseType.CANCEL)

		with tests.DialogContext(cancel_dialog):
			extension.insert_sourceview()

		tree = window.pageview.get_parsetree()
		#print(tree.tostring())
		elt = tree.find('object')
		self.assertIsNone(elt)


@tests.skipIf(GtkSource is None, 'GtkSource not available')
class TestSourceViewObject(tests.TestCase):

	def setUp(self):
		self.plugin = SourceViewPlugin()

	def tearDown(self):
		self.plugin.destroy()

	def testPreferencesChanged(self):
		obj = self.plugin._objecttype
		model = obj.create_model()
		widget = obj.create_widget(model)
		self.assertTrue(widget.view.get_smart_home_end())
		self.plugin.preferences['smart_home_end'] = False
		self.assertFalse(widget.view.get_smart_home_end())

	def testPopUp(self):
		obj = self.plugin._objecttype
		model = obj.create_model()
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
