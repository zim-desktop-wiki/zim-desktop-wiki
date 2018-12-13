
# Copyright 2008-2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains the notebook dialog which is used for the
"open another notebook" action and which is shown if you start zim without
argument. The dialog directly modifies the notebook list obtained from
zim.notebook.get_notebook_list(). A special dropdown allows settign the
special entry for the default notebook which will be openend directly
the next time zim is started without arguments.

@newfield column: Column, Columns
'''

from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango
from gi.repository import GdkPixbuf

import os
import logging

import zim.main
from zim.fs import File, Dir
from zim.notebook import get_notebook_list, get_notebook_info, init_notebook, NotebookInfo
from zim.config import data_file
from zim.gui.widgets import Dialog, IconButton, encode_markup_text, ScrolledWindow, \
	strip_boolean_result

logger = logging.getLogger('zim.gui.notebookdialog')


OPEN_COL = 0   # column with boolean if notebook is open already
NAME_COL = 1   # column with notebook name
TEXT_COL = 2   # column with a formatted containing name and path
PIXBUF_COL = 3 # column containing the notebook icon
INFO_COL = 4   # column with the NotebookInfo object


def _run_dialog_with_mainloop(dialog):
	# Apparently Gtk.Dialog.run() does not work outside of a main loop
	from zim.gui.widgets import TEST_MODE, TEST_MODE_RUN_CB
	if TEST_MODE and TEST_MODE_RUN_CB:
		TEST_MODE_RUN_CB(dialog)
	else:
		dialog.show_all()
		dialog.present()
		dialog.connect("response", lambda *a: Gtk.main_quit())
		Gtk.main()
	return dialog.result

def prompt_notebook():
	'''Prompts the NotebookDialog and returns the result or None.
	As a special case for first time usage it immediately prompts for
	the notebook location without showing the notebook list.
	@returns: a L{NotebookInfo} object or C{None}
	'''
	list = get_notebook_list()
	if len(list) == 0:
		logger.debug('First time usage - prompt for notebook folder')
		fields = _run_dialog_with_mainloop(AddNotebookDialog(None))
		if fields:
			dir = Dir(fields['folder'])
			init_notebook(dir, name=fields['name'])
			list.append(NotebookInfo(dir.uri, name=fields['name']))
			list.write()
			return NotebookInfo(dir.uri, name=fields['name'])
		else:
			return None # User canceled the dialog ?
	else:
		# Multiple notebooks defined and no default
		return _run_dialog_with_mainloop(NotebookDialog(None))


class NotebookTreeModel(Gtk.ListStore):
	'''TreeModel that wraps a notebook list

	@column: C{OPEN_COL}: boolean, True if the notebook is opened already
	@column: C{NAME_COL}: string, name of the notebook
	@column: C{TEXT_COL}: string, formatted string containg the name and path
	@column: C{PIXBUF_COL}: GdkPixbuf.Pixbuf, the icon of the notebook (if any)
	@column: C{INFO_COL}: L{NotebookInfo} object

	@note: To refer to the notebook in an unambiguous way, use the uri stored
	in the L{NotebookInfo} object.
	'''

	def __init__(self, notebooklist=None):
		'''Constructor. If "notebooklist" is None, the default list as
		provided by zim.notebook.get_notebook_list() is used.

		@param notebooklist: a list of L{NotebookInfo} objects
		'''
		Gtk.ListStore.__init__(self, bool, str, str, GdkPixbuf.Pixbuf, object)
						# OPEN_COL, NAME_COL, TEXT_COL PIXBUF_COL INFO_COL

		if notebooklist is None:
			self.notebooklist = get_notebook_list()
		else:
			self.notebooklist = notebooklist

		self._loading = True
		for info in self.notebooklist:
			self._append(info)
		self._loading = False

	def get_iter_for_notebook(self, uri):
		'''Returns the TreeIter for a notebook path or None'''
		assert uri.startswith('file://')
		for row in self:
			if row[INFO_COL].uri == uri:
				return row.iter
		else:
			return None

	def append_notebook(self, uri, name=None):
		'''Append a notebook to the list. If the name is not specified
		it will be looked up by reading the config file of the notebook.
		Returns an iter for this notebook in the list.
		'''
		assert uri.startswith('file://')
		info = NotebookInfo(uri, name=name)
		info.update()
		self._append(info)
		self.write()
		return len(self) - 1 # iter

	def _append(self, info):
		path = File(info.uri).path
		text = '<b>%s</b>\n<span foreground="#5a5a5a" size="small">%s</span>' % \
				(encode_markup_text(info.name), encode_markup_text(path))
				# T: Path label in 'open notebook' dialog

		if info.icon and File(info.icon).exists():
			w, h = strip_boolean_result(Gtk.icon_size_lookup(Gtk.IconSize.BUTTON))
			pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(File(info.icon).path, w, h)
		else:
			pixbuf = None

		self.append((False, info.name, text, pixbuf, info))
				# OPEN_COL NAME_COL TEXT_COL PIXBUF_COL INFO_COL

	def get_iter_for_default(self):
		'''Returns a TreeIter for the default notebook or None'''
		if self.notebooklist.default:
			return self.get_iter_for_notebook(self.notebooklist.default.uri)
		else:
			return None

	def set_default_from_iter(self, iter):
		'''Set the default notebook using a TreeIter,
		set to None to reset the default.
		'''
		if iter is None:
			self.notebooklist.default = None
		else:
			self.notebooklist.default = self[iter][INFO_COL]
		self.write()

	def write(self):
		'''Save the notebook list.'''
		if self._loading:
			return # ignore signals while first populating the list

		list = [row[INFO_COL] for row in self]
		self.notebooklist[:] = list
		self.notebooklist.write()


class NotebookTreeView(Gtk.TreeView):

	def __init__(self, model=None):
		# TODO: add logic to flag open notebook italic - needs daemon
		if model is None:
			model = NotebookTreeModel()
		GObject.GObject.__init__(self)
		self.set_model(model)
		self.get_selection().set_mode(Gtk.SelectionMode.BROWSE)
		self.set_rules_hint(True)
		self.set_reorderable(True)

		cell_renderer = Gtk.CellRendererPixbuf()
		column = Gtk.TreeViewColumn(None, cell_renderer, pixbuf=PIXBUF_COL)
		column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
		w, h = strip_boolean_result(Gtk.icon_size_lookup(Gtk.IconSize.MENU))
		column.set_fixed_width(w * 2)
		self.append_column(column)

		cell_renderer = Gtk.CellRendererText()
		cell_renderer.set_property('ellipsize', Pango.EllipsizeMode.END)
		cell_renderer.set_fixed_height_from_font(2)
		column = Gtk.TreeViewColumn(_('Notebook'), cell_renderer, markup=TEXT_COL)
			# T: Column heading in 'open notebook' dialog
		column.set_sort_column_id(NAME_COL)
		self.append_column(column)



class NotebookComboBox(Gtk.ComboBox):
	'''Combobox showing the a list of notebooks'''

	def __init__(self, model=None, current=None):
		'''Constructor,

		@param model: either a L{NotebookTreeModel} or C{None} to use
		the default list.
		@param current: uri, C{Dir}, C{NotebookInfo}, or C{Notebook}
		object for the current notebook. If C{None} the default
		notebook will be shown (if any).
		'''
		if model is None:
			model = NotebookTreeModel()
		GObject.GObject.__init__(self)
		self.set_model(model)
		cell_renderer = Gtk.CellRendererText()
		self.pack_start(cell_renderer, True)
		self.add_attribute(cell_renderer, 'text', NAME_COL)

		if current:
			self.set_notebook(current, append=True)
		else:
			self.set_default_active()

	def set_default_active(self):
		'''Select the default notebook in the combobox or clear the
		combobox if no default notebook was defined.
		'''
		model = self.get_model()
		iter = model.get_iter_for_default()
		if iter is None:
			self.set_active(-1)
		else:
			self.set_active_iter(iter)

	def set_notebook(self, uri, append=False):
		'''Select a specific notebook in the combobox.

		@param uri: uri, C{Dir}, C{NotebookInfo}, or C{Notebook}
		object for a notebook (string or any object with an C{uri}
		property)
		@param append: if C{True} the notebook will appended to the list
		if it was not listed yet.
		'''
		if isinstance(uri, str):
			assert uri.startswith('file://')
		else:
			assert hasattr(uri, 'uri')
			uri = uri.uri

		model = self.get_model()
		iter = model.get_iter_for_notebook(uri)
		if iter is None:
			if append:
				i = model.append_notebook(uri)
				self.set_active(i)
			else:
				self.set_active(-1)
		else:
			self.set_active_iter(iter)

	def get_notebook(self):
		'''Returns the uri for the current selected notebook'''
		iter = self.get_active()
		if iter == -1:
			return None
		else:
			model = self.get_model()
			return model[iter][INFO_COL].uri


class DefaultNotebookComboBox(NotebookComboBox):
	'''Combobox which sets the default notebook'''

	def __init__(self, model=None):
		NotebookComboBox.__init__(self, model, current=None)
		self.connect('changed', self.__class__.do_changed)

	def do_changed(self):
		# Set default if triggered by user action
		model = self.get_model()
		iter = self.get_active()
		if iter >= 0:
			model.set_default_from_iter(iter)
		else:
			model.set_default_from_iter(None)


class NotebookDialog(Dialog):
	'''Dialog which allows the user to select a notebook from a list
	of defined notebooks.

	Can either be run modal using run(), in which case the selected
	notebook is returned (or None when the dialog is canceled).
	To run this dialog non-model a callback needs to be specified
	which will be called with the path for the selected notebook.
	'''

	def __init__(self, parent, callback=None):
		Dialog.__init__(self, parent, _('Open Notebook')) # T: dialog title
		# TODO set button to "OPEN" instead of "OK"
		self.callback = callback
		self.set_default_size(500, 400)
		self.set_help(':Help:Notebooks')

		# show some art work in an otherwise boring dialog
		path = data_file('globe_banner_small.png').path
		image = Gtk.Image()
		image.set_from_file(path) # new_from_file not in 2.6
		align = Gtk.Alignment.new(0, 0.5, 0, 0)
		align.add(image)
		self.vbox.pack_start(align, False, True, 0)

		# split between treeview and vbuttonbox
		hbox = Gtk.HBox(spacing=12)
		self.vbox.pack_start(hbox, True, True, 0)

		# add notebook list - open notebook on clicking a row
		self.treeview = NotebookTreeView()
		self.treeview.connect(
			'row-activated', lambda *a: self.response(Gtk.ResponseType.OK))

		hbox.add(ScrolledWindow(self.treeview))

		# add buttons for modifying the treeview
		vbbox = Gtk.VButtonBox()
		vbbox.set_layout(Gtk.ButtonBoxStyle.START)
		hbox.pack_start(vbbox, False, True, 0)
		add_button = Gtk.Button.new_with_mnemonic(_('_Add')) # T: Button label
		add_button.connect('clicked', self.do_add_notebook)
		#~ edit_button = Gtk.Button.new_with_mnemonic(_('_Edit')) # T: Button label
		#~ edit_button.connect('clicked', self.do_edit_notebook)
		rm_button = Gtk.Button.new_with_mnemonic(_('_Remove')) # T: Button label
		rm_button.connect('clicked', self.do_remove_notebook)
		#~ for b in (add_button, edit_button, rm_button):
		for b in (add_button, rm_button):
			b.set_alignment(0.0, 0.5)
			vbbox.add(b)
		# FIXME buttons for "up" and "down" ?

		# add dropdown to select default
		self.combobox = DefaultNotebookComboBox(self.treeview.get_model())

		# clear button de-selects any item in the combobox
		clear_button = IconButton('gtk-clear')
		clear_button.connect('clicked', lambda o: self.combobox.set_active(-1))

		hbox = Gtk.HBox(spacing=5)
		hbox.pack_start(Gtk.Label(_('Default notebook') + ': '), False, True, 0)
			# T: Input label in 'open notebook' dialog
		hbox.pack_start(self.combobox, False, True, 0)
		hbox.pack_start(clear_button, False, True, 0)
		self.vbox.pack_start(hbox, False, True, 0)

	def show_all(self):
		# We focus on the treeview so that the user can start typing the
		# notebook name directly when the dialog opens.
		Dialog.show_all(self)
		self.treeview.grab_focus()

	def do_response_ok(self):
		model, iter = self.treeview.get_selection().get_selected()
		model.write() # List will be read by open_notebook again..
		if iter is None:
			return False
		else:
			self.result = model[iter][INFO_COL]
			if self.callback:
				self.callback(self.result)
			return True

	def do_add_notebook(self, *a):
		fields = AddNotebookDialog(self).run()
		if fields:
			dir = Dir(fields['folder'])
			init_notebook(dir, name=fields['name'])
			model = self.treeview.get_model()
			model.append_notebook(dir.uri, name=fields['name'])

	#~ def do_edit_notebook(self, *a):
		#~ model, iter = self.treeview.get_selection().get_selected()
		#~ if iter is None:
			#~ return
		#~ name = unicode(model[iter][NAME_COL])
		#~ folder = unicode(model[iter][PATH_COL])
		#~ properties = EditNotebookDialog(self, name, folder).run()
		#~ if properties:
			#~ model.set(iter,
				#~ OPEN_COL, False,
				#~ NAME_COL, properties['name'],
				#~ PATH_COL, properties['folder'] )
			#~ model.write()

	def do_remove_notebook(self, *a):
		model, iter = self.treeview.get_selection().get_selected()
		model.remove(iter)
		# explicitly _no_ model.write()

	def show_help(self, page=None):
		zim.main.ZIM_APPLICATION.run('--manual', page or self.help_page)


class AddNotebookDialog(Dialog):

	def __init__(self, parent, name=None, folder=None):
		Dialog.__init__(self, parent, _('Add Notebook')) # T: Dialog window title

		label = Gtk.Label(label=_('Please select a name and a folder for the notebook.')) # T: Label in Add Notebook dialog
		label.set_alignment(0.0, 0.5)
		self.vbox.pack_start(label, False, True, 0)

		self._name_set = not name is None
		self._folder_set = not folder is None

		nb_folder = '~/Notebooks/'

		if not self._name_set and not self._folder_set:
			name = 'Notes'
			folder = nb_folder + name
		# else set below by _changed methods

		self.add_form((
			('name', 'string', _('Name')), # T: input field in 'Add Notebook' dialog
			('folder', 'dir', _('Folder')), # T: input field in 'Add Notebook' dialog
		), {
			'name': name,
			'folder': folder,
		})

		self.add_help_text(_('''\
To create a new notebook you need to select an empty folder.
Of course you can also select an existing zim notebook folder.
''')) # T: help text in the 'Add Notebook' dialog

		# Hook entries to copy name when appropriate
		self._block_update = False
		self.on_name_changed(None, interactive=False)
		self.on_folder_changed(None, interactive=False)
		self.form.widgets['name'].connect('changed', self.on_name_changed)
		self.form.widgets['folder'].connect('changed', self.on_folder_changed)

	def on_name_changed(self, o, interactive=True):
		# When name is changed, update folder accordingly
		# unless the folder was set explicitly already
		if self._block_update:
			return
		self._name_set = self._name_set or interactive
		if self._folder_set:
			return

		name = self.form.widgets['name'].get_text()
		folder = self.form.widgets['folder'].get_text()
		dir = os.path.dirname(folder).strip('/\\')

		self._block_update = True
		self.form.widgets['folder'].set_text(os.path.join(dir, name))
		self._block_update = False

	def on_folder_changed(self, o, interactive=True):
		# When folder is changed, update name accordingly
		if self._block_update:
			return
		self._folder_set = self._folder_set or interactive

		# Check notebook info (even when name was set already)
		if interactive or not self._name_set:
			folder = self.form['folder']
			if folder and folder.exists():
				info = get_notebook_info(folder)
				if info: # None when no config found
					self._block_update = True
					self.form['name'] = info.name
					self._block_update = False
					return

		# Else use basename unless the name was set explicitly already
		if self._name_set:
			return

		folder = self.form.widgets['folder'].get_text().strip('/\\')
		self._block_update = True
		self.form['name'] = os.path.basename(folder)
		self._block_update = False

	def do_response_ok(self):
		name = self.form['name']
		folder = self.form['folder']
		if name and folder:
			self.result = {'name': name, 'folder': folder}
			return True
		else:
			return False
