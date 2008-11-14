# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import gobject
import gtk

from zim import Application
from zim.utils import data_file

def debug(msg):
	print '# '+msg

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
		self.window = None

		# set default icon for all windows
		icon = data_file('zim.png').path
		gtk.window_set_default_icon(gtk.gdk.pixbuf_new_from_file(icon))

	def main(self):
		'''FIXME'''
		if self.notebook is None:
			debug('No notebook given, starting notebookdialog')
			import notebookdialog
			notebookdialog.NotebookDialog(self).run()
			# notebookdialog should trigger open_notebook()

		if self.notebook is None:
			# Close application. Either the user cancelled the notebook dialog,
			# or the notebook was opened in a different process.
			return

		self.mainwindow.show()
		gtk.main()

	def do_open_notebook(self, notebook):
		'''FIXME'''
		self.notebook = notebook

		# construct main window to show this notebook
		import mainwindow
		self.mainwindow = mainwindow.MainWindow(self)
		self.window = self.mainwindow.window

		# TODO load history and set intial page
		self.open_page(notebook.get_home_page())

	def open_page(self, page):
		'''FIXME'''
		assert self.notebook
		if isinstance(page, basestring):
			debug('Open page: %s' % page)
			page = self.notebook.get_page(page)
		else:
			debug('Open page: %s (object)' % page.name)
		self.emit('open-page', page)

	def do_open_page(self, page):
		'''FIXME'''
		self.page = page

# Need to register classes defining gobject signals
gobject.type_register(GtkApplication)
