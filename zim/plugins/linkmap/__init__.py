# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

from zim.plugins import PluginClass

class LinkMapPlugin(PluginClass):
	'''FIXME'''

	info = {
		'name': 'Link Map',
		'description': '''\
This plugin provides a dialog with a grahical
representation of the linking structure of the
notebook. It can be used as a kind of "mind map"
showing how pages relate.

This plugin depends on GraphViz, please make
sure it is installed.

This is a core plugin shipping with zim.
''',
		'author': 'Jaap Karssenberg',
	}

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		if self.ui.ui_type == 'gtk':
			import gui
			self.gui = gui.GtkLinkMap(self.ui)
		else:
			self.gui = False

	def disconnect(self):
		if self.gui:
			self.gui.disconnect

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
