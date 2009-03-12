# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

from zim.plugins import PluginClass
from zim.index import LINK_DIR_BOTH

class LinkMapPlugin(PluginClass):
	'''FIXME'''

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

	def __init__(self, notebook, path, depth=2):
		self.notebook = notebook
		self.path = path
		self.depth = depth

	def _all_links():
		for page in self.notebook.index.walk():
			for link in self.notebook.index.list_links(page):
				yield link

	def _links(self, path, depth, seen=None):
		if seen is None:
			seen = set()

		for link in self.notebook.index.list_links(path, direction=LINK_DIR_BOTH):
			key = (link.source.name, link.href.name)

			if not key in seen:
				yield link
				seen.add(key)

				if link.source == path: other = link.href
				else: other = link.source
				if depth > 0:
					for link in self._links(other, depth-1, seen):
						yield link

	def get_linkmap(self, format=None):
		'''FIXME'''
		dotcode = self.get_dotcode()
		# TODO pass format to dot -Tformat

	def get_dotcode(self):
		'''FIXME'''
		dotcode = [
			'digraph LINKS {',
			'  size="6,6";',
			#~ '  node [shape=box, style="rounded,filled", color="#204a87", fillcolor="#729fcf"];',
			'  node [shape=note, style="filled", color="#204a87", fillcolor="#729fcf"];',
			'  %s [color="#4e9a06", fillcolor="#8ae234"]' % self.path.name, # special node
		]

		for link in self._links(self.path, self.depth):
			dotcode.append(
				'  "%s" -> "%s";'  % (link.source.name, link.href.name))

		dotcode.append('}')

		return '\n'.join(dotcode)+'\n'


# And a bit of debug code...

if __name__ == '__main__':
	import sys
	import zim
	import zim.notebook
	import gui
	notebook = zim.notebook.get_notebook(sys.argv[1])
	path = notebook.resolve_path(sys.argv[2])
	ui = zim.NotebookInterface(notebook)
	linkmap = LinkMap(notebook, path)
	dialog = gui.LinkMapDialog(ui, linkmap)
	dialog.show_all()
	dialog.run()
