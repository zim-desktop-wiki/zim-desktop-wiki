# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Plugin showing a map of links between pages based on GraphViz'''

import gtk

from zim.plugins import PluginClass, extends, WindowExtension
from zim.actions import action
from zim.notebook import Path
from zim.index import LINK_DIR_BOTH
from zim.applications import Application
from zim.fs import Dir
from zim.gui.widgets import ui_environment, Dialog, IconButton
from zim.inc import xdot



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

	@classmethod
	def check_dependencies(klass):
		has_graphviz = Application(('fdp',)).tryexec()
		return has_graphviz, [('GraphViz', has_graphviz, True)]


class LinkMap(object):

	def __init__(self, notebook, path, depth=2):
		self.notebook = notebook
		self.path = path
		self.depth = depth

	def _all_links(self):
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



@extends('MainWindow')
class MainWindowExtension(WindowExtension):

	uimanager_xml = '''
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

	@action(_('Show Link Map'), stock='zim-linkmap') # T: menu item
	def show_linkmap(self):
		linkmap = LinkMap(self.window.ui.notebook, self.window.ui.page) # XXX
		dialog = LinkMapDialog(self.window, linkmap, self.window.get_resource_opener())
		dialog.show_all()


class LinkMapDialog(Dialog):

	def __init__(self, ui, linkmap, opener):
		Dialog.__init__(self, ui, 'LinkMap',
			defaultwindowsize=(400, 400), buttons=gtk.BUTTONS_CLOSE)
		self.linkmap = linkmap
		self.opener = opener

		hbox = gtk.HBox(spacing=5)
		self.vbox.add(hbox)

		self.xdotview = xdot.DotWidget()
		self.xdotview.set_filter('fdp')
		self.xdotview.set_dotcode(linkmap.get_dotcode())
		self.xdotview.connect('clicked', self.on_node_clicked)
		hbox.add(self.xdotview)

		vbox = gtk.VBox()
		hbox.pack_start(vbox, False)
		for stock, method in (
			(gtk.STOCK_ZOOM_IN,  self.xdotview.on_zoom_in ),
			(gtk.STOCK_ZOOM_OUT, self.xdotview.on_zoom_out),
			(gtk.STOCK_ZOOM_FIT, self.xdotview.on_zoom_fit),
			(gtk.STOCK_ZOOM_100, self.xdotview.on_zoom_100),
		):
			button = IconButton(stock)
			button.connect('clicked', method)
			vbox.pack_start(button, False)

	def on_node_clicked(self, widget, name, event):
		self.opener.open_page(Path(name))

# And a bit of debug code...

if __name__ == '__main__':
	import sys
	import zim
	import zim.notebook
	import gui
	notebook = zim.notebook.build_notebook(Dir(sys.argv[1]))
	path = notebook.resolve_path(sys.argv[2])
	linkmap = LinkMap(notebook, path)
	dialog = LinkMapDialog(None, linkmap, None)
	dialog.show_all()
	dialog.run()
