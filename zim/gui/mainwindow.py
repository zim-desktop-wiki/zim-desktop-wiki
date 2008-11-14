# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import gtk

import pageindex
import pageview

class MainWindow(object):
	'''FIXME'''

	def __init__(self, app):
		'''FIXME'''
		self.app = app
		app.connect('open-page', self.do_open_page)

		self.window = gtk.Window()
		self.window.set_default_size(500, 500)
		self.window.connect("destroy", self.destroy)
		# TODO menubar and toolbar
		hpane = gtk.HPaned()
		self.window.add(hpane)
		self.pageindex = pageindex.PageIndex()
		hpane.add1(self.pageindex)
		# TODO pathbar
		self.pageview = pageview.PageView()
		hpane.add2(self.pageview)
		# TODO statusbar

		self.pageindex.connect('page-activated',
			lambda index, pagename: self.app.open_page(pagename) )

	def show(self):
		'''FIXME'''
		self.pageindex.set_pages( self.app.notebook.get_root() )
		self.window.show_all()

	def destroy(self, widget, data=None):
		'''FIXME'''
		# really destructive
		gtk.main_quit()

	def do_open_page(self, app, page):
		'''FIXME'''
		self.pageview.set_page(page)

