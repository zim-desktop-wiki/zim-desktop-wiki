# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module stands apart from the rest of the gui modules as it is not
part from the main Gtk interface. It defines a Gtk interface that can be
used to start/stop the WWW server.
'''

import gtk
import webbrowser # FIXME replace with XDG aware method

from zim.config import data_file
from zim.gui.widgets import IconButton, gtk_window_set_default_icon, ErrorDialog
from zim.gui.notebookdialog import NotebookComboBox, NotebookDialog

stock_started = ('gtk-yes', gtk.ICON_SIZE_DIALOG)
stock_stopped = ('gtk-no', gtk.ICON_SIZE_DIALOG)

class ServerWindow(gtk.Window):

	def __init__(self, server):
		'''Constructor needs a Server object to control'''
		gtk.Window.__init__(self)
		gtk_window_set_default_icon() # FIXME - should go in main
		self.set_border_width(10)
		self.connect('destroy', lambda a: gtk.main_quit())

		self.server = server
		self.server.connect_after('started', self.do_server_started)
		self.server.connect_after('stopped', self.do_server_stopped)

		def _start(*a):
			try:
				self.server.set_notebook(
					self.notebookcombobox.get_notebook() )
				self.server.start()
			except Exception, error:
				ErrorDialog(self, error).run()

		def _stop(*a):
			try:
				self.server.stop()
			except Exception, error:
				ErrorDialog(self, error).run()

		# Build the interface
		vbox = gtk.VBox()
		self.add(vbox)

		# first some art work
		#~ path = data_file('globe_banner_small.png').path
		#~ image = gtk.Image()
		#~ image.set_from_file(path) # new_from_file not in 2.6
		#~ align = gtk.Alignment(0,0.5, 0,0)
		#~ align.add(image)
		#~ vbox.add(align)

		# Table with status
		table = gtk.Table(4, 2, False)
		table.set_col_spacings(12)
		table.set_row_spacings(5)
		hbox = gtk.HBox()
		hbox.pack_start(table, False)
		vbox.pack_start(hbox, False)

		self.status_icon = gtk.image_new_from_stock(*stock_stopped)
		table.attach(self.status_icon, 0,2, 0,2)
		self.status_label = gtk.Label()
		self.status_label.set_markup('<i>'+_('Server not started')+'</i>')
			# T: Status in web server gui
		table.attach(self.status_label, 4,5, 0,1)
		self.link_button = gtk.LinkButton('') # FIXME since 2.10
		self.link_button.set_sensitive(False)
		gtk.link_button_set_uri_hook(lambda o, url: webbrowser.open(url))
		table.attach(self.link_button, 4,5, 1,2)

		start_button = IconButton('gtk-media-play')
		start_button.connect('clicked', _start)
		table.attach(start_button, 2,3, 0,1)
		stop_button = IconButton('gtk-media-stop')
		stop_button.connect('clicked', _stop)
		table.attach(stop_button, 3,4, 0,1)

		# Table with server properties
		table = gtk.Table(3, 3, False)
		table.set_col_spacings(12)
		table.set_row_spacings(5)
		vbox.add(table)

		table.attach(gtk.Label(_('Notebook')+': '), 0,1, 0,1)
			# T: Field in web server gui
		self.notebookcombobox = NotebookComboBox(current=server.interface.notebook)
		self.notebookcombobox.connect('changed', _stop)
		table.attach(self.notebookcombobox, 1,2, 0,1)

		open_button = IconButton('gtk-index')
		open_button.connect('clicked', lambda *a: NotebookDialog(self).run())
		table.attach(open_button, 2,3, 0,1)

		table.attach(gtk.Label(_('Port')+': '), 0,1, 1,2)
			# T: Field in web server gui for HTTLP port (e.g. port 80)
		self.portentry = gtk.SpinButton()
		self.portentry.set_numeric(True)
		self.portentry.set_range(80, 10000)
		self.portentry.set_increments(1, 80)
		self.portentry.set_value(self.server.port)
		self.portentry.connect('value-changed', _stop)
		self.portentry.connect('value-changed',
			lambda o: self.server.set_port(self.portentry.get_value_as_int()))
		table.attach(self.portentry, 1,2, 1,2)

		# TODO: expander or button to open the server log

	def open_notebook(self, notebook):
		'''Sets the notebook in the combobox

		This method is called by the NotebookDialog when a notebook is opened.
		'''
		self.notebookcombobox.set_notebook(notebook)

	def do_server_started(self, server):
		self.status_icon.set_from_stock(*stock_started)
		self.status_label.set_markup('<i>'+_('Server started')+'</i>')
			# T: Status in web server gui
		url = 'http://localhost:%i' % server.port
		self.link_button.set_uri(url)
		self.link_button.set_label(url)
		self.link_button.set_sensitive(True)

	def do_server_stopped(self, server):
		self.status_icon.set_from_stock(*stock_stopped)
		self.status_label.set_markup('<i>'+_('Server stopped')+'</i>')
			# T: Status in web server gui
		self.link_button.set_sensitive(False)
