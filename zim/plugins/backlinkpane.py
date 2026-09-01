
# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>



from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango

from zim.plugins import PluginClass
from zim.notebook import Path, LINK_DIR_BACKWARD
from zim.notebook.index import IndexNotFoundError

from zim.gui.pageview import PageViewExtension
from zim.gui.uiactions import UIActions, PAGE_ACCESS_ACTIONS
from zim.gui.widgets import RIGHT_PANE, PANE_POSITIONS, BrowserTreeView, \
	WindowSidePaneWidget, StatusPage


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
		('show_count', 'bool', _('Show BackLink count in title'), True),
			# T: option for plugin preferences
		('show_full_paths', 'bool', _('Show full Page Names'), False),
			# T: option for plugin preferences
	)


class BackLinksPanePageViewExtension(PageViewExtension):

	def __init__(self, plugin, window):
		PageViewExtension.__init__(self, plugin, window)
		self.preferences = plugin.preferences
		self.preferences.connect('changed', self.on_preferences_changed)

		self.widget = BackLinksWidget(self.navigation, self.preferences)

		if self.pageview.page is not None:
			self.on_page_changed(self.pageview, self.pageview.page)
		self.connectto(self.pageview, 'page-changed')

		self.add_sidepane_widget(self.widget, 'pane')

	def on_page_changed(self, window, page):
		self.widget.set_page(window.notebook, page)

	def on_preferences_changed(self, *a):
		# updates both backlink count and link text
		self.on_page_changed(self.pageview, self.pageview.page)

PAGE_COL = 0
TEXT_COL = 1

class BackLinksWidget(Gtk.ScrolledWindow, WindowSidePaneWidget):

	title = _('BackLinks') # T: widget label

	def __init__(self, opener, preferences):
		GObject.GObject.__init__(self)
		self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
		self.set_shadow_type(Gtk.ShadowType.IN)

		self.opener = opener
		self.preferences = preferences
		self.notebook = None

		self._stack = Gtk.Stack()
		self.treeview = LinksTreeView()
		for name, widget in (
			('placeholder', StatusPage(None, _('No backlinks'))), # T: placeholder label in sidepane
			('treeview', self.treeview),
		):
			widget.show_all()
			self._stack.add_named(widget, name)
		self._stack.set_visible_child_name('placeholder')

		self.add(self._stack)
		self.treeview.connect('row-activated', self.on_link_activated)
		self.treeview.connect('populate-popup', self.on_populate_popup)

	def set_page(self, notebook, page):
		self.notebook = notebook
		model = self.treeview.get_model()
		model.clear()

		try:
			backlinks = notebook.links.list_links(page, LINK_DIR_BACKWARD)
				# XXX allow access through page object
		except IndexNotFoundError:
			backlinks = []

		if self.preferences['show_full_paths']:
			for link in backlinks:
				model.append((link.source, str(link.source)))
		else:
			for link in backlinks:
				href = notebook.pages.create_link(link.target, link.source)
					# relative link from target *back* to source
				text = href.to_wiki_link().strip(':')
				#~ model.append(None, (link.source, text))
				model.append((link.source, text))

		self.update_status(model)

		## TODO make hierarchy by link type ?
		## use link.type attribute
		#self.treeview.expand_all()

	def update_status(self, treeview_model):
		n = len(treeview_model)
		if self.preferences['show_count']:
			self.set_info(ngettext('%i _BackLink', '%i _BackLinks', n) % n)
			# T: Label for the statusbar, %i is the number of BackLinks to the current page
		else:
			self.set_info(None)

		if n == 0:
			self._stack.set_visible_child_name('placeholder')
		else:
			self._stack.set_visible_child_name('treeview')

	def on_link_activated(self, treeview, path, column):
		model = treeview.get_model()
		path = model[path][PAGE_COL]
		self.opener.open_page(path)

	def on_populate_popup(self, treeview, menu):
		model, iter = treeview.get_selection().get_selected()
		if model is None or iter is None:
			return # E.g. right click below the last row

		# Use the "access" actions, not the full page menu: this is a list of
		# pages that refer to the current page, so e.g. "Delete Page" would
		# remove the page from the notebook, not the link from the list
		uiactions = UIActions(
			self,
			self.notebook,
			model[iter][PAGE_COL],
			self.opener,
		)
		uiactions.populate_menu_with_actions(PAGE_ACCESS_ACTIONS, menu)
		menu.show_all()


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
