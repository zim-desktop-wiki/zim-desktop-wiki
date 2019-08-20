
# Copyright 2015 Tobias Haupenthal
# Copyright 2016-2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>


from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import Pango

import re
import logging


logger = logging.getLogger('zim.plugin.tableeditor')

from zim.plugins import PluginClass, InsertedObjectTypeExtension
from zim.actions import action
from zim.signals import SignalEmitter, ConnectorMixin, SIGNAL_RUN_LAST
from zim.utils import WeakSet, natural_sort_key
from zim.config import String
from zim.main import ZIM_APPLICATION
from zim.formats import ElementTreeModule as ElementTree
from zim.formats import TABLE, HEADROW, HEADDATA, TABLEROW, TABLEDATA
from zim.formats.wiki import Parser as WikiParser

from zim.gui.pageview import PageViewExtension
from zim.gui.widgets import Dialog, ScrolledWindow, IconButton, InputEntry, gtk_popup_at_pointer
from zim.gui.insertedobjects import InsertedObjectWidget


SYNTAX_CELL_INPUT = [
	('&amp;', '&'), ('&gt;', '>'), ('&lt;', '<'), ('&quot;', '"'), ('&apos;', "'")
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
COLUMNS_ALIGNMENTS = {'left': ['left', Gtk.STOCK_JUSTIFY_LEFT, _('Left')],  # T: alignment option
					  'center': ['center', Gtk.STOCK_JUSTIFY_CENTER, _('Center')],  # T: alignment option
					  'right': ['right', Gtk.STOCK_JUSTIFY_RIGHT, _('Right')],  # T: alignment option
					  'normal': ['normal', None, _('Unspecified')], }  # T: alignment option


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
	'''
	plugin_info = {
		'name': _('Table Editor'),  # T: plugin name
		'description': _('''\
With this plugin you can embed a 'Table' into the wiki page. Tables will be shown as GTK TreeView widgets.
Exporting them to various formats (i.e. HTML/LaTeX) completes the feature set.
'''),  # T: plugin description
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


class CellFormatReplacer:
	'''
	Static class for converting formated text from one into the other format:
	- cell:	in a wiki pageview the table-cell must be of this format
	- input: if a user is editing the cell, this format is used
	- zimtree: Format for zimtree xml structure
	'''
	@staticmethod
	def cell_to_input(text, with_pango=True):
		''' Displayed table-cell will converted to gtk-entry input text '''
		text = text or ''
		if with_pango:
			for pattern, replace in zip(SYNTAX_WIKI_PANGO, SYNTAX_WIKI_PANGO2):
				text = pattern[1].sub(replace[2], text)
		for k, v in SYNTAX_CELL_INPUT:
			text = text.replace(k, v)
		return text

	@staticmethod
	def input_to_cell(text, with_pango=True):
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


class TableViewObjectType(InsertedObjectTypeExtension):

	name = 'table'

	label = _('Table') # T: menu item
	verb_icon = 'zim-insert-table'

	object_attr = {
		'aligns': String(''),  # i.e. String(left,right,center)
		'wraps': String('')	  # i.e. String(0,1,0)
	}

	def __init__(self, plugin, objmap):
		self._widgets = WeakSet()
		self.preferences = plugin.preferences
		InsertedObjectTypeExtension.__init__(self, plugin, objmap)
		self.connectto(self.preferences, 'changed', self.on_preferences_changed)

	def new_model_interactive(self, parent, notebook, page):
		definition = EditTableDialog(parent).run()
		if definition is None:
			raise ValueError # dialog cancelled

		ids, headers, wraps, aligns = definition
		attrib = self.parse_attrib({
			'aligns': ','.join(map(str, aligns)),
			'wraps': ','.join(map(str, wraps))
		})
		rows = [''] * len(headers)
		return TableModel(attrib, headers, rows)

	def model_from_data(self, notebook, page, attrib, data):
		tree = WikiParser().parse(data)
		element = tree._etree.getroot().find('table') # XXX - should use token interface instead
		if element is not None:
			return self.model_from_element(element.attrib, element)
		else:
			return TableModel(attrib, [data.strip()], [''])

	def model_from_element(self, attrib, element):
		assert ElementTree.iselement(element)
		attrib = self.parse_attrib(attrib)
		headers, rows = self._tabledom_to_list(element)
		return TableModel(attrib, headers, rows)

	def _tabledom_to_list(self, tabledata):
		'''
		Extracts necessary data out of a xml-table into a list structure

		:param tabledata: XML - formated as a zim-tree table-object
		:return: tuple of header-list and list of row lists -  ([h1,h2],[[r11,r12],[r21,r22])
		'''
		headers = [head.text for head in tabledata.findall('thead/th')]
		headers = list(map(CellFormatReplacer.zim_to_cell, headers))

		rows = []
		for trow in tabledata.findall('trow'):
			row = trow.findall('td')
			row = [ElementTree.tostring(r, 'unicode').replace('<td>', '').replace('</td>', '') for r in row]
			row = list(map(CellFormatReplacer.zim_to_cell, row))
			rows.append(row)
		return headers, rows

	def create_widget(self, model):
		widget = TableViewWidget(model)
		widget.set_preferences(self.preferences)
		self._widgets.add(widget)
		return widget

	def on_preferences_changed(self, preferences):
		for widget in self._widgets:
			widget.set_preferences(preferences)

	def dump(self, builder, model):
		headers, attrib, rows = model.get_object_data()
		def append(tag, text):
			builder.start(tag)
			builder.data(text)
			builder.end(tag)

		builder.start(TABLE, dict(attrib))
		builder.start(HEADROW)
		for header in headers:
			append(HEADDATA, header)
		builder.end(HEADROW)
		for row in rows:
			builder.start(TABLEROW)
			for cell in row:
				append(TABLEDATA, cell)
			builder.end(TABLEROW)
		builder.end(TABLE)


class TableModel(ConnectorMixin, SignalEmitter):
	'''Thin object that contains a C{Gtk.ListStore}
	Key purpose of this wrapper is to allow replacing the store
	'''

	__signals__ = {
		'changed': (SIGNAL_RUN_LAST, None, ()),
		'model-changed': (SIGNAL_RUN_LAST, None, ()),
	}

	def __init__(self, attrib, headers, rows):
		self._attrib = attrib
		self.headers = headers
		self.liststore = self._create_liststore(headers)
		for row in rows:
			self.liststore.append(row)

	def _create_liststore(self, headers):
		cols = [str] * len(headers)
		self.liststore = Gtk.ListStore(*cols)
		self.connectto_all(
			self.liststore,
			('row-changed', 'row-deleted', 'row-inserted', 'rows-reordered'),
			handler=lambda *a: self.emit('changed')
		)
		return self.liststore

	def get_object_data(self):
		rows = [
			map(CellFormatReplacer.cell_to_input, row)
				for row in self.liststore
		]
		return self.headers, self._attrib, rows

	def get_aligns(self):
		return self._attrib['aligns'].split(',')

	def set_aligns(self, data):
		self._attrib['aligns'] = ','.join(map(str, data))

	def get_wraps(self):
		return list(map(int, self._attrib['wraps'].split(',')))

	def set_wraps(self, data):
		self._attrib['wraps'] = ','.join(map(str, data))

	def change_model(self, newdefinition):
		'''Creates a new C{Gtk.ListStore} based on C{newdefinition}
		and notifies all widgets to replace the current one by the
		"model-changed" signal
		'''
		ids, headers, wraps, aligns = newdefinition

		self.disconnect_from(self.liststore)
		oldliststore = self.liststore

		self.liststore = self._create_liststore(headers)
		self.headers = headers
		self.set_aligns(aligns)
		self.set_wraps(wraps)

		for row in oldliststore:
			newrow = [
				(row[i] if i >= 0 else '') for i in ids
			]
			self.liststore.append(newrow)

		self.emit('model-changed')
		self.emit('changed')


GTK_GRIDLINES = {
	LINES_BOTH: Gtk.TreeViewGridLines.BOTH,
	LINES_NONE: Gtk.TreeViewGridLines.NONE,
	LINES_HORIZONTAL: Gtk.TreeViewGridLines.HORIZONTAL,
	LINES_VERTICAL: Gtk.TreeViewGridLines.VERTICAL,
}


class TableViewWidget(InsertedObjectWidget):

	def __init__(self, model):
		InsertedObjectWidget.__init__(self)
		self.textarea_width = 0
		self.model = model

		# used in pageview
		self._has_cursor = False  # Skip table object, if someone moves cursor around in textview

		# used here
		self._timer = None  # NONE or number of current GObject.timer, which is running
		self._keep_toolbar_open = False  # a cell is currently edited, toolbar should not be hidden
		self._cellinput_canceled = None  # cell changes should be skipped
		self._toolbar_enabled = True  # sets if toolbar should be shown beneath a selected table

		# Toolbar for table actions
		self.toolbar = self.create_toolbar()
		self.toolbar.show_all()
		self.toolbar.set_no_show_all(True)
		self.toolbar.hide()

		# Create treeview
		self._init_treeview(model)

		# package gui elements
		self.vbox = Gtk.VBox()
		self.add(self.vbox)
		self.vbox.pack_end(self.toolbar, True, True, 0)
		self.scroll_win = ScrolledWindow(self.treeview, Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER, Gtk.ShadowType.NONE)
		self.vbox.pack_start(self.scroll_win, True, True, 0)

		# signals
		model.connect('model-changed', self.on_model_changed)

	def _init_treeview(self, model):
		# Actual gtk table object
		self.treeview = self.create_treeview(model)

		# Hook up signals & set options
		self.treeview.connect('button-press-event', self.on_button_press_event)
		self.treeview.connect('focus-in-event', self.on_focus_in, self.toolbar)
		self.treeview.connect('focus-out-event', self.on_focus_out, self.toolbar)
		self.treeview.connect('move-cursor', self.on_move_cursor)

		# Set options
		self.treeview.set_grid_lines(Gtk.TreeViewGridLines.BOTH)
		self.treeview.set_receives_default(True)
		self.treeview.set_size_request(-1, -1)
		self.treeview.set_border_width(2)

		# disable interactive column search
		self.treeview.set_enable_search(False)
		#Gtk.binding_entry_remove(Gtk.TreeView, Gdk.KEY_f, Gdk.ModifierType.CONTROL_MASK)
		self.treeview.set_search_column(-1)

	def on_model_changed(self, model):
		self.scroll_win.remove(self.treeview)
		self.treeview.destroy()
		self._init_treeview(model)
		self.scroll_win.add(self.treeview)
		self.scroll_win.show_all()

	def old_do_size_request(self, requisition): # TODO - FIX this behavior
		model = self.get_model()
		wraps = model.get_wraps()
		if not any(wraps):
			return InsertedObjectWidget.do_size_request(self, requisition)

		# Negotiate how to wrap ..
		for col in self.treeview.get_columns():
			cr = col.get_cell_renderers()[0]
			cr.set_property('wrap-width', -1) # reset size

			#~ col.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)  # allow column shrinks
			#~ col.set_max_width(0)	 # shrink column
			#~ col.set_max_width(-1)  # reset value
			#~ col.set_sizing(Gtk.TreeViewColumnSizing.GROW_ONLY)  # reset value

		InsertedObjectWidget.do_size_request(self, requisition)

		#~ print("Widget requests: %i textview: %i" % (requisition.width, self._textview_width))
		if requisition.width > self._textview_width:
			# Figure out width of fixed cols
			fixed = 0
			for col, wrap in zip(self.treeview.get_columns(), wraps):
				if not wrap:
					fixed += col.get_width()

			nwrap = sum(wraps)
			wrap_size = (self._textview_width - fixed) // nwrap

			# Set width for wrappable cols
			#~ print("Fixed, nwrap, wrap_size", (fixed, nwrap, wrap_size))
			for col, wrap in zip(self.treeview.get_columns(), wraps):
				if wrap:
					cr = col.get_cell_renderers()[0]
					cr.set_property('wrap-width', wrap_size) # reset size

			# Update request
			InsertedObjectWidget.do_size_request(self, requisition)
		else:
			pass

	def on_focus_in(self, treeview, event, toolbar):
		'''After a table is selected, this function will be triggered'''

		self._keep_toolbar_open = False
		if self._timer:
			GObject.source_remove(self._timer)
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

		self._timer = GObject.timeout_add(500, receive_alarm)

	def create_toolbar(self):
		'''This function creates a toolbar which is displayed next to the table'''
		toolbar = Gtk.Toolbar()
		toolbar.set_orientation(Gtk.Orientation.HORIZONTAL)
		toolbar.set_style(Gtk.ToolbarStyle.ICONS)
		toolbar.set_border_width(1)

		for pos, stock, handler, data, tooltip in (
			(0, Gtk.STOCK_ADD, self.on_add_row, None, _('Add row')),  # T: tooltip on mouse hover
			(1, Gtk.STOCK_DELETE, self.on_delete_row, None, _('Remove row')),  # T: tooltip on mouse hover
			(2, Gtk.STOCK_COPY, self.on_clone_row, None, _('Clone row')),  # T: tooltip on mouse hover
			(3, None, None, None, None),
			(4, Gtk.STOCK_GO_UP, self.on_move_row, -1, _('Row up')),  # T: tooltip on mouse hover
			(5, Gtk.STOCK_GO_DOWN, self.on_move_row, 1, _('Row down')),  # T: tooltip on mouse hover
			(6, None, None, None, None),
			(7, Gtk.STOCK_PREFERENCES, self.on_change_columns, None, _('Change columns')),  # T: tooltip on mouse hover
			(8, None, None, None, None),
			(9, Gtk.STOCK_HELP, self.on_open_help, None, _('Open help')),  # T: tooltip on mouse hover
		):
			if stock is None:
				toolbar.insert(Gtk.SeparatorToolItem(), pos)
			else:
				button = Gtk.ToolButton(stock)
				if data:
					button.connect('clicked', handler, data)
				else:
					button.connect('clicked', handler)
				button.set_tooltip_text(tooltip)
				toolbar.insert(button, pos)

		toolbar.set_size_request(300, -1)
		toolbar.set_icon_size(Gtk.IconSize.MENU)

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

	def create_treeview(self, model):
		'''Initializes a treeview with its model (liststore) and all its columns'''
		treeview = Gtk.TreeView(model.liststore)

		# Set default sorting function.
		model.liststore.set_default_sort_func(lambda *a: 0)

		aligns = model.get_aligns()
		wraps = model.get_wraps()
		for i, headcol in enumerate(model.headers):
			cell = Gtk.CellRendererText()
			tview_column = Gtk.TreeViewColumn(headcol, cell)
			tview_column.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)  # allow column shrinks
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
			model.liststore.set_sort_func(i, self.sort_by_number_or_string, i)
			# set alignment - left center right
			align = self._column_alignment(aligns[i])
			if align:
				tview_column.set_alignment(align)
				cell.set_alignment(align, 0.0)

			# set wrap mode, wrap-size is set elsewhere
			if wraps[i]:
				cell.set_property('wrap-mode', Pango.WrapMode.WORD)

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
		col_widget = Gtk.VBox()
		col_widget.show()


		col_label = Gtk.Label(label='<u>' + title + '</u>')
		col_label.set_use_markup(True)
		col_label.show()
		col_widget.pack_start(col_label, True, True, 0)
		#col_align.add(col_label)

		'''col_entry = InputEntry()
		col_entry.set_name('treeview-header-entry')
		col_entry.show()
		col_widget.pack_start(col_entry, True, True, 0)'''

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
		if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 1 and event.get_state() & Gdk.ModifierType.CONTROL_MASK:
			# With CTRL + LEFT-Mouse-Click link of cell is opened
			cellvalue = self.fetch_cell_by_event(event, treeview)
			linkvalue = self.get_linkurl(cellvalue)
			if linkvalue:
				self.emit('link-clicked', {'href': str(linkvalue)})
			return

		if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 3:
			# Right button opens context menu
			self._keep_toolbar_open = True
			cellvalue = self.fetch_cell_by_event(event, treeview)
			linkvalue = self.get_linkurl(cellvalue)
			linkitem_is_activated = (linkvalue is not None)

			menu = Gtk.Menu()

			for stock, handler, data, tooltip in (
				(Gtk.STOCK_ADD, self.on_add_row, None, _('Add row')),  # T: menu item
				(Gtk.STOCK_DELETE, self.on_delete_row, None, _('Delete row')),  # T: menu item
				(Gtk.STOCK_COPY, self.on_clone_row, None, _('Clone row')),  # T: menu item
				(None, None, None, None),  # T: menu item
				(Gtk.STOCK_JUMP_TO, self.on_open_link, linkvalue, _('Open cell content link')),  # T: menu item
				(None, None, None, None),
				(Gtk.STOCK_GO_UP, self.on_move_row, -1, _('Row up')),  # T: menu item
				(Gtk.STOCK_GO_DOWN, self.on_move_row, 1, _('Row down')),  # T: menu item
				(None, None, None, None),
				(Gtk.STOCK_PREFERENCES, self.on_change_columns, None, _('Change columns'))  # T: menu item
			):

				if stock is None:
					menu.append(Gtk.SeparatorMenuItem())
				else:
					item = Gtk.ImageMenuItem(stock)
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
			gtk_popup_at_pointer(menu, event)

	def on_add_row(self, action):
		''' Context menu: Add a row '''
		selection = self.treeview.get_selection()
		model, treeiter = selection.get_selected()
		if not treeiter:  # no selected item
			self.selection_info()
			return

		# Set default sorting.
		model.set_sort_column_id(-1, Gtk.SortType.ASCENDING)

		row = len(self.treeview.get_columns()) * ['']
		path = model.insert_after(treeiter, row)

	def on_clone_row(self, action):
		''' Context menu: Clone a row '''
		selection = self.treeview.get_selection()
		model, treeiter = selection.get_selected()
		if not treeiter:  # no selected item
			self.selection_info()
			return

		path = model.get_path(treeiter)
		row = list(model[path[0]]) # copy
		model.insert_after(treeiter, row)

	def on_delete_row(self, action):
		''' Context menu: Delete a row '''
		selection = self.treeview.get_selection()
		model, treeiter = selection.get_selected()
		if not treeiter:  # no selected item
			self.selection_info()
			return

		if len(model) > 1:
			model.remove(treeiter)
		else:
			md = Gtk.MessageDialog(None, Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.WARNING, Gtk.ButtonsType.CLOSE,
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

		# Set default sorting.
		model.set_sort_column_id(-1, Gtk.SortType.ASCENDING)

		# Change values of two rows.
		for col in range(model.get_n_columns()):
			value = model.get_value(treeiter, col)
			newvalue = model.get_value(newiter, col)
			model.set_value(newiter, col, value)
			model.set_value(treeiter, col, newvalue)

	def on_open_link(self, action, link):
		''' Context menu: Open a link, which is written in a cell '''
		self.emit('link-clicked', {'href': str(link)})

	def on_open_help(self, action):
		''' Context menu: Open help '''
		ZIM_APPLICATION.run('--manual', 'Plugins:Table Editor')

	def on_change_columns(self, action):
		''' Context menu: Edit table, run the EditTableDialog '''
		aligns = self.model.get_aligns()
		wraps = self.model.get_wraps()
		headers = [col.get_title() for col in self.treeview.get_columns()]
		ids = [i for i in range(len(headers))]
		definition = ids, headers, wraps, aligns
		newdefinition = EditTableDialog(self.get_toplevel(), definition).run()
		if newdefinition:
			self.model.change_model(newdefinition) # Will call back to change our treeview

	def on_cell_changed(self, cellrenderer, path, text, liststore, colid):
		''' Trigger after cell-editing, to transform displayed table cell into right format '''
		self._keep_toolbar_open = False
		markup = CellFormatReplacer.input_to_cell(text)
		liststore[path][colid] = markup
		self._cellinput_canceled = False

	def on_cell_editing_started(self, cellrenderer, editable, path, liststore, colid):
		''' Trigger before cell-editing, to transform text-field data into right format '''
		self._keep_toolbar_open = True

		editable.connect('focus-out-event', self.on_cell_focus_out, cellrenderer, path, liststore, colid)
		markup = liststore[path][colid]
		markup = CellFormatReplacer.cell_to_input(markup)
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
		data1 = natural_sort_key(liststore.get_value(treeiter1, colid))
		data2 = natural_sort_key(liststore.get_value(treeiter2, colid))
		return (data1 > data2) - (data1 < data2) # python3 jargon for "cmp()"

	def selection_info(self):
		''' Info-Popup for selecting a cell before this action can be done '''
		md = Gtk.MessageDialog(None, Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.WARNING, Gtk.ButtonsType.CLOSE,
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
		id, title, wrapped, align, alignicon, aligntext = list(range(6))

	def __init__(self, parent, definition=None):
		'''
		Constructor, which intializes the dialog window
		:param parent:
		:param definition: tuple of C{(ids, headers, wraps, aligns)}
		:return:
		'''
		title = _('Insert Table') if definition is None else _('Edit Table')  # T: Dialog title
		Dialog.__init__(self, parent, title)

		# Prepare treeview in which all columns of the table are listed
		self.default_column_item = [-1, "", 0, "left", Gtk.STOCK_JUSTIFY_LEFT, _("Left")]
		# currently edited cell - tuple (editable, path, colid) save it on exit
		self.currently_edited = None

		# Set layout of Window
		self.add_help_text(_('Managing table columns'))  # T: Description of "Table-Insert" Dialog
		self.set_default_size(380, 400)

		liststore = self._prepare_liststore(definition)
		self.treeview = self._prepare_treeview_with_headcolumn_list(liststore)
		hbox = Gtk.HBox(spacing=5)
		hbox.set_size_request(300, 300)
		self.vbox.pack_start(hbox, False, True, 0)
		header_scrolled_area = ScrolledWindow(self.treeview)
		header_scrolled_area.set_size_request(200, -1)
		hbox.pack_start(header_scrolled_area, True, True, 0)
		hbox.pack_start(self._button_box(), False, False, 0)

		self.show_all()
		if definition is None: # preselect first entry
			path = self.treeview.get_model().get_path(self.treeview.get_model().get_iter_first())
			self.treeview.set_cursor_on_cell(path, self.treeview.get_column(0), None, True)


	def _prepare_liststore(self, definition):
		'''
		Preparation of liststore to show a treeview, that displays the columns of the table
		:param definition: tuple of C{(ids, headers, wraps, aligns)}
		:return:liststore
		'''
		liststore = Gtk.ListStore(int, str, int, str, str, str)

		# each table column is displayed in a new row
		if definition is None:
			first_column_item = list(self.default_column_item)
			first_column_item[1] = _("Column 1")   # T: Initial data for column title in table
			liststore.append(first_column_item)
		else:
			ids, headers, wraps, aligns = definition
			default_align = COLUMNS_ALIGNMENTS['normal']
			for row in map(list, zip(ids, headers, wraps, aligns)):
				align = row.pop()
				align_fields = COLUMNS_ALIGNMENTS.get(align, default_align)
				row.extend(align_fields)
				liststore.append(row)

		return liststore

	def _prepare_treeview_with_headcolumn_list(self, liststore):
		'''
		Preparation of the treeview element, that displays the columns of the table
		:param liststore: model for current treeview
		:return: the treeview
		'''
		treeview = Gtk.TreeView(liststore)

		# 1. Column - Title
		cell = Gtk.CellRendererText()
		cell.set_property('editable', True)
		column = Gtk.TreeViewColumn(_('Title'), cell, text=self.Col.title)
		column.set_min_width(120)
		treeview.append_column(column)
		cell.connect('edited', self.on_cell_changed, liststore, self.Col.title)
		cell.connect('editing-started', self.on_cell_editing_started, liststore, self.Col.title)

		# 2. Column - Wrap Line
		cell = Gtk.CellRendererToggle()
		cell.connect('toggled', self.on_wrap_toggled, liststore, self.Col.wrapped)
		column = Gtk.TreeViewColumn(_('Auto\nWrap'), cell)  # T: table header
		treeview.append_column(column)
		column.add_attribute(cell, 'active', self.Col.wrapped)

		# 3. Column - Alignment
		store = Gtk.ListStore(str, str, str)
		store.append(COLUMNS_ALIGNMENTS['left'])
		store.append(COLUMNS_ALIGNMENTS['center'])
		store.append(COLUMNS_ALIGNMENTS['right'])

		column = Gtk.TreeViewColumn(_('Align'))  # T: table header
		cellicon = Gtk.CellRendererPixbuf()
		column.pack_start(cellicon, True)
		column.add_attribute(cellicon, 'stock-id', self.Col.alignicon)

		cell = Gtk.CellRendererCombo()
		cell.set_property('model', store)
		cell.set_property('has-entry', False)
		cell.set_property('text-column', 2)
		cell.set_property('width', 50)
		cell.set_property('editable', True)
		column.pack_start(cell, True)
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
		vbox = Gtk.VBox(spacing=5)
		for stock, handler, data, tooltip in (
			(Gtk.STOCK_ADD, self.on_add_new_column, None, _('Add column')),  # T: hoover tooltip
			(Gtk.STOCK_DELETE, self.on_delete_column, None, _('Remove column')),  # T: hoover tooltip
			(Gtk.STOCK_GO_UP, self.on_move_column, -1, _('Move column ahead')),  # T: hoover tooltip
			(Gtk.STOCK_GO_DOWN, self.on_move_column, 1, _('Move column backward')),  # T: hoover tooltip
		):
			button = IconButton(stock)
			if data:
				button.connect('clicked', handler, data)
			else:
				button.connect('clicked', handler)
			button.set_tooltip_text(tooltip)
			vbox.pack_start(button, False, True, 0)

		vbox.show_all()
		return vbox

	def do_response_ok(self):
		''' Dialog Window is closed with "OK" '''
		self.autosave_title_cell()
		m = [r[0:4] for r in self.treeview.get_model()]
		ids, headers, aligns, wraps = list(zip(*m))
		self.result = ids, headers, aligns, wraps
		return True

	def do_response_cancel(self):
		''' Dialog Window is closed with "Cancel" '''
		self.result = None
		return True

	def on_cell_editing_started(self, renderer, editable, path, model, colid):
		''' Trigger before cell-editing, to transform text-field data into right format '''
		text = model[path][colid]
		text = CellFormatReplacer.cell_to_input(text, with_pango=False)
		editable.set_text(text)
		self.currently_edited = (editable, model, path, colid)

	def on_cell_changed(self, renderer, path, text, model, colid):
		''' Trigger after cell-editing, to transform text-field data into right format '''
		model[path][colid] = CellFormatReplacer.input_to_cell(text, with_pango=False)
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
			model[path][colid] = CellFormatReplacer.input_to_cell(text, with_pango=False)
			self.currently_edited = None

	def on_add_new_column(self, btn):
		''' Trigger for adding a new column into the table / it is a new row in the treeview '''
		self.autosave_title_cell()
		(model, treeiter) = self.treeview.get_selection().get_selected()
		if not treeiter:  # preselect first entry
			path = model.iter_n_children(None) - 1
			treeiter = model.get_iter(path)
		newiter = model.insert_after(treeiter, self.default_column_item)
		self.treeview.set_cursor_on_cell(model.get_path(newiter), self.treeview.get_column(0), None, True)

	def on_delete_column(self, btn):
		''' Trigger for deleting a column out of the table / it is a deleted row in the treeview '''
		self.autosave_title_cell()
		(model, treeiter) = self.treeview.get_selection().get_selected()

		if treeiter:
			if len(model) > 1:
				model.remove(treeiter)
			else:
				md = Gtk.MessageDialog(None, Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.WARNING, Gtk.ButtonsType.CLOSE,
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
		md = Gtk.MessageDialog(None, Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.WARNING, Gtk.ButtonsType.CLOSE,
								_("Please select a row, before you push the button.")) # T: Popup dialog
		md.run()
		md.destroy()
