# -*- coding: utf-8 -*-

# Copyright 2010 Jaap Karssenberg <pardus@cpan.org>

import gtk

import re
from datetime import date as dateclass

from zim.plugins import PluginClass
from zim.config import config_file, data_file
from zim.notebook import Notebook
from zim.daemon import DaemonProxy
from zim.gui.widgets import Dialog, scrolled_text_view, IconButton
from zim.gui.notebookdialog import NotebookComboBox


usagehelp = '''\
usage: zim --plugin createnoted [OPTIONS]

Options:
  notebook=URI      Select the notebook in the dialog
  namespace=STRING  Fill in the namespace in the dialog
  basename=STRING   Fill in the page name in the dialog
  text=TEXT         Provide the text directly
  input=stdin       Provide the text on stdin
  input=clipboard   Take the text from the clipboard
'''


def main(daemonproxy, *args):
	assert daemonproxy is None, 'Not intended as daemon child'

	import os
	assert not os.name == 'nt', 'RPC not supported on windows'

	options = {}
	for arg in args:
		if '=' in arg:
			key, value = arg.split('=', 1)
			options[key] = value
		else:
			options[arg] = True

	if 'help' in options:
		print usagehelp
		return

	icon = data_file('zim.png').path
	gtk.window_set_default_icon(gtk.gdk.pixbuf_new_from_file(icon))

	dialog = CreateNoteDialog(None, options)
	dialog.run()


class CreateNotePlugin(PluginClass):

	plugin_info = {
		'name': _('Create Note'), # T: plugin name
		'description': _('''\
This plugin adds a dialog to quickly drop some text or clipboard
content into a zim page.

This is a core plugin shipping with zim.
'''), # T: plugin description
		'author': 'Jaap Karssenberg',
		'help': 'Plugins:Drop Window',
	}

	#~ plugin_preferences = (
		# key, type, label, default
	#~ )

	def show(self):
		dialog = CreateNoteDialog.unique(self, None)
		dialog.show()


class CreateNoteDialog(Dialog):

	def __init__(self, ui, options):
		self.config = config_file('createnote.conf')
		self.uistate = self.config['CreateNoteDialog']

		Dialog.__init__(self, ui, _('Create Note'))
		self._updating_title = False
		self._title_set_manually = False

		self.uistate.setdefault('lastnotebook', None)
		if self.uistate['lastnotebook']:
			notebook = self.uistate['lastnotebook']
			self.config['Namespaces'].setdefault(notebook, None)
			namespace = self.config['Namespaces'][notebook]
		else:
			notebook = None
			namespace = None

		notebook = options.get('notebook') or notebook
		namespace = options.get('namespace') or namespace
		basename = options.get('basename')

		table = gtk.Table()
		self.vbox.pack_start(table, False)

		# TODO dropdown could use an option "Other..."
		label = gtk.Label(_('Notebook')+': ')
		label.set_alignment(0.0, 0.5)
		table.attach(label, 0,1, 0,1, xoptions=gtk.FILL)
			# T: Field to select Notebook from drop down list
		self.notebookcombobox = NotebookComboBox(current=notebook)
		table.attach(self.notebookcombobox, 1,2, 0,1)

		self.add_fields( (
				('namespace', 'namespace', _('Namespace'), namespace), # T: text entry field
				('basename', 'page', _('Page Name'), basename) # T: text entry field
			), table=table, trigger_response=False,
		)

		window, textview = scrolled_text_view(text=options.get('text', None))
		self.textview = textview
		self.textview.set_editable(True)
		self.vbox.add(window)

		self.notebookcombobox.connect('changed', self.on_notebook_changed)
		self.inputs['basename'].connect('changed', self.on_title_changed)
		self.textview.get_buffer().connect('changed', self.on_text_changed)

		if 'text' in options:
			text = options['text']
		elif 'input' in options:
			if options['input'] == 'stdin':
				import sys
				text = sys.stdin.read()
			elif options['input'] == 'clipboard':
				text = gtk.Clipboard(selection='PRIMARY').wait_for_text()
				if not text:
					text = gtk.Clipboard(selection='CLIPBOARD').wait_for_text()
		else:
			text = None

		if text:
			self.textview.get_buffer().set_text(text)

	def on_notebook_changed(self, o):
		notebook = self.notebookcombobox.get_notebook()
		self.uistate['lastnotebook'] = notebook
		self.config['Namespaces'].setdefault(notebook, None)
		namespace = self.config['Namespaces'][notebook]
		if namespace:
			self.inputs['namespace'].set_text(namespace)

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
			title = Notebook.cleanup_pathname(title, purge=True)
			self.inputs['basename'].set_text(title)
			self._updating_title = False

	def do_response_ok(self):
		if not (self.inputs['namespace'].get_input_valid()
		and self.inputs['basename'].get_input_valid() ):
			return False

		notebook = self.notebookcombobox.get_notebook()
		namespace = self.inputs['namespace'].get_text()
		basename = self.inputs['basename'].get_text()
		self.uistate['lastnotebook'] = notebook
		self.config['Namespaces'][notebook] = namespace

		if not namespace or not basename:
			return False

		buffer = self.textview.get_buffer()
		bounds = buffer.get_bounds()
		text = buffer.get_text(*bounds)

		# HACK to start daemon from separate process
		# we are not allowed to fork since we already loaded gtk
		from subprocess import check_call
		from zim import ZIM_EXECUTABLE
		check_call([ZIM_EXECUTABLE, '--daemon'])

		gui = DaemonProxy().get_notebook(notebook)
		gui.new_page_from_text(text, namespace + ':' + basename)
		gui.present()
		return True

	def save_uistate(self):
		self.config.write()

