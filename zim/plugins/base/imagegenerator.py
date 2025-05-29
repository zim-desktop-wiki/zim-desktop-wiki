
# Copyright 2009-2022 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains the base classes used by all plugins that
create an image from text based input. Like the equation editor, the
diagram editor etc.
'''

import logging

logger = logging.getLogger('zim.plugins')

from gi.repository import Gtk

from zim.newfs.base import md5_for_unsave_usage
from zim.fs import adapt_from_oldfs
from zim.plugins import PluginClass, InsertedObjectTypeExtension
from zim.signals import SignalEmitter, SIGNAL_RUN_FIRST
from zim.config import String
from zim.errors import show_error, Error
from zim.applications import ApplicationError
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

	See L{zim.insertedobjects} for more information on the C{ObjectType}
	interface
	'''

	syntax = None
	widget_style = None

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
		return ImageGeneratorWidget(model, self.label, self.syntax, self.widget_style)


class BackwardImageGeneratorObjectType(ImageGeneratorObjectType):
	'''Base class for backward compatible image generator objects.'''

	object_attr = {
		'src': String('_new_'),
	}

	is_inline = True # Behave like an image
	scriptname = None

	def model_from_data(self, notebook, page, attrib, data):
		generator = self.generator_klass(self.plugin, notebook, page)
		return BackwardImageGeneratorModel(notebook, page, generator, attrib, data, self.scriptname)

	def format(self, format, dumper, attrib, data):
		if data:
			logger.warning('Unexpected data in %s object: %r', attrib['type'], data)

		try:
			return ImageGeneratorObjectType.format(self, format, dumper, attrib, data)
		except ValueError:
			if attrib['type'].startswith('image+'):
				attrib = attrib.copy()
				attrib['type'] = attrib['type'][6:]
			return dumper.dump_img(IMAGE, attrib, None)


class ImageGeneratorModelBase(SignalEmitter):

	__signals__ = {'changed': (SIGNAL_RUN_FIRST, None, ())}

	def __init__(self, notebook, page, generator, attrib, data):
		self.notebook = notebook
		self.page = page
		self.generator = generator
		self.attrib = attrib
		self.data = data
		self.image_file = None

	def get_text(self):
		'''Get the text of the model or default value'''
		text = self.data or self.generator.get_default_text()
		return self.generator.filter_source(text)

	def set_from_generator(self, text, image_file):
		'''Update state of the model based on output of the generator
		this is used after the generator is run by another class.
		@emits: changed
		'''
		raise NotImplementedError


class ImageGeneratorModel(ImageGeneratorModelBase):

	def __init__(self, notebook, page, generator, attrib, data):
		ImageGeneratorModelBase.__init__(self, notebook, page, generator, attrib, data)
		self.image_file = self._new_image_file()

		if self.data and not self.image_file.exists():
			logger.debug('Image did not exist, re-generating: %r', self.image_file.path)
			# Cache was cleaned - should we do this async ?
			try:
				image_file, log_file = self.generator.generate_image(data)
			except Error:
				pass
			else:
				self.set_from_generator(data, image_file)
		elif not data and self.image_file.exists():
			self.image_file.remove()

	def _new_image_file(self):
		cache_dir = self.notebook.folder.folder('_images')
		if self.data:
			content = []
			for k, v in sorted(self.attrib.items()):
				content.extend([k, v])
			content.append(self.data)
			basename = md5_for_unsave_usage(''.join(content).encode()).hexdigest() + self.generator.imagefile_extension
		else:
			basename = 'empty_image' + self.generator.imagefile_extension
		file = cache_dir.file(basename)
		logger.debug('New cache image: %s', file.path)
		return file

	def set_from_generator(self, text, image_file):
		# Do not clean up the existing self.image_file - we don't know if
		# any other object is using the same file
		# TODO: use index table to keep track and clean up when ref count is zero ?
		self.data = text
		self.image_file = self._new_image_file()
		image_file.moveto(self.image_file)
		self.emit('changed')


class BackwardImageGeneratorModel(ImageGeneratorModelBase):

	def __init__(self, notebook, page, generator, attrib, data, scriptname):
		ImageGeneratorModelBase.__init__(self, notebook, page, generator, attrib, data)
		imagefile_extension = self.generator.imagefile_extension
		if attrib['src'] and not attrib['src'] == '_new_':
			# File give, derive script
			self.image_file = adapt_from_oldfs(notebook.resolve_file(attrib['src'], page))
			self.script_file = _stitch_fileextension(self.image_file, scriptname)
		else:
			# Find available combo of script and image files
			def check_image_file(new_script_file):
				new_image_file = _stitch_fileextension(new_script_file, imagefile_extension)
				return not new_image_file.exists()

			folder = adapt_from_oldfs(notebook.get_attachments_dir(page))
			self.script_file = folder.new_file(scriptname, check_image_file)
			self.image_file = _stitch_fileextension(self.script_file, imagefile_extension)
			self.attrib['src'] = './' + self.image_file.basename

		# Regen missing/outdated image if the notebook/page isn't readonly
		if not (notebook.readonly or (page and page.readonly)) and self.script_file.exists() and (
				not self.image_file.exists() or
				self.script_file.mtime() + 1 > self.image_file.mtime()):
			logger.debug('Image did not exist or source file was modified externally, re-generating')
			try:
				text = self.get_text()
				image_file, log_file = self.generator.generate_image(text)
			except Error:
				pass
			else:
				self.set_from_generator(text, image_file)

	def find_simple_match(self, query: 'FindQuery') -> bool:
		# Default behavior checks data field, but this is empty for this model type
		text = self.get_text()
		return (query.regex.search(text) is not None) if text else False

	def get_text(self):
		if self.image_file is not None and self.script_file.exists():
			text = self.script_file.read()
		else:
			text = self.generator.get_default_text()

		return self.generator.filter_source(text)

	def set_from_generator(self, text, image_file):
		# FIXME: refactor the file saving sequence (save script first, generate image second); see #2112
		self.script_file.write(text)
		image_file = adapt_from_oldfs(image_file)
		image_file._set_mtime(self.script_file.mtime())  # avoid needless regen

		if image_file == self.image_file:
			pass
		else:
			if self.image_file.exists():
				self.image_file.remove()

			if image_file and image_file.exists():
				image_file.moveto(self.image_file)

		self.emit('changed')


def _stitch_fileextension(file, basename):
	# Take extension of basename, and put it on path from file
	file = adapt_from_oldfs(file)
	i = basename.rfind('.')
	j = file.basename.rfind('.')
	return file.parent().file(file.basename[:j] + basename[i:])


def copy_imagegenerator_src_files(src_file, folder):
	# Helper method to allow copy-paste dealing with image files generated
	# by a BackwardImageGeneratorObjectType instance
	# We want to be agnostic of the exact image object type, so we just look
	# at any files that share the same basename as the image being copied
	src_file = adapt_from_oldfs(src_file)
	folder = adapt_from_oldfs(folder)
	basename = src_file.basename
	i = basename.rfind('.')
	basename = basename[:i]

	src_files = []
	for f in src_file.parent():
		if f.basename.startswith(basename) \
			and not '.' in f.basename[len(basename)+1:]:
				src_files.append(f)

	def check_new_file(new_file):
		for f in src_files:
			new_f = _stitch_fileextension(new_file, f.basename)
			if new_f.exists():
				return False
		else:
			return True

	new_file = folder.new_file(src_file.basename, check_new_file)
	for f in src_files:
		new_f = _stitch_fileextension(new_file, f.basename)
		if f.exists():
			f.copyto(new_f)
		else:
			logger.warning('File not found: %s' % f.userpath)

	return new_file


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

	imagefile_extension = None #: e.g. ".png" used by the model to create proper file path

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

	def __init__(self, model, label, syntax=None, widget_style=None):
		ImageFileWidget.__init__(self, model.image_file, widget_style=widget_style)
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
		result = cls(
			widget,
			label,
			model.generator,
			model.image_file,
			model.get_text(),
			syntax
		).run()
		if result is not None and result[0] is not None:
			text, image_file = result
			model.set_from_generator(text, image_file)
		model.generator.cleanup()

	def __init__(self, widget, label, generator, image_file:'LocalFile'=None, text='', syntax=None):
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
		if self._file_deleted:
			self.update_image()  # includes setting imageview file
		else:
			self.imageview.set_file(self.image_file) # if None sets broken image
		self.textview.grab_focus()

	@property
	def _file_deleted(self):  # see #2102
		" Returns True when image_file is set but doesn't exist, ie. when the file has been deleted. "
		return self.image_file is not None and not self.image_file.exists()

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
		assert self.log_file, 'BUG: no log_file set (yet)'
		LogFileDialog(self, self.log_file).run()

	def do_response_ok(self):
		buffer = self.textview.get_buffer()
		if buffer.get_modified() or self._file_deleted:  # XXX: doesn't check notebook editable
			logger.debug('Image modified or did not exist, re-generating')
			self.update_image()

		if not (self.image_file and self.image_file.exists()):
			dialog = QuestionDialog(self,
					_('An error occurred while generating the image.\nDo you want to save the source text anyway?'))
					# T: Question prompt when e.g. equation editor encountered an error generating the image to insert
			if not dialog.run():
				return False

		self.result = (self.get_text(), self.image_file)

		return True
