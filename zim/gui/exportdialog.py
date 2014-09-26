# -*- coding: utf-8 -*-

# Copyright 2008,2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement

import gtk

import logging

import zim.formats
import zim.templates

from zim.fs import File, Dir, TmpFile
from zim.stores import encode_filename
from zim.gui.widgets import Assistant, AssistantPage, \
	ProgressBarDialog, ErrorDialog, QuestionDialog, \
	MessageDialog, LogFileDialog, Button
from zim.notebook import Path

from zim.export import *
from zim.export.selections import *


logger = logging.getLogger('zim.export')


class ExportDialog(Assistant):

	def __init__(self, ui):
		Assistant.__init__(self, ui, _('Export'), # T: dialog title
			help=':Help:Export', defaultwindowsize=(400, 325))

		self.append_page(InputPage(self))
		self.append_page(FormatPage(self))
		self.append_page(OutputPage(self))

	def do_response_ok(self):
		output, exporter = self.get_exporter()
		selection = self.get_selection()
		logger.debug('exporter: %s, selection: %s',
			exporter.__class__.__name__,
			selection.__class__.__name__)
		if exporter is None or selection is None:
			logger.debug('Cancelled - selection')
			return False # canceled

		# Check index up to date
		index = self.ui.notebook.index
		if index.updating:
			with ProgressBarDialog(self, _('Updating index')) as dialog: # T: Title of progressbar dialog
				index.ensure_update(callback=lambda p: dialog.pulse(p.name))
				if dialog.cancelled:
					logger.debug('Cancelled - progress dialog index')
					return False

		# Run export
		logging_context = LogContext()
		with logging_context:
			with ProgressBarDialog(self, _('Exporting notebook')) as dialog:
				# T: Title for progressbar window
				for p in exporter.export_iter(selection):
					if not dialog.pulse(p.name):
						logger.debug('Cancelled - progress dialog export')
						return False # canceled

		#~ print '>>> %s E: %i, W: %i' % (
			#~ logging_context.file.path,
			#~ logging_context.handler.n_error, logging_context.handler.n_warning)
		#~ print logging_context.file.read()
		#~ print '---'

		ExportDoneDialog(self, logging_context, output).run()

		return True

	def get_selection(self):
		if self.uistate['selection'] == 'all':
			return AllPages(self.ui.notebook)
		else:
			path = self.uistate['selected_page']
			if self.uistate['selection_recursive']:
				return SubPages(self.ui.notebook, path)
			else:
				return SinglePage(self.ui.notebook, path)

	def get_exporter(self):
		#~ import pprint
		#~ pprint.pprint(self.uistate)
		#~ return True

		options = {}
		for k in ('format', 'template', 'index_page'):
			if self.uistate[k] and not self.uistate[k].isspace():
				options[k] = self.uistate[k]

		options['format'] = \
			zim.formats.canonical_name(options['format'])

		if options['template'] == '__file__':
			options['template'] = self.uistate['template_file']

		if self.uistate['document_root'] == 'url':
			options['document_root_url'] = self.uistate['document_root_url']

		if options['format'] == 'mhtml':
			# Export MHTML file
			options.pop('format', None)
			options.pop('index_page', None)
			file = self.get_file()
			if file:
				return file, build_mhtml_file_exporter(file, **options)
			else:
				return None, None
		elif self.uistate['output'] == 'single_file':
			options.pop('index_page', None)
			if self.uistate['selection'] == 'page':
				options['namespace'] = self.uistate['selected_page']

			file = self.get_file()
			if file:
				return file, build_single_file_exporter(file, **options)
			else:
				return None, None
		elif self.uistate['selection'] == 'all':
			# Export full notebook to dir
			dir = self.get_folder()
			if dir:
				return dir, build_notebook_exporter(dir, **options)
			else:
				return None, None
		else:
			# Export page to file
			options.pop('index_page', None)
			file = self.get_file()
			if file:
				path = self.uistate['selected_page']
				return file, build_page_exporter(file, page=path, **options)
			else:
				return None, None

	def get_folder(self):
		dir = Dir(self.uistate['output_folder'])
		if dir.exists() and len(dir.list()) > 0:
			ok = QuestionDialog(self, (
				_('Folder exists: %s') % dir.path, # T: message heading
				_('Folder already exists and has content, '
				  'exporting to this folder may overwrite '
				  'existing files. '
				  'Do you want to continue?' ) # T: detailed message, answers are Yes and No
			) ).run()
			if not ok:
				return None
		return dir

	def get_file(self):
		file = File(self.uistate['output_file'])
		if file.exists():
			ok = QuestionDialog(self, (
				_('File exists'), # T: message heading
				_('This file already exists.\n'
				  'Do you want to overwrite it?' ) # T: detailed message, answers are Yes and No
			) ).run()
			if not ok:
				return None
		return file


class InputPage(AssistantPage):
	'''Assistant page allowing to select the page(s) for export'''

	title = _('Select the pages to export') # T: title of step in export dialog

	def __init__(self, assistant):
		AssistantPage.__init__(self, assistant)

		self.add_form((
			('selection:all', 'option', _('Complete _notebook')),
				# T: Option in export dialog to export complete notebook
			#~ ('selection:selection', 'option', _('_Selection')),
				# T: Option in export dialog to export selection
			#~ ('selection_query', 'string', None),
			('selection:page', 'option', _('Single _page')),
				# T: Option in export dialog to export selection
			None,
			('page', 'page', _('Page')), # T: Input field in export dialog
			('recursive', 'bool', _('Include subpages')), # T: Input field in export dialog
		), {
			'page': assistant.ui.page,
			'recursive': True,
		},
		depends={
			'page': 'selection:page',
			'recursive': 'selection:page',
		} )
		self.form.widgets['page'].existing_only = True

	def init_uistate(self):
		#~ self.uistate.setdefault('selection', 'all', ('all', 'page'))
		self.uistate.setdefault('selection', 'all')
		self.uistate.setdefault('selection_recursive', True)
		self.uistate.setdefault('selected_page', self.form['page'], check=Path)
		self.form['selection'] = self.uistate['selection']

	def save_uistate(self):
		self.uistate['selection'] = self.form['selection']
		self.uistate['selected_page'] = self.form['page']
		self.uistate['selection_recursive'] = self.form['recursive']


class FormatPage(AssistantPage):
	'''Assistant page allowing to select the output format and template'''

	title = _('Select the export format') # T: title of step in export dialog

	CHOICE_OTHER = _('Other...')
		# T: Option in drop down menu to specify another file

	# FUTURE: this page could have a dynamic form with additional
	# fields requested by the template, e.g. author etc.

	def __init__(self, assistant):
		AssistantPage.__init__(self, assistant)
		self.export_formats = zim.formats.list_formats(zim.formats.EXPORT_FORMAT)
		self.export_formats.insert(1, 'MHTML (Web Page Archive)') # TODO translatable

		self.add_form((
			('format', 'choice', _('Format'), self.export_formats), # T: Input label in the export dialog
			('template', 'choice', _('Template'), ()), # T: Input label in the export dialog
			('template_file', 'file', None),
			None,
			('document_root:absolute', 'option', _('Link files under document root with full file path')), # T: radio option in export dialog
			('document_root:url', 'option', _('Map document root to URL')+': '), # T: radio option in export dialog
			('document_root_url', 'string', None),
		), depends={
			'document_root_url': 'document_root:url'
		} )

		## Same button appears in edit preferences dialog
		if gtk.gtk_version >= (2, 10):
			url_button = gtk.LinkButton(
				'https://github.com/jaap-karssenberg/zim-wiki/wiki/Templates',
				_('Get more templates online') # T: label for button with URL
			)
			self.pack_start(url_button, False)


		# Set template list based on selected format
		def set_templates(self):
			format = self.form['format']
			format = zim.formats.canonical_name(format)
			if format == 'mhtml':
				format = 'html'
			combobox = self.form.widgets['template']
			combobox.get_model().clear()

			for name, _ in zim.templates.list_templates(format):
				combobox.append_text(name)
			combobox.append_text(self.CHOICE_OTHER)
			combobox.set_sensitive(True)

			template = self.uistate['template']
			if template == '__file__':
				# Select "Other..."
				combobox.set_active(len(templates))
			else:
				try:
					self.form['template'] = template
				except ValueError:
					combobox.set_active(0)

		self.form.widgets['format'].connect_object('changed', set_templates, self)

		# Hook template entry to be sensitive on "Other.."
		self.form.widgets['template_file'].set_sensitive(False)
		self.form.widgets['template'].connect('changed',
			lambda o: self.form.widgets['template_file'].set_sensitive(
							o.get_active_text() == self.CHOICE_OTHER) )

		# Check if we have a document root - if not disable all options
		docroot = assistant.ui.notebook.document_root
		if not docroot:
			for widget in self.form.widgets:
				if widget.startswith('document_root:'):
					self.form.widgets[widget].set_sensitive(False)
			self.uistate.input(document_root_url='')

	def init_uistate(self):
		self.uistate.setdefault('format', 'HTML')
		self.uistate.setdefault('template', 'Default')
		self.uistate.setdefault('template_file', '')
		self.uistate.setdefault('document_root', 'absolute', check=set(('absolute', 'url')))
		self.uistate.setdefault('document_root_url', '')

		try:
			self.form['format'] = self.uistate['format']
			if self.uistate['template'] == '__file__':
				self.form['template'] = self.CHOICE_OTHER
			else:
				self.form['template'] = self.uistate['template']
		except ValueError:
			pass

		self.form['template_file'] = self.uistate['template_file']
		self.form['document_root'] = self.uistate['document_root']
		self.form['document_root_url'] = self.uistate['document_root_url']

	def save_uistate(self):
		self.uistate.update(self.form)
		if self.uistate['template'] == self.CHOICE_OTHER:
			self.uistate['template'] = '__file__'


class OutputPage(AssistantPage):
	'''Assistant page allowing to select output file or folder'''

	title = _('Select the output file or folder') # T: title of step in export dialog

	def __init__(self, assistant):
		AssistantPage.__init__(self, assistant)

		self.add_form((
			('output:multi_file', 'option', _('Export each page to a separate file')),
				# T: Label for option in export dialog
			('output:single_file', 'option', _('Export all pages to a single file')),
				# T: Label for option in export dialog
			None,
			('folder', 'dir', _('Output folder')),
				# T: Label for folder selection in export dialog
			('index', 'string', _('Index page')),
				# T: Label for setting a name for the index of exported pages
				# TODO validation for this entry - valid name, but not existing
			('file', 'output-file', _('Output file')),
				# T: Label for file selection in export dialog
		), depends={
			'index': 'folder',
		} )

		for widget in self.form.widgets:
			self.form.widgets[widget].set_no_show_all(True)

		self.form.widgets['output:single_file'].connect('toggled', self.on_output_changed)

	def init_uistate(self):
		# Switch between folder selection or file selection based
		# on whether we selected full notebook or single page in the
		# first page
		self.uistate.setdefault('output', 'multi_file')
		self.uistate.setdefault('output_folder', None, Dir)
		self.uistate.setdefault('index_page', '')
		self.uistate.setdefault('output_file', None, File)

		if self.uistate.get('format', '').startswith('MHTML'):
			# XXX make this a format property to be queried
			self.form.widgets['output:multi_file'].set_sensitive(False)
			self.form.widgets['output:single_file'].set_sensitive(False)
			self.form.widgets['output:single_file'].set_active(True)
		else:
			self.form.widgets['output:multi_file'].set_sensitive(True)
			self.form.widgets['output:single_file'].set_sensitive(True)

		self.form.widgets['output:multi_file'].show()
		self.form.widgets['output:single_file'].show()

		self.form['output'] = self.uistate['output']

		self.on_output_changed(None)

		# Set file name
		basename = self.uistate['selected_page'].basename
		format = self.uistate['format']
		if format.startswith('MHTML'):
			ext = 'mht'
		else:
			ext = zim.formats.get_format(format).info['extension']

		if self.uistate['output_file'] \
		and isinstance(self.uistate['output_file'], File):
			dir = self.uistate['output_file'].dir
			file = dir.file(encode_filename(basename  + '.' + ext))
		else:
			file = File('~/' + encode_filename(basename  + '.' + ext))
		self.uistate['output_file'] = file

		self.form['file'] = self.uistate['output_file']
		self.form['folder'] = self.uistate['output_folder']

	def on_output_changed(self, o):
		if self.uistate.get('selection') == 'page':
			self.set_show_file(True)
		else:
			self.set_show_file(self.form['output'] == 'single_file')

	def set_show_file(self, show_file):
		if show_file:
			self.form.widgets['folder'].set_sensitive(False)
			self.form.widgets['folder'].hide()
			self.form.widgets['file'].set_sensitive(True)
			self.form.widgets['file'].show()
		else:
			self.form.widgets['folder'].set_sensitive(True)
			self.form.widgets['folder'].show()
			self.form.widgets['file'].set_sensitive(False)
			self.form.widgets['file'].hide()

	def save_uistate(self):
		self.uistate['output_file'] = self.form['file']
		self.uistate['output_folder'] = self.form['folder']
		self.uistate['index_page'] = self.form['index']
		self.uistate['output'] = self.form['output']


class ExportDoneDialog(MessageDialog):

	def __init__(self, parent, logging_context, output):
		self.logging_context = logging_context
		self.output = output

		n_error = logging_context.handler.n_error
		n_warning = logging_context.handler.n_warning
		if n_error and n_warning:
			text = _('%(n_errors)i errors and %(n_warnings)i warnings occurred, see log') % {'n_error': n_error, 'n_warnings': n_warning}
				# T: label in export dialog
		elif n_error:
			text = _('%i errors occurred, see log') % n_error
				# T: label in export dialog
		elif n_warning:
			text = _('%i warnings occurred, see log') % n_warning
				# T: label in export dialog
		else:
			text = None

		MessageDialog.__init__(self, parent, (_('Export completed'), text))
			# T: label in export dialog

		log_button = Button(_('View _Log'), stock='gtk-file')
			# T: button in export dialog
		log_button.set_sensitive(logging_context.file.exists())
		log_button.connect_object(
			'clicked', self.__class__.on_show_log, self)

		#~ open_button =

		#~ self.add_extra_button(open_button)
		self.add_extra_button(log_button)

	def on_show_log(self):
		LogFileDialog(self, self.logging_context.file).run()

	def on_open_file(self):
		self.ui.open_file(self.output) # XXX


class LogContext(object):
	'''Context to log errors and warnings to a log file'''

	def __init__(self):
		names = ['zim.export', 'zim.templates', 'zim.formats']
		level = logging.INFO

		self.logger = logging.getLogger('zim')
		self.level = level
		self.file = TmpFile(basename='export-log.txt', unique=False, persistent=True)
		self.file.remove() # clean up previous run
		self.handler = LogHandler(self.file.path)
		self.handler.setLevel(self.level)
		self.handler.addFilter(LogFilter(names))
		self.handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s') )

	def __enter__(self):
		#~ self._old_level = self.logger.getEffectiveLevel()
		#~ if self._old_level > self.level:
			#~ self.logger.setLevel(self.level)
		self.logger.addHandler(self.handler)

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.logger.removeHandler(self.handler)
		#~ self.logger.setLevel(self._old_level)
		self.handler.close()
		return False # re-raises error


class LogFilter(logging.Filter):

	def __init__(self, names):
		self.names = names

	def filter(self, record):
		return any(record.name.startswith(n) for n in self.names)


class LogHandler(logging.FileHandler):

	def __init__(self, filename, mode='w', encoding='UTF-8', delay=True):
		logging.FileHandler.__init__(self, filename, mode, encoding, delay)
		self.n_warning = 0
		self.n_error = 0

	def emit(self, record):
		# more detailed logging has lower number, so WARN > INFO > DEBUG
		# log to file unless output is a terminal and logging <= INFO
		if record.levelno >= logging.ERROR:
			self.n_error += 1
		elif record.levelno >= logging.WARNING:
			self.n_warning += 1

		logging.FileHandler.emit(self, record)

