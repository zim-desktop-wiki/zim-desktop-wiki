# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import gtk

from zim.fs import *
from zim.exporter import Exporter
import zim.formats
import zim.templates
from zim.stores import encode_filename
from zim.gui.widgets import Assistant, AssistantPage, \
	ProgressBarDialog, ErrorDialog, QuestionDialog


class ExportDialog(Assistant):

	def __init__(self, ui):
		Assistant.__init__(self, ui, _('Export'), # T: dialog title
			help=':Help:Export', defaultwindowsize=(400, 325))

		self.append_page(InputPage(self))
		self.append_page(FormatPage(self))
		self.append_page(OutputPage(self))

	def do_response_ok(self):
		#~ import pprint
		#~ pprint.pprint(self.uistate)
		#~ return True
		options = {}
		for k in ('format', 'template', 'index_page'):
			if self.uistate[k] and not self.uistate[k].isspace():
				options[k] = self.uistate[k]

		if options['template'] == '__file__':
			options['template'] = self.uistate['template_file']

		if self.uistate['document_root_url'] == 'url':
			options['document_root_url'] = self.uistate['document_root_url']

		try:
			exporter = Exporter(self.ui.notebook, **options)
		except Exception, error:
			ErrorDialog(self, error).run()
			return False

		if self.uistate['selection'] == 'all':
			dir = Dir(self.uistate['output_folder'])
			if dir.exists() and len(dir.list()) > 0:
				ok = QuestionDialog(self, (
					_('Folder exists: %s') % dir.path, # T: message heading
					_('Folder already exists and has content, '
					  'exporting to this folder may overwrite '
					  'exisitng files. '
					  'Do you want to continue?' ) # T: detailed message, answers are Yes and No
				) ).run()
				if not ok:
					return False

			dialog = ProgressBarDialog(self, _('Exporting notebook'))
				# T: Title for progressbar window
				# TODO make progressbar a context manager - now it stays alive in case of an error during the export
			dialog.show_all()
			exporter.export_all(dir, callback=lambda p: dialog.pulse(p.name))
			dialog.destroy()
		elif self.uistate['selection'] == 'selection':
			pass # TODO
		elif self.uistate['selection'] == 'page':
			file = File(self.uistate['output_file'])
			if file.exists():
				ok = QuestionDialog(self, (
					_('File exists'), # T: message heading
					_('This file already exists.\n'
					  'Do you want to overwrite it?' ) # T: detailed message, answers are Yes and No
				) ).run()
				if not ok:
					return False

			page = self.ui.notebook.get_page(self.uistate['selected_page'])

			# FIXME - HACK - dump and parse as wiki first to work
			# around glitches in pageview parsetree dumper
			# main visibility when copy pasting bullet lists
			# Same hack in gui clipboard code
			from zim.notebook import Path, Page
			from zim.formats import get_format
			parsetree = page.get_parsetree()
			dumper = get_format('wiki').Dumper()
			text = ''.join( dumper.dump(parsetree) ).encode('utf-8')
			parser = get_format('wiki').Parser()
			parsetree = parser.parse(text)
			page = Page(Path(page.name), parsetree=parsetree)

			exporter.export_page(file.dir, page, filename=file.basename)

		return True


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
			#~ ('recursive', 'bool', _('Recursive')),
		), {
			'page': assistant.ui.page,
		},
		depends={
			'page': 'selection:page',
			#~ 'recursive': 'selection:page',
		} )
		self.form.widgets['page'].existing_only = True

	def init_uistate(self):
		#~ self.uistate.setdefault('selection', 'all', ('all', 'page'))
		self.uistate.setdefault('selection', 'all')
		#~ self.uistate.setdefault('selection_recursive', False)
		self.form['selection'] = self.uistate['selection']

	def save_uistate(self):
		self.uistate['selection'] = self.form['selection']
		self.uistate['selected_page'] = self.form['page']


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

		# Set template list based on selected format
		def set_templates(self):
			format = self.form['format']
			combobox = self.form.widgets['template']
			combobox.get_model().clear()

			templates = zim.templates.list_templates(format)
			for name in sorted(templates):
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
			self.uistate['document_root_url'] = ''

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

	def init_uistate(self):
		# Switch between folder selection or file selection based
		# on whether we selected full notebook or single page in the
		# first page
		self.uistate.setdefault('output_folder', '')
		self.uistate.setdefault('index_page', '')
		self.uistate.setdefault('output_file', '')

		show_file = self.uistate.get('selection') == 'page'
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

		if show_file:
			basename = self.uistate['selected_page'].basename
			ext = zim.formats.get_format(self.uistate['format']).info['extension']
			file = File('~/' + encode_filename(basename  + '.' + ext))
			self.uistate['output_file'] = file
			# TODO rememeber last file output folder

		self.form['file'] = self.uistate['output_file']
		self.form['folder'] = self.uistate['output_folder']

	def save_uistate(self):
		self.uistate['output_file'] = self.form['file']
		self.uistate['output_folder'] = self.form['folder']
		self.uistate['index_page'] = self.form['index']
