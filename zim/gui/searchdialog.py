# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import gtk
import gobject
import logging

from zim.notebook import Path
from zim.gui.widgets import Dialog, BrowserTreeView, InputEntry, ErrorDialog, ScrolledWindow
from zim.search import *


logger = logging.getLogger('zim.gui.searchdialog')


class SearchDialog(Dialog):

	READY = 0
	SEARCHING = 1
	CANCELLED = 2

	def __init__(self, ui):
		Dialog.__init__(self, ui, _('Search'), # T: Dialog title
			buttons=gtk.BUTTONS_CLOSE, help='Help:Searching',
			defaultwindowsize=(400, 300)
		)

		hbox = gtk.HBox(spacing=5)
		self.vbox.pack_start(hbox, False)
		hbox.pack_start(gtk.Label(_('Search')+': '), False) # T: input label
		self.query_entry = InputEntry()
		hbox.add(self.query_entry)
		self.search_button = gtk.Button(stock=gtk.STOCK_FIND)
		hbox.pack_start(self.search_button, False)

		if gtk.gtk_version >= (2, 20) \
		and gtk.pygtk_version >= (2, 22):
			self.spinner = gtk.Spinner()
			hbox.pack_start(self.spinner, False)
		else:
			self.spinner = None

		self.cancel_button = gtk.Button(stock=gtk.STOCK_STOP)
		hbox.pack_start(self.cancel_button, False)
		self._set_state(self.READY)

		help_text = _(
			'For advanced search you can use operators like\n'
			'AND, OR and NOT. See the help page for more details.'
		) # T: help text for the search dialog
		if gtk.gtk_version >= (2, 12, 0):
			self.query_entry.set_tooltip_text(help_text)
		else:
			tooltips = gtk.Tooltips()
			tooltips.set_tip(self.query_entry, help_text)

		self.namespacecheckbox = gtk.CheckButton(_('Limit search to the current page and sub-pages'))
			# T: checkbox option in search dialog
		self.vbox.pack_start(self.namespacecheckbox, False)

		# TODO advanced query editor
		# TODO checkbox _('Match c_ase')
		# TODO checkbox _('Whole _word')

		self.results_treeview = SearchResultsTreeView(self.ui)
		self.vbox.add(ScrolledWindow(self.results_treeview))

		self.search_button.connect_object('clicked', self.__class__._search, self)
		self.cancel_button.connect_object('clicked', self.__class__._cancel, self)
		self.query_entry.connect_object('activate', self.__class__._search, self)

	def search(self, query):
		'''Trigger a search to be performed.
		Because search can take a long time to execute it is best to
		call this method after the dialog is shown.

		@param query: the query as string
		'''
		self.query_entry.set_text(query)
		self._search()

	def _search(self):
		string = self.query_entry.get_text()
		if self.namespacecheckbox.get_active():
			string = 'Section: "%s" ' % self.ui.page.name + string
		#~ print '!! QUERY: ' + string

		self._set_state(self.SEARCHING)
		try:
			self.results_treeview.search(string)
		except Exception, error:
			ErrorDialog(self, error).run()

		if not self.results_treeview.cancelled:
			self._set_state(self.READY)
		else:
			self._set_state(self.CANCELLED)

	def _cancel(self):
		self.results_treeview.cancelled = True

	def _set_state(self, state):
		# TODO set cursor for treeview part
		# TODO set label or something ?
		def hide(button):
			button.hide_all()
			button.set_no_show_all(True)

		def show(button):
			button.set_no_show_all(False)
			button.show_all()

		if state in (self.READY, self.CANCELLED):
			self.query_entry.set_sensitive(True)
			hide(self.cancel_button)
			if self.spinner:
				self.spinner.stop()
				hide(self.spinner)
			show(self.search_button)
		elif state == self.SEARCHING:
			self.query_entry.set_sensitive(False)
			hide(self.search_button)
			if self.spinner:
				show(self.spinner)
				self.spinner.start()
			show(self.cancel_button)
		else:
			assert False, 'BUG: invalid state'



class SearchResultsTreeView(BrowserTreeView):

	NAME_COL = 0
	SCORE_COL = 1
	PATH_COL = 2

	def __init__(self, ui):
		model = gtk.ListStore(str, int, object)
			# NAME_COL, SCORE_COL, PATH_COL
		BrowserTreeView.__init__(self, model)
		self.ui = ui
		self.query = None
		self.selection = SearchSelection(ui.notebook)
		self.cancelled = False

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

		self.connect('row-activated', self._do_open_page)
		self.connect('destroy', self.__class__._cancel)

	def _cancel(self): self.cancelled = True

	def search(self, query):
		query = query.strip()
		if not query:
			return
		logger.info('Searching for: %s', query)

		self.get_model().clear()
		self.cancelled = False
		self.query = Query(query)
		self.selection.search(self.query, callback=self._search_callback)
		self._update_results(self.selection)

	def _search_callback(self, results, path):
		# Returning False will cancel the search
		#~ print '!! CB', path
		if results is not None:
			self._update_results(results)

		while gtk.events_pending():
			gtk.main_iteration(block=False)

		return not self.cancelled

	def _update_results(self, results):
		model = self.get_model()
		if not model:
			return

		# Update score for paths that are already present
		order = []
		seen = set()
		i = -1
		for i, row in enumerate(model):
			path = row[self.PATH_COL]
			if path in results:
				score = results.scores.get(path, row[self.SCORE_COL])
			else:
				score = -1 # went missing !??? - technically a bug
			row[self.SCORE_COL] = score
			order.append((score, i))
			seen.add(path)

		# Add new paths
		new = results - seen
		for path in new:
			score = results.scores.get(path, 0)
			model.append((path.name, score, path))
			i += 1
			order.append((score, i))

		# re-order
		order.sort() # sort on first item, which is score
		model.reorder([x[1] for x in order]) # use second item

	def _do_open_page(self, view, path, col):
		page = Path( self.get_model()[path][0].decode('utf-8') )
		self.ui.open_page(page)

		# Popup find dialog with same query
		if self.query and self.query.simple_match:
			string = self.query.simple_match
			string = string.strip('*') # support partial matches
			self.ui.mainwindow.pageview.show_find(string, highlight=True)
