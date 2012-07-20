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
		else:
			self.ui.mainwindow.remove(self.sidepane_widget)

		self.ui.mainwindow.add_tab(
			_('BackLinks'), self.sidepane_widget, self.preferences['pane'])
			# T: widget label
		self.sidepane_widget.show_all()


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
		ui.connect('open-page', self.on_open_page)
		if ui.page:
			self.on_open_page(ui, ui.page, Path(ui.page.name))

	def on_open_page(self, ui, page, path):
		model = self.treeview.get_model()
		model.clear()

		backlinks = ui.notebook.index.list_links(path, LINK_DIR_BACKWARD)
		for link in backlinks:
			source = link.source
			model.append(None, (source, source.name))
			## TODO make names relative

		## TODO make hierarchy by link type ?
		## use link.type attribute
		#self.treeview.expand_all()

	def on_link_activated(self, treeview, path, column):
		model = treeview.get_model()
		page = model[path][PAGE_COL]
		self.ui.open_page(page)


class LinksTreeView(BrowserTreeView):
	## TODO common base class with page index for popup menus etc. ?

	def __init__(self):
		BrowserTreeView.__init__(self, LinksTreeModel())
		self.set_headers_visible(False)

		cell_renderer = gtk.CellRendererText()
		cell_renderer.set_property('ellipsize', pango.ELLIPSIZE_END)
		column = gtk.TreeViewColumn('_page_', cell_renderer, text=TEXT_COL)
		self.append_column(column)



class LinksTreeModel(gtk.TreeStore):

	def __init__(self):
		gtk.TreeStore.__init__(self, object, str) # PAGE_COL, TEXT_COL

