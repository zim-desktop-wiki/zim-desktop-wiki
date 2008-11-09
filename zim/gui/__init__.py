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

	def __init__(self):
		'''FIXME'''
		Application.__init__(self)
		self.mainwindow = mainwindow.MainWindow(self)

	def main(self):
		'''FIXME'''
		self.mainwindow.show()
		gtk.main()

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
