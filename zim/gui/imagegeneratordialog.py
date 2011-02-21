# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import gtk
import logging

from zim.fs import *
from zim.gui.widgets import ui_environment, \
	Dialog, ImageView, Button, QuestionDialog, scrolled_text_view

logger = logging.getLogger('zim.gui')


class ImageGeneratorDialog(Dialog):
	'''Base class for use by plugins that generate and insert an image
	based on textual user input. This is used e.g. by the equation editor
	and similar plugins. The dialog provides text input and an image view
	for showing previews.
	'''

	# TODO: use uistate to remember pane position

	def __init__(self, ui, title, generator, image=None, **opt):
		if ui_environment['platform'] == 'maemo':
			defaultsize = (450,480)
			# Use maximum available vertical space because decorations take
			# too much real state
		else:
			defaultsize = (450,300)
		Dialog.__init__(self, ui, title, defaultwindowsize=defaultsize, **opt)
		if ui_environment['platform'] == 'maemo':
			self.resize(450,480)
			# Force maximum dialog size under maemo, otherwise
			# we'll end with a too small dialog and no way to resize it
		self.generator = generator
		self.imagefile = None
		self.logfile = None
		self._existing_file = None

		self.vpane = gtk.VPaned()
		self.vpane.set_position(150)
		self.vbox.add(self.vpane)

		self.imageview = ImageView(bgcolor='#FFF', checkboard=False)
		self.vpane.add1(self.imageview)
		# TODO scrolled window and option to zoom in / real size

		window, textview = scrolled_text_view(monospace=True)
		self.textview = textview
		self.textview.set_editable(True)
		self.vpane.add2(window)
		# TODO supply at least an Undo stack for this textview
		# or optionally subclass from gtksourceview

		hbox = gtk.HBox(spacing=5)
		self.vbox.pack_start(hbox, False)

		self.previewbutton = Button(_('_Preview'), stock='gtk-refresh')
			# T: button in e.g. equation editor dialog
		self.previewbutton.set_sensitive(False)
		self.previewbutton.connect_object(
			'clicked', self.__class__.preview, self)
		hbox.pack_start(self.previewbutton, False)

		self.textview.get_buffer().connect('modified-changed',
			lambda b: self.previewbutton.set_sensitive(b.get_modified()))

		self.logbutton = Button(_('View _Log'), stock='gtk-file')
			# T: button in e.g. equation editor dialog
		self.logbutton.set_sensitive(False)
		self.logbutton.connect_object(
			'clicked', self.__class__.show_log, self)
		hbox.pack_start(self.logbutton, False)

		if image:
			file = image['_src_file'] # FIXME ?
			textfile = self._stitch_fileextension(file, self.generator.basename)
			if file.exists() and textfile.exists():
				self._existing_file = textfile
				self.imageview.set_file(file)
				self.set_text(textfile.read())

		self.textview.grab_focus()

	def _stitch_fileextension(self, file, basename):
		'''Stitches the file extension from 'basename' to the path of 'file'
		and returns a File object.
		'''
		i = basename.rfind('.')
		j = file.path.rfind('.')
		return File(file.path[:j] + basename[i:])

	def set_text(self, text):
		buffer = self.textview.get_buffer()
		buffer.set_text(text)
		buffer.set_modified(False)

	def get_text(self):
		buffer = self.textview.get_buffer()
		bounds = buffer.get_bounds()
		return buffer.get_text(*bounds)

	def generate_image(self):
		self.imagefile = None
		self.logfile = None

		text = self.get_text()
		try:
			imagefile, logfile = self.generator.generate_image(text)
		except:
			logger.exception('Could not generate image')
				# TODO set "error" image instead of "broken" image
				# TODO set exception text as log message
		else:
			self.imagefile = imagefile
			self.logfile = logfile

		self.textview.get_buffer().set_modified(False)

	def preview(self):
		self.generate_image()
		self.imageview.set_file(self.imagefile) # if None sets broken image
		self.logbutton.set_sensitive(not self.logfile is None)

	def show_log(self):
		assert self.logfile, 'BUG: no logfile set (yet)'
		LogFileDialog(self, self.logfile).run()

	def do_response_ok(self):
		if not self.imagefile \
		or self.textview.get_buffer().get_modified():
			self.generate_image()

		if not (self.imagefile and self.imagefile.exists()):
			dialog = QuestionDialog(self,
				_('An error occured while generating the image.\nDo you want to save the source text anyway?'))
				# T: Question prompt when e.g. equation editor encountered an error genrating the image to insert
			if not dialog.run():
				return False

		if self._existing_file:
			textfile = self._existing_file
		else:
			page = self.ui.page
			dir = self.ui.notebook.get_attachments_dir(page)
			textfile = dir.new_file(self.generator.basename)

		imgfile = self._stitch_fileextension(textfile, self.imagefile.basename)

		textfile.write( self.get_text() )
		self.imagefile.rename(imgfile)

		if self._existing_file:
			self.ui.reload_page()
		else:
			pageview = self.ui.mainwindow.pageview
			pageview.insert_image(imgfile, type=self.generator.type, interactive=False)

		if self.logfile and self.logfile.exists():
			self.logfile.remove()

		return True

	def destroy(self):
		self.generator.cleanup()
		Dialog.destroy(self)


class LogFileDialog(Dialog):

	def __init__(self, ui, file):
		Dialog.__init__(self, ui, _('Log file'), buttons=gtk.BUTTONS_CLOSE)
			# T: dialog title for log view dialog - e.g. for Equation Editor
		self.set_default_size(600, 300)
		window, textview = scrolled_text_view(file.read(), monospace=True)
		self.vbox.add(window)
