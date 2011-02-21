# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import gtk
import logging

from zim.notebook import Path
from zim.gui.widgets import Dialog, BrowserTreeView, InputEntry
from zim.search import *


logger = logging.getLogger('zim.gui.searchdialog')


class SearchDialog(Dialog):

	def __init__(self, ui, query=None):
		Dialog.__init__(self, ui, _('Search'), # T: Dialog title
			buttons=gtk.BUTTONS_CLOSE, help='Help:Searching')

		hbox = gtk.HBox(spacing=5)
		self.vbox.pack_start(hbox, False)
		hbox.pack_start(gtk.Label(_('Search')+': '), False) # T: input label
		self.query_entry = InputEntry()
		hbox.add(self.query_entry)
		button = gtk.Button(stock=gtk.STOCK_FIND)
		hbox.pack_start(button, False)

		help_text = _(
			'For advanced search you can use operators like\n'
			'AND, OR and NOT. See the help page for more details.'
		) # T: help text for the search dialog
		if gtk.gtk_version >= (2, 12, 0):
			self.query_entry.set_tooltip_text(help_text)
		else:
			tooltips = gtk.Tooltips()
			tooltips.set_tip(self.query_entry, help_text)

		self.namespacecheckbox = gtk.CheckButton(_('Limit search to current namespace'))
			# T: checkbox option in search dialog
		self.vbox.pack_start(self.namespacecheckbox, False)

		# TODO advanced query editor
		# TODO checkbox _('Match c_ase')
		# TODO checkbox _('Whole _word')

		scrollwindow = gtk.ScrolledWindow()
		scrollwindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
		scrollwindow.set_shadow_type(gtk.SHADOW_IN)
		self.vbox.add(scrollwindow)

		self.results_treeview = SearchResultsTreeView(self.ui)
		scrollwindow.add(self.results_treeview)

		if query:
			self.query_entry.set_text(query)
			self.results_treeview.set_query(query)


		def search(*a):
			string = self.query_entry.get_text()
			if self.namespacecheckbox.get_active():
				string = 'Namespace: "%s" ' % self.ui.page.name + string
			#~ print '!! QUERY: ' + string
			self.results_treeview.set_query( string )

		button.connect('clicked', search)
		self.query_entry.connect('activate', search)


class SearchResultsTreeView(BrowserTreeView):

	def __init__(self, ui):
		model = gtk.ListStore(str, int) # page, rank
		BrowserTreeView.__init__(self, model)
		self.ui = ui
		self.query = None
		self.selection = SearchSelection(ui.notebook)

		cell_renderer = gtk.CellRendererText()
		for name, i in (
			(_('Page'), 0), # T: Column header search dialog
			(_('Score'), 1), # T: Column header search dialog
		):
			column = gtk.TreeViewColumn(name, cell_renderer, text=i)
			column.set_sort_column_id(i)
			if i == 0:
				column.set_expand(True)
			self.append_column(column)

		model.set_sort_column_id(1, gtk.SORT_DESCENDING)
			# By default sort by score

		self.connect('row-activated', self._do_open_page) # FIXME

	def set_query(self, query):
		query = query.strip()
		if not query:
			return
		logger.info('Searching for: %s', query)

		self.query = Query(query)
		self.selection.search(self.query)
		# TODO need callback here

		model = self.get_model()
		model.clear()
		for path in sorted(self.selection, key=lambda p: p.name):
			model.append((path.name, self.selection.scores[path]))

	def _do_open_page(self, view, path, col):
		page = Path( self.get_model()[path][0].decode('utf-8') )
		self.ui.open_page(page)

		# Popup find dialog with same query
		if self.query and self.query.simple_match:
			string = self.query.simple_match
			string.strip('*') # support partial matches
			self.ui.mainwindow.pageview.show_find(string, highlight=True)
