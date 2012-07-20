# -*- coding: utf-8 -*-

# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement

import gobject
import gtk
import pango

from zim.plugins import PluginClass
from zim.notebook import Path
from zim.gui.widgets import RIGHT_PANE, PANE_POSITIONS, BrowserTreeView, populate_popup_add_separator
from zim.index import LINK_DIR_BACKWARD


class BackLinksPanePlugin(PluginClass):

	plugin_info = {
		'name': _('BackLinks Pane'), # T: plugin name
		'description': _('''\
This plugin adds an extra widget showing a list of pages
linking to the current page.

This is a core plugin shipping with zim.
'''), # T: plugin description
		'author': 'Jaap Karssenberg',
		#~ 'help': 'Plugins:BackLinks Pane',
	}

	plugin_preferences = (
		# key, type, label, default
		('pane', 'choice', _('Position in the window'), RIGHT_PANE, PANE_POSITIONS),
			# T: option for plugin preferences
	)


	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		self.sidepane_widget = None

	def finalize_notebook(self, ui):
		self.do_preferences_changed()

	def disconnect(self):
		if self.sidepane_widget:
			self.ui.mainwindow.remove(self.sidepane_widget)
			self.sidepane_widget.destroy()
			self.sidepane_widget = None

		PluginClass.disconnect(self)

	def do_preferences_changed(self):
		if self.ui.ui_type != 'gtk':
			return

		if not self.sidepane_widget:
			self.sidepane_widget = BackLinksWidget(self.ui)
			self.connectto(self.ui, 'open-page')

		else:
			self.ui.mainwindow.remove(self.sidepane_widget)

		self.ui.mainwindow.add_tab(
			_('BackLinks'), self.sidepane_widget, self.preferences['pane'])
			# T: widget label
		self.sidepane_widget.show_all()

	def on_open_page(self, ui, page, path):
		self.sidepane_widget.set_page(page)


PAGE_COL = 0
TEXT_COL = 1

class BackLinksWidget(gtk.ScrolledWindow):

	def __init__(self, ui):
		gtk.ScrolledWindow.__init__(self)
		self.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
		self.set_shadow_type(gtk.SHADOW_IN)

		self.ui = ui

		self.treeview = LinksTreeView()
		self.add(self.treeview)
		self.treeview.connect('row-activated', self.on_link_activated)
		self.treeview.connect('populate-popup', self.on_populate_popup)

		if self.ui.page:
			self.set_page(self.ui.page)

	def set_page(self, page):
		model = self.treeview.get_model()
		model.clear()

		backlinks = self.ui.notebook.index.list_links(page, LINK_DIR_BACKWARD)
		for link in backlinks:
			href = self.ui.notebook.relative_link(link.href, link.source)
				# relative link from href *back* to source
			href = href.lstrip(':')
			#~ model.append(None, (link.source, href))
			model.append((link.source, href))

		## TODO make hierarchy by link type ?
		## use link.type attribute
		#self.treeview.expand_all()

	def on_link_activated(self, treeview, path, column):
		model = treeview.get_model()
		path = model[path][PAGE_COL]
		self.ui.open_page(path)

	def on_populate_popup(self, treeview, menu):
		populate_popup_add_separator(menu)

		if gtk.gtk_version >= (2, 16, 0):
			action = self.ui.actiongroup.get_action('open_new_window')
			label = action.get_label()
			item = gtk.MenuItem(label)
			item.connect('activate', self.on_open_new_window, treeview)
			menu.append(item)

		# Other per page menu items do not really apply here...

	def on_open_new_window(self, o, treeview):
		model, iter = treeview.get_selection().get_selected()
		if model and iter:
			path = model[iter][PAGE_COL]
			self.ui.open_new_window(path)


class LinksTreeView(BrowserTreeView):

	def __init__(self):
		BrowserTreeView.__init__(self, LinksTreeModel())
		self.set_headers_visible(False)

		cell_renderer = gtk.CellRendererText()
		cell_renderer.set_property('ellipsize', pango.ELLIPSIZE_END)
		column = gtk.TreeViewColumn('_page_', cell_renderer, text=TEXT_COL)
		self.append_column(column)

		if gtk.gtk_version >= (2, 12, 0):
			self.set_tooltip_column(TEXT_COL)


#~ class LinksTreeModel(gtk.TreeStore):
class LinksTreeModel(gtk.ListStore):

	def __init__(self):
		#~ gtk.TreeStore.__init__(self, object, str) # PAGE_COL, TEXT_COL
		gtk.ListStore.__init__(self, object, str) # PAGE_COL, TEXT_COL

