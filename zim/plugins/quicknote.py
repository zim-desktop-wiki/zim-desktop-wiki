
# Copyright 2010-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from gi.repository import Gtk

import re

from zim.parse.encode import url_decode, URL_ENCODE_DATA
from zim.fs import adapt_from_oldfs
from zim.newfs import LocalFolder
from zim.plugins import PluginClass
from zim.actions import action
from zim.config import ConfigManager
from zim.notebook import Path, Notebook, NotebookInfo, \
	resolve_notebook, build_notebook
from zim.templates import get_template
from zim.templates.expression import ExpressionFunction
from zim.main import GtkCommand

from zim.gui.mainwindow import MainWindowExtension
from zim.gui.widgets import Dialog, ScrolledTextView, InputForm, QuestionDialog
from zim.gui.clipboard import Clipboard, SelectionClipboard
from zim.gui.notebookdialog import NotebookComboBox


import logging

logger = logging.getLogger('zim.plugins.quicknote')


class QuickNotePluginCommand(GtkCommand):

	options = (
		('notebook=', '', 'Select the notebook in the dialog'),
		('page=', '', 'Fill in full page name'),
		('section=', '', 'Fill in the page section in the dialog'),
		('namespace=', '', 'Fill in the page section in the dialog'), # backward compatibility
		('basename=', '', 'Fill in the page name in the dialog'),
		('append=', '', 'Set whether to append or create new page ("true" or "false")'),
		('text=', '', 'Provide the text directly'),
		('input=', '', 'Provide the text on stdin ("stdin") or take the text from the clipboard ("clipboard")'),
		('encoding=', '', 'Text encoding ("base64" or "url")'),
		('attachments=', '', 'Import all files in FOLDER as attachments, wiki input can refer these files relatively'),
		('option=', '', 'Set template parameter, e.g. "url=URL"'),
	)

	cmdhelp = '''\
usage: zim --plugin quicknote [OPTIONS]

Options:
  --help, -h             Print this help text and exit
  --notebook URI         Select the notebook in the dialog
  --page STRING          Fill in full page name
  --section STRING       Fill in the page section in the dialog
  --basename STRING      Fill in the page name in the dialog
  --append [true|false]  Set whether to append or create new page
  --text TEXT            Provide the text directly
  --input stdin          Provide the text on stdin
  --input clipboard      Take the text from the clipboard
  --encoding base64      Text is encoded in base64
  --encoding url         Text is url encoded
                         (In both cases expects UTF-8 after decoding)
  --attachments FOLDER   Import all files in FOLDER as attachments,
                         wiki input can refer these files relatively
  --option url=STRING    Set template parameter
'''

	def handle_local_commandline(self, args):
		# This runs in local process before dispatching via GtkApplication
		# calling get_text_local() here ensures we handle e.g. stdin in local process
		# In main run() method only the "--text" option is looked at and other ignored.
		# If "--text" is already in the arguments, the final one in the list will
		# be used. So no need to "clean up" the arguments.
		text = self.get_text_local()
		args.extend(['--text', text])
		return args

	def parse_options(self, *args):
		self.opts['option'] = [] # allow list

		GtkCommand.parse_options(self, *args)

		self.template_options = {}
		for arg in self.opts['option']:
			key, value = arg.split('=', 1)
			self.template_options[key] = value

		if 'append' in self.opts:
			self.opts['append'] = \
				self.opts['append'].lower() == 'true'

		if self.opts.get('attachments', None):
			folderpath = LocalFolder(self.pwd).get_abspath(self.opts['attachments'])
			self.opts['attachments'] = LocalFolder(folderpath)

	def get_text_local(self):
		if 'text' in self.opts: 
			text = self.opts['text']
		elif 'input' in self.opts:
			if self.opts['input'] == 'stdin':
				import sys
				text = sys.stdin.read()
			elif self.opts['input'] == 'clipboard':
				text = SelectionClipboard.get_text() or Clipboard.get_text()
			else:
				raise AssertionError('Unknown input type: %s' % self.opts['input'])
		else:
			text = ''

		if text and 'encoding' in self.opts:
			if self.opts['encoding'] == 'base64':
				import base64
				text = base64.b64decode(text).decode('UTF-8')
			elif self.opts['encoding'] == 'url':
				text = url_decode(text, mode=URL_ENCODE_DATA)
			else:
				raise AssertionError('Unknown encoding: %s' % self.opts['encoding'])

		assert isinstance(text, str), '%r is not decoded' % text
		return text

	def run(self):
		if 'notebook' in self.opts:
			notebook = resolve_notebook(self.opts['notebook'])
		else:
			notebook = None

		dialog = QuickNoteDialog(None,
			notebook=notebook,
			namespace=self.opts.get('namespace'),
			basename=self.opts.get('basename'),
			append=self.opts.get('append'),
			text=self.opts.get('text', ''),
			template_options=self.template_options,
			attachments=self.opts.get('attachments')
		)
		dialog.show_all()
		return dialog


class QuickNotePlugin(PluginClass):

	plugin_info = {
		'name': _('Quick Note'), # T: plugin name
		'description': _('''\
This plugin adds a dialog to quickly drop some text or clipboard
content into a zim page.

This is a core plugin shipping with zim.
'''), # T: plugin description
		'author': 'Jaap Karssenberg',
		'help': 'Plugins:Quick Note',
	}

	#~ plugin_preferences = (
		# key, type, label, default
	#~ )


class QuickNoteMainWindowExtension(MainWindowExtension):

	@action(_('Quick Note...'), menuhints='notebook') # T: menu item
	def show_quick_note(self):
		dialog = QuickNoteDialog.unique(self, self.window, self.window.notebook)
		dialog.show()


class QuickNoteDialog(Dialog):

	def __init__(self, window, notebook=None,
		page=None, namespace=None, basename=None,
		append=None, text=None, template_options=None, attachments=None
	):
		assert page is None, 'TODO'

		self.config = ConfigManager.get_config_dict('quicknote.conf')
		self.uistate = self.config['QuickNoteDialog']

		Dialog.__init__(self, window, _('Quick Note'))
		self._updating_title = False
		self._title_set_manually = not basename is None
		self.attachments = attachments

		if notebook and not isinstance(notebook, str):
			notebook = notebook.uri

		self.uistate.setdefault('lastnotebook', None, str)
		if self.uistate['lastnotebook']:
			notebook = notebook or self.uistate['lastnotebook']
			self.config['Namespaces'].setdefault(notebook, None, str)
			namespace = namespace or self.config['Namespaces'][notebook]

		self.form = InputForm()
		self.vbox.pack_start(self.form, False, True, 0)

		# TODO dropdown could use an option "Other..."
		label = Gtk.Label(label=_('Notebook') + ': ')
		label.set_alignment(0.0, 0.5)
		self.form.attach(label, 0, 1, 0, 1, xoptions=Gtk.AttachOptions.FILL)
			# T: Field to select Notebook from drop down list
		self.notebookcombobox = NotebookComboBox(current=notebook)
		self.notebookcombobox.connect('changed', self.on_notebook_changed)
		self.form.attach(self.notebookcombobox, 1, 2, 0, 1)

		self._init_inputs(namespace, basename, append, text, template_options)

		self.uistate['lastnotebook'] = notebook
		self._set_autocomplete(notebook)

	def _init_inputs(self, namespace, basename, append, text, template_options, custom=None):
		if template_options is None:
			template_options = {}
		else:
			template_options = template_options.copy()

		if namespace is not None and basename is not None:
			page = namespace + ':' + basename
		else:
			page = namespace or basename

		self.form.add_inputs((
				('page', 'page', _('Page')),
				('namespace', 'namespace', _('Page section')), # T: text entry field
				('new_page', 'bool', _('Create a new page for each note')), # T: checkbox in Quick Note dialog
				('basename', 'string', _('Title')) # T: text entry field
			))
		self.form.update({
				'page': page,
				'namespace': namespace,
				'new_page': True,
				'basename': basename,
			})

		self.uistate.setdefault('open_page', True)
		self.uistate.setdefault('new_page', True)

		if basename:
			self.uistate['new_page'] = True # Be consistent with input

		# Set up the inputs and set page/ namespace to switch on
		# toggling the checkbox
		self.form.widgets['page'].set_no_show_all(True)
		self.form.widgets['namespace'].set_no_show_all(True)
		if append is None:
			self.form['new_page'] = bool(self.uistate['new_page'])
		else:
			self.form['new_page'] = not append

		def switch_input(*a):
			if self.form['new_page']:
				self.form.widgets['page'].hide()
				self.form.widgets['namespace'].show()
				self.form.widgets['basename'].set_sensitive(True)
			else:
				self.form.widgets['page'].show()
				self.form.widgets['namespace'].hide()
				self.form.widgets['basename'].set_sensitive(False)

		switch_input()
		self.form.widgets['new_page'].connect('toggled', switch_input)

		self.open_page_check = Gtk.CheckButton.new_with_mnemonic(_('Open _Page')) # T: Option in quicknote dialog
			# Don't use "O" as accelerator here to avoid conflict with "Ok"
		self.open_page_check.set_active(self.uistate['open_page'])
		self.action_area.pack_start(self.open_page_check, False, True, 0)
		self.action_area.set_child_secondary(self.open_page_check, True)

		# Add the main textview and hook up the basename field to
		# sync with first line of the textview
		window, textview = ScrolledTextView()
		self.textview = textview
		self.textview.set_editable(True)
		self.vbox.pack_start(window, True, True, 0)

		self.form.widgets['basename'].connect('changed', self.on_title_changed)
		self.textview.get_buffer().connect('changed', self.on_text_changed)

		# Initialize text from template
		CURSOR_CHAR = '\ufffe' # unicode "non-character"
		template = get_template('plugins', 'quicknote.txt')
		template_options['text'] = text or ''
		template_options.setdefault('url', '')
		template_options['place_cursor'] = ExpressionFunction(lambda: CURSOR_CHAR)

		lines = []
		template.process(lines, template_options)
		text = ''.join(lines)

		buffer = self.textview.get_buffer()
		try:
			i = text.index(CURSOR_CHAR)
			text = text.replace(CURSOR_CHAR, '')
			buffer.set_text(text)
			iter = buffer.get_iter_at_offset(i)
			buffer.place_cursor(iter)
		except:
			buffer.set_text(text)
			buffer.place_cursor(buffer.get_end_iter())

		buffer.set_modified(False)

		self.connect('delete-event', self.do_delete_event)

	def on_notebook_changed(self, o):
		notebook = self.notebookcombobox.get_notebook()
		if not notebook or notebook == self.uistate['lastnotebook']:
			return

		self.uistate['lastnotebook'] = notebook
		self.config['Namespaces'].setdefault(notebook, None, str)
		namespace = self.config['Namespaces'][notebook]
		if namespace:
			self.form['namespace'] = namespace

		self._set_autocomplete(notebook)

	def _set_autocomplete(self, notebook):
		if notebook:
			try:
				if isinstance(notebook, str):
					notebook = NotebookInfo(notebook)
				obj, x = build_notebook(notebook)
				self.form.widgets['namespace'].notebook = obj
				self.form.widgets['page'].notebook = obj
				logger.debug('Notebook for autocomplete: %s (%s)', obj, notebook)
			except:
				logger.exception('Could not set notebook: %s', notebook)
		else:
			self.form.widgets['namespace'].notebook = None
			self.form.widgets['page'].notebook = None
			logger.debug('Notebook for autocomplete unset')

	def do_response(self, id):
		if id == Gtk.ResponseType.DELETE_EVENT:
			if self.textview.get_buffer().get_modified():
				ok = QuestionDialog(self, _('Discard note?')).run()
					# T: confirm closing quick note dialog
				if ok:
					Dialog.do_response(self, id)
				# else pass
			else:
				Dialog.do_response(self, id)
		else:
			Dialog.do_response(self, id)

	def do_delete_event(self, *a):
		# Block deletion if do_response did not yet destroy the dialog
		return True

	def run(self):
		self.textview.grab_focus()
		Dialog.run(self)

	def show(self):
		self.textview.grab_focus()
		Dialog.show(self)

	def show_all(self):
		self.textview.grab_focus()
		Dialog.show_all(self)

	def save_uistate(self):
		notebook = self.notebookcombobox.get_notebook()
		self.uistate['lastnotebook'] = notebook
		self.uistate['new_page'] = self.form['new_page']
		self.uistate['open_page'] = self.open_page_check.get_active()
		if notebook is not None:
			if self.uistate['new_page']:
				self.config['Namespaces'][notebook] = self.form['namespace']
			else:
				self.config['Namespaces'][notebook] = self.form['page']
		self.config.write()

	def on_title_changed(self, o):
		o.set_input_valid(True)
		if not self._updating_title:
			self._title_set_manually = True

	def on_text_changed(self, buffer):
		if not self._title_set_manually:
			# Automatically generate a (valid) page name
			self._updating_title = True
			start, end = buffer.get_bounds()
			text = start.get_text(end).strip()
			# Limit page name to contents of first line
			title = text.split('\n')[0]
			# Get heading 1 as the page name, if present
			heading_pattern = r'={1,}\s*(.*?)\s*={1,}'
			heading_match = re.search(heading_pattern, title)
			if heading_match:
				title = heading_match.group(1)
			# Remove colons and limit to 50 characters
			title = title.replace(':', '')[:50]
			try:
				title = Path.makeValidPageName(title)
				self.form['basename'] = title
			except ValueError:
				pass
			self._updating_title = False

	def do_response_ok(self):
		buffer = self.textview.get_buffer()
		start, end = buffer.get_bounds()
		text = start.get_text(end)

		# HACK: change "[]" at start of line into "[ ]" so checkboxes get inserted correctly
		text = re.sub(r'(?m)^(\s*)\[\](\s)', r'\1[ ]\2', text)
		# Specify "(?m)" instead of re.M since "flags" keyword is not
		# supported in python 2.6

		notebook = self._get_notebook()
		if notebook is None:
			return False

		if self.form['new_page']:
			if not self.form.widgets['namespace'].get_input_valid() \
			or not self.form['basename']:
				if not self.form['basename']:
					entry = self.form.widgets['basename']
					entry.set_input_valid(False, show_empty_invalid=True)
				return False

			path = self.form['namespace'] + self.form['basename']
			self.create_new_page(notebook, path, text)
		else:
			if not self.form.widgets['page'].get_input_valid() \
			or not self.form['page']:
				return False

			path = self.form['page']
			self.append_to_page(notebook, path, '\n------\n' + text)

		if self.attachments:
			self.import_attachments(notebook, path, self.attachments)

		if self.open_page_check.get_active():
			self.hide()
			self.get_application().open_notebook(notebook, path)

		return True

	def _get_notebook(self):
		uri = self.notebookcombobox.get_notebook()
		notebook, x = build_notebook(LocalFolder(uri))
		return notebook

	def create_new_page(self, notebook, path, text):
		page = notebook.get_new_page(path)
		page.parse('wiki', text) # FIXME format hard coded
		notebook.store_page(page)

	def append_to_page(self, notebook, path, text):
		page = notebook.get_page(path)
		page.parse('wiki', text, append=True) # FIXME format hard coded
		notebook.store_page(page)

	def import_attachments(self, notebook, path, from_dir):
		from_dir = adapt_from_oldfs(from_dir)
		attachments = notebook.get_attachments_dir(path)
		for file in from_dir.list_files():
			file.copyto(attachments)
