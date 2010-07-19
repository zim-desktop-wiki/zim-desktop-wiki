# -*- coding: utf-8 -*-

# Copyright 2010 Jaap Karssenberg <pardus@cpan.org>

import gtk

import re
from datetime import date as dateclass

from zim.plugins import PluginClass
from zim.config import config_file, data_file
from zim.notebook import Notebook, PageNameError
from zim.daemon import DaemonProxy
from zim.gui.widgets import Dialog, scrolled_text_view, IconButton, \
	gtk_window_set_default_icon
from zim.gui.notebookdialog import NotebookComboBox
from zim.templates import GenericTemplate, StrftimeFunction


usagehelp = '''\
usage: zim --plugin quicknoted [OPTIONS]

Options:
  notebook=URI       Select the notebook in the dialog
  namespace=STRING   Fill in the namespace in the dialog
  basename=STRING    Fill in the page name in the dialog
  text=TEXT          Provide the text directly
  input=stdin        Provide the text on stdin
  input=clipboard    Take the text from the clipboard
  base64             Text is encoded in base64
                     expects utf-8 after base64 decoding
  option:url=STRING  Set template parameter
'''


def main(daemonproxy, *args):
	assert daemonproxy is None, 'Not intended as daemon child'

	import os
	assert not os.name == 'nt', 'RPC not supported on windows'

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

	if 'input' in options:
		if options['input'] == 'stdin':
			import sys
			text = sys.stdin.read()
		elif options['input'] == 'clipboard':
			text = \
				gtk.Clipboard(selection='PRIMARY').wait_for_text() \
				or gtk.Clipboard(selection='CLIPBOARD').wait_for_text()
	else:
		text = options.get('text')

	if text and options.get('base64'):
		import base64
		text = base64.b64decode(text)

	if text and not isinstance(text, unicode):
		text = text.decode('utf-8')

	icon = data_file('zim.png').path
	gtk_window_set_default_icon()

	dialog = QuickNoteDialog(None,
		options.get('notebook'),
		options.get('namespace'), options.get('basename'),
		text, template_options )
	dialog.run()


ui_actions = (
	# name, stock id, label, accelerator, tooltip, read only
	('show_quick_note', 'gtk-new', _('Quick Note...'), '', '', True), # T: menu item
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

	def __init__(self, ui, namespace=None, basename=None, text=None, template_options=None):
		Dialog.__init__(self, ui, _('Quick Note'))
		self._updating_title = False
		self._title_set_manually = False

		self.uistate.setdefault('namespace', None)
		namespace = namespace or self.uistate['namespace']

		self._init_inputs(namespace, basename, text, template_options)

	def _init_inputs(self, namespace, basename, text, template_options, table=None):
		if template_options is None: template_options = {}
		else: template_options = template_options.copy()

		# Set up the inputs and set page/ namespace to switch on
		# toggling the checkbox
		table = self.add_fields( (
				('page', 'page', _('Page'), namespace),
				('namespace', 'namespace', _('Namespace'), namespace), # T: text entry field
				('newpage', 'bool', _('Create a new page for each note'), False), # T: checkbox in Quick Note dialog
				('basename', 'page', _('Title'), basename) # T: text entry field
			), table=table, trigger_response=False )

		self.inputs['page'].set_no_show_all(True)
		self.inputs['namespace'].set_no_show_all(True)

		def switch_input(*a):
			if self.inputs['newpage'].get_active():
				self.inputs['page'].hide()
				self.inputs['namespace'].show()
				self.inputs['basename'].set_sensitive(True)
			else:
				self.inputs['page'].show()
				self.inputs['namespace'].hide()
				self.inputs['basename'].set_sensitive(False)

		switch_input()
		self.inputs['newpage'].connect('toggled', switch_input)

		# Add the main textview and hook up the basename field to
		# sync with first line of the textview
		window, textview = scrolled_text_view()
		self.textview = textview
		self.textview.set_editable(True)
		self.vbox.add(window)

		self.inputs['basename'].connect('changed', self.on_title_changed)
		self.textview.get_buffer().connect('changed', self.on_text_changed)

		# Initialize text from template
		file = data_file('templates/_quicknote.txt')
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

	def run(self):
		self.textview.grab_focus()
		Dialog.run(self)

	def show(self):
		self.textview.grab_focus()
		Dialog.show(self)

	def save_uistate(self):
		self.uistate['newpage'] = self.inputs['newpage'].get_active()
		if self.uistate['newpage']:
			self.uistate['namespace'] = self.inputs['namespace'].get_text()
		else:
			self.uistate['namespace'] = self.inputs['page'].get_text()

	def on_title_changed(self, o):
		if not self._updating_title:
			self._title_set_manually = True

	def on_text_changed(self, buffer):
		if not self._title_set_manually:
			# Automatically generate a (valid) page name
			self._updating_title = True
			bounds = buffer.get_bounds()
			title = buffer.get_text(*bounds).strip()[:25]
			title = title.replace(':', '')
			if '\n' in title:
				title, _ = title.split('\n', 1)
			try:
				title = Notebook.cleanup_pathname(title, purge=True)
				self.inputs['basename'].set_text(title)
			except PageNameError:
				pass
			self._updating_title = False

	def do_response_ok(self, get_ui=None):
		newpage = self.inputs['newpage'].get_active()
		page = self.inputs['page'].get_text()
		namespace = self.inputs['namespace'].get_text()
		basename = self.inputs['basename'].get_text()

		buffer = self.textview.get_buffer()
		bounds = buffer.get_bounds()
		text = buffer.get_text(*bounds)

		if newpage:
			if not self.inputs['namespace'].get_input_valid() \
			or not self.inputs['basename'].get_input_valid():
				return False
			elif not basename:
				self.inputs['basename'].set_input_valid(False)
				return False

			if get_ui: ui = get_ui()
			else: ui = self.ui
			ui.new_page_from_text(text, namespace + ':' + basename)
		else:
			if not self.inputs['page'].get_input_valid() \
			or not page:
				self.inputs['page'].set_input_valid(False)
				return False

			if get_ui: ui = get_ui()
			else: ui = self.ui
			ui.append_text_to_page(page, '\n----\n'+text)

		ui.present()
		return True


class QuickNoteDialog(BoundQuickNoteDialog):
	'''Dialog which includes a notebook chooser'''

	def __init__(self, ui, notebook=None, namespace=None, basename=None, text=None, template_options=None):
		self.config = config_file('quicknote.conf')
		self.uistate = self.config['QuickNoteDialog']

		Dialog.__init__(self, ui, _('Quick Note'))
		self._updating_title = False
		self._title_set_manually = False

		self.uistate.setdefault('lastnotebook', None)
		if self.uistate['lastnotebook']:
			notebook = notebook or self.uistate['lastnotebook']
			self.config['Namespaces'].setdefault(notebook, None)
			namespace = namespace or self.config['Namespaces'][notebook]

		table = gtk.Table()
		self.vbox.pack_start(table, False)

		# TODO dropdown could use an option "Other..."
		label = gtk.Label(_('Notebook')+': ')
		label.set_alignment(0.0, 0.5)
		table.attach(label, 0,1, 0,1, xoptions=gtk.FILL)
			# T: Field to select Notebook from drop down list
		self.notebookcombobox = NotebookComboBox(current=notebook)
		self.notebookcombobox.connect('changed', self.on_notebook_changed)
		table.attach(self.notebookcombobox, 1,2, 0,1)

		self._init_inputs(namespace, basename, text, template_options, table)

	def save_uistate(self):
		notebook = self.notebookcombobox.get_notebook()
		self.uistate['lastnotebook'] = notebook
		self.uistate['newpage'] = self.inputs['newpage'].get_active()
		if self.uistate['newpage']:
			self.config['Namespaces'][notebook] = self.inputs['namespace'].get_text()
		else:
			self.config['Namespaces'][notebook] = self.inputs['page'].get_text()
		self.config.write()

	def on_notebook_changed(self, o):
		notebook = self.notebookcombobox.get_notebook()
		self.uistate['lastnotebook'] = notebook
		self.config['Namespaces'].setdefault(notebook, None)
		namespace = self.config['Namespaces'][notebook]
		if namespace:
			self.inputs['namespace'].set_text(namespace)

	def do_response_ok(self):
		def get_ui():
			# HACK to start daemon from separate process
			# we are not allowed to fork since we already loaded gtk
			from subprocess import check_call
			from zim import ZIM_EXECUTABLE
			check_call([ZIM_EXECUTABLE, '--daemon'])

			notebook = self.notebookcombobox.get_notebook()
			return DaemonProxy().get_notebook(notebook)

		return BoundQuickNoteDialog.do_response_ok(self, get_ui)

