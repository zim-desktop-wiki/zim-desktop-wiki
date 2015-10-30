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
from zim.formats import ElementTreeModule as ElementTree
from zim.formats import TABLE, HEADROW, HEADDATA, TABLEROW, TABLEDATA


OBJECT_TYPE = 'table'

SYNTAX_CELL_INPUT = [
	('&amp;', '&'), ('&gt;', '>'), ('&lt;', '<'), ('&quot;', '"'), ('&apos;', "'"), ('\n', '\\n')
]

# Regex replacement strings: Wiki-Parsetree -> Pango (Table cell) -> Input (Table cell editing)
# the target pattern is easier to read, the source pattern is generated out of it
# With this syntax text can be format within a table-cell
SYNTAX_WIKI_PANGO2 = [
	(r'<strong>\1</strong>', r'<b>\1</b>', r'**\1**'),
	(r'<mark>\1</mark>', r'<span background="yellow">\1</span>', r'__\1__'),
	(r'<code>\1</code>', r'<tt>\1</tt>', r"''\1''"),
	(r'<strike>\1</strike>', r'<s>\1</s>', r'~~\1~~'),
	# Link url without link text  - Link url has always size = 0
	(r'<link href="\1">\1</link>', r'<span foreground="blue">\1<span size="0">\1</span></span>', r'[[\1]]'),
	# Link url with link text  - Link url has always size = 0
	(r'<link href="\1">\2</link>', r'<span foreground="blue">\2<span size="0">\1</span></span>', r'[[\2|\1]]'),
	(r'<emphasis>\1</emphasis>', r'<i>\1</i>', r'//\1//')
]

# Possible alignments in edit-table-dialog
COLUMNS_ALIGNMENTS = {'left': ['left', gtk.STOCK_JUSTIFY_LEFT, _('Left')],  # T: alignment option
					  'center': ['center', gtk.STOCK_JUSTIFY_CENTER, _('Center')],  # T: alignment option
					  'right': ['right', gtk.STOCK_JUSTIFY_RIGHT, _('Right')],  # T: alignment option
					  'normal': ['normal', None, _('Unspecified')],}  # T: alignment option


def reg_replace(string):
	'''
	Target pattern is translated into source regex pattern
	:param string: target pattern
	:return:source pattern
	'''
	string = string.replace('*', '\*').replace('[', '\[').replace(']', '\]') \
		.replace(r'\1', '(.+?)', 1).replace(r'\2', '(.+?)', 1).replace('|', '\|')
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
		('show_helper_toolbar', 'bool', _('Show helper toolbar'), True),   # T: preference description

		# option for displaying grid-lines within the table
		('grid_lines', 'choice', _('Grid lines'), LINES_BOTH, (LINES_BOTH, LINES_NONE, LINES_HORIZONTAL, LINES_VERTICAL)),
		# T: preference description
	)

	def __init__(self, config=None):
		''' Constructor '''
		PluginClass.__init__(self, config)
		ObjectManager.register_object(OBJECT_TYPE, self.create_table)
		self.connectto(self.preferences, 'changed', self.on_preferences_changed)

	def create_table(self, attrib, text):
		'''
		Automatic way for displaying the table-object as a table within the wiki,
		:param attrib:  {type: 'table', wraps:'1,0,1' , aligns:'left,right,center' }
		:param text: XML - formated as a zim-tree table-object OR tuple of [header], [row1], [row2]
		:return: a TableViewObject
		'''
		assert ElementTree.iselement(text)
		(header, rows) = self._tabledom_to_list(text)
		return TableViewObject(attrib, header, rows, self.preferences)

	def _tabledom_to_list(self, tabledata):
		'''
		Extracts necessary data out of a xml-table into a list structure

		:param tabledata: XML - formated as a zim-tree table-object
		:return: tuple of header-list and list of row lists -  ([h1,h2],[[r11,r12],[r21,r22])
		'''
		header = map(lambda head: head.text.decode('utf-8'), tabledata.findall('thead/th'))
		header = map(CellFormatReplacer.zim_to_cell, header)

		rows = []
		for trow in tabledata.findall('trow'):
			row = trow.findall('td')
			row = [ElementTree.tostring(r, 'utf-8').replace('<td>', '').replace('</td>', '') for r in row]
			row = map(CellFormatReplacer.zim_to_cell, row)
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
			# Links without text are handled as [[link]] and not as [[link|text]], therefore reverse order of replacements
			for pattern, replace in zip(reversed(SYNTAX_WIKI_PANGO), reversed(SYNTAX_WIKI_PANGO2)):
				text = pattern[2].sub(replace[1], text)
		return text

	@staticmethod
	def zim_to_cell(text):
		for pattern, replace in zip(SYNTAX_WIKI_PANGO, SYNTAX_WIKI_PANGO2):
			text = pattern[0].sub(replace[1], text)
		return text

	@staticmethod
	def cell_to_zim(text):
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

	def __init__(self, plugin, window):
		''' Constructor '''
		WindowExtension.__init__(self, plugin, window)

		# reload tables on current page after plugin activation
		if self.window.ui.page:
			self.window.ui.reload_page()

	def teardown(self):
		''' Deconstructor '''
		ObjectManager.unregister_object(OBJECT_TYPE)
		self.window.ui.reload_page()

	@action(_('Table'), stock='zim-insert-table', readonly=False)  # T: menu item
	def insert_table(self):
		'''Run the EditTableDialog'''
		col_model = EditTableDialog(self.window).run()
		if not col_model:
			return

		_ids, headers, aligns, wraps = ([], [], [], [])

		for model in col_model:
			headers.append(model[1])
			aligns.append(model[3])
			wraps.append(model[2])

		attrib = {'aligns': aligns, 'wraps': wraps}
		rows = [len(headers) * [' ']]

		obj = TableViewObject(attrib, headers, rows, self.plugin.preferences)
		pageview = self.window.pageview # XXX
		pageview.insert_object(obj)


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
		self.attrib = {'type': OBJECT_TYPE} # just to be sure

		self._tableattrib = attrib
		self._header = header
		self._rows = rows
		self._widgets = WeakSet()
		self._liststore = None # shared model between widgets

		self.preferences = preferences

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

	def _get_liststore(self, reset=False):
		if reset or not self._liststore:
			cols = [str]*len(self._header)
			self._liststore = gtk.ListStore(*cols)
			for trow in self._rows:
				self._liststore.append(trow)
			self._liststore.connect('row-changed', self.on_modified_changed)

		return self._liststore

	def get_widget(self):
		''' Creates a new table-widget which can displayed on the wiki-page '''
		liststore = self._get_liststore()
		attrib = {'aligns': self.get_aligns(), 'wraps': self.get_wraps()}
		widget = TableViewWidget(self, liststore, self._header, attrib)
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
		headers = self._header
		attrs = {'aligns': self._attrib['aligns'], 'wraps': self._attrib['wraps']}

		if not self._liststore:
			rows = self._rows
		else:
			rows = []
			for treerow in self._liststore:
				rows.append(map(
					lambda cell: CellFormatReplacer.cell_to_input(cell, True),
					treerow
				))

		return headers, rows, attrs

	def change_model(self, new_model):
		'''
		Replace liststore with new model and notify widgets to update
		their treeview.
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

		# update data
		if self._liststore:
			liststore = self._get_liststore()
			self._rows = self._update_rows(liststore, id_mapping, len(headers))
			liststore = self._get_liststore(reset=True)
		else:
			liststore = None
			self._rows = self._update_rows(self._rows, id_mapping, len(headers))

		self.set_aligns(aligns)
		self.set_wraps(wraps)
		self.set_modified(True)

		# notify widgets
		for widget in self._widgets:
			assert liststore is not None, 'Huh?'
			attrib = {'aligns': self.get_aligns(), 'wraps': self.get_wraps()}
			widget.on_model_changed(liststore, headers, attrib)

		self.preferences_changed() # reset prefs on widgets

	def _update_rows(self, old_rows, id_mapping, nr_cols):
		''' Old value of cells are used in the new table, but only if its column is not deleted '''
		new_rows = []
		for oldrow in old_rows:
				newrow = [' ']*nr_cols
				for v, k in id_mapping.iteritems():
					newrow[v] = oldrow[k]
				new_rows.append(newrow)
		return new_rows

	def build_parsetree_of_table(self, builder, iter):
			logger.debug("Anchor with TableObject: %s", self)

			# inserts a newline before and after table-object
			bound = iter.copy()
			bound.backward_char()
			char_before_table = bound.get_slice(iter)
			need_newline_infront = char_before_table.decode('utf-8') != "\n".decode('utf-8')
			bound = iter.copy()
			bound.forward_char()
			iter2 = bound.copy()
			bound.forward_char()
			char_after_table = iter2.get_slice(bound)
			need_newline_behind = char_after_table.decode('utf-8') != "\n".decode('utf-8')
			#

			headers, rows, attrib = self.get_data()
			#~ print "Table data:", headers, rows, attrib


			if need_newline_infront:
				builder.data('\n')

			builder.start(TABLE, attrib)
			builder.start(HEADROW)
			for header in headers:
				builder.append(HEADDATA, header)
			builder.end(HEADROW)
			for row in rows:
				builder.start(TABLEROW)
				for cell in row:
					builder.append(TABLEDATA, cell)
				builder.end(TABLEROW)
			builder.end(TABLE)

			if need_newline_behind:
				builder.data('\n')



GTK_GRIDLINES = {
	LINES_BOTH: gtk.TREE_VIEW_GRID_LINES_BOTH,
	LINES_NONE: gtk.TREE_VIEW_GRID_LINES_NONE,
	LINES_HORIZONTAL: gtk.TREE_VIEW_GRID_LINES_HORIZONTAL,
	LINES_VERTICAL: gtk.TREE_VIEW_GRID_LINES_VERTICAL,
}


class TableViewWidget(CustomObjectWidget):

	__gsignals__ = {
		'size-request': 'override',
	}

	def __init__(self, obj, liststore, headers, attrs):
		'''
		This is a group of GTK Gui elements which are directly displayed within the wiki textarea
		On initilizing also some signals are registered and a toolbar is initialized
		:param obj: a Table-View-Object
		:param liststore: a gtk.ListStore object
		:param headers: list of titles
		:param attrs: table settings, like alignment and wrapping
		:return:
		'''
		CustomObjectWidget.__init__(self)
		self.textarea_width = 0

		# used in pageview
		self._has_cursor = False  # Skip table object, if someone moves cursor around in textview

		# used here
		self.obj = obj
		self._timer = None  # NONE or number of current gobject.timer, which is running
		self._keep_toolbar_open = False  # a cell is currently edited, toolbar should not be hidden
		self._cellinput_canceled = None  # cell changes should be skipped
		self._toolbar_enabled = True  # sets if toolbar should be shown beneath a selected table

		# Toolbar for table actions
		self.toolbar = self.create_toolbar()
		self.toolbar.show_all()
		self.toolbar.set_no_show_all(True)
		self.toolbar.hide()

		# Create treeview
		self._init_treeview(liststore, headers, attrs)

		# package gui elements
		self.vbox.pack_end(self.toolbar)
		self.scroll_win = ScrolledWindow(self.treeview, gtk.POLICY_NEVER, gtk.POLICY_NEVER, gtk.SHADOW_NONE)
		self.vbox.pack_start(self.scroll_win)

	def _init_treeview(self, liststore, headers, attrs):
		# Actual gtk table object
		self.treeview = self.create_treeview(liststore, headers, attrs)

		# Hook up signals & set options
		self.treeview.connect('button-press-event', self.on_button_press_event)
		self.treeview.connect('focus-in-event', self.on_focus_in, self.toolbar)
		self.treeview.connect('focus-out-event', self.on_focus_out, self.toolbar)
		self.treeview.connect('move-cursor', self.on_move_cursor)

		# Set options
		self.treeview.set_grid_lines(gtk.TREE_VIEW_GRID_LINES_BOTH)
		self.treeview.set_receives_default(True)
		self.treeview.set_size_request(-1, -1)
		self.treeview.set_border_width(2)

		# disable interactive column search
		self.treeview.set_enable_search(False)
		gtk.binding_entry_remove(gtk.TreeView, gtk.keysyms.f, gtk.gdk.CONTROL_MASK)
		self.treeview.set_search_column(-1)

	def on_model_changed(self, liststore, headers, attrs):
		'''Called by TableViewObject when columns changed, replaces the
		treeview idget with a new one for the new model
		'''
		self.scroll_win.remove(self.treeview)
		self._init_treeview(liststore, headers, attrs)
		self.scroll_win.add(self.treeview)
		self.scroll_win.show_all()

	def do_size_request(self, requisition):
		wraps = self.obj.get_wraps()
		if not any(wraps):
			return CustomObjectWidget.do_size_request(self, requisition)

		# Negotiate how to wrap ..
		for col in self.treeview.get_columns():
			cr = col.get_cell_renderers()[0]
			cr.set_property('wrap-width', -1) # reset size

			#~ col.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)  # allow column shrinks
			#~ col.set_max_width(0)	 # shrink column
			#~ col.set_max_width(-1)  # reset value
			#~ col.set_sizing(gtk.TREE_VIEW_COLUMN_GROW_ONLY)  # reset value

		CustomObjectWidget.do_size_request(self, requisition)

		#~ print "Widget requests: %i textview: %i" % (requisition.width, self._textview_width)
		if requisition.width > self._textview_width:
			# Figure out width of fixed cols
			fixed = 0
			for col, wrap in zip(self.treeview.get_columns(), wraps):
				if not wrap:
					fixed += col.get_width()

			nwrap = sum(wraps)
			wrap_size = (self._textview_width - fixed) // nwrap

			# Set width for wrappable cols
			#~ print "Fixed, nwrap, wrap_size", (fixed, nwrap, wrap_size)
			for col, wrap in zip(self.treeview.get_columns(), wraps):
				if wrap:
					cr = col.get_cell_renderers()[0]
					cr.set_property('wrap-width', wrap_size) # reset size

			# Update request
			CustomObjectWidget.do_size_request(self, requisition)
		else:
			pass

	def on_focus_in(self, treeview, event, toolbar):
		'''After a table is selected, this function will be triggered'''

		self._keep_toolbar_open = False
		if self._timer:
			gobject.source_remove(self._timer)
		if self._toolbar_enabled:
			toolbar.show()

	def on_focus_out(self, treeview, event, toolbar):
		'''After a table is deselected, this function will be triggered'''
		def receive_alarm():
			if self._keep_toolbar_open:
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
			(0, gtk.STOCK_ADD, self.on_add_row, None, _('Add row')),  # T: tooltip on mouse hover
			(1, gtk.STOCK_DELETE, self.on_delete_row, None, _('Remove row')),  # T: tooltip on mouse hover
			(2, gtk.STOCK_COPY, self.on_clone_row, None, _('Clone row')),  # T: tooltip on mouse hover
			(3, None, None, None, None),
			(4, gtk.STOCK_GO_UP, self.on_move_row, -1, _('Row up')),  # T: tooltip on mouse hover
			(5, gtk.STOCK_GO_DOWN, self.on_move_row, 1, _('Row down')),  # T: tooltip on mouse hover
			(6, None, None, None, None),
			(7, gtk.STOCK_PREFERENCES, self.on_change_columns, None, _('Change columns')),  # T: tooltip on mouse hover
			(8, None, None, None, None),
			(9, gtk.STOCK_HELP, self.on_open_help, None, _('Open help')),  # T: tooltip on mouse hover
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

	def create_treeview(self, liststore, headers, attrs):
		'''
		Initializes a treeview with its model (liststore) and all its columns
		:param headers: a list of title values for the column-headers
		:param rows: a list of list of cells, for the table body
		:param attrs: some more attributes, which define the layout of a column
		:return: gtk.treeview
		'''
		treeview = gtk.TreeView(liststore)

		for i, headcol in enumerate(headers):
			cell = gtk.CellRendererText()
			tview_column = gtk.TreeViewColumn(headcol, cell)
			tview_column.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)  # allow column shrinks
			treeview.append_column(tview_column)

			# set title as label
			header_label = self.create_headerlabel(headcol)
			tview_column.set_widget(header_label)

			# set properties of column
			tview_column.set_attributes(cell, markup=i)
			cell.set_property('editable', True)
			cell.set_property('yalign', 0.0)  # no vertical alignment, text starts on the top
			tview_column.set_sort_column_id(i)
			# set sort function
			liststore.set_sort_func(i, self.sort_by_number_or_string, i)
			# set alignment - left center right
			align = self._column_alignment(attrs['aligns'][i])
			if align:
				tview_column.set_alignment(align)
				cell.set_alignment(align, 0.0)

			# set wrap mode, wrap-size is set elsewhere
			if attrs['wraps'][i]:
				cell.set_property('wrap-mode', pango.WRAP_WORD)

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
		self._toolbar_enabled = preferences.get('show_helper_toolbar', True)
		self.treeview.set_grid_lines(GTK_GRIDLINES[preferences.get('grid_lines', LINES_BOTH)])

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
		linkregex = r'<span foreground="blue">.*?<span.*?>(.*?)</span></span>'
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
			# Right button opens context menu
			self._keep_toolbar_open = True
			cellvalue = self.fetch_cell_by_event(event, treeview)
			linkvalue = self.get_linkurl(cellvalue)
			linkitem_is_activated = (linkvalue is not None)

			menu = gtk.Menu()

			for stock, handler, data, tooltip in (
				(gtk.STOCK_ADD, self.on_add_row, None, _('Add row')),  # T: menu item
				(gtk.STOCK_DELETE, self.on_delete_row, None, _('Delete row')),  # T: menu item
				(gtk.STOCK_COPY, self.on_clone_row, None, _('Clone row')),  # T: menu item
				(None, None, None, None),  # T: menu item
				(gtk.STOCK_JUMP_TO, self.on_open_link, linkvalue, _('Open cell content link')),  # T: menu item
				(None, None, None, None),
				(gtk.STOCK_GO_UP, self.on_move_row, -1, _('Row up')),  # T: menu item
				(gtk.STOCK_GO_DOWN, self.on_move_row, 1, _('Row down')),  # T: menu item
				(None, None, None, None),
				(gtk.STOCK_PREFERENCES, self.on_change_columns, None, _('Change columns'))  # T: menu item
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
									# T: Popup dialog
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
		''' Context menu: Edit table, run the EditTableDialog '''
		aligns = self.obj.get_aligns()
		wraps = self.obj.get_wraps()
		titles = [col.get_title() for col in self.treeview.get_columns()]
		old_model = []
		for i in range(len(titles)):
			old_model.append([i, titles[i], aligns[i], wraps[i]])

		new_model = EditTableDialog(self.get_toplevel(), old_model).run()

		if new_model:
			self.obj.change_model(new_model) # Will call back to change our treeview

	def on_cell_changed(self, cellrenderer, path, text, liststore, colid):
		''' Trigger after cell-editing, to transform displayed table cell into right format '''
		self._keep_toolbar_open = False
		markup = CellFormatReplacer.input_to_cell(text, True)
		liststore[path][colid] = markup
		self._cellinput_canceled = False

	def on_cell_editing_started(self, cellrenderer, editable, path, liststore, colid):
		''' Trigger before cell-editing, to transform text-field data into right format '''
		self._keep_toolbar_open = True

		editable.connect('focus-out-event', self.on_cell_focus_out, cellrenderer, path, liststore, colid)
		markup = liststore[path][colid]
		markup = CellFormatReplacer.cell_to_input(markup, True)
		editable.set_text(markup)
		self._cellinput_canceled = False

	def on_cell_focus_out(self, editable, event, cellrenderer, path, liststore, colid):
		if not self._cellinput_canceled:
			self.on_cell_changed(cellrenderer, path, editable.get_text(), liststore, colid)

	def on_cell_editing_canceled(self, renderer):
		''' Trigger after a cell is edited but any change is skipped '''
		self._cellinput_canceled = True


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
		# T:
		md.run()
		md.destroy()

	#~ def _search_in_widget(self, start, step):
		#~ '''
		#~ Search within a widget
		#~ :param start: position-of-widget
		#~ :param step: search direction (up / down): -1 / 1
		#~ :return: tuple (startiter, enditer, match)
		#~ '''
		#~ if start.get_child_anchor() is None or len(start.get_child_anchor().get_widgets()) < 1:
			#~ return
		#~ widgets = start.get_child_anchor().get_widgets()
		#~ # TODO TODO TODO - generalize interface so all widgets can integrate find
		#~ if isinstance(widgets[0], zim.plugins.tableeditor.TableViewWidget):
			#~ table = widgets[0]
			#~ # get treeview first
			#~ treeview = table.get_treeview()
			#~ liststore = treeview.get_model()
			#~ iter = liststore.get_iter_root()
			#~ while iter is not None:
				#~ for col in range(liststore.get_n_columns()):
					#~ text = liststore.get_value(iter, col)
					#~ matches = self.regex.finditer(text)
					#~ if step == -1:
						#~ matches = list(matches)
						#~ matches.reverse()
					#~ for match in matches:
						#~ startiter = iter
						#~ enditer = iter
						#~ return startiter, enditer, match
				#~ iter = liststore.iter_next(iter)

	#~ def _replace_in_widget(self, start, regex, string, replaceall=False):
		#~ '''
		#~ Replace within a widget
		#~ :param start: position-of-widget
		#~ :param regex: regular expression pattern
		#~ :param text: substituation text
		#~ :param replaceall: boolean if all matches should be replaced
		#~ :return: True / False - a replacement was done / no replaces
		#~ '''
		#~ if start.get_child_anchor() is None or len(start.get_child_anchor().get_widgets()) < 1:
			#~ return
		#~ widgets = start.get_child_anchor().get_widgets()
		#~ if isinstance(widgets[0], zim.plugins.tableeditor.TableViewWidget):
			#~ table = widgets[0]
			#~ liststore = table.get_liststore()
			#~ iter = liststore.get_iter_root()
			#~ has_replaced = False
			#~ while iter is not None:
				#~ for col in range(liststore.get_n_columns()):
					#~ text = liststore.get_value(iter, col)
					#~ if(regex.search(text)):
						#~ newtext = regex.sub(string, text)
						#~ liststore.set_value(iter, col, newtext)
						#~ if(not replaceall):
							#~ return True
						#~ else:
							#~ has_replaced = True
				#~ iter = liststore.iter_next(iter)
		#~ return has_replaced


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

	def __init__(self, ui, tablemodel=None):
		'''
		Constructor, which intializes the dialog window
		:param ui:
		:param tablemodel: list of row-data
		:return:
		'''
		title = _('Insert Table') if tablemodel is None else _('Edit Table')  # T: Dialog title
		Dialog.__init__(self, ui, title)

		# Prepare treeview in which all columns of the table are listed
		self.creation_mode = tablemodel is None
		self.default_column_item = [-1, "", 0, "left", gtk.STOCK_JUSTIFY_LEFT, _("Left")]
		# currently edited cell - tuple (editable, path, colid) save it on exit
		self.currently_edited = None

		# Set layout of Window
		self.add_help_text(_('Managing table columns'))  # T: Description of "Table-Insert" Dialog
		self.set_default_size(380, 400)

		liststore = self._prepare_liststore(tablemodel)
		self.treeview = self._prepare_treeview_with_headcolumn_list(liststore)
		hbox = gtk.HBox(spacing=5)
		hbox.set_size_request(300, 300)
		self.vbox.pack_start(hbox, False)
		header_scrolled_area = ScrolledWindow(self.treeview)
		header_scrolled_area.set_size_request(200, -1)
		hbox.add(header_scrolled_area)
		hbox.add(self._button_box())

		self.show_all()
		if self.creation_mode:  # preselect first entry
			path = self.treeview.get_model().get_path(self.treeview.get_model().get_iter_first())
			self.treeview.set_cursor_on_cell(path, self.treeview.get_column(0), start_editing=True)


	def _prepare_liststore(self, tablemodel):
		'''
		Preparation of liststore to show a treeview, that displays the columns of the table
		:param tablemodel: list of row-data
		:return:liststore
		'''
		first_column_item = list(self.default_column_item)
		first_column_item[1] = _("Column 1")   # T: Initial data for column title in table
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
		column = gtk.TreeViewColumn(_('Auto\nWrap'), cell)  # T: table header
		treeview.append_column(column)
		column.add_attribute(cell, 'active', self.Col.wrapped)

		# 3. Column - Alignment
		store = gtk.ListStore(str, str, str)
		store.append(COLUMNS_ALIGNMENTS['left'])
		store.append(COLUMNS_ALIGNMENTS['center'])
		store.append(COLUMNS_ALIGNMENTS['right'])

		column = gtk.TreeViewColumn(_('Align'))  # T: table header
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
			(gtk.STOCK_ADD, self.on_add_new_column, None, _('Add column')),  # T: hoover tooltip
			(gtk.STOCK_DELETE, self.on_delete_column, None, _('Remove column')),  # T: hoover tooltip
			(gtk.STOCK_GO_UP, self.on_move_column, -1, _('Move column ahead')),  # T: hoover tooltip
			(gtk.STOCK_GO_DOWN, self.on_move_column, 1, _('Move column backward')),  # T: hoover tooltip
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
		if not treeiter:  # preselect first entry
			path = model.iter_n_children(None)-1
			treeiter = model.get_iter(path)
		newiter = model.insert_after(treeiter, self.default_column_item)
		self.treeview.set_cursor_on_cell(model.get_path(newiter), self.treeview.get_column(0), start_editing=True)

	def on_delete_column(self, btn):
		''' Trigger for deleting a column out of the table / it is a deleted row in the treeview '''
		self.autosave_title_cell()
		(model, treeiter) = self.treeview.get_selection().get_selected()

		if treeiter:
			if len(model) > 1:
				model.remove(treeiter)
			else:
				md = gtk.MessageDialog(None, gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_WARNING, gtk.BUTTONS_CLOSE,
										_("A table needs to have at least one column."))  # T: popup dialog
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
								_("Please select a row, before you push the button.")) # T: Popup dialog
		md.run()
		md.destroy()
