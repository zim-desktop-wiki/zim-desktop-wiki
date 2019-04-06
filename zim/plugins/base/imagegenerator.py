
# Copyright 2009-2019 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains the base classes used by all plugins that
create an image from text based input. Like the equation editor, the
diagram editor etc.
'''

import logging

logger = logging.getLogger('zim.plugins')

from gi.repository import Gtk

from zim.plugins import PluginClass, InsertedObjectTypeExtension
from zim.signals import SignalEmitter, SIGNAL_RUN_FIRST
from zim.config import String
from zim.errors import show_error, Error
from zim.applications import ApplicationError
from zim.fs import File, Dir
from zim.formats import IMAGE

from zim.gui.widgets import \
	Dialog, ImageView, QuestionDialog, LogFileDialog, \
	ScrolledWindow, ScrolledTextView, ScrolledSourceView, VPaned, \
	populate_popup_add_separator
from zim.gui.insertedobjects import ImageFileWidget


class ImageGeneratorObjectType(InsertedObjectTypeExtension):
	'''Base class for object types that produce an image based on text input
	from the user.
	Plugins should contain a sub-class of of this class to define the object
	type name, label etc. It then will automatically load a sub-class from
	ImageGeneratorClass defined in the same plugin to do the work.
	'''

	syntax = None

	def __init__(self, plugin, objmap):
		generators = list(plugin.discover_classes(ImageGeneratorClass))
		assert len(generators) == 1, 'Expect exactly one subclass of ImageGeneratorClass in plugin'
		self.generator_klass = generators[0]
		InsertedObjectTypeExtension.__init__(self, plugin, objmap)
			# Don't call this before above initialization is done,
			# else we trigger InsertedObjectTypeMap "changed" before we are
			# ready to go

	def new_model_interactive(self, parent, notebook, page):
		attrib, data = self.new_object()
		model = self.model_from_data(notebook, page, attrib, data)
		ImageGeneratorDialog.run_dialog_for_model(parent, model, self.label, self.syntax)
		return model

	def model_from_data(self, notebook, page, attrib, data):
		generator = self.generator_klass(self.plugin, notebook, page)
		return ImageGeneratorModel(notebook, page, generator, attrib, data)

	def data_from_model(self, model):
		return model.attrib, model.data

	def create_widget(self, model):
		return ImageGeneratorWidget(model, self.label, self.syntax)


class BackwardImageGeneratorObjectType(ImageGeneratorObjectType):
	'''Base class for backward compatible image generator objects.'''

	object_attr = {
		'src': String('_new_'),
	}

	scriptname = None
	imagefile_extension = None

	def model_from_data(self, notebook, page, attrib, data):
		generator = self.generator_klass(self.plugin, notebook, page)
		return BackwardImageGeneratorModel(notebook, page, generator, attrib, data, self.scriptname, self.imagefile_extension)

	def format(self, format, dumper, attrib, data):
		if data:
			logger.warn('Unexpected data in %s object: %r', attrib['type'], data)

		try:
			return ImageGeneratorObjectType.format(self, format, dumper, attrib, data)
		except ValueError:
			if attrib['type'].startswith('image+'):
				attrib = attrib.copy()
				attrib['type'] = attrib['type'][6:]
			return dumper.dump_img(IMAGE, attrib, None)


class ImageGeneratorModel(SignalEmitter):

	__signals__ = {'changed': (SIGNAL_RUN_FIRST, None, ())}

	def __init__(self, notebook, page, generator, attrib, data):
		self.notebook = notebook
		self.page = page
		self.generator = generator
		self.attrib = attrib
		self.data = data

	def get_text(self):
		raise NotImplementedError

	def set_from_generator(self, text, image_file):
		raise NotImplementedError


class BackwardImageGeneratorModel(ImageGeneratorModel):

	def __init__(self, notebook, page, generator, attrib, data, scriptname, imagefile_extension):
		ImageGeneratorModel.__init__(self, notebook, page, generator, attrib, data)
		if attrib['src'] and not attrib['src'] == '_new_':
			# File give, derive script
			self.image_file = notebook.resolve_file(attrib['src'], page)
			self.script_file = self._stitch_fileextension(self.image_file, scriptname)
		else:
			# Find available combo of script and image files
			def check_image_file(new_script_file):
				new_image_file = self._stitch_fileextension(new_script_file, imagefile_extension)
				return not new_image_file.exists()

			folder = notebook.get_attachments_dir(page)
			self.script_file = folder.new_file(scriptname, check_image_file)
			self.image_file = self._stitch_fileextension(self.script_file, imagefile_extension)
			self.attrib['src'] = './' + self.image_file.basename

	def _stitch_fileextension(self, file, basename):
		# Take extension of basename, and put it on path from file
		i = basename.rfind('.')
		j = file.path.rfind('.')
		return File(file.path[:j] + basename[i:])

	def get_text(self):
		if self.image_file is not None and self.script_file.exists():
			text = self.script_file.read()
		else:
			text = self.generator.get_default_text()

		return self.generator.filter_source(text)

	def set_from_generator(self, text, image_file):
		self.script_file.write(text)
		if image_file == self.image_file:
			pass
		elif image_file and image_file.exists():
			image_file.rename(self.image_file)
		elif self.image_file.exists():
			self.image_file.remove()
		self.emit('changed')


class ImageGeneratorClass(object):
	'''Base class for image generators.
	A plugin defining an L{ImageGeneratorObjectType} should also define a
	sub-class of this class to do the actual work.

	The generator does the actual work to generate an image from text. It does
	this in a temporary folder and must not try to directly modify the page or
	store anything in the attachements folder. The reason is that the user can
	still press "cancel" after the generator has run. The model takes care of
	storing the image and the text in the right place.

	Since the content of the image can depent on the notebook location, a
	generator object is specific for a notebook page.
	'''

	def __init__(self, plugin, notebook, page):
		self.plugin = plugin
		self.notebook = notebook
		self.page = page

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
		@raises Error: this method is allowed to raise errors like
		L{ApplicationError} when running a command failed.

		@implementation: must be implemented by subclasses
		'''
		raise NotImplemented

	def check_user_input(self, text):
		'''Check user input before generating image

		This method is used to post-process user input before
		generating image and writing the user input into the script
		file.

		@param text: the source text as string - raw user input
		@returns: string used for generate_image, also the string
		written to script file.

		@implementation: Not mandatory to be implemented by a subclass.
		It defaults to user input.
		'''
		return text

	def get_default_text(self):
		'''Provides a template or starting point for the user to begin editing.

		@implementation: Not mandatory to be implemented by a subclass.
		It defaults to the empty string.
		'''
		return ''

	def filter_source(self, text):
		'''Filter contents of script file before displaying in textarea

		This method is used to pre-process contents of script file
		before displaying in textarea.

		@param text: the contents of script file
		@returns: string used to display for user input.

		@implementation: Not mandatory to be implemented by a subclass.
		It defaults to script file contents.
		'''
		return text

	def cleanup(self):
		'''Cleanup any temporary files that were created by this
		generator. Including log files and image files.

		@implementation: should be implemented by subclasses
		'''
		pass


class ImageGeneratorWidget(ImageFileWidget):

	def __init__(self, model, label, syntax=None):
		ImageFileWidget.__init__(self, model.image_file)
		self.model = model
		self.label = label
		self.syntax = syntax
		self.model.connect('changed', self.on_model_changed)

	def on_model_changed(self, model):
		self.set_file(model.image_file)

	def populate_popup(self, menu):
		item = Gtk.MenuItem.new_with_mnemonic(_('_Edit...')) # T: context menu for inserted objects
		item.connect('activate', lambda o: self.edit_object())
		menu.append(item)

	def edit_object(self):
		ImageGeneratorDialog.run_dialog_for_model(self, self.model, self.label, self.syntax)


class ImageGeneratorDialog(Dialog):
	'''Dialog that provides text input and an image view
	for showing previews for an L{ImageGeneratorClass} implementation.
	'''

	@classmethod
	def run_dialog_for_model(cls, widget, model, label, syntax):
		text, image_file = cls(
			widget,
			label,
			model.generator,
			model.image_file,
			model.get_text(),
			syntax
		).run()
		if text is not None:
			model.set_from_generator(text, image_file)
		model.generator.cleanup()

	def __init__(self, widget, label, generator, image_file=None, text='', syntax=None):
		title = _('Edit %s') % label # T: dialog title, %s is the object name like "Equation"
		Dialog.__init__(self, widget, title, defaultwindowsize=(450, 300))
		self.generator = generator
		self.log_file = None
		self.image_file = image_file
		self.result = None, None

		self.vpane = VPaned()
		self.vpane.set_position(150)
		self.vbox.pack_start(self.vpane, True, True, 0)

		self.imageview = ImageView(bgcolor='#FFF')
		swin = ScrolledWindow(self.imageview)
		swin.set_size_request(200, 50)
		self.vpane.pack1(swin, resize=True)
		# TODO scrolled window and option to zoom in / real size

		window, textview = ScrolledSourceView(syntax=syntax)
		self.textview = textview
		self.textview.set_editable(True)
		self.vpane.pack2(window, resize=False)

		hbox = Gtk.HBox(spacing=5)
		self.vbox.pack_start(hbox, False, True, 0)

		self.previewbutton = Gtk.Button.new_with_mnemonic(_('_Preview'))
			# T: button in e.g. equation editor dialog
		self.previewbutton.set_sensitive(False)
		self.previewbutton.connect('clicked', lambda o: self.update_image())
		hbox.pack_start(self.previewbutton, False, True, 0)

		self.textview.get_buffer().connect('modified-changed',
			lambda b: self.previewbutton.set_sensitive(b.get_modified()))

		self.logbutton = Gtk.Button.new_with_mnemonic(_('View _Log'))
			# T: button in e.g. equation editor dialog
		self.logbutton.set_sensitive(False)
		self.logbutton.connect('clicked', lambda o: self.show_log())
		hbox.pack_start(self.logbutton, False, True, 0)

		self.set_text(text)
		self.imageview.set_file(self.image_file) # if None sets broken image
		self.textview.grab_focus()

	def set_text(self, text):
		buffer = self.textview.get_buffer()
		buffer.set_text(text)
		buffer.set_modified(False)

	def get_text(self):
		buffer = self.textview.get_buffer()
		start, end = buffer.get_bounds()
		text = start.get_text(end)
		return self.generator.check_user_input(text)

	def update_image(self):
		text = self.get_text()

		try:
			self.image_file, self.log_file = self.generator.generate_image(text)
		except Error as error:
			self.image_file, self.log_file = None, None
			show_error(error)

		self.textview.get_buffer().set_modified(False)
		self.imageview.set_file(self.image_file) # if None sets broken image
		self.logbutton.set_sensitive(self.log_file is not None)

	def show_log(self):
		assert self.logfile, 'BUG: no logfile set (yet)'
		LogFileDialog(self, self.logfile).run()

	def do_response_ok(self):
		buffer = self.textview.get_buffer()
		if buffer.get_modified():
			self.update_image()

		if not (self.image_file and self.image_file.exists()):
			dialog = QuestionDialog(self,
					_('An error occurred while generating the image.\nDo you want to save the source text anyway?'))
					# T: Question prompt when e.g. equation editor encountered an error generating the image to insert
			if not dialog.run():
				return False

		self.result = (self.get_text(), self.image_file)

		return True
