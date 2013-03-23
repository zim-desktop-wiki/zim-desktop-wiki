# -*- coding: utf-8 -*-

# Copyright 2010 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import gtk

import re
from datetime import date as dateclass

from zim.plugins import PluginClass
from zim.config import get_config, data_file
from zim.notebook import resolve_notebook, get_notebook, Notebook, PageNameError
from zim.ipc import start_server_if_not_running, ServerProxy
from zim.gui.widgets import Dialog, ScrolledTextView, IconButton, \
	InputForm, gtk_window_set_default_icon, QuestionDialog
from zim.gui.clipboard import Clipboard, SelectionClipboard
from zim.gui.notebookdialog import NotebookComboBox
from zim.templates import GenericTemplate, StrftimeFunction


import logging

logger = logging.getLogger('zim.plugins.quicknote')


usagehelp = '''\
usage: zim --plugin quicknote [OPTIONS]

Options:
  notebook=URI         Select the notebook in the dialog
  page=STRING          Fill in full page name
  namespace=STRING     Fill in the namespace in the dialog
  basename=STRING      Fill in the page name in the dialog
  append=[true|false]  Set whether to append or create new page
  text=TEXT            Provide the text directly
  input=stdin          Provide the text on stdin
  input=clipboard      Take the text from the clipboard
  encoding=base64      Text is encoded in base64
  encoding=url         Text is url encoded
                       (In both cases expects UTF-8 after decoding)
  attachments=FOLDER   Import all files in FOLDER as attachments,
                       wiki input can refer these files relatively
  option:url=STRING    Set template parameter
'''


def main(*args):
	options = {}
	template_options = {}
	for arg in args:
		if arg.startswith('option:'):
			arg = arg[7:]
			dict = template_options
		else:
			dict = options

		if '=' in arg:
			key, value = arg.split('=', 1)
			dict[key] = value
		else:
			dict[arg] = True
	#~ print 'OPTIONS:', options, template_options

	if 'help' in options:
		print usagehelp
		return

	if 'notebook' in options:
		notebook, page = resolve_notebook(options['notebook'])
	else:
		notebook = None

	if 'append' in options:
		if options['append'].lower() == 'true':
			options['append'] = True
		else:
			options['append'] = False

	if 'input' in options:
		if options['input'] == 'stdin':
			import sys
			text = sys.stdin.read()
		elif options['input'] == 'clipboard':
			text = \
				SelectionClipboard.get_text() \
				or Clipboard.get_text()
	else:
		text = options.get('text')

	if text and options.get('encoding'):
		if options['encoding'] == 'base64':
			import base64
			text = base64.b64decode(text)
		elif options['encoding'] == 'url':
			from zim.parsing import url_decode, URL_ENCODE_DATA
			text = url_decode(text, mode=URL_ENCODE_DATA)
		else:
			raise AssertionError, 'Unknown encoding: %s' % options['encoding']

	if text and not isinstance(text, unicode):
		text = text.decode('utf-8')

	icon = data_file('zim.png').path
	gtk_window_set_default_icon()

	dialog = QuickNoteDialog(None,
		notebook,
		options.get('namespace'), options.get('basename'),
		options.get('append'),
		text,
		template_options,
		options.get('attachments')
	)
	dialog.run()


ui_actions = (
	# name, stock id, label, accelerator, tooltip, read only
	('show_quick_note', 'gtk-new', _('Quick Note...'), '', '', False), # T: menu item
)

ui_xml = '''
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

	def initialize_ui(self, ui):
		if ui.ui_type == 'gtk':
			ui.add_actions(ui_actions, self)
			ui.add_ui(ui_xml, self)

	def show_quick_note(self):
		dialog = BoundQuickNoteDialog.unique(self, self.ui, {})
		dialog.show()


class BoundQuickNoteDialog(Dialog):
	'''Dialog bound to a specific notebook'''

	def __init__(self, ui, page=None, namespace=None, basename=None, append=None, text=None, template_options=None, attachments=None):
		Dialog.__init__(self, ui, _('Quick Note'))
		self._updating_title = False
		self._title_set_manually = not basename is None
		self.attachments = attachments

		self.uistate.setdefault('namespace', None, basestring)
		namespace = namespace or self.uistate['namespace']

		self.form = InputForm(notebook=self.ui.notebook)
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
				('namespace', 'namespace', _('Namespace')), # T: text entry field
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
		file = data_file('templates/plugins/quicknote.txt')
		template = GenericTemplate(file.readlines(), name=file)
		template_options.update({
			'text': text or '',
			'strftime': StrftimeFunction(),
		} )
		output = template.process(template_options)
		buffer = self.textview.get_buffer()
		buffer.set_text(''.join(output))
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

	def do_response_ok(self, get_ui=None):
		# NOTE: Keep in mind that this method should also work using
		# a proxy object for the ui. This is why we have the get_ui()
		# argument to construct a proxy.

		buffer = self.textview.get_buffer()
		bounds = buffer.get_bounds()
		text = buffer.get_text(*bounds)

		if self.form['new_page']:
			if not self.form.widgets['namespace'].get_input_valid() \
			or not self.form['basename']:
				if not self.form['basename']:
					entry = self.form.widgets['basename']
					entry.set_input_valid(False, show_empty_invalid=True)
				return False

			if get_ui: ui = get_ui()
			else: ui = self.ui
			if ui is None:
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

			if get_ui: ui = get_ui()
			else: ui = self.ui
			if ui is None:
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

	def __init__(self, ui, notebook=None, namespace=None, basename=None, append=None, text=None, template_options=None, attachments=None):
		self.config = get_config('quicknote.conf')
		self.uistate = self.config['QuickNoteDialog']

		Dialog.__init__(self, ui, _('Quick Note'))
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
			obj = get_notebook(notebook)
			self.form.widgets['namespace'].notebook = obj
			self.form.widgets['page'].notebook = obj
			# Could still be None, e.g. if the notebook folder is not mounted
			logger.debug('Notebook for autocomplete: %s (%s)', obj, notebook)
		else:
			self.form.widgets['namespace'].notebook = None
			self.form.widgets['page'].notebook = None
			logger.debug('Notebook for autocomplete unset')

	def do_response_ok(self):
		def get_ui():
			start_server_if_not_running()
			notebook = self.notebookcombobox.get_notebook()
			if notebook:
				return ServerProxy().get_notebook(notebook)
			else:
				return None

		return BoundQuickNoteDialog.do_response_ok(self, get_ui)
