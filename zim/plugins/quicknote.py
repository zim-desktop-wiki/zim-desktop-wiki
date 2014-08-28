# -*- coding: utf-8 -*-

# Copyright 2010-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import gtk

import re
from datetime import date as dateclass

from zim.plugins import PluginClass, WindowExtension, extends
from zim.command import Command
from zim.actions import action
from zim.config import data_file, ConfigManager
from zim.notebook import Notebook, PageNameError, NotebookInfo, \
	resolve_notebook, build_notebook
from zim.ipc import start_server_if_not_running, ServerProxy
from zim.gui.widgets import Dialog, ScrolledTextView, IconButton, \
	InputForm, gtk_window_set_default_icon, QuestionDialog
from zim.gui.clipboard import Clipboard, SelectionClipboard
from zim.gui.notebookdialog import NotebookComboBox
from zim.templates import get_template


import logging

logger = logging.getLogger('zim.plugins.quicknote')


usagehelp = '''\
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


class QuickNotePluginCommand(Command):

	options = (
		('help', 'h', 'Print this help text and exit'),
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

	def parse_options(self, *args):
		self.opts['option'] = [] # allow list

		if all(not a.startswith('-') for a in args):
			# Backward compartibility for options not prefixed by "--"
			# used "=" as separator for values
			# template options came as "option:KEY=VALUE"
			for arg in args:
				if arg.startswith('option:'):
					self.opts['option'].append(arg[7:])
				elif arg == 'help':
					self.opts['help'] = True
				else:
					key, value = arg.split('=', 1)
					self.opts[key] = value
		else:
			Command.parse_options(self, *args)

		self.template_options = {}
		for arg in self.opts['option']:
			key, value = arg.split('=', 1)
			self.template_options[key] = value

		if 'append' in self.opts:
			self.opts['append'] = \
				self.opts['append'].lower() == 'true'

	def get_text(self):
		if 'input' in self.opts:
			if self.opts['input'] == 'stdin':
				import sys
				text = sys.stdin.read()
			elif self.opts['input'] == 'clipboard':
				text = \
					SelectionClipboard.get_text() \
					or Clipboard.get_text()
			else:
				raise AssertionError, 'Unknown input type: %s' % self.opts['input']
		else:
			text = self.opts.get('text')

		if text and 'encoding' in self.opts:
			if self.opts['encoding'] == 'base64':
				import base64
				text = base64.b64decode(text)
			elif self.opts['encoding'] == 'url':
				from zim.parsing import url_decode, URL_ENCODE_DATA
				text = url_decode(text, mode=URL_ENCODE_DATA)
			else:
				raise AssertionError, 'Unknown encoding: %s' % self.opts['encoding']

		if text and not isinstance(text, unicode):
			text = text.decode('utf-8')

		return text

	def run(self):
		if self.opts.get('help'):
			print usagehelp # TODO handle this in Command base class
		else:
			gtk_window_set_default_icon()

			if 'notebook' in self.opts:
				notebook = resolve_notebook(self.opts['notebook'])
			else:
				notebook = None

			dialog = QuickNoteDialog(None,
				notebook=notebook,
				namespace=self.opts.get('namespace'),
				basename=self.opts.get('basename'),
				append=self.opts.get('append'),
				text=self.get_text(),
				template_options=self.template_options,
				attachments=self.opts.get('attachments')
			)
			dialog.run()


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


@extends('MainWindow')
class MainWindowExtension(WindowExtension):

	uimanager_xml = '''
	<ui>
		<menubar name='menubar'>
			<menu action='file_menu'>
				<placeholder name="open_items">
					<menuitem action="show_quick_note" />
				</placeholder>
			</menu>
		</menubar>
	</ui>
	'''

	@action(_('Quick Note...'), stock='gtk-new') # T: menu item
	def show_quick_note(self):
		ui = self.window.ui # XXX
		notebook = self.window.ui.notebook # XXX
		dialog = BoundQuickNoteDialog.unique(self, self.window, notebook, ui)
		dialog.show()


class BoundQuickNoteDialog(Dialog):
	'''Dialog bound to a specific notebook'''

	def __init__(self, window, notebook, ui,
		page=None, namespace=None, basename=None,
		append=None, text=None, template_options=None, attachments=None
	):
		Dialog.__init__(self, window, _('Quick Note'))
		self._ui = ui
		self._updating_title = False
		self._title_set_manually = not basename is None
		self.attachments = attachments

		self.uistate.setdefault('namespace', None, basestring)
		namespace = namespace or self.uistate['namespace']

		self.form = InputForm(notebook=notebook)
		self.vbox.pack_start(self.form, False)
		self._init_inputs(namespace, basename, append, text, template_options)

	def _init_inputs(self, namespace, basename, append, text, template_options, custom=None):
		if template_options is None:
			template_options = {}
		else:
			template_options = template_options.copy()

		if namespace is not None and basename is not None:
			page = namespace + ':' + basename
		else:
			page = namespace or basename

		self.form.add_inputs( (
				('page', 'page', _('Page')),
				('namespace', 'namespace', _('Page section')), # T: text entry field
				('new_page', 'bool', _('Create a new page for each note')), # T: checkbox in Quick Note dialog
				('basename', 'string', _('Title')) # T: text entry field
			) )
		self.form.update({
				'page': page,
				'namespace': namespace,
				'new_page': True,
				'basename': basename,
			} )

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

		self.open_page = gtk.CheckButton(_('Open _Page')) # T: Option in quicknote dialog
			# Don't use "O" as accelerator here to avoid conflict with "Ok"
		self.open_page.set_active(self.uistate['open_page'])
		self.action_area.pack_start(self.open_page, False)
		self.action_area.set_child_secondary(self.open_page, True)

		# Add the main textview and hook up the basename field to
		# sync with first line of the textview
		window, textview = ScrolledTextView()
		self.textview = textview
		self.textview.set_editable(True)
		self.vbox.add(window)

		self.form.widgets['basename'].connect('changed', self.on_title_changed)
		self.textview.get_buffer().connect('changed', self.on_text_changed)

		# Initialize text from template
		template = get_template('plugins', 'quicknote.txt')
		template_options['text'] = text or ''
		template_options.setdefault('url', '')

		lines = []
		template.process(lines, template_options)
		buffer = self.textview.get_buffer()
		buffer.set_text(''.join(lines))
		begin, end = buffer.get_bounds()
		buffer.place_cursor(begin)

		buffer.set_modified(False)

		self.connect('delete-event', self.do_delete_event)

	def do_response(self, id):
		if id == gtk.RESPONSE_DELETE_EVENT:
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

	def save_uistate(self):
		self.uistate['new_page'] = self.form['new_page']
		self.uistate['open_page'] = self.open_page.get_active()
		if self.uistate['new_page']:
			self.uistate['namespace'] = self.form['namespace']
		else:
			self.uistate['namespace'] = self.form['page']

	def on_title_changed(self, o):
		o.set_input_valid(True)
		if not self._updating_title:
			self._title_set_manually = True

	def on_text_changed(self, buffer):
		if not self._title_set_manually:
			# Automatically generate a (valid) page name
			self._updating_title = True
			bounds = buffer.get_bounds()
			title = buffer.get_text(*bounds).strip()[:50]
				# Cut off at 50 characters to prevent using a whole paragraph
			title = title.replace(':', '')
			if '\n' in title:
				title, _ = title.split('\n', 1)
			try:
				title = Notebook.cleanup_pathname(title, purge=True)
				self.form['basename'] = title
			except PageNameError:
				pass
			self._updating_title = False

	def _get_ui(self):
		return self._ui

	def do_response_ok(self):
		# NOTE: Keep in mind that this method should also work using
		# a proxy object for the ui. This is why we have the get_ui()
		# argument to construct a proxy.

		buffer = self.textview.get_buffer()
		bounds = buffer.get_bounds()
		text = buffer.get_text(*bounds)

		# HACK: change "[]" at start of line into "[ ]" so checkboxes get inserted correctly
		text = re.sub(r'(?m)^(\s*)\[\](\s)', r'\1[ ]\2', text)
		# Specify "(?m)" instead of re.M since "flags" keyword is not
		# supported in python 2.6


		ui = self._get_ui()
		if ui is None:
			return False

		if self.form['new_page']:
			if not self.form.widgets['namespace'].get_input_valid() \
			or not self.form['basename']:
				if not self.form['basename']:
					entry = self.form.widgets['basename']
					entry.set_input_valid(False, show_empty_invalid=True)
				return False

			path = self.form['namespace'].name + ':' + self.form['basename']
			ui.new_page_from_text(text, path,
				attachments=self.attachments,
				open_page=self.open_page.get_active()
			)
		else:
			if not self.form.widgets['page'].get_input_valid() \
			or not self.form['page']:
				return False

			path = self.form['page'].name
			if self.attachments:
				ui.import_attachments(path, self.attachments)
			ui.append_text_to_page(path, '\n----\n'+text)
			if self.open_page.get_active():
				ui.present(path) # also works with proxy

		return True


class QuickNoteDialog(BoundQuickNoteDialog):
	'''Dialog which includes a notebook chooser'''

	def __init__(self, window, notebook=None,
		page=None, namespace=None, basename=None,
		append=None, text=None, template_options=None, attachments=None
	):
		assert page is None, 'TODO'
		manager = ConfigManager() # FIXME should be passed in
		self.config = manager.get_config_dict('quicknote.conf')
		self.uistate = self.config['QuickNoteDialog']

		Dialog.__init__(self, window, _('Quick Note'))
		self._updating_title = False
		self._title_set_manually = not basename is None
		self.attachments = attachments

		if notebook and not isinstance(notebook, basestring):
			notebook = notebook.uri

		self.uistate.setdefault('lastnotebook', None, basestring)
		if self.uistate['lastnotebook']:
			notebook = notebook or self.uistate['lastnotebook']
			self.config['Namespaces'].setdefault(notebook, None, basestring)
			namespace = namespace or self.config['Namespaces'][notebook]

		self.form = InputForm()
		self.vbox.pack_start(self.form, False)

		# TODO dropdown could use an option "Other..."
		label = gtk.Label(_('Notebook')+': ')
		label.set_alignment(0.0, 0.5)
		self.form.attach(label, 0,1, 0,1, xoptions=gtk.FILL)
			# T: Field to select Notebook from drop down list
		self.notebookcombobox = NotebookComboBox(current=notebook)
		self.notebookcombobox.connect('changed', self.on_notebook_changed)
		self.form.attach(self.notebookcombobox, 1,2, 0,1)

		self._init_inputs(namespace, basename, append, text, template_options)

		self.uistate['lastnotebook'] = notebook
		self._set_autocomplete(notebook)

	def save_uistate(self):
		notebook = self.notebookcombobox.get_notebook()
		self.uistate['lastnotebook'] = notebook
		self.uistate['new_page'] = self.form['new_page']
		self.uistate['open_page'] = self.open_page.get_active()
		if notebook is not None:
			if self.uistate['new_page']:
				self.config['Namespaces'][notebook] = self.form['namespace']
			else:
				self.config['Namespaces'][notebook] = self.form['page']
		self.config.write()

	def on_notebook_changed(self, o):
		notebook = self.notebookcombobox.get_notebook()
		if not notebook or notebook == self.uistate['lastnotebook']:
			return

		self.uistate['lastnotebook'] = notebook
		self.config['Namespaces'].setdefault(notebook, None, basestring)
		namespace = self.config['Namespaces'][notebook]
		if namespace:
			self.form['namespace'] = namespace

		self._set_autocomplete(notebook)

	def _set_autocomplete(self, notebook):
		if notebook:
			if isinstance(notebook, basestring):
				notebook = NotebookInfo(notebook)
			obj, x = build_notebook(notebook)
			self.form.widgets['namespace'].notebook = obj
			self.form.widgets['page'].notebook = obj
			logger.debug('Notebook for autocomplete: %s (%s)', obj, notebook)
		else:
			self.form.widgets['namespace'].notebook = None
			self.form.widgets['page'].notebook = None
			logger.debug('Notebook for autocomplete unset')

	def _get_ui(self):
		start_server_if_not_running()
		notebook = self.notebookcombobox.get_notebook()
		if notebook:
			return ServerProxy().get_notebook(notebook)
		else:
			return None
