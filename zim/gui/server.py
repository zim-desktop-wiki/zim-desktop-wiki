
# Copyright 2008,2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module stands apart from the rest of the gui modules as it is not
part from the main Gtk interface. It defines a Gtk interface that can be
used to start/stop the WWW server.
'''

# TODO: allow setting a password for public access to private server..

# TODO: expander or button to open the server log

# TODO: have url button show public hostname
#       commented out because while testing I got stuff like
#       "localhost6.localdomain6" which could not be resolved
#       by the browser :(


from gi.repository import Gtk
from gi.repository import GObject

import sys
import logging

from zim.www import make_server

from zim.notebook import build_notebook, NotebookInfo
from zim.templates import list_templates
from zim.config import data_file
from zim.gui.widgets import IconButton, ErrorDialog, input_table_factory
from zim.gui.notebookdialog import NotebookComboBox, NotebookDialog


logger = logging.getLogger('zim.gui.server')


class ServerWindow(Gtk.Window):

	def __init__(self, notebookinfo=None, template='Default', port=8080, public=True, config=None):
		'''Constructor
		@param notebookinfo: the notebook location
		@param template: html template for zim pages
		@param port: the http port to serve on
		@param public: allow connections to the server from other
		computers - if C{False} can only connect from localhost
		@param config: optional C{ConfigManager} object
		'''
		GObject.GObject.__init__(self)
		self.set_title('Zim - ' + _('Web Server')) # T: Window title
		self.set_border_width(10)
		self.template = template
		self.config = config
		self.httpd = None
		self._source_id = None

		# Widgets
		self.status_label = Gtk.Label()
		self.status_label.set_markup('<i>' + _('Server not started') + '</i>')
			# T: Status in web server gui
		self.start_button = IconButton('gtk-media-play')
		self.start_button.connect('clicked', lambda o: self.start())
		self.stop_button = IconButton('gtk-media-stop')
		self.stop_button.connect('clicked', lambda o: self.stop())
		self.stop_button.set_sensitive(False)

		self.link_button = Gtk.LinkButton('')
		self.link_button.set_sensitive(False)

		self.notebookcombobox = NotebookComboBox(current=notebookinfo)
		self.open_button = IconButton('gtk-index')
		self.open_button.connect('clicked', lambda *a: NotebookDialog(self).run())

		self.templatecombobox = TemplateComboBox()
		self.templatecombobox.set_template(template)

		self.portentry = Gtk.SpinButton()
		self.portentry.set_numeric(True)
		self.portentry.set_range(80, 10000)
		self.portentry.set_increments(1, 80)
		self.portentry.set_value(port)

		self.public_checkbox = Gtk.CheckButton.new_with_mnemonic(_('Allow public access'))
			# T: Checkbox in web server gui
		self.public_checkbox.set_active(public)


		# Build the interface
		vbox = Gtk.VBox()
		self.add(vbox)

		hbox = Gtk.HBox(spacing=12)
		hbox.pack_start(self.start_button, False, True, 0)
		hbox.pack_start(self.stop_button, False, True, 0)
		hbox.pack_start(self.status_label, False, True, 0)
		vbox.pack_start(hbox, False, False, 0)

		table = input_table_factory((
			(_('Notebook'), self.notebookcombobox, self.open_button),
				# T: Field in web server gui
			(_('Template'), self.templatecombobox),
				# T: Field in web server gui for template selection
			(_('Port'), self.portentry),
				# T: Field in web server gui for HTTP port (e.g. port 80)
			self.public_checkbox
		))
		vbox.pack_start(table, False, False, 0)

		if self.link_button:
			hbox = Gtk.HBox()
			hbox.pack_end(self.link_button, False, True, 0)
			vbox.pack_start(hbox, False, False, 0)


	def open_notebook(self, notebook):
		'''Sets the notebook in the combobox

		This method is called by the NotebookDialog when a notebook is opened.
		'''
		self.notebookcombobox.set_notebook(notebook)

	def start(self):
		# Start server
		try:
			uri = self.notebookcombobox.get_notebook()
			if uri:
				notebook, x = build_notebook(NotebookInfo(uri))
				if not notebook:
					return
			else:
				return

			if not notebook.index.is_uptodate:
				for info in notebook.index.update_iter():
					#logger.info('Indexing %s', info)
					pass # TODO meaningful info for above message

			template = self.templatecombobox.get_template()
			port = int(self.portentry.get_value())
			public = self.public_checkbox.get_active()
			config = self.config
			self.httpd = make_server(notebook, template, port, public, config)
			if sys.platform == 'win32':
				# GObject io watch conflicts with socket use on windows..
				# idle handler uses a bit to much CPU for my taste,
				# timeout every 0.5 sec is better
				self.httpd.timeout = 0.1 # 100 ms
				self._source_id = GObject.timeout_add(500, self.do_serve_on_poll)
			else:
				self.httpd.timeout = 3 # if no response after 3 sec, drop it
				self._source_id = GObject.io_add_watch(
					self.httpd.fileno(),
					GObject.IO_IN | GObject.IO_OUT | GObject.IO_ERR | GObject.IO_HUP | GObject.IO_PRI, # any event..
					self.do_serve_on_io
				)
			logger.info("Serving HTTP on %s port %i...", self.httpd.server_name, self.httpd.server_port)
		except Exception as error:
			ErrorDialog(self, error).run()
			return

		# Update UI
		self.notebookcombobox.set_sensitive(False)
		self.templatecombobox.set_sensitive(False)
		self.portentry.set_sensitive(False)
		self.public_checkbox.set_sensitive(False)
		self.open_button.set_sensitive(False)
		self.start_button.set_sensitive(False)
		self.stop_button.set_sensitive(True)

		self.status_label.set_markup('<i>' + _('Server started') + '</i>')
			# T: Status in web server gui
		#if self.public_checkbox.get_active():
		#	url = 'http://%s:%i' % (self.httpd.server_name, self.httpd.server_port)
		#else:
		#	url = 'http://localhost:%i' % self.httpd.server_port
		url = 'http://localhost:%i' % self.httpd.server_port
		if self.link_button:
			self.link_button.set_uri(url)
			self.link_button.set_label(url)
			self.link_button.set_sensitive(True)

	def do_serve_on_io(self, fd, event):
		try:
			if event & GObject.IO_HUP:
				self.stop()
				raise Exception('Socket disconnected')
			else:
				self.httpd.handle_request()
		except:
			logger.exception('Exception while handling IO request:')

		return True # keep event running

	def do_serve_on_poll(self):
		self.httpd.handle_request()
		return True # keep event running

	def stop(self):
		# Stop server
		logger.debug('Stop server')
		if self._source_id is not None:
			GObject.source_remove(self._source_id)
			self._source_id = None

		if self.httpd:
			self.httpd.socket.close()
				# There is also a httpd.server_close(), but undocumented (!?)
			self.httpd = None

		# Update UI
		self.status_label.set_markup('<i>' + _('Server stopped') + '</i>')
			# T: Status in web server gui
		if self.link_button:
			self.link_button.set_sensitive(False)
		self.notebookcombobox.set_sensitive(True)
		self.templatecombobox.set_sensitive(True)
		self.portentry.set_sensitive(True)
		self.public_checkbox.set_sensitive(True)
		self.open_button.set_sensitive(True)
		self.stop_button.set_sensitive(False)
		self.start_button.set_sensitive(True)

class TemplateComboBox(Gtk.ComboBox):
	'''Combobox showing a list of templates'''

	def __init__(self):
		'''Constructor
		'''
		templates = [t[0] for t in list_templates('html')]
		template_store = Gtk.ListStore(str)
		for template in templates:
			template_store.append([template])
		model = template_store

		GObject.GObject.__init__(self)
		self.set_model(model)
		cell_renderer = Gtk.CellRendererText()
		self.pack_start(cell_renderer, True)
		self.add_attribute(cell_renderer, 'text', 0)
		self.set_active(0)

	def set_template(self, template):
		'''Select a specific template in the combobox.
		@param template: html template for zim pages as string
		'''
		template_store = self.get_model()

		for idx, row in enumerate(template_store):
			if row[0] == template:
				self.set_active(idx)
				break

	def get_template(self):
		'''Returns the name for the current selected template'''
		iter = self.get_active()
		if iter == -1:
			return None
		else:
			model = self.get_model()
			return model[iter][0]

def main(notebookinfo=None, template='Default', port=8080, public=True, config=None):
	from zim.widgets import gtk_window_set_default_icon
	gtk_window_set_default_icon()
	window = ServerWindow(notebookinfo, template, port, public, config)
	window.show_all()
	Gtk.main()
