# -*- coding: utf-8 -*-

# Author: Tobias Haupenthal
# Plugin created: 2015
#
#
# This plugin includes a whole featureset. Please be familiar with the documentation in 'Plugins:Table Editor',
# before you do here any code change.
#
# - Suggestions for the future:
# better column sort-algorithm "sort-by-number-or-string"
# undo / redo - not trivial, because currently only position in textview is saved
# 				ideas: save everytime the whole table OR save a tuple (position in textview, row, column)


import gobject
import gtk
import logging
from xml.etree import ElementTree
import re
import pango

logger = logging.getLogger('zim.plugin.tableeditor')

from zim.actions import action
from zim.plugins import PluginClass, extends, WindowExtension
from zim.utils import WeakSet
from zim.objectmanager import ObjectManager, CustomObjectClass
from zim.config import String
from zim.main import get_zim_application
from zim.gui.widgets import Dialog, ScrolledWindow, IconButton, InputEntry
from zim.gui.objectmanager import CustomObjectWidget

OBJECT_TYPE = 'table'

SYNTAX_CELL_INPUT = [
	('&amp;', '&'), ('&gt;', '>'), ('&lt;', '<'), ('&quot;', '"'), ('&apos;', "'"), ('\n', '\\n')
]

# Regex replacement strings: Wiki-Parsetree -> Pango (Table cell) -> Input (Table cell editing)
# the target pattern is easier to read, the source pattern is generated out of it
# With this syntax text can be format within a table-cell
SYNTAX_WIKI_PANGO2 = [
	(r'<strong>\1</strong>', r'<b>\1</b>', r'**\1**'),
	(r'<emphasis>\1</emphasis>', r'<i>\1</i>', r'//\1//'),
	(r'<mark>\1</mark>', r'<span background="yellow">\1</span>', r'__\1__'),
	(r'<code>\1</code>', r'<tt>\1</tt>', r"''\1''"),
	(r'<link href="\1">\2</link>', r'<span foreground="blue">\1</span>', r'[[\1]]')
]

# Possible alignments in edit-table-dialog
COLUMNS_ALIGNMENTS = {'left': ['left', gtk.STOCK_JUSTIFY_LEFT, _('Left')],
					  'center': ['center', gtk.STOCK_JUSTIFY_CENTER, _('Center')],
					  'right': ['right', gtk.STOCK_JUSTIFY_RIGHT, _('Right')],
					  'normal': ['normal', None, _('Unspecified')],}


def reg_replace(string):
	'''
	Target pattern is translated into source regex pattern
	:param string: target pattern
	:return:source pattern
	'''
	string = string.replace('*', '\*').replace('[', '\[').replace(']', '\]') \
		.replace(r'\1', '(.+?)').replace(r'\2', '(.+?)')
	return re.compile(string)

# Regex compiled search patterns
SYNTAX_WIKI_PANGO = [tuple(map(reg_replace, expr_list)) for expr_list in SYNTAX_WIKI_PANGO2]


class TableEditorPlugin(PluginClass):
	'''
	This is the plugin for displaying tables within the wiki.
	A table consists always of a header with at least one header-cell and at least one or several rows.
	The number of cells in a row must be equal to the header.
	Currently there are two attributes, which have a tuple format, so they can describe all columns:
	- aligns: left, center, right
	- wraps: 0 	/ display text in a row		1 / long text will be broken and wrapped

	Most other files which are linked to this plugin are:
	- zim.gui.pageview
	- zim.formats.wiki
	'''
	plugin_info = {
		'name': _('Table Editor'),  # T: plugin name
		'description': _('''\
With this plugin you can embed a 'Table' into the wiki page. Tables will be shown as GTK TreeView widgets.
Exporting them to various formats (i.e. HTML/LaTeX) completes the feature set.
'''),  # T: plugin description
		'object_types': (OBJECT_TYPE, ),
		'help': 'Plugins:Table Editor',
		'author': 'Tobias Haupenthal',
	}

	global LINES_NONE, LINES_HORIZONTAL, LINES_VERTICAL, LINES_BOTH # Hack - to make sure translation is loaded
	LINES_BOTH = _('with lines') # T: option value
	LINES_NONE = _('no grid lines') # T: option value
	LINES_HORIZONTAL = _('horizontal lines') # T: option value
	LINES_VERTICAL = _('vertical lines') # T: option value



	plugin_preferences = (
		# key, type, label, default
		('show_helper_toolbar', 'bool', _('Show helper toolbar'), True),

		# option for displaying grid-lines within the table
		('grid_lines', 'choice', _('Grid lines'), LINES_BOTH, (LINES_BOTH, LINES_NONE, LINES_HORIZONTAL, LINES_VERTICAL)),
	)

	def __init__(self, config=None):
		''' Constructor '''
		PluginClass.__init__(self, config)
		self.connectto(self.preferences, 'changed', self.on_preferences_changed)

	def create_table(self, attrib, text):
		'''
		Automatic way for displaying the table-object as a table within the wiki,
		:param attrib:  {type: 'table', wraps:'1,0,1' , aligns:'left,right,center' }
		:param text: XML - formated as a zim-tree table-object OR tuple of [header], [row1], [row2]
		:return: a TableViewObject
		'''
		if ElementTree.iselement(text) and text.get('type') == 'table':
			(header, rows) = self._tabledom_to_list(text)
		else:
			# parameters in case of the Table-Insert-Dialog
			header = text[0]
			rows = [len(text[0]) * [' ']]

		'''Factory method for Table objects'''
		obj = TableViewObject(attrib, header, rows, self.preferences)
		return obj

	def _tabledom_to_list(self, tabledata):
		'''
		Extracts necessary data out of a xml-table into a list structure

		:param tabledata: XML - formated as a zim-tree table-object
		:return: tuple of header-list and list of row lists -  ([h1,h2],[[r11,r12],[r21,r22])
		'''
		header = map(lambda head: head.text.decode('utf-8'), tabledata.findall('thead/th'))
		header = map(CellFormatReplacer.zimtree_to_cell, header)

		rows = []
		for trow in tabledata.findall('trow'):
			row = trow.findall('td')
			row = [ElementTree.tostring(r, 'utf-8').replace('<td>', '').replace('</td>', '') for r in row]
			row = map(CellFormatReplacer.zimtree_to_cell, row)
			rows.append(row)
		return header, rows

	def on_preferences_changed(self, preferences):
		'''Update preferences on open table objects'''
		for obj in ObjectManager.get_active_objects(OBJECT_TYPE):
			obj.preferences_changed()


class CellFormatReplacer:
	'''
	Static class for converting formated text from one into the other format:
	- cell:	in a wiki pageview the table-cell must be of this format
	- input: if a user is editing the cell, this format is used
	- zimtree: Format for zimtree xml structure
	'''
	@staticmethod
	def cell_to_input(text, with_pango=False):
		''' Displayed table-cell will converted to gtk-entry input text '''
		if with_pango:
			for pattern, replace in zip(SYNTAX_WIKI_PANGO, SYNTAX_WIKI_PANGO2):
				text = pattern[1].sub(replace[2], text)
		for k, v in SYNTAX_CELL_INPUT:
			text = text.replace(k, v)
		return text

	@staticmethod
	def input_to_cell(text, with_pango=False):
		for k, v in SYNTAX_CELL_INPUT:
			text = text.replace(v, k)
		if with_pango:
			for pattern, replace in zip(SYNTAX_WIKI_PANGO, SYNTAX_WIKI_PANGO2):
				text = pattern[2].sub(replace[1], text)
		return text

	@staticmethod
	def zimtree_to_cell(text):
		for pattern, replace in zip(SYNTAX_WIKI_PANGO, SYNTAX_WIKI_PANGO2):
			text = pattern[0].sub(replace[1], text)
		return text

	@staticmethod
	def cell_to_zimtree(text):
		for pattern, replace in zip(SYNTAX_WIKI_PANGO, SYNTAX_WIKI_PANGO2):
			text = pattern[1].sub(replace[0], text)
		return text

@extends('MainWindow')
class MainWindowExtension(WindowExtension):
	'''
	Connector between the zim application with its toolbar and menu and the tableview-object
	In GTK there is no native table symbol. So this image is needed: data/pixmaps/insert-table.png
	'''
	uimanager_xml = '''
		<ui>
		<menubar name='menubar'>
			<menu action='insert_menu'>
				<placeholder name='plugin_items'>
					<menuitem action='insert_table'/>
				</placeholder>
			</menu>
		</menubar>
		<toolbar name='toolbar'>
				<placeholder name='format'>
					<toolitem action='insert_table'/>
				</placeholder>
			</toolbar>
		</ui>
	'''

	''' static reference to window object, necessary for access to pageview '''
	window = None

	def __init__(self, plugin, window):
		''' Constructor '''
		WindowExtension.__init__(self, plugin, window)
		MainWindowExtension.window = window

		ObjectManager.register_object(OBJECT_TYPE, self.plugin.create_table, self)

		# reload tables on current page after plugin activation
		if self.window.ui.page:
			self.window.ui.reload_page()

	def teardown(self):
		''' Deconstructor '''
		ObjectManager.unregister_object(OBJECT_TYPE)
		self.window.ui.reload_page()

	@staticmethod
	def get_geometry():
		'''Returns tuple of geometry data from wiki textview window. Useful for setting width of object'''
		pageview = MainWindowExtension.window.pageview.view
		geometry = pageview.get_geometry() if hasattr(pageview, 'get_geometry') else None
		return geometry

	@action(_('Insert Table'), stock='zim-insert-table', readonly=False)  # T: menu item
	def insert_table(self):
		'''Run the InsertTableDialog'''
		col_model = EditTableDialog(self.window, self.plugin, self.window.pageview).run()
		if not col_model:
			return

		_ids, headers, aligns, wraps = ([], [], [], [])

		for model in col_model:
			headers.append(model[1])
			aligns.append(model[3])
			wraps.append(model[2])

		attrs = {'aligns': aligns, 'wraps': wraps}

		obj = self.plugin.create_table(attrs, [headers])
		obj.attrib = {'type': OBJECT_TYPE}
		pageview = self.window.pageview
		pageview.insert_table_at_cursor(obj)

	def do_edit_object(self, obj):
		'''
		With the right button press a context-menu is opened and a table can then be edited
		'''
		self.do_edit_table(obj)

	def do_edit_table(self, obj):
		'''Run the EditTableDialog '''

		aligns = obj.get_aligns()
		wraps = obj.get_wraps()
		titles = [col.get_title() for col in obj.treeview.get_columns()]
		old_model = []
		for i in range(len(titles)):
			old_model.append([i, titles[i], aligns[i], wraps[i]])
		new_model = EditTableDialog(self.window, self.plugin, self.window.pageview, old_model).run()

		if new_model:
			self._update_table_view(obj, new_model)

	def _update_table_view(self, obj, new_model):
		'''
		Replaces liststore of currently displayed treeview with updated data and fixes references to attributes
		:param obj: tableview object
		:param new_model: tuple of lists for ([id], [header], [warps], [aligns])
		'''
		# prepare results out of dialog-window
		id_mapping, headers, aligns, wraps = ({}, [], [], [])
		for i, model in enumerate(new_model):
			if model[0] != -1:
				id_mapping[i] = model[0]
			header = model[1] if model[1] else ' '
			headers.append(header)
			aligns.append(model[3])
			wraps.append(model[2])

		# creation of new table-view widget
		attrs = {'aligns': aligns, 'wraps': wraps}
		newrows = self._calculate_new_liststore(obj.treeview.get_model(), id_mapping, len(headers))
		widget = TableViewWidget(obj, headers, newrows, attrs)
		new_treeview = widget.get_treeview()
		new_model = new_treeview.get_model()

		# update of displayed table(=treeview) and its structure (=liststore)
		obj.treeview.set_model(new_model)
		# remove all old columns and move new columns to original treeview
		for col in obj.treeview.get_columns():
			obj.treeview.remove_column(col)
		for i, col in enumerate(new_treeview.get_columns()):
			new_treeview.remove_column(col)
			obj.treeview.append_column(col)
			title_label = TableViewWidget.create_headerlabel(headers[i])
			col.set_widget(title_label)

		obj.set_aligns(aligns)
		obj.set_wraps(wraps)
		obj.set_modified(True)

	def _calculate_new_liststore(self, liststore, id_mapping, nr_cols):
		''' Old value of cells are used in the new table, but only if its column is not deleted '''
		new_rows = []
		for oldrow in liststore:
				newrow = [' ']*nr_cols
				for v, k in id_mapping.iteritems():
					newrow[v] = oldrow[k]
				new_rows.append(newrow)
		return new_rows


class TableViewObject(CustomObjectClass):
	'''data presenter of an inserted table within a page'''
	OBJECT_ATTR = {
		'type': String('table'),
		'aligns': String(''),  # i.e. String(left,right,center)
		'wraps': String('')	  # i.e. String(0,1,0)
	}

	def __init__(self, attrib, header, rows, preferences):
		'''
		Creates a new object which can displayed within the page
		:param attrib: aligns, wraps
		:param header: titles of the table as list
		:param rows: body-rows of the table as list of lists
		:param preferences: optionally some preferences
		'''
		_attrib = {}
		for k, v in attrib.iteritems():
			if isinstance(v, list):
				v = ','.join(map(str, v))
			_attrib[k] = v
		CustomObjectClass.__init__(self, _attrib, [header]+rows)

		self._tableattrib = attrib
		self._header = header
		self._rows = rows
		self.modified = False
		self.preferences = preferences
		self.treeview = None
		self._widgets = WeakSet()
		self.textview_geometry = None

	# getters and setters for attributes
	def get_aligns(self):
		''' get the list of align-attributes '''
		return self._attrib['aligns'].split(',')

	def set_aligns(self, data):
		''' Set list of align attributes for the current table. Each item belongs to a column.'''
		assert(isinstance(data, list))
		self._attrib['aligns'] = ','.join(data)

	def get_wraps(self):
		''' get the list of wrap-attributes '''
		return map(int, self._attrib['wraps'].split(','))

	def set_wraps(self, data):
		''' Set list of wrap attributes for the current table. Each item belongs to a column.'''
		assert(isinstance(data, list))
		self._attrib['wraps'] = ','.join(str(item) for item in data)

	def get_widget(self):
		''' Creates a new table-widget which can displayed on the wiki-page '''
		attrib = {'aligns': self.get_aligns(), 'wraps': self.get_wraps()}
		widget = TableViewWidget(self, self._header, self._rows, attrib)
		treeview = widget.get_treeview()
		self.treeview = treeview
		liststore = treeview.get_model()
		liststore.connect('row-changed', self.on_modified_changed)

		self._widgets.add(widget)
		widget.set_preferences(self.preferences)
		return widget

	def preferences_changed(self):
		'''	Updates all created table-widgets, if preferences have changed '''
		for widget in self._widgets:
			widget.set_preferences(self.preferences)

	def on_sort_column_changed(self, liststore):
		''' Trigger after a column-header is clicked and therefore its sort order has changed '''
		self.set_modified(True)

	def on_modified_changed(self, liststore, path, treeiter):
		''' Trigger after a table cell content is changed by the user '''
		self.set_modified(True)

	def get_data(self):
		'''Returns table-object into textual data, for saving it as text.'''
		liststore = self.treeview.get_model()
		headers = []
		rows = []

		# parsing table header and attributes
		for column in self.treeview.get_columns():
			title = column.get_title() if column.get_title() else ' '
			headers.append(title)
		attrs = {'aligns': self._attrib['aligns'], 'wraps': self._attrib['wraps']}

		# parsing rows
		treeiter = liststore.get_iter_first()
		while treeiter is not None:
			row = []
			for colid in range(len(self.treeview.get_columns())):
				val = liststore.get_value(treeiter, colid) if liststore.get_value(treeiter, colid) else ' '
				row.append(val)
			rows.append(row)
			treeiter = liststore.iter_next(treeiter)
		rows = [map(lambda cell: CellFormatReplacer.cell_to_input(cell, True), row) for row in rows]

		# logger.debug("Table as get-data: : %s, %s, %s", headers, rows, attrs)
		return headers, rows, attrs


	def dump(self, format, dumper, linker=None):
		''' Dumps currently structure for table into textual format - mostly used for debugging / testing purposes '''
		return CustomObjectClass.dump(self, format, dumper, linker)


class TableViewWidget(CustomObjectWidget):

	textarea_width = None

	def __init__(self, obj, headers, rows, attrs):
		'''
		This is a group of GTK Gui elements which are directly displayed within the wiki textarea
		On initilizing also some signals are registered and a toolbar is initialized
		:param obj: a Table-View-Object
		:param headers: list of titles
		:param rows: list of list of cells
		:param attrs: table settings, like alignment and wrapping
		:return:
		'''
		if MainWindowExtension.get_geometry() is not None:
			self.textarea_width = MainWindowExtension.get_geometry()[2]

		# used in pageview
		self._resize = True  # attribute, that triggers resizing
		self._has_cursor = False  # Skip table object, if someone moves cursor around in textview

		# used here
		self.obj = obj
		self._timer = None  # NONE or number of current gobject.timer, which is running
		self._cell_editing = False  # a cell is currently edited, toolbar should not be hidden
		self._toolbar_enabled = True  # sets if toolbar should be shown beneath a selected table

		gtk.EventBox.__init__(self)
		self.set_border_width(5)

		# Add vbox and wrap it to have a shadow around it
		self.vbox = gtk.VBox() #: C{gtk.VBox} to contain widget contents

		# Toolbar for table actions
		toolbar = self.create_toolbar()
		self.obj.toolbar = toolbar

		# Actual gtk table object
		self.treeview = self.create_treeview(headers, rows, attrs)

		# Hook up signals & set options
		self.treeview.connect('button-press-event', self.on_button_press_event)
		self.treeview.connect('focus-in-event', self.on_focus_in, toolbar)
		self.treeview.connect('focus-out-event', self.on_focus_out, toolbar)
		self.treeview.connect('move-cursor', self.on_move_cursor)

		# Set options
		self.treeview.set_grid_lines(gtk.TREE_VIEW_GRID_LINES_BOTH)
		self.treeview.set_receives_default(True)
		self.treeview.set_size_request(-1, -1)
		self.treeview.set_border_width(5)

		# disable interactive column search
		self.treeview.set_enable_search(False)
		gtk.binding_entry_remove(gtk.TreeView, gtk.keysyms.f, gtk.gdk.CONTROL_MASK)
		self.treeview.set_search_column(-1)

		# package gui elements
		self.vbox.pack_end(toolbar)
		self.add(self.vbox)
		win = ScrolledWindow(self.treeview, gtk.POLICY_NEVER, gtk.POLICY_NEVER, gtk.SHADOW_OUT)
		self.vbox.pack_start(win)

	def on_focus_in(self, treeview, event, toolbar):
		'''After a table is selected, this function will be triggered'''

		self._cell_editing = False
		if self._timer:
			gobject.source_remove(self._timer)
		if self._toolbar_enabled:
			toolbar.show()

	def on_focus_out(self, treeview, event, toolbar):
		'''After a table is deselected, this function will be triggered'''
		def receive_alarm():
			if self._cell_editing:
				self._timer = None
			if self._timer:
				self._timer = None
				treeview.get_selection().unselect_all()
				if self._toolbar_enabled:
					toolbar.hide()
			return False

		self._timer = gobject.timeout_add(500, receive_alarm)

	def create_toolbar(self):
		'''This function creates a toolbar which is displayed next to the table'''
		toolbar = gtk.Toolbar()
		toolbar.set_orientation(gtk.ORIENTATION_HORIZONTAL)
		toolbar.set_style(gtk.TOOLBAR_ICONS)
		toolbar.set_border_width(1)

		tooltips = gtk.Tooltips()
		for pos, stock, handler, data, tooltip in (
			(0, gtk.STOCK_ADD, self.on_add_row, None, _('Add row')),
			(1, gtk.STOCK_DELETE, self.on_delete_row, None, _('Remove row')),
			(2, gtk.STOCK_COPY, self.on_clone_row, None, _('Clone row')),
			(3, None, None, None, None),
			(4, gtk.STOCK_GO_UP, self.on_move_row, -1, _('Row up')),
			(5, gtk.STOCK_GO_DOWN, self.on_move_row, 1, _('Row down')),
			(6, None, None, None, None),
			(7, gtk.STOCK_PREFERENCES, self.on_change_columns, None, _('Change columns')),
			(8, None, None, None, None),
			(9, gtk.STOCK_HELP, self.on_open_help, None, _('Open help')),
		):
			if stock is None:
				toolbar.insert(gtk.SeparatorToolItem(), pos)
			else:
				button = gtk.ToolButton(stock)
				if data:
					button.connect('clicked', handler, data)
				else:
					button.connect('clicked', handler)
				tooltips.set_tip(button, tooltip)
				toolbar.insert(button, pos)

		toolbar.set_size_request(300,-1)
		toolbar.set_icon_size(gtk.ICON_SIZE_MENU)

		return toolbar

	def toolbar_hide(self):
		''' Hide toolbar of the table (moving rows around, etc.) '''
		self.obj.toolbar.hide()

	def resize_to_textview(self, view):
		''' Overriding - on resizing the table should not expanded to 100% width'''
		win = view.get_window(gtk.TEXT_WINDOW_TEXT)
		if not win:
			return
		old_width = self.textarea_width
		self.textarea_width = win.get_geometry()[2]

		if old_width == self.textarea_width:
			return

		for i, wrap in enumerate(self.obj.get_wraps()):
			if wrap == 1 and gtk.gtk_version >= (2, 8) and self.textarea_width:
				column = self.treeview.get_column(i)
				cell = column.get_cell_renderers()[0]
				cell.set_property('wrap-width', self.textarea_width/len(self.obj.get_wraps()))
				cell.set_property('wrap-mode', pango.WRAP_WORD)

				column.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE) # allow column shrinks
				column.set_max_width(0)	# shrink column
				column.set_max_width(-1) # reset value
				column.set_sizing(gtk.TREE_VIEW_COLUMN_GROW_ONLY) # reset value

		# override setting table to a special size
		self.set_size_request(-1, -1)

	def _column_alignment(self, aligntext):
		''' The column alignment must be converted from numeric to keywords '''
		if aligntext == 'left':
			align = 0.0
		elif aligntext == 'center':
			align = 0.5
		elif aligntext == 'right':
			align = 1.0
		else:
			align = None
		return align

	def create_treeview(self, headers, rows, attrs):
		'''
		Initializes a treeview with its model (liststore) and all its columns
		:param headers: a list of title values for the column-headers
		:param rows: a list of list of cells, for the table body
		:param attrs: some more attributes, which define the layout of a column
		:return: gtk.treeview
		'''
		nrcols = len(headers)

		cols = [str]*nrcols

		liststore = gtk.ListStore(*cols)
		treeview = gtk.TreeView(liststore)
		for trow in rows:
			liststore.append(trow)

		for i, headcol in enumerate(headers):
			cell = gtk.CellRendererText()
			tview_column = gtk.TreeViewColumn(headcol, cell)
			treeview.append_column(tview_column)

			# set title as label
			header_label = self.create_headerlabel(headcol)
			tview_column.set_widget(header_label)

			# set properties of column
			tview_column.set_attributes(cell, markup=i)
			cell.set_property('editable', True)
			tview_column.set_sort_column_id(i)
			# set sort function
			liststore.set_sort_func(i, self.sort_by_number_or_string, i)

			# if wrapping is enabled, the column can only be as wide as 1/nrcols and is then fragmented into two lines
			if attrs['wraps'][i] == 1 and gtk.gtk_version >= (2, 8) and self.textarea_width is not None:
				cell.set_property('wrap-width', self.textarea_width/nrcols)
				cell.set_property('wrap-mode', pango.WRAP_WORD)

			# set alignment - left center right
			align = self._column_alignment(attrs['aligns'][i])
			if align:
				tview_column.set_alignment(align)
				cell.set_alignment(align, 0.0)

			# callbacks after an action
			cell.connect('edited', self.on_cell_changed, treeview.get_model(), i)
			cell.connect('editing-started', self.on_cell_editing_started, treeview.get_model(), i)
			cell.connect('editing-canceled', self.on_cell_editing_canceled)

		return treeview

	def create_headerlabel(self, title):
		return TableViewWidget.create_headerlabel(title)

	@staticmethod
	def create_headerlabel(title):
		''' Sets options for the treeview header'''
		col_widget = gtk.VBox()
		col_widget.show()


		col_label = gtk.Label('<u>'+title+'</u>')
		col_label.set_use_markup(True)
		col_label.show()
		col_widget.pack_start(col_label)
		#col_align.add(col_label)

		'''col_entry = InputEntry()
		col_entry.set_name('treeview-header-entry')
		col_entry.show()
		col_widget.pack_start(col_entry)'''

		return col_widget

	def get_treeview(self):
		# treeview of current table
		return self.treeview

	def set_preferences(self, preferences):
		self._toolbar_enabled = preferences['show_helper_toolbar']

		''' Sets general plugin settings for this object'''
		grid_option = self.pref_gridlines(preferences['grid_lines'])
		self.treeview.set_grid_lines(grid_option)
		pass

	def pref_gridlines(self, option):
		if option == LINES_BOTH:
			return gtk.TREE_VIEW_GRID_LINES_BOTH
		elif option == LINES_NONE:
			return gtk.TREE_VIEW_GRID_LINES_NONE
		elif option == LINES_HORIZONTAL:
			return gtk.TREE_VIEW_GRID_LINES_HORIZONTAL
		elif option == LINES_VERTICAL:
			return gtk.TREE_VIEW_GRID_LINES_VERTICAL

	def on_cell_editing_canceled(self, renderer):
		''' Trigger after a cell is edited but not change is skipped'''
		pass

	def on_move_cursor(self, view, step_size, count):
		''' If you try to move the cursor out of the tableditor release the cursor to the parent textview '''
		return None  # let parent handle this signal

	def fetch_cell_by_event(self, event, treeview):
		'''	Looks for the cell where the mouse clicked on it '''
		liststore = treeview.get_model()
		(xpos, ypos) = event.get_coords()
		(treepath, treecol, xrel, yrel) = treeview.get_path_at_pos(int(xpos), int(ypos))
		treeiter = liststore.get_iter(treepath)
		cellvalue = liststore.get_value(treeiter, treeview.get_columns().index(treecol))
		return cellvalue

	def get_linkurl(self, celltext):
		'''	Checks a cellvalue if it contains a link and returns only the link value '''
		linkregex = r'<span foreground="blue">(.*?)</span>'
		matches = re.match(linkregex, celltext)
		linkvalue = matches.group(1) if matches else None
		return linkvalue

	def on_button_press_event(self, treeview, event):
		'''
		Displays a context-menu on right button click
		Opens the link of a tablecell on CTRL pressed and left button click
		'''
		if event.type == gtk.gdk.BUTTON_PRESS and event.button == 1 and event.get_state() &  gtk.gdk.CONTROL_MASK:
			# With CTRL + LEFT-Mouse-Click link of cell is opened
			cellvalue = self.fetch_cell_by_event(event, treeview)
			linkvalue = self.get_linkurl(cellvalue)
			if linkvalue:
				self.obj.emit('link-clicked', {'href': linkvalue})
			return

		if event.type == gtk.gdk.BUTTON_PRESS and event.button == 3:
			self._cell_editing = True
			cellvalue = self.fetch_cell_by_event(event, treeview)
			linkvalue = self.get_linkurl(cellvalue)
			linkitem_is_activated = (linkvalue is not None)

			menu = gtk.Menu()

			for stock, handler, data, tooltip in (
				(gtk.STOCK_ADD, self.on_add_row, None, _('Add row')),
				(gtk.STOCK_DELETE, self.on_delete_row, None, _('Delete row')),
				(gtk.STOCK_COPY, self.on_clone_row, None, _('Clone row')),
				(None, None, None, None),
				(gtk.STOCK_JUMP_TO, self.on_open_link, linkvalue, _('Open cell content link')),
				(None, None, None, None),
				(gtk.STOCK_GO_UP, self.on_move_row, -1, _('Row up')),
				(gtk.STOCK_GO_DOWN, self.on_move_row, 1, _('Row down')),
				(None, None, None, None),
				(gtk.STOCK_PREFERENCES, self.on_change_columns, None, _('Change columns'))
			):

				if stock is None:
					menu.append(gtk.SeparatorMenuItem())
				else:
					item = gtk.ImageMenuItem(stock)
					item.set_always_show_image(True)
					item.set_label(_(tooltip))
					if data:
						item.connect_after('activate', handler, data)
					else:
						item.connect_after('activate', handler)
					if handler == self.on_open_link:
						item.set_sensitive(linkitem_is_activated)
					menu.append(item)

			menu.show_all()
			menu.popup(None, None, None, event.button, event.time)

	def on_add_row(self, action):
		''' Context menu: Add a row '''
		selection = self.treeview.get_selection()
		model, treeiter = selection.get_selected()
		if not treeiter:  # no selected item
			self.selection_info()
			return

		row = len(self.treeview.get_columns())*['']
		path = model.insert_after(treeiter, row)
		self.obj.set_modified(True)

	def on_clone_row(self, action):
		''' Context menu: Clone a row '''
		selection = self.treeview.get_selection()
		model, treeiter = selection.get_selected()
		if not treeiter:  # no selected item
			self.selection_info()
			return

		path = model.get_path(treeiter)
		row = model[path[0]]
		model.insert_after(treeiter, row)
		self.obj.set_modified(True)

	def on_delete_row(self, action):
		''' Context menu: Delete a row '''
		selection = self.treeview.get_selection()
		model, treeiter = selection.get_selected()
		if not treeiter:  # no selected item
			self.selection_info()
			return

		if len(model) > 1:
			model.remove(treeiter)
			self.obj.set_modified(True)
		else:
			md = gtk.MessageDialog(None, gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_WARNING, gtk.BUTTONS_CLOSE,
									_("The table must consist of at least on row!\n No deletion done."))
			md.run()
			md.destroy()

	def on_move_row(self, action, direction):
		''' Trigger for moving a row one position up/down '''
		selection = self.treeview.get_selection()
		model, treeiter = selection.get_selected()
		if not treeiter:  # no selected item
			self.selection_info()
			return

		path = model.get_path(treeiter)
		newpos = path[0] + direction
		if 0 > newpos or newpos >= len(model):  # first item cannot be pushed forward, last not backwards
			return
		newiter = model.get_iter((newpos,))

		model.swap(treeiter, newiter)
		self.obj.set_modified(True)


	def on_open_link(self, action, link):
		''' Context menu: Open a link, which is written in a cell '''
		self.obj.emit('link-clicked', {'href': link})

	def on_open_help(self, action):
		''' Context menu: Open help '''
		get_zim_application('--manual', 'Plugins:Table Editor').spawn()
		pass

	def on_change_columns(self, action):
		''' Context menu: Edit table '''
		self.obj.emit('edit-object', self.obj)

	def on_cell_changed(self, cellrenderer, path, text, liststore, colid):
		''' Trigger after cell-editing, to transform displayed table cell into right format '''
		self._cell_editing = False
		markup = CellFormatReplacer.input_to_cell(text, True)
		liststore[path][colid] = markup


	def on_cell_editing_started(self, cellrenderer, editable, path, liststore, colid):
		''' Trigger before cell-editing, to transform text-field data into right format '''
		self._cell_editing = True
		markup = liststore[path][colid]
		markup = CellFormatReplacer.cell_to_input(markup, True)
		editable.set_text(markup)

	def start_timer(self):
		return self._timer

	def sort_by_number_or_string(self, liststore, treeiter1, treeiter2, colid):
		'''
		Sort algorithm for sorting numbers correctly and putting 10 after 3.
		This part can be improved in future to support also currencies, dates, floats, etc.
		:param liststore: model of treeview
		:param treeiter1: treeiter 1
		:param treeiter2: treeiter 2
		:param colid: a column number
		:return: -1 / first data is smaller than second, 0 / equality, 1 / else
		'''
		data1 = liststore.get_value(treeiter1, colid)
		data2 = liststore.get_value(treeiter2, colid)
		if data1.isdigit() and data2.isdigit():
			data1 = int(data1)
			data2 = int(data2)
		self.obj.set_modified(True)
		return cmp(data1, data2)

	def selection_info(self):
		''' Info-Popup for selecting a cell before this action can be done '''
		md = gtk.MessageDialog(None, gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_WARNING, gtk.BUTTONS_CLOSE,
								_("Please select a row, before you push the button."))
		md.run()
		md.destroy()


class EditTableDialog(Dialog):
	'''
	Graphical dialog for the user, where a new table can be created or an existing one can be modified
	Here columns can be added / modified and titles be managed.
	'''
	class Col():
		'''
		Format of the treeview in which columns of the table can be managed:
		- id: -1 or position of original column
		- wrapped: 0/1 should text be wrapped over multiple lines
		- align, alignicon, aligntext:	english-keyword, GTK-ICON, translated-keyword for alignments
		'''
		id, title, wrapped, align, alignicon, aligntext = range(6)

	def __init__(self, ui, plugin, pageview, tablemodel=None):
		'''
		Constructor, which intializes the dialog window
		:param ui:
		:param plugin:
		:param pageview:
		:param tablemodel: list of row-data
		:return:
		'''
		title = _('Insert Table') if tablemodel is None else _('Edit Table')
		Dialog.__init__(self, ui, title)

		# Prepare treeview in which all columns of the table are listed
		self.default_column_item = [-1, "", 0, "left", gtk.STOCK_JUSTIFY_LEFT, _("Left")]

		# Set layout of Window
		self.add_help_text(_('Managing table columns'))
		self.set_default_size(380, 400)

		liststore = self._prepare_liststore(tablemodel)
		treeview = self._prepare_treeview_with_headcolumn_list(liststore)
		hbox = gtk.HBox(spacing=5)
		hbox.set_size_request(300, 300)
		self.vbox.pack_start(hbox, False)
		header_scrolled_area = ScrolledWindow(treeview)
		header_scrolled_area.set_size_request(200, -1)
		hbox.add(header_scrolled_area)
		hbox.add(self._button_box())

		# currently edited cell - tuple (editable, path, colid) save it on exit
		self.currently_edited = None
		self.treeview = treeview

	def _prepare_liststore(self, tablemodel):
		'''
		Preparation of liststore to show a treeview, that displays the columns of the table
		:param tablemodel: list of row-data
		:return:liststore
		'''
		first_column_item = list(self.default_column_item)
		first_column_item[1] = _("Column 1")
		liststore = gtk.ListStore(int, str, int, str, str, str)

		# each table column is displayed in a new row
		if tablemodel is None:
			liststore.append(first_column_item)
		else:
			for col in tablemodel:
				align = col.pop(2)
				col += COLUMNS_ALIGNMENTS[align] if align in COLUMNS_ALIGNMENTS else COLUMNS_ALIGNMENTS['normal']
				liststore.append(col)

		return liststore

	def _prepare_treeview_with_headcolumn_list(self, liststore):
		'''
		Preparation of the treeview element, that displays the columns of the table
		:param liststore: model for current treeview
		:return: the treeview
		'''
		treeview = gtk.TreeView(liststore)

		# 1. Column - Title
		cell = gtk.CellRendererText()
		cell.set_property('editable', True)
		column = gtk.TreeViewColumn(_('Title'), cell, text=self.Col.title)
		column.set_min_width(120)
		treeview.append_column(column)
		cell.connect('edited', self.on_cell_changed, liststore, self.Col.title)
		cell.connect('editing-started', self.on_cell_editing_started, liststore, self.Col.title)

		# 2. Column - Wrap Line
		cell = gtk.CellRendererToggle()
		cell.connect('toggled', self.on_wrap_toggled, liststore, self.Col.wrapped)
		column = gtk.TreeViewColumn(_('Auto\nWrap'), cell)
		treeview.append_column(column)
		column.add_attribute(cell, 'active', self.Col.wrapped)

		# 3. Column - Alignment
		store = gtk.ListStore(str, str, str)
		store.append(COLUMNS_ALIGNMENTS['left'])
		store.append(COLUMNS_ALIGNMENTS['center'])
		store.append(COLUMNS_ALIGNMENTS['right'])

		column = gtk.TreeViewColumn(_('Align'))
		cellicon = gtk.CellRendererPixbuf()
		column.pack_start(cellicon)
		column.add_attribute(cellicon, 'stock-id', self.Col.alignicon)

		cell = gtk.CellRendererCombo()
		cell.set_property('model', store)
		cell.set_property('has-entry', False)
		cell.set_property('text-column', 2)
		cell.set_property('width', 50)
		cell.set_property('editable', True)
		column.pack_start(cell)
		column.add_attribute(cell, 'text', self.Col.aligntext)
		cell.connect('changed', self.on_alignment_changed, liststore)
		treeview.append_column(column)

		return treeview

	def _button_box(self):
		'''
		Panel which includes buttons for manipulating the current treeview:
		- add / delete
		- move up / move down row
		:return: vbox-panel
		'''
		vbox = gtk.VBox(spacing=5)
		tooltips = gtk.Tooltips()
		for stock, handler, data, tooltip in (
			(gtk.STOCK_ADD, self.on_add_new_column, None, _('Add column')),
			(gtk.STOCK_DELETE, self.on_delete_column, None, _('Remove column')),
			(gtk.STOCK_GO_UP, self.on_move_column, -1, _('Move column ahead')),
			(gtk.STOCK_GO_DOWN, self.on_move_column, 1, _('Move column backward')),
		):
			button = IconButton(stock)
			if data:
				button.connect('clicked', handler, data)
			else:
				button.connect('clicked', handler)
			tooltips.set_tip(button, tooltip)
			vbox.pack_start(button, False)

		vbox.show_all()
		return vbox

	def do_response_ok(self):
		''' Dialog Window is closed with "OK" '''
		self.autosave_title_cell()
		self.result = [[m[0], m[1], m[2],m[3]] for m in self.treeview.get_model()]
		return True

	def do_response_cancel(self):
		''' Dialog Window is closed with "Cancel" '''
		self.result = None
		return True

	def on_cell_editing_started(self, renderer, editable, path, model, colid):
		''' Trigger before cell-editing, to transform text-field data into right format '''
		text = model[path][colid]
		text = CellFormatReplacer.cell_to_input(text)
		editable.set_text(text)
		self.currently_edited = (editable, model, path, colid)

	def on_cell_changed(self, renderer, path, text, model, colid):
		''' Trigger after cell-editing, to transform text-field data into right format '''
		model[path][colid] = CellFormatReplacer.input_to_cell(text)
		self.currently_edited = None

	def on_wrap_toggled(self, renderer, path, model, colid):
		''' Trigger for wrap-option (enable/disable)'''
		treeiter = model.get_iter(path)
		val = model.get_value(treeiter, colid)
		model.set_value(treeiter, colid, not val)

	def on_alignment_changed(self, renderer, path, comboiter, model):
		''' Trigger for align-option (selectionbox with icon and alignment as text)'''
		combomodel = renderer.get_property('model')
		align = combomodel.get_value(comboiter, 0)
		alignimg = combomodel.get_value(comboiter, 1)
		aligntext = combomodel.get_value(comboiter, 2)

		treeiter = model.get_iter(path)
		model.set_value(treeiter, self.Col.align, align)
		model.set_value(treeiter, self.Col.alignicon, alignimg)
		model.set_value(treeiter, self.Col.aligntext, aligntext)

	def autosave_title_cell(self):
		''' Saving cell, in case of editing it and then do not close it, but do another action, like closing window '''
		if self.currently_edited:
			editable, model, path, colid = self.currently_edited
			text = editable.get_text()
			model[path][colid] = CellFormatReplacer.input_to_cell(text)
			self.currently_edited = None

	def on_add_new_column(self, btn):
		''' Trigger for adding a new column into the table / it is a new row in the treeview '''
		self.autosave_title_cell()
		(model, treeiter) = self.treeview.get_selection().get_selected()
		model.insert_after(treeiter, self.default_column_item)
		newiter = treeiter if treeiter else model.get_iter_first()
		self.treeview.get_selection().select_iter(newiter)

	def on_delete_column(self, btn):
		''' Trigger for deleting a column out of the table / it is a deleted row in the treeview '''
		self.autosave_title_cell()
		(model, treeiter) = self.treeview.get_selection().get_selected()

		if treeiter:
			if len(model) > 1:
				model.remove(treeiter)
			else:
				md = gtk.MessageDialog(None, gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_WARNING, gtk.BUTTONS_CLOSE,
										_("A table needs to have at least one column."))
				md.run()
				md.destroy()
		else:
			self.selection_info()

	def on_move_column(self, btn, direction):
		''' Trigger for moving a column one position left/right) - it is a movement up/down in the treeview '''
		self.autosave_title_cell()
		(model, treeiter) = self.treeview.get_selection().get_selected()

		if not treeiter:  # no selected item
			self.selection_info()
			return

		path = model.get_path(treeiter)
		newpos = path[0] + direction
		if 0 > newpos or newpos >= len(model):  # first item cannot be pushed forward, last not backwards
			return
		newiter = model.get_iter((newpos,))

		model.swap(treeiter, newiter)

	def selection_info(self):
		''' Info-Popup for selecting a cell before this action can be done '''
		md = gtk.MessageDialog(None, gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_WARNING, gtk.BUTTONS_CLOSE,
								_("Please select a row, before you push the button."))
		md.run()
		md.destroy()