# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

from zim.plugins import PluginClass

ui = '''
<ui>
	<menubar name='menubar'>
		<menu action='view_menu'>
			<placeholder name='plugin_items'>
				<menuitem action='show_linkmap'/>
			</placeholder>
		</menu>
	</menubar>
</ui>
'''

ui_actions = (
	# name, stock id, label, accelerator, tooltip
	('show_linkmap', None, 'Show Link Map', None, 'Show Link Map'),
)

class LinkMapPlugin(PluginClass):
	'''FIXME'''

	def __init__(self, app):
		PluginClass.__init__(self, app)
		#~ if app.type == 'GtkApplication':
			# Hook LinkMapDialog into the application
		self.add_actions(ui_actions)
		self.add_ui(ui)
		# TODO similar for www ?

	def show_linkmap(self):
		from gui import LinkMapDialog
		linkmap = LinkMap(self.app.notebook)
		dialog = LinkMapDialog(linkmap)
		dialog.show_all()

class LinkMap(object):
	'''FIXME'''

	def __init__(self, notebook):
		self.notebook = notebook

	def links(self):
		root = self.notebook.get_root()
		for page in root.walk():
			tree = page.get_parsetree()
			if tree is None:
				continue
			for link in tree.getiterator('link'):
				yield page, link

	def get_linkmap(self, format=None):
		'''FIXME'''
		dotcode = self.get_dotcode()
		# TODO pass format to dot -Tformat

	def get_dotcode(self):
		'''FIXME'''
		dotcode = [
			'digraph LINKS {',
			'  size="6,6";',
			'  node [color=lightblue2, style=filled];',
		]

		for page, link in self.links():
			dotcode.append('  "%s" -> "%s";'  % (page.name, link.attrib['href']))

		dotcode.append('}')

		return '\n'.join(dotcode)+'\n'
