#!/usr/bin/python

import pygtk
import gtk

class HelloWorld:

	def __init__(s):
		s.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
		s.window.connect("destroy", s.destroy)
		s.window.set_border_width(10)
		b = gtk.Button("hello world")
		b.connect('clicked', s.hello, None)
		s.window.add(b)
		s.window.show_all()

	def main(self):
		print "bar"
		gtk.main()

	def destroy(self, widget, data=None):
		"""window is being destroyed"""
		# really destructive
		gtk.main_quit()

	def hello (self, widget, data=None):
		import test_import
		print "Hello World"
		print test_import.foo

if __name__ == '__main__':
	hello = HelloWorld()
	print "fooo"
	hello.main()
