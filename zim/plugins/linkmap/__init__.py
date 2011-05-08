# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Plugin showing a map of links between pages based on GraphViz'''

from zim.plugins import PluginClass
from zim.index import LINK_DIR_BOTH
from zim.applications import Application

class LinkMapPlugin(PluginClass):

	plugin_info = {
		'name': _('Link Map'), # T: plugin name
		'description': _('''\
This plugin provides a dialog with a graphical
representation of the linking structure of the
notebook. It can be used as a kind of "mind map"
showing how pages relate.

This is a core plugin shipping with zim.
'''), # T: plugin description
		'author': 'Jaap Karssenberg',
		'help': 'Plugins:Link Map',
	}

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		if self.ui.ui_type == 'gtk':
			import gui
			self.gui = gui.GtkLinkMap(self.ui)
		else:
			self.gui = False

	@classmethod
	def check_dependencies(klass):
		return [('GraphViz',Application(('fdp',)).tryexec())]

	def disconnect(self):
		pass


class LinkMap(object):

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
		dotcode = self.get_dotcode()
		# TODO pass format to dot -Tformat

	def get_dotcode(self):
		dotcode = [
			'digraph LINKS {',
			'  size="6,6";',
			#~ '  node [shape=box, style="rounded,filled", color="#204a87", fillcolor="#729fcf"];',
			'  node [shape=note, style="filled", color="#204a87", fillcolor="#729fcf"];',
			'  "%s" [color="#4e9a06", fillcolor="#8ae234", URL="%s"]' % (self.path.name, self.path.name), # special node
		]

		seen = set()
		seen.add(self.path.name)
		for link in self._links(self.path, self.depth):
			for name in (link.source.name, link.href.name):
				if not name in seen:
					dotcode.append('  "%s" [URL="%s"];' % (name, name))
					seen.add(name)
			dotcode.append(
				'  "%s" -> "%s";'  % (link.source.name, link.href.name))

		dotcode.append('}')

		#~ print '\n'.join(dotcode)+'\n'
		return '\n'.join(dotcode)+'\n'


# And a bit of debug code...

if __name__ == '__main__':
	import sys
	import zim
	import zim.notebook
	import gui
	notebook = zim.notebook.get_notebook(Dir(sys.argv[1]))
	path = notebook.resolve_path(sys.argv[2])
	ui = zim.NotebookInterface(notebook)
	linkmap = LinkMap(notebook, path)
	dialog = gui.LinkMapDialog(ui, linkmap)
	dialog.show_all()
	dialog.run()
