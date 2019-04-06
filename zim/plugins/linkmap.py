
# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Plugin showing a map of links between pages based on GraphViz'''

import re
import ast

from gi.repository import Gtk

from zim.plugins import PluginClass
from zim.actions import action
from zim.notebook import Path, LINK_DIR_BOTH
from zim.applications import Application
from zim.fs import Dir

from zim.gui.pageview import PageViewExtension
from zim.gui.widgets import Dialog, IconButton

try:
	import xdot
except ImportError:
	xdot = None


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
		has_xdot = xdot is not None
		has_graphviz = Application(('fdp',)).tryexec()
		return has_xdot and has_graphviz, [
			('xdot', has_xdot, True),
			('GraphViz', has_graphviz, True)
		]


class LinkMap(object):

	def __init__(self, notebook, path, depth=2):
		self.notebook = notebook
		self.path = path
		self.depth = depth

	def _all_links(self):
		for page in self.notebook.pages.walk():
			for link in self.notebook.links.list_links(page):
				yield link

	def _links(self, path, depth, seen=None):
		if seen is None:
			seen = set()

		for link in self.notebook.links.list_links(path, direction=LINK_DIR_BOTH):
			key = (link.source.name, link.target.name)

			if not key in seen:
				yield link
				seen.add(key)

				if link.source == path:
					other = link.target
				else:
					other = link.source
				if depth > 0:
					for link in self._links(other, depth - 1, seen):
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
			for name in (link.source.name, link.target.name):
				if not name in seen:
					dotcode.append('  "%s" [URL="%s"];' % (name, name))
					seen.add(name)
			dotcode.append(
				'  "%s" -> "%s";' % (link.source.name, link.target.name))

		dotcode.append('}')

		#print( '\n'.join(dotcode)+'\n')
		return '\n'.join(dotcode) + '\n'


class LinkMapPageViewExtension(PageViewExtension):

	@action(_('Link Map'), icon='zim-linkmap', menuhints='view') # T: menu item
	def show_linkmap(self):
		linkmap = LinkMap(self.pageview.notebook, self.pageview.page)
		dialog = LinkMapDialog(self.pageview, linkmap, self.navigation)
		dialog.show_all()


class LinkMapDialog(Dialog):

	def __init__(self, parent, linkmap, navigation):
		Dialog.__init__(self, parent, 'LinkMap',
			defaultwindowsize=(400, 400), buttons=Gtk.ButtonsType.CLOSE)
		self.linkmap = linkmap
		self.navigation = navigation

		hbox = Gtk.HBox(spacing=5)
		self.vbox.pack_start(hbox, True, True, 0)

		self.xdotview = xdot.DotWidget()
		self.xdotview.set_filter('fdp')
		self.xdotview.set_dotcode(linkmap.get_dotcode().encode('UTF-8'))
		self.xdotview.connect('clicked', self.on_node_clicked)
		hbox.add(self.xdotview)

		vbox = Gtk.VBox()
		hbox.pack_start(vbox, False, False, 0)
		for stock, method in (
			(Gtk.STOCK_ZOOM_IN, self.xdotview.on_zoom_in),
			(Gtk.STOCK_ZOOM_OUT, self.xdotview.on_zoom_out),
			(Gtk.STOCK_ZOOM_FIT, self.xdotview.on_zoom_fit),
			(Gtk.STOCK_ZOOM_100, self.xdotview.on_zoom_100),
		):
			button = IconButton(stock)
			button.connect('clicked', method)
			vbox.pack_start(button, False, True, 0)

	def on_node_clicked(self, widget, name, event):
		if re.match('b\'.*?\'$', name):
			# Bug in dotcode ? URLS come in as strings containing byte representation
			name = ast.literal_eval(name).decode('UTF-8')
		self.navigation.open_page(Path(name))
