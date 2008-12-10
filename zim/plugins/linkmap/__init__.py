# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

from zim.plugins import PluginClass

class LinkMapPlugin(PluginClass):
	'''FIXME'''

	def __init__(self, app):
		PluginClass.__init__(self, app)
		if app.ui_type == 'gtk':
			import gui
			self.ui = gui.GtkLinkMap(self.app)
		else:
			self.ui = False

	def disconnect(self):
		if self.ui:
			self.ui.disconnect

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
