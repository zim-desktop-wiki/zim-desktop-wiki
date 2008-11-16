# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import gtk

from zim import Application, Component
from zim.utils import data_file
from zim.gui import gtkutils

class GtkWWWAplication(Application):
	'''FIXME'''

	def __init__(self, **opts):
		# FIXME proper way would be to filter out server options and pass on the dict
		Application.__init__(self, executable=opts['executable'])

	def main(self):
		'''FIXME'''
		self.mainwindow = MainWindow(self)
		self.mainwindow.show_all()
		gtk.main()


class MainWindow(gtk.Window, Component):
	'''FIXME'''

	def __init__(self, app):
		gtk.Window.__init__(self)

		vbox = gtk.VBox()
		self.add(vbox)

		path = data_file('globe_banner_small.png').path
		image = gtk.image_new_from_file(path)
		align = gtk.Alignment(0,0.5, 0,0)
		align.add(image)
		vbox.add(align)

		# Table with server properties
		table = gtk.Table(3, 3, False)
		table.set_col_spacings(12)
		table.set_row_spacings(5)
		vbox.add(table)

		table.attach(gtk.Label('Notebook:'), 0,1, 0,1)
		table.attach(gtk.Label('Port:'), 0,1, 1,2)
		table.attach(gtk.ComboBox(), 1,2, 0,1)
		table.attach(gtk.Label('TODO: open editor button'), 2,3, 0,1)
		table.attach(gtk.Entry(), 1,2, 1,2)

		# Start / stop button and status
		hbox = gtk.HBox(spacing=12)
		vbox.add(hbox)
		vbox.add(gtk.Label('TODO: start / stop buttons'))

		start_button = gtkutils.icon_button('gtk-media-play')
		stop_button = gtkutils.icon_button('gtk-media-stop')
		hbox.pack_start(start_button, False)
		hbox.pack_start(stop_button, False)

		icon = gtk.image_new_from_stock('gtk-yes', gtk.ICON_SIZE_BUTTON)
		hbox.pack_start(icon, False)
		hbox.add(gtk.Label('<b><server status></b>'))

		vbox.add(gtk.Label('TODO: open browser button'))
		vbox.add(gtk.Label('TODO: expander for server log'))
