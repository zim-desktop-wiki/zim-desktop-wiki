# -*- coding: utf-8 -*-

# Copyright 2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import gtk
import gobject
import logging

import zim.datetimetz as datetime

from zim.notebook import Path
from zim.gui.widgets import Dialog, BrowserTreeView, ScrolledWindow


logger = logging.getLogger('zim.gui.dialogs')


class RecentChangesDialog(Dialog):

	def __init__(self, ui):
		Dialog.__init__(self, ui, _('Recent Changes'), # T: Dialog title
			buttons=gtk.BUTTONS_CLOSE,
			defaultwindowsize=(400, 300)
		)

		self.treeview = RecentChangesTreeView(ui)
		self.vbox.add(ScrolledWindow(self.treeview))

		self.update()
		self.ui.notebook.connect_after('stored-page', lambda *a: self.update())

	def update(self):
		model = self.treeview.get_model()
		model.clear()
		list = self.ui.notebook.index.list_recent_pages(offset=0, limit=50)
		for indexpath in list:
			model.append((indexpath.name, indexpath.contentkey)) # HACK !



class RecentChangesTreeView(BrowserTreeView):

	NAME_COL = 0
	MODIFIED_COL = 1

	def __init__(self, ui):
		model = gtk.ListStore(str, str)
			# NAME_COL, MODIFIED_COL
		BrowserTreeView.__init__(self, model)
		self.ui = ui

		cell_renderer = gtk.CellRendererText()

		column = gtk.TreeViewColumn(_('Page'), cell_renderer, text=self.NAME_COL) # T: Column header
		column.set_sort_column_id(self.NAME_COL)
		column.set_expand(True)
		self.append_column(column)

		today = datetime.date.today()
		yesterday = today - datetime.timedelta(days=1)
		def render_date(col, cell, model, i):
			utime = model.get_value(i, self.MODIFIED_COL)
			if utime:
				utime = float(utime)
				dt = datetime.datetime.fromtimestamp(utime)
				date = dt.date()
				if date == today:
					text = _('Today') + dt.strftime(' %H:%M')
					# T: label for modified time
				elif date == yesterday:
					text = _('Yesterday') + dt.strftime(' %H:%M')
					# T: label for modified time
				elif date.year == today.year:
					text = dt.strftime('%a %d %b %H:%M') # TODO allow config for format ?
				else:
					text = dt.strftime('%a %d %b, %Y %H:%M') # TODO allow config for format ?
			else:
				text = ''

			cell.set_property('text', text)

		cell_renderer = gtk.CellRendererText()
		#cell_renderer.set_property('font', 'mono')
		column = gtk.TreeViewColumn(_('Last Modified'), cell_renderer, text=self.MODIFIED_COL) # T: Column header
		column.set_cell_data_func(cell_renderer, render_date)
		column.set_sort_column_id(self.MODIFIED_COL)
		self.append_column(column)


		self.connect('row-activated', self._do_open_page)

	def _do_open_page(self, view, path, col):
		page = Path( self.get_model()[path][self.NAME_COL].decode('utf-8') )
		self.ui.open_page(page)

