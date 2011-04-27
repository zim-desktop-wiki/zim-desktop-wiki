# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains the notebook dialog which is used for the
"open another notebook" action and which is shown if you start zim without
argument. The dialog directly modifies the notebook list obtained from
zim.notebook.get_notebook_list(). A special dropdown allows settign the
special entry for the default notebook which will be openend directly
the next time zim is started without arguments.

@newfield column: Column, Columns
'''

import gtk
import pango
import logging

from zim.fs import *
from zim.notebook import get_notebook_list, init_notebook, NotebookInfo
from zim.config import data_file
from zim.gui.widgets import ui_environment, Dialog, IconButton, _encode_xml

logger = logging.getLogger('zim.gui.notebookdialog')


OPEN_COL = 0   # column with boolean if notebook is open alreadys
NAME_COL = 1   # column with notebook name
TEXT_COL = 2   # column with a formatted containing name and path
PIXBUF_COL = 3 # column containing the notebook icon
INFO_COL = 4   # column with the NotebookInfo object


def prompt_notebook():
	'''Prompts the NotebookDialog and returns the result or None.
	As a special case for first time usage it immediatly prompts for
	the notebook location without showing the notebook list.
	'''
	list = get_notebook_list()
	if len(list) == 0:
		logger.debug('First time usage - prompt for notebook folder')
		fields = AddNotebookDialog(ui=None).run()
		if fields:
			dir = Dir(fields['folder'])
			init_notebook(dir, name=fields['name'])
			list.append(NotebookInfo(dir.uri, name=fields['name']))
			list.write()
			return dir.uri
		else:
			return None # User cancelled the dialog ?
	else:
		# Multiple notebooks defined and no default
		return NotebookDialog(ui=None).run()


class NotebookTreeModel(gtk.ListStore):
	'''TreeModel that wraps a notebook list

	@column OPEN_COL: boolean, True if the notebook is opened already
	@column NAME_COL: string, name of the notebook
	@column TEXT_COL: string, formatted string containg the name and path
	@column PIXBUF_COL: gtk.gdk.Pixbuf, the icon of the notebook (if any)
	@column INFO_COL: L{NotebookInfo} object

	@note: To refer to the notebook in an unambiguous way, use the uri stored
	in the L{NotebookInfo} object.
	'''

	def __init__(self, notebooklist=None):
		'''Constructor. If "notebooklist" is None, the default list as
		provided by zim.notebook.get_notebook_list() is used.

		@param notebooklist: a list of L{NotebookInfo} objects
		'''
		gtk.ListStore.__init__(self, bool, str, str, gtk.gdk.Pixbuf, object)
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
				(_encode_xml(info.name), _encode_xml(path))
				# T: Path label in 'open notebook' dialog

		if info.icon and File(info.icon).exists():
			w, h = gtk.icon_size_lookup(gtk.ICON_SIZE_BUTTON)
			pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(File(info.icon).path, w, h)
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


class NotebookTreeView(gtk.TreeView):

	def __init__(self, model=None):
		# TODO: add logic to flag open notebook italic - needs daemon
		if model is None:
			model = NotebookTreeModel()
		gtk.TreeView.__init__(self, model)
		self.get_selection().set_mode(gtk.SELECTION_BROWSE)
		self.set_rules_hint(True)
		self.set_reorderable(True)

		cell_renderer = gtk.CellRendererPixbuf()
		column = gtk.TreeViewColumn(None, cell_renderer, pixbuf=PIXBUF_COL)
		column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
		w, h = gtk.icon_size_lookup(gtk.ICON_SIZE_MENU)
		column.set_fixed_width(w*2)
		self.append_column(column)

		cell_renderer = gtk.CellRendererText()
		cell_renderer.set_property('ellipsize', pango.ELLIPSIZE_END)
		cell_renderer.set_fixed_height_from_font(2)
		column = gtk.TreeViewColumn(_('Notebook'), cell_renderer, markup=TEXT_COL)
			# T: Column heading in 'open notebook' dialog
		column.set_sort_column_id(NAME_COL)
		self.append_column(column)



class NotebookComboBox(gtk.ComboBox):
	'''Combobox showing the a list of notebooks'''

	def __init__(self, model=None, current=None):
		'''Constructor, "model" should be a NotebookTreeModel or None to
		use the default list. The notebook 'current' will be shown in the
		widget - if it is not in the list it wil be added. Otherwise the default
		will be shown.
		'''
		if model is None:
			model = NotebookTreeModel()
		gtk.ComboBox.__init__(self, model)
		cell_renderer = gtk.CellRendererText()
		self.pack_start(cell_renderer, False)
		self.set_attributes(cell_renderer, text=NAME_COL)

		if current:
			self.set_notebook(current, append=True)
		else:
			self.set_default_active()

	def set_default_active(self):
		'''Select the default notebook in the combobox'''
		iter = self.get_model().get_iter_for_default()
		if iter is None:
			self.set_active(-1)
		else:
			self.set_active_iter(iter)

	def set_notebook(self, uri, append=False):
		'''Select a specific notebook in the combobox.
		If 'append' is True it will appended if it didn't exist yet
		in the notebook list.
		'''
		if isinstance(uri, basestring):
			assert uri.startswith('file://')
		else:
			assert hasattr(uri, 'uri')
			uri = uri.uri

		model = self.get_model()
		iter = model.get_iter_for_notebook(uri)
		if iter is None:
			if append:
				iter = model.append_notebook(uri)
				self.set_active_iter(iter)
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
	notebook is returned (or None when the dialog is cancelled).
	To run this dialog non-model a callback needs to be specified
	which will be called with the path for the selected notebook.
	'''

	def __init__(self, ui, callback=None):
		Dialog.__init__(self, ui, _('Open Notebook')) # T: dialog title
		# TODO set button to "OPEN" instead of "OK"
		self.callback = callback
		self.set_default_size(500, 400)
		self.set_help(':Help:Notebooks')

		# show some art work in an otherwise boring dialog
		path = data_file('globe_banner_small.png').path
		image = gtk.Image()
		image.set_from_file(path) # new_from_file not in 2.6
		align = gtk.Alignment(0,0.5, 0,0)
		align.add(image)
		self.vbox.pack_start(align, False)

		# split between treeview and vbuttonbox
		hbox = gtk.HBox(spacing=12)
		self.vbox.add(hbox)

		# add notebook list - open notebook on clicking a row
		self.treeview = NotebookTreeView()
		self.treeview.connect(
			'row-activated', lambda *a: self.response(gtk.RESPONSE_OK))

		swindow = gtk.ScrolledWindow()
		swindow.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
		swindow.set_shadow_type(gtk.SHADOW_IN)
		swindow.add(self.treeview)
		hbox.add(swindow)

		# add buttons for modifying the treeview
		vbbox = gtk.VButtonBox()
		vbbox.set_layout(gtk.BUTTONBOX_START)
		hbox.pack_start(vbbox, False)
		add_button = gtk.Button(stock='gtk-add')
		add_button.connect('clicked', self.do_add_notebook)
		#~ edit_button = gtk.Button(stock='gtk-edit')
		#~ edit_button.connect('clicked', self.do_edit_notebook)
		rm_button = gtk.Button(stock='gtk-remove')
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

		hbox = gtk.HBox(spacing=5)
		hbox.pack_start(gtk.Label(_('Default notebook')+': '), False)
			# T: Input label in 'open notebook' dialog
		hbox.pack_start(self.combobox, False)
		hbox.pack_start(clear_button, False)
		self.vbox.pack_start(hbox, False)

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
			self.result = model[iter][INFO_COL].uri
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


class AddNotebookDialog(Dialog):

	def __init__(self, ui, name=None, folder=None):
		Dialog.__init__(self, ui, _('Add Notebook')) # T: Dialog window title

		label = gtk.Label(_('Please select a name and a folder for the notebook.')) # T: Label in Add Notebook dialog
		label.set_alignment(0.0, 0.5)
		self.vbox.pack_start(label, False)

		if name is None and folder is None:
			name = 'Notes'
			if ui_environment['platform'] == 'maemo':
				folder = '~/MyDocs/Notes' # 'MyDocs' is the "Device" folder on maemo
			else:
				folder = '~/Notes'

		self.add_form((
			('name', 'string', _('Name')), # T: input field in 'Add Notebook' dialog
			('folder', 'dir', _('Folder')), # T: input field in 'Add Notebook' dialog
		), {
			'name': name,
			'folder': folder,
		} )

		self.add_help_text('''\
To create a new notebook you need to select an empty folder.
Of course you can also select an existing zim notebook folder.
''') # T: help text in the 'Add Notebook' dialog

	def do_response_ok(self):
		name = self.form['name']
		folder = self.form['folder']
		if name and folder:
			self.result = {'name': name, 'folder': folder}
			return True
		else:
			return False
