
# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Plugin showing a map of links between pages based on GraphViz'''

import re
import ast
import logging

from gi.repository import Gtk

from zim.plugins import PluginClass
from zim.actions import action
from zim.notebook import Path, LINK_DIR_BOTH
from zim.applications import Application

from zim.gui.pageview import PageViewExtension, PromptExistingFileDialog
from zim.gui.widgets import Dialog, IconButton

logger = logging.getLogger('zim.plugins')

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


	plugin_preferences = (
		# key, type, label, default
		('button_in_headerbar', 'bool', _('Show linkmap button in headerbar'), True),
			# T: preferences option
		('zoom_fit', 'bool', _('Autozoom to fit map'), False),
			# T: preferences option
		('sticky', 'bool', _('Follow main window'), False),
			# T: preferences option
		('new_window', 'bool', _('Always open links in new windows'), False),
			# T: preferences option
	)

	@classmethod
	def check_dependencies(klass):
		has_xdot = xdot is not None
		has_graphviz = Application(('fdp',)).tryexec()
		return has_xdot and has_graphviz, [
			('xdot', has_xdot, True),
			('GraphViz', has_graphviz, True)
		]


class LinkMap(object):

	def __init__(self, notebook, path, depth=2, blocklist=set()):
		self.notebook = notebook
		self.path = path
		self.depth = depth
		self.blocklist = blocklist

	def _all_links(self):
		for page in self.notebook.pages.walk():
			for link in self.notebook.links.list_links(page):
				yield link

	def _links(self, path, depth, seen=None):
		if seen is None:
			seen = set()

		if path.name in self.blocklist:
			return

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
			f'  "{self.path.name}" [color="#4e9a06", fillcolor="#8ae234", URL="{self.path.name}"]', # special node
		]

		seen = self.blocklist.copy()
		seen.add(self.path.name)
		for link in self._links(self.path, self.depth):
			#if link.source.name in self.blocklist:
			#	continue
			for name in (link.source.name, link.target.name):
				if not name in seen:
					dotcode.append(f'  "{name}" [URL="{name}"];')
					seen.add(name)
			if link.source.name not in self.blocklist and link.target.name not in self.blocklist:
				dotcode.append(
					f'  "{link.source.name}" -> "{link.target.name}";')

		if len(self.blocklist) > 0:
			dotcode.append('  subgraph cluster0 {')
			dotcode.append('    node [color="#875e20", fillcolor="#cfa272"];')
			dotcode.append('    label = ' + _('Excluded'))  # T: link map cluster
			for url in self.blocklist:
				dotcode.append(f'      "{url}" [URL="{url}"]')
			dotcode.append('  }')

		dotcode.append('}')

		#print( '\n'.join(dotcode)+'\n')
		return '\n'.join(dotcode) + '\n'


class LinkMapPageViewExtension(PageViewExtension):

	def __init__(self, plugin, pageview):
		PageViewExtension.__init__(self, plugin, pageview)
		self.preferences = plugin.preferences
		self.on_preferences_changed(self.preferences)
		self.connectto(plugin.preferences, 'changed', self.on_preferences_changed)

	def on_preferences_changed(self, preferences):
		self.set_action_in_headerbar(self.show_linkmap, preferences['button_in_headerbar'])

	@action(_('Link Map'), icon='linkmap-symbolic', menuhints='view:headerbar') # T: menu item
	def show_linkmap(self):
		dialog = LinkMapDialog(self.pageview, self.navigation, self.preferences)
		dialog.show_all()

class LinkMapWidget(xdot.DotWidget):
	def on_click(self, element, event):
		# override to add middle-click support
		logger.debug('on_click: %s, %s', element, event.button)
		if element and event.button != 1:
			try:
				self.emit('clicked', element.url, event)
				return True
			except Exception:
				pass
		return False

class LinkMapDialog(Dialog):

	def __init__(self, parent, navigation, preferences):
		# LinkMap can't navigate across notebooks
		self.title_ending = ' - ' + parent.notebook.name + ' - LinkMap'
		Dialog.__init__(self, parent, parent.page.name + self.title_ending,
			defaultwindowsize=(400, 400), buttons=Gtk.ButtonsType.CLOSE)
		self.pageview = parent
		self.page = parent.page
		self.navigation = navigation
		self.preferences = preferences
		self.blocklist = set()

		# TODO: optionally refresh linkmap on pageview navigation
		# (makes navigating painfully slow)
		#parent.connect('activate-link', self.refresh_xdotview)

		hbox = Gtk.HBox(spacing=5)
		self.vbox.pack_start(hbox, True, True, 0)

		self.xdotview = LinkMapWidget()
		self.xdotview.set_filter('fdp')
		self.refresh_xdotview()
		self.xdotview.connect('clicked', self.on_node_clicked)
		hbox.add(self.xdotview)

		vbox = Gtk.VBox()
		hbox.pack_start(vbox, False, False, 0)
		for stock, method in (
			(Gtk.STOCK_ZOOM_IN, self.xdotview.on_zoom_in),
			(Gtk.STOCK_ZOOM_OUT, self.xdotview.on_zoom_out),
			(Gtk.STOCK_ZOOM_FIT, self.xdotview.on_zoom_fit),
			(Gtk.STOCK_ZOOM_100, self.xdotview.on_zoom_100),
			(Gtk.STOCK_REFRESH, self.refresh_xdotview),
			(Gtk.STOCK_SAVE, self.save_dotcode),
		):
			button = IconButton(stock)
			button.connect('clicked', method)
			vbox.pack_start(button, False, True, 0)

	def set_dotcode(self, page):
		logger.debug('Load dotcode for page %s', page.name)
		self.set_title(page.name + self.title_ending)
		self.xdotview.set_dotcode(
			LinkMap(self.pageview.notebook, page, blocklist=self.blocklist).get_dotcode().encode('UTF-8'))
		if self.preferences['zoom_fit']:
			self.xdotview.on_zoom_fit(0)  # takes an action, doesn't use it

	def save_dotcode(self, *a):
		import os  # FIXME: learn zim fs api
		folder = self.pageview.notebook.get_attachments_dir(self.page)
		if folder is None:
			raise Error('%s does not have an attachments dir' % path)
		dest = folder.file('linkmap.dot')
		if dest.exists():
			dialog = PromptExistingFileDialog(self, dest)
			dest = dialog.run()
			if dest is None:
				return None
			elif dest.exists():
				dest.remove

		try:
			os.mkdir(str(folder))
		except Exception:
			pass
		with open(str(dest), 'w') as f:
			f.write(LinkMap(self.pageview.notebook, self.page, blocklist=self.blocklist).get_dotcode())

	def refresh_xdotview(self, *a):
		if self.preferences['sticky']:
			self.set_dotcode(self.pageview.page)
		else:
			self.set_dotcode(self.page)

	def on_node_clicked(self, widget, name, event):
		if re.match('b\'.*?\'$', name):
			# Bug in dotcode ? URLS come in as strings containing byte representation
			name = ast.literal_eval(name).decode('UTF-8')

		new_window = event.button == 2 or self.preferences['new_window']

		if event.button != 3:
			self.navigation.open_page(Path(name), new_window=new_window)

			if not new_window and self.preferences['sticky']:
				self.page = self.pageview.page  # for attachments
				self.refresh_xdotview()
		else:
			# toggle blocklist
			if name in self.blocklist:
				logger.debug('including %s', name)
				self.blocklist.remove(name)
			else:
				logger.debug('excluding %s', name)
				self.blocklist.add(name)
