# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import gtk

class MainWindow(object):
	'''FIXME'''

	def __init__(self):
		self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
		self.window.connect("destroy", self.destroy)
		self.window.set_border_width(10)
		b = gtk.Button("hello world")
		b.connect('clicked', s.hello, None)
		self.window.add(b)
		self.window.show_all()

	def destroy(self, widget, data=None):
		"""window is being destroyed"""
		# really destructive
		gtk.main_quit()

	def hello (self, widget, data=None):
		print "Hello World"
