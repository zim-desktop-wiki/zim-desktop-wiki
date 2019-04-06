
# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>



from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango

from zim.plugins import PluginClass
from zim.notebook import Path, LINK_DIR_BACKWARD
from zim.notebook.index import IndexNotFoundError

from zim.gui.pageview import PageViewExtension
from zim.gui.widgets import RIGHT_PANE, PANE_POSITIONS, BrowserTreeView, populate_popup_add_separator, \
	WindowSidePaneWidget


class BackLinksPanePlugin(PluginClass):

	plugin_info = {
		'name': _('BackLinks Pane'), # T: plugin name
		'description': _('''\
This plugin adds an extra widget showing a list of pages
linking to the current page.

This is a core plugin shipping with zim.
'''), # T: plugin description
		'author': 'Jaap Karssenberg',
		'help': 'Plugins:BackLinks Pane',
	}

	plugin_preferences = (
		# key, type, label, default
		('pane', 'choice', _('Position in the window'), RIGHT_PANE, PANE_POSITIONS),
			# T: option for plugin preferences
	)


class BackLinksPanePageViewExtension(PageViewExtension):

	def __init__(self, plugin, window):
		PageViewExtension.__init__(self, plugin, window)

		self.widget = BackLinksWidget(self.navigation)

		if self.pageview.page is not None:
			self.on_page_changed(self.pageview, self.pageview.page)
		self.connectto(self.pageview, 'page-changed')

		self.add_sidepane_widget(self.widget, 'pane')

	def on_page_changed(self, window, page):
		self.widget.set_page(window.notebook, page)


PAGE_COL = 0
TEXT_COL = 1

class BackLinksWidget(Gtk.ScrolledWindow, WindowSidePaneWidget):

	title = _('BackLinks') # T: widget label

	def __init__(self, opener):
		GObject.GObject.__init__(self)
		self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
		self.set_shadow_type(Gtk.ShadowType.IN)

		self.opener = opener

		self.treeview = LinksTreeView()
		self.add(self.treeview)
		self.treeview.connect('row-activated', self.on_link_activated)
		self.treeview.connect('populate-popup', self.on_populate_popup)

	def set_page(self, notebook, page):
		model = self.treeview.get_model()
		model.clear()

		try:
			backlinks = notebook.links.list_links(page, LINK_DIR_BACKWARD)
				# XXX allow access through page object
		except IndexNotFoundError:
			backlinks = []

		for link in backlinks:
			href = notebook.pages.create_link(link.target, link.source)
				# relative link from target *back* to source
			text = href.to_wiki_link().strip(':')
			#~ model.append(None, (link.source, text))
			model.append((link.source, text))

		## TODO make hierarchy by link type ?
		## use link.type attribute
		#self.treeview.expand_all()

	def on_link_activated(self, treeview, path, column):
		model = treeview.get_model()
		path = model[path][PAGE_COL]
		self.opener.open_page(path)

	def on_populate_popup(self, treeview, menu):
		populate_popup_add_separator(menu)

		item = Gtk.MenuItem.new_with_mnemonic(_('Open in New _Window'))
		item.connect('activate', self.on_open_new_window, treeview)
		menu.append(item)

		# Other per page menu items do not really apply here...

	def on_open_new_window(self, o, treeview):
		model, iter = treeview.get_selection().get_selected()
		if model and iter:
			path = model[iter][PAGE_COL]
			self.opener.open_page(path, new_window=True)


class LinksTreeView(BrowserTreeView):

	def __init__(self):
		BrowserTreeView.__init__(self, LinksTreeModel())
		self.set_headers_visible(False)

		cell_renderer = Gtk.CellRendererText()
		cell_renderer.set_property('ellipsize', Pango.EllipsizeMode.END)
		column = Gtk.TreeViewColumn('_page_', cell_renderer, text=TEXT_COL)
		self.append_column(column)
		self.set_tooltip_column(TEXT_COL)


class LinksTreeModel(Gtk.ListStore):

	def __init__(self):
		Gtk.ListStore.__init__(self, object, str) # PAGE_COL, TEXT_COL
