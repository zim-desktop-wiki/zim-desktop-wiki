# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains the base classes used by all plugins that
create an image from text based input. Like the equation editor, the
diagram editor etc. There is a class for the edit dialog that is used
for images that are inserted with an object type, and there is a base
class for the generators that implement specific translations from
text to an image.
'''


import gtk
import logging

from zim.fs import File, Dir
from zim.gui.widgets import ui_environment, \
	Dialog, ImageView, Button, QuestionDialog, \
	ScrolledTextView, ScrolledSourceView, VPaned

logger = logging.getLogger('zim.gui')


class ImageGeneratorClass(object):
	'''Base class for image generators which can be used by the
	L{ImageGeneratorDialog}
	'''

	uses_log_file = True #: set to C{False} for subclasses that do not generate a log

	type = None #: generator type, e.g. "equation"
	scriptname = None #: basename of the source files, e.g. "equation.tex"
	imagename = None #: basename of the resulting image files, e.g. "equation.png"

	def generate_image(self, text):
		'''Generate an image for a user input

		This is the method that does the actual work to generate an
		image out of input text. Typically it will write the text to
		a temporary file using a template and then call an external
		program (e.g. latex) to create an image out of that source
		file. The result should be an image file and optionally a
		log file.

		When the external program failed preferably this method should
		still return a log file, so the user can check the details of
		why the creation failed.

		@param text: the source text as string - raw user input
		@returns: a 2-tuple of the image file and the log file as
		L{File} objects. If no image file was created the first
		element should be C{None}, if no log file is created second
		element should be C{None}.

		@implementation: must be implemented by subclasses
		'''
		raise NotImplemented

	def process_input(self, text):
		'''Process user input before generating image

		This method is used to post-process user input before
		generating image and writing the user input into the script
		file.

		@param text: the source text as string - raw user input
		@returns: string used for generate_image, also the string
		written to script file.

		@implementation: Not mandatory to be implemented by subclass.
		It defaults to user input.
		'''
		return text

	def filter_input(self, text):
		'''Filter contents of script file before displaying in textarea

		This method is used to pre-process contents of script file
		before displaying in textarea.

		@param text: the contents of script file
		@returns: string used to display for user input.

		@implementation: Not mandatory to be implemented by subclass.
		It defaults to script file contents.
		'''
		return text

	def cleanup(self):
		'''Cleanup any temporary files that were created by this
		generator. Including log files and image files.

		@implementation: should be implemented by subclasses
		'''
		pass


class ImageGeneratorDialog(Dialog):
	'''Base class for use by plugins that generate and insert an image
	based on textual user input. This is used e.g. by the equation editor
	and similar plugins. The dialog provides text input and an image view
	for showing previews.
	'''

	# TODO: use uistate to remember pane position

	def __init__(self, ui, title, generator, image=None, syntax=None, **opt):
		'''Constructor

		@param ui: L{GtkInterface} object or parent window
		@param title: the dialog title
		@param generator: an L{ImageGeneratorClass} object
		@param image: image data for an image in the
		L{TextBuffer<zim.gui.pageview.TextBuffer>}
		@param syntax: optional syntax name (as understood by gtksourceview)
		@param opt: any other arguments to pass to the L{Dialog} constructor
		'''
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

		self.vpane = VPaned()
		self.vpane.set_position(150)
		self.vbox.add(self.vpane)

		self.imageview = ImageView(bgcolor='#FFF', checkerboard=False)
		self.vpane.pack1(self.imageview, resize=True)
		# TODO scrolled window and option to zoom in / real size

		window, textview = ScrolledSourceView(syntax=syntax)
		self.textview = textview
		self.textview.set_editable(True)
		self.vpane.pack2(window, resize=False)

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
		if generator.uses_log_file:
			hbox.pack_start(self.logbutton, False)
		# else keep hidden

		self._existing_file = None
		if image:
			file = image['_src_file'] # FIXME ?
			textfile = self._stitch_fileextension(file, self.generator.scriptname)
			self._existing_file = textfile
			self.imageview.set_file(file)
			self.set_text(self.generator.filter_input(textfile.read()))

		self.textview.grab_focus()

	def _stitch_fileextension(self, file, basename):
		'''Stitches the file extension from 'basename' to the path of 'file'
		and returns a File object.
		'''
		i = basename.rfind('.')
		j = file.path.rfind('.')
		return File(file.path[:j] + basename[i:])

	def set_text(self, text):
		'''Set text in the buffer'''
		buffer = self.textview.get_buffer()
		buffer.set_text(text)
		buffer.set_modified(False)

	def get_text(self):
		'''Get the text from the buffer

		@returns: text as string
		'''
		buffer = self.textview.get_buffer()
		bounds = buffer.get_bounds()
		return buffer.get_text(*bounds)

	def generate_image(self):
		'''Update the image based on the text in the text buffer'''
		self.imagefile = None
		self.logfile = None

		text = self.get_text()
		text = self.generator.process_input(text)
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
		'''Action for the "Preview" button'''
		self.generate_image()
		self.imageview.set_file(self.imagefile) # if None sets broken image
		self.logbutton.set_sensitive(not self.logfile is None)

	def show_log(self):
		'''Action for the "View Log" button'''
		assert self.logfile, 'BUG: no logfile set (yet)'
		LogFileDialog(self, self.logfile).run()

	def do_response_ok(self):
		if not self.imagefile \
		or self.textview.get_buffer().get_modified():
			self.generate_image()

		if not (self.imagefile and self.imagefile.exists()):
			dialog = QuestionDialog(self,
				_('An error occurred while generating the image.\nDo you want to save the source text anyway?'))
				# T: Question prompt when e.g. equation editor encountered an error generating the image to insert
			if not dialog.run():
				return False

		if self._existing_file:
			textfile = self._existing_file
		else:
			page = self.ui.page
			dir = self.ui.notebook.get_attachments_dir(page)
			textfile = dir.new_file(self.generator.scriptname)

		textfile.write( self.generator.process_input(self.get_text()) )

		imgfile = self._stitch_fileextension(textfile, self.generator.imagename)
		if self.imagefile and self.imagefile.exists():
			self.imagefile.rename(imgfile)
		elif imgfile.exists():
			imgfile.remove()

		if self._existing_file:
			self.ui.reload_page()
		else:
			pageview = self.ui.mainwindow.pageview
			pageview.insert_image(imgfile, type=self.generator.type, interactive=False, force=True)

		if self.logfile and self.logfile.exists():
			self.logfile.remove()

		return True

	def destroy(self):
		self.generator.cleanup()
		Dialog.destroy(self)


class LogFileDialog(Dialog):
	'''Simple dialog to show the log file'''

	def __init__(self, ui, file):
		Dialog.__init__(self, ui, _('Log file'), buttons=gtk.BUTTONS_CLOSE)
			# T: dialog title for log view dialog - e.g. for Equation Editor
		self.set_default_size(600, 300)
		window, textview = ScrolledTextView(file.read(), monospace=True)
		self.vbox.add(window)
