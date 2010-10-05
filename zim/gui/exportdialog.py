# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

import gtk

from zim.fs import *
from zim.exporter import Exporter
import zim.formats
import zim.templates
from zim.stores import encode_filename
from zim.gui.widgets import Dialog, ProgressBarDialog, ErrorDialog, QuestionDialog
from zim.gui.widgets import Assistant, AssistantPage, PageEntry, InputEntry


def form_factory(inputs, table=None):
	'''Takes a list of inputs and returns a table with nice layout for
	those inputs. Forms are tables with one column for a label followed
	by a colon and one column for an input widget. Some widgets, like
	checkboxes, break this layout and contain a label themselves. So
	inputs in the list given should be either a gtk widget or a tuple
	of a string and a widget. If a tuple is given and the first item
	is 'None', the widget will be lined out in the 2nd column. A 'None'
	value in the input list represents an empty row in the table.
	'''
	# TODO move this to widgets, merge with Dialog.add_fields
	if table is None:
		table = gtk.Table()
		#~ table.set_border_width(5)
		table.set_row_spacings(5)
		table.set_col_spacings(12)
	i = table.get_property('n-rows')

	def _hook_label_to_widget(label, widget):
		# Hook label to follow state of entry widget
		def _sync_state(widget, spec):
			label.set_sensitive(widget.get_property('sensitive'))
			label.set_no_show_all(widget.get_no_show_all())
			if widget.get_property('visible'):
				label.show()
			else:
				label.hide()

		for property in ('visible', 'no-show-all', 'sensitive'):
			widget.connect_after('notify::%s' % property, _sync_state)

	for input in inputs:
		if input is None:
			table.attach(gtk.Label(' '), 0,2, i,i+1, xoptions=gtk.FILL)
			# force empty row to have height of label
		elif isinstance(input, tuple):
			text, widget = input
			if not text is None:
				label = gtk.Label(text + ':')
				label.set_alignment(0.0, 0.5)
				table.attach(label, 0,1, i,i+1, xoptions=gtk.FILL)
				_hook_label_to_widget(label, widget)
			table.attach(widget, 1,2, i,i+1)
		else:
			widget = input
			table.attach(widget, 0,2, i,i+1)
		i += 1

	return table


def help_text_factory(text):
	'''Create a label with an info icon in front of it. Intended for
	iformational text in dialogs.
	'''
	# TODO move this to widgets, merge with Dialog.add_fields
	hbox = gtk.HBox(spacing=12)

	image = gtk.image_new_from_stock(gtk.STOCK_INFO, gtk.ICON_SIZE_BUTTON)
	image.set_alignment(0.5, 0.0)
	hbox.pack_start(image, False)

	label = gtk.Label(text)
	label.set_use_markup(True)
	label.set_alignment(0.0, 0.0)
	hbox.add(label)

	return hbox


def file_entry_factory(dialog, type):
	# HACK - duplicate code from widgets.Dialog - needs refactoring
	entry = InputEntry()
	browse = gtk.Button('_Browse')
	browse.connect('clicked', dialog._select_file, (type, entry))
	return entry, browse


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

		if self.uistate['use_document_root_url']:
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
					_('Folder exists'), # T: message heading
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

		self.all_pages_radio = gtk.RadioButton(None, _('Complete _notebook'))
			# T: Option in export dialog to export complete notebook
		self.selection_radio = gtk.RadioButton(self.all_pages_radio, _('_Selection'))
			# T: Option in export dialog to export selection
		self.single_page_radio = gtk.RadioButton(self.all_pages_radio, _('Single _page'))
			# T: Option in export dialog to export selection

		self.recursive_box = gtk.CheckButton('Recursive')
		self.recursive_box.set_no_show_all(True)
		self.recursive_box.hide()
		# TODO: supprot recursive export for pages

		self.page_entry = PageEntry(assistant.ui.notebook, assistant.ui.page)
		self.page_entry.force_existing = True
			# do not use uistate['selection_page'] here - default to current page
		self.page_entry.set_sensitive(self.single_page_radio.get_active())
		self.add_validation_widget(self.page_entry)

		self.single_page_radio.connect('toggled',
			lambda b: (
				self.recursive_box.set_sensitive(b.get_active()),
				self.page_entry.set_sensitive(b.get_active())
			) )

		table = form_factory( [
			self.all_pages_radio,
			#~ self.selection_radio,
			#~ (None, self.selection_entry),
			self.single_page_radio,
			None,
			(_('Page'), self.page_entry), # T: input in export dialog
			(None, self.recursive_box),
		] )
		self.pack_start(table, False)

	def init_uistate(self):
		self.uistate.setdefault('selection', 'all')
		self.uistate.setdefault('selection_recursive', False)

		if self.uistate['selection'] == 'all':
			self.all_pages_radio.set_active(True)
		elif self.uistate['selection'] == 'selection':
			self.selection_radio.set_active(True)
		elif self.uistate['selection'] == 'page':
			self.single_page_radio.set_active(True)

		self.recursive_box.set_sensitive(self.single_page_radio.get_active())
		self.recursive_box.set_active(self.uistate['selection_recursive'])

	def save_uistate(self):
		if self.all_pages_radio.get_active(): selection = 'all'
		elif self.selection_radio.get_active(): selection = 'selection'
		elif self.single_page_radio.get_active(): selection = 'page'
		self.uistate['selection'] = selection
		self.uistate['selected_page'] = self.page_entry.get_path()
		self.uistate['selection_recursive'] = self.recursive_box.get_active()


class FormatPage(AssistantPage):
	'''Assistant page allowing to select the output format and template'''

	title = _('Select the export format') # T: title of step in export dialog

	CHOICE_OTHER = _('Other...')
		# T: Option in drop down menu to specify another file

	# FUTURE: this page could have a dynamic form with additional
	# fields requested by the template, e.g. author etc.

	def __init__(self, assistant):
		AssistantPage.__init__(self, assistant)

		# Formats
		self.formats_combobox = gtk.combo_box_new_text()
		self.export_formats = zim.formats.list_formats(zim.formats.EXPORT_FORMAT)
		for name in self.export_formats:
			self.formats_combobox.append_text(name)

		# Templates
		self.templates_combobox = gtk.combo_box_new_text()
		self.templates_combobox.set_sensitive(False)

		self.other_template_selector = \
			gtk.FileChooserButton(_('Please select a template file'))
			# T: Title of file selection dialog
		self.other_template_selector.set_sensitive(False)
		self.add_validation_widget(self.other_template_selector)

		self.templates_combobox.connect('changed',
			lambda o: self.other_template_selector.set_sensitive(
							o.get_active_text() == self.CHOICE_OTHER) )
			# connect this one before initializing template list

		def set_templates(formats_combobox, templates_combobox):
			format = formats_combobox.get_active_text()
			templates_model = templates_combobox.get_model()
			templates_model.clear()
			template_dict = zim.templates.list_templates(format)
			templates = sorted(template_dict.keys())
			for name in templates:
				templates_combobox.append_text(name)
			templates_combobox.append_text(self.CHOICE_OTHER)
			templates_combobox.set_sensitive(True)
			template = self.uistate['template']
			if template == '__file__':
				templates_combobox.set_active(len(templates))
			else:
				try:
					i = templates.index(template)
					templates_combobox.set_active(i)
				except ValueError:
					templates_combobox.set_active(0)

		self.formats_combobox.connect('changed', set_templates, self.templates_combobox)

		# Document root
		self.absolute_document_root = \
			gtk.RadioButton(None,
			_('Link files under document root with full file path') )
			# T: radio option in export dialog
		self.use_document_root_url = \
			gtk.RadioButton(self.absolute_document_root,
			_('Map document root to URL')+': ' )
			# T: radio option in export dialog

		self.document_root_url_entry = InputEntry()
		self.document_root_url_entry.set_sensitive(False)
		if assistant.ui.notebook.get_document_root():
			self.uistate.setdefault('use_document_root_url', False)
			self.use_document_root_url.connect('toggled',
				lambda o: self.document_root_url_entry.set_sensitive(o.get_active()) )
			self.use_document_root_url.set_active(self.uistate['use_document_root_url'])
		else:
			self.use_document_root_url.set_sensitive(False)
			self.absolute_document_root.set_sensitive(False)

		# And set the layout of all controls
		table = form_factory( [
			(_('Format'), self.formats_combobox), # T: Input label in the export dialog
			(_('Template'), self.templates_combobox), # T: Input label in the export dialog
			(None, self.other_template_selector),
			None,
			self.absolute_document_root,
			self.use_document_root_url,
			(None, self.document_root_url_entry),
		] )
		self.pack_start(table, False)

	def init_uistate(self):
		self.uistate.setdefault('format', 'HTML')
		self.uistate.setdefault('template', 'Default')
		self.uistate.setdefault('template_file', '')
		self.uistate.setdefault('use_document_root_url', False)
		self.uistate.setdefault('document_root_url', '')

		try:
			i = self.export_formats.index(self.uistate['format'])
			self.formats_combobox.set_active(i)
		except ValueError:
			pass

		if self.uistate['template_file']:
			try:
				self.other_template_selector.set_filename(
					self.uistate['template_file'] )
			except:
				pass

		self.document_root_url_entry.set_text(self.uistate['document_root_url'])


	def save_uistate(self):
		self.uistate['use_document_root_url'] = self.use_document_root_url.get_active()
		for key, value in (
			('format', self.formats_combobox.get_active_text()),
			('template', self.templates_combobox.get_active_text()),
			('template_file', self.other_template_selector.get_filename()),
			('document_root_url', self.document_root_url_entry.get_text()),
		):
			if isinstance(value, basestring):
				value = value.decode('utf-8')
			self.uistate[key] = value

		if self.uistate['template'] == self.CHOICE_OTHER:
			self.uistate['template'] = '__file__'


class OutputPage(AssistantPage):
	'''Assistant page allowing to select output file or folder'''

	title = _('Select the output file or folder') # T: title of step in export dialog

	def __init__(self, assistant):
		AssistantPage.__init__(self, assistant)

		entry, button = file_entry_factory(assistant, 'dir')
		self.output_folder_hbox = gtk.HBox(spacing=12)
		self.output_folder_hbox.add(entry)
		self.output_folder_hbox.pack_end(button, False)
		self.output_folder_entry = entry
		# TODO validation for these entries

		self.index_page_entry = InputEntry()
		# TODO validation for this entry - valid name, but not existing

		entry, button = file_entry_factory(assistant, 'output-file')
		self.output_file_hbox = gtk.HBox(spacing=12)
		self.output_file_hbox.add(entry)
		self.output_file_hbox.pack_end(button, False)
		self.output_file_entry = entry
		# TODO validation for these entries

		# TODO add attachments folder selection when single page is exported

		table = form_factory( [
			(_('Output folder'), self.output_folder_hbox),
				# T: Label for folder selection in export dialog
			(_('Index page'), self.index_page_entry),
				# T: Label for setting a name for the index of exported pages
			(_('Output file'), self.output_file_hbox)
				# T: Label for file selection in export dialog
		] )
		self.pack_start(table, False)

	def init_uistate(self):
		# Switch between folder selection or file selection based
		# on whether we selected full notebook or single page in the
		# first page
		show_file = self.uistate.get('selection') == 'page'

		if show_file:
			self.output_folder_hbox.hide()
			self.index_page_entry.hide()
			self.output_file_hbox.show()
		else:
			self.output_folder_hbox.show()
			self.index_page_entry.show()
			self.output_file_hbox.hide()

		if show_file:
			basename = self.uistate['selected_page'].basename
			ext = zim.formats.get_format(self.uistate['format']).info['extension']
			filename = File('~/' + encode_filename(basename  + '.' + ext)).path
			self.uistate.setdefault('output_file', filename)
			# TODO rememeber last file output folder

		for param, entry in (
			('output_folder', self.output_folder_entry),
			('output_file', self.output_file_entry),
		):
			if self.uistate.get(param):
				try:
					entry.set_text(self.uistate[param])
				except:
					pass

	def save_uistate(self):
		for param, entry in (
			('output_folder', self.output_folder_entry),
			('output_file', self.output_file_entry),
		):
			value = entry.get_text()
			self.uistate[param] = value

		self.uistate['index_page'] = self.index_page_entry.get_text()

	def _check_valid(self):
		# HACK - really needs special validating widget
		show_file = self.uistate.get('selection') == 'page'
		if show_file: entry = self.output_file_entry
		else: entry = self.output_folder_entry

		value = entry.get_text().strip()
		if not value:
			raise AssertionError, 'Missing file or folder'
		return True
