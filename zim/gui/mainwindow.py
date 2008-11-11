# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import gtk

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
		# TODO side pane
		# TODO pathbar
		self.pageview = pageview.PageView()
		# TODO statusbar
		self.window.add(self.pageview.widget)

	def show(self):
		'''FIXME'''
		self.window.show_all()

	def destroy(self, widget, data=None):
		'''FIXME'''
		# really destructive
		gtk.main_quit()

	def do_open_page(self, app, page):
		'''FIXME'''
		self.pageview.set_page(page)

