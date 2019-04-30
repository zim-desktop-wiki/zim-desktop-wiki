
# Copyright 2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from gi.repository import Gtk
from gi.repository import GObject
import logging

import zim.datetimetz as datetime

from zim.notebook import Path
from zim.gui.widgets import Dialog, BrowserTreeView, ScrolledWindow


logger = logging.getLogger('zim.gui.dialogs')


class RecentChangesDialog(Dialog):

	def __init__(self, widget, notebook, navigation):
		Dialog.__init__(self, widget, _('Recent Changes'), # T: Dialog title
			buttons=Gtk.ButtonsType.CLOSE,
			defaultwindowsize=(400, 300)
		)
		self.notebook = notebook
		self.navigation = navigation

		self.treeview = RecentChangesTreeView()
		self.vbox.pack_start(ScrolledWindow(self.treeview), True, True, 0)
		self.treeview.connect('row-activated', self.on_row_activated)

		self.update()
		self.notebook.connect_after('stored-page', lambda *a: self.update())

	def update(self):
		model = self.treeview.get_model()
		if model is not None:
			model.clear()
			for rec in self.notebook.pages.list_recent_changes(limit=50):
				model.append((rec.name, rec.mtime))
		# else already destroyed ?

	def on_row_activated(self, view, path, col):
		page = Path(view.get_model()[path][view.NAME_COL])
		self.navigation.open_page(page)


class RecentChangesTreeView(BrowserTreeView):

	NAME_COL = 0
	MODIFIED_COL = 1

	def __init__(self):
		model = Gtk.ListStore(str, float)
			# NAME_COL, MODIFIED_COL
		BrowserTreeView.__init__(self, model)

		cell_renderer = Gtk.CellRendererText()

		column = Gtk.TreeViewColumn(_('Page'), cell_renderer, text=self.NAME_COL) # T: Column header
		column.set_sort_column_id(self.NAME_COL)
		column.set_expand(True)
		self.append_column(column)

		today = datetime.date.today()
		yesterday = today - datetime.timedelta(days=1)
		def render_date(col, cell, model, i, data):
			mtime = model.get_value(i, self.MODIFIED_COL)
			if mtime:
				dt = datetime.datetime.fromtimestamp(mtime)
				date = dt.date()
				if date == today:
					text = _('Today') + datetime.strftime(' %H:%M', dt)
					# T: label for modified time
				elif date == yesterday:
					text = _('Yesterday') + datetime.strftime(' %H:%M', dt)
					# T: label for modified time
				elif date.year == today.year:
					text = datetime.strftime('%a %d %b %H:%M', dt) # TODO allow config for format ?
				else:
					text = datetime.strftime('%a %d %b %Y %H:%M', dt) # TODO allow config for format ?
			else:
				text = ''

			cell.set_property('text', text)

		cell_renderer = Gtk.CellRendererText()
		#cell_renderer.set_property('font', 'mono')
		column = Gtk.TreeViewColumn(_('Last Modified'), cell_renderer) # T: Column header
		column.set_cell_data_func(cell_renderer, render_date)
		column.set_sort_column_id(self.MODIFIED_COL)
		self.append_column(column)
