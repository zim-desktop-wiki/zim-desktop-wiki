# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import gobject
import gtk

from zim import Application
import mainwindow

class GtkApplication(Application):
	'''FIXME'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'open-page': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE,
			(gobject.TYPE_PYOBJECT,) ),
	}

	def __init__(self, **opts):
		'''FIXME'''
		Application.__init__(self, **opts)
		self.mainwindow = mainwindow.MainWindow(self)

	def main(self):
		'''FIXME'''
		# TODO run NotebookDialog first if no notebook defined
		self.mainwindow.show()
		gtk.main()

	def do_open_notebook(self, notebook):
		'''FIXME'''
		self.notebook = notebook
		# TODO load history and set intial page

	def open_page(self, pagename):
		'''FIXME'''
		assert self.notebook
		page = self.notebook.get_page(pagename)
		self.emit('open-page', page)

	def do_open_page(self, page):
		'''FIXME'''
		self.page = page

# Need to register classes defining gobject signals
gobject.type_register(GtkApplication)
