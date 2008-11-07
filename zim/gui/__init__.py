# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

from zim import Application

import mainwindow

class GtkApplication(Application):
	'''FIXME'''

	def __init__(self):
		self.notebook = None

	def main(self):
		gtk.main()

	def open_notebook(self, notebook=None):
		if notebook is None:
			# Run notebookdialog
			pass
		if self.notebook is None:
			self.notebook = notebook
			self.main()
		# elif daemon call daemon
		# else exec new process
