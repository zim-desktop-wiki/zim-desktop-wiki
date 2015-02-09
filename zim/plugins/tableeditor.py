# -*- coding: utf-8 -*-

# Copyright 2015 Tobias Haupenthal

import gtk
import logging
from xml.etree import ElementTree
import pango
import re

logger = logging.getLogger('zim.plugin.tableeditor')

from zim.actions import action
from zim.plugins import PluginClass, extends, WindowExtension
from zim.utils import WeakSet
from zim.objectmanager import ObjectManager, CustomObjectClass
from zim.config import String
from zim.gui.widgets import Dialog, ScrolledWindow, IconButton
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

	# TODO cleanup
	plugin_preferences = (
		# key, type, label, default
		('auto_indent', 'bool', _('Auto indenting'), True),
			# T: preference option for tableeditor plugin
		('smart_home_end', 'bool', _('Smart Home key'), True),
			# T: preference option for tableeditor plugin
		('highlight_current_line', 'bool', _('Highlight current line'), False),
			# T: preference option for tableeditor plugin
		('show_right_margin', 'bool', _('Show right margin'), False),
			# T: preference option for tableeditor plugin
		('right_margin_position', 'int', _('Right margin position'), 72, (1, 1000)),
			# T: preference option for tableeditor plugin
		('tab_width', 'int', _('Tab width'), 4, (1, 80)),
			# T: preference option for tableeditor plugin
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
		geometry = MainWindowExtension.window.pageview.view.get_window(gtk.TEXT_WINDOW_TEXT).get_geometry()
		assert(geometry is not None)
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
		for col in new_treeview.get_columns():
			new_treeview.remove_column(col)
			obj.treeview.append_column(col)

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
		'text': String('abc'),
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
		return self._attrib['aligns'].split(',')

	def set_aligns(self, data):
		assert(isinstance(data, list))
		self._attrib['aligns'] = ','.join(data)

	def get_wraps(self):
		return map(int, self._attrib['wraps'].split(','))

	def set_wraps(self, data):
		assert(isinstance(data, list))
		self._attrib['wraps'] = ','.join(str(item) for item in data)

	def set_textview_geometry(self, geometry):
		self.textview_geometry = geometry

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

	def on_modified_changed(self, liststore, path, iter):
		''' Trigger after a table cell content is changed by the user '''
		self.set_modified(True)

	def get_data(self):
		'''Returns table-object into textual data, for saving it as text.'''
		liststore = self.treeview.get_model()
		logger.fatal("get-data")
		logger.fatal(liststore)
		headers = []
		aligns = []
		rows = []
		wraps = []

		# parsing table header and attributes
		for column in self.treeview.get_columns():
			title = column.get_title() if column.get_title() else ' '
			headers.append(title)
		attrs = {'aligns': self._attrib['aligns'], 'wraps': self._attrib['wraps']}

		# parsing rows
		iter = liststore.get_iter_first()
		while iter is not None:
			row = []
			for colid in range(len(self.treeview.get_columns())):
				val = liststore.get_value(iter, colid) if liststore.get_value(iter, colid) else ' '
				row.append(val)
			rows.append(row)
			iter = liststore.iter_next(iter)
		rows = [map(lambda cell: CellFormatReplacer.cell_to_input(cell, True), row) for row in rows]

		logger.debug("Table as get-data: : %s, %s, %s", headers, rows, attrs)
		return headers, rows, attrs


	def dump(self, format, dumper, linker=None):
		''' Dumps currently structure for table into textual format - mostly used for debugging / testing purposes '''
		return CustomObjectClass.dump(self, format, dumper, linker)


class TableViewWidget(CustomObjectWidget):
	textarea_width = None
	# TODO add comments
	def __init__(self, obj, headers, rows, attrs):
		if MainWindowExtension.get_geometry() is not None:
			self.textarea_width = MainWindowExtension.get_geometry()[2]

		#logger.fatal(MainWindowExtension.textarea_width)

		logger.fatal("----------------")
		self.obj = obj
		#self.liststore = None


		#tree = self.get_treeview()
		#logger.fatal(tree)
		#raise
		#logger.fatal(self._data.get('cols'))


		gtk.EventBox.__init__(self)
		self.set_border_width(5)
		self._has_cursor = False
		self._resize = True

		#

		# Add vbox and wrap it to have a shadow around it
		self.vbox = gtk.VBox() #: C{gtk.VBox} to contain widget contents
		win = ScrolledWindow(self.vbox, gtk.POLICY_NEVER, gtk.POLICY_NEVER, gtk.SHADOW_IN)
		#win.add(gtk.Button("abc",gtk.STOCK_OK))
		#self.add(win)

		self.set_has_cursor(True)

		self.treeview = self.create_treeview(headers, rows, attrs)
		#win = ScrolledWindow(self.treeview, gtk.POLICY_AUTOMATIC, gtk.POLICY_NEVER, gtk.SHADOW_NONE)
		# only horizontal scroll
		#self.vbox.pack_start(win)

		# Hook up signals
		self.treeview.connect('button-press-event', self.on_button_press_event)
		self.treeview.set_receives_default(True)
		self.treeview.set_size_request(-1, -1)


		self.add(self.treeview)
		#self.treeview.set_border_width(5)
		#self.treeview.connect('row-activated', self.on_row_activated)
		#self.treeview.connect('populate-popup', self.on_populate_popup)
		#self.view.connect('move-cursor', self.on_move_cursor)

	def resize_to_textview(self, view):
		win = view.get_window(gtk.TEXT_WINDOW_TEXT)
		if not win:
			return
		self.textarea_width = win.get_geometry()[2]

		vmargin = view.get_left_margin() + view.get_right_margin() \
					+ 2 * self.get_border_width()

		# override size
		#self.get_size_request()

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


	def get_treeview(self):
		return self.treeview

	#def get_liststore(self):
	#	return self.liststore

	def create_treeview(self, headers, rows, attrs):
		#logger.fatal(attrs)
		nrcols = len(headers)

		cols = [str]*nrcols

		#self.liststore = gtk.ListStore(*cols)
		liststore = gtk.ListStore(*cols)
		treeview = gtk.TreeView(liststore)

		align = None
		for i, headcol in enumerate(headers):
			#logger.fatal("new head")
			cell = gtk.CellRendererText()
			tview_column = gtk.TreeViewColumn(headcol, cell)
			treeview.append_column(tview_column)

			if attrs['wraps'][i] == 1 and gtk.gtk_version >= (2, 8) and self.textarea_width is not None:
				cell.set_property('wrap-width', self.textarea_width/len(headers))
				cell.set_property('wrap-mode', pango.WRAP_WORD)
			#tview_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
			#tview_column.set_expand(False)

			#tview_column.pack_start(cell, True)

			# set sort function
			liststore.set_sort_func(i, self.sort_by_number_or_string, i)

			# set alignment

			align = self._column_alignment(attrs['aligns'][i])
			if align:
				tview_column.set_alignment(align)
				cell.set_alignment(align, 0.0)

			# set properties of column
			tview_column.set_attributes(cell, markup=i)
			tview_column.set_sort_column_id(i)

			# set properties of cell
			cell.set_property('editable', True)
			cell.connect('edited', self.on_cell_changed, treeview.get_model(), i)
			cell.connect('editing-started', self.on_cell_editing_started, treeview.get_model(), i)


		for trow in rows:
			liststore.append(trow)


		# Hook up signals
		treeview.connect('move-cursor', self.on_move_cursor)

		return treeview


	def set_preferences(self, preferences):
		logger.fatal("Preferences changed")
		pass
		#self.view.set_auto_indent(preferences['auto_indent'])
		#self.view.set_smart_home_end(preferences['smart_home_end'])
		#self.view.set_highlight_current_line(preferences['highlight_current_line'])
		#self.view.set_right_margin_position(preferences['right_margin_position'])
		#self.view.set_show_right_margin(preferences['show_right_margin'])
		#self.view.set_tab_width(preferences['tab_width'])


	def on_move_cursor(self, view, step_size, count, extend_selection):
		# If you try to move the cursor out of the tableditor
		# release the cursor to the parent textview
		buffer = view.get_buffer()
		iter = buffer.get_iter_at_mark(buffer.get_insert())
		if (iter.is_start() or iter.is_end()) \
		and not extend_selection:
			if iter.is_start() and count < 0:
				self.release_cursor(POSITION_BEGIN)
				return None
			elif iter.is_end() and count > 0:
				self.release_cursor(POSITION_END)
				return None

		return None # let parent handle this signal

	#~ def on_lang_changed(self, selector):
		#~ '''Callback for language selector'''
		#~ lang = selector.get_active()
		#~ self.set_language(lang_ids[lang-1] if lang>0 else '')

	#~ def on_line_numbers_toggled(self, button):
		#~ '''Callback for toggling line numbers.'''
		#~ self.show_line_numbers(button.get_active())

	def fetch_cell_by_event(self, event, treeview):
		liststore = treeview.get_model()
		(xpos, ypos) = event.get_coords()
		(treepath, treecol, xrel, yrel) = treeview.get_path_at_pos(int(xpos), int(ypos))
		treeiter = liststore.get_iter(treepath)
		cellvalue = liststore.get_value(treeiter, treeview.get_columns().index(treecol))
		return cellvalue

	def get_linkurl(self, celltext):
		linkregex = r'<span foreground="blue">(.*?)</span>'
		matches = re.match(linkregex, celltext)
		linkvalue = matches.group(1) if matches else None
		return linkvalue

	def on_button_press_event(self, treeview, event):
		if event.type == gtk.gdk.BUTTON_PRESS and event.button == 1 and event.get_state() &  gtk.gdk.CONTROL_MASK:
			# With CTRL + LEFT-Mouse-Click link of cell is opened
			cellvalue = self.fetch_cell_by_event(event, treeview)
			linkvalue = self.get_linkurl(cellvalue)
			if linkvalue:
				#logger.fatal(linkvalue)
				self.obj.emit('link-clicked', {'href': linkvalue})
			return


		#logger.fatal(treeviw)
		#(treemodel, iter) = treeview.get_selection().get_selected()
		#logger.fatal(iter)
		#logger.fatal(self.liststore.get_value(iter, 0))

		if event.type == gtk.gdk.BUTTON_PRESS and event.button == 3:
			cellvalue = self.fetch_cell_by_event(event, treeview)
			linkvalue = self.get_linkurl(cellvalue)
			linkitem_is_activated = (linkvalue is not None)

			menu = gtk.Menu()

			# Create a new menu-item with a name...
			item = gtk.ImageMenuItem(gtk.STOCK_ADD)
			item.set_always_show_image(True)
			item.set_label(_('Add row'))
			item.connect_after('activate', self.on_add_row)
			menu.append(item)

			item = gtk.ImageMenuItem(gtk.STOCK_DELETE)
			item.set_always_show_image(True)
			item.set_label(_('Delete row'))
			item.connect_after('activate', self.on_delete_row)
			menu.append(item)

			item = gtk.ImageMenuItem(gtk.STOCK_COPY)
			item.set_always_show_image(True)
			item.set_label(_('Clone row'))
			item.connect_after('activate', self.on_clone_row)
			menu.append(item)

			menu.append(gtk.SeparatorMenuItem())

			item = gtk.ImageMenuItem(gtk.STOCK_JUMP_TO)
			item.set_always_show_image(True)
			# only if clicked cell contains a link, this menu item is selectable
			item.set_sensitive(linkitem_is_activated)
			item.set_label(_('Open cell content link'))
			item.connect_after('activate', self.on_open_link, linkvalue)
			menu.append(item)

			menu.append(gtk.SeparatorMenuItem())

			item = gtk.ImageMenuItem(gtk.STOCK_PREFERENCES)
			item.set_always_show_image(True)
			item.set_label(_('Change columns'))
			item.connect_after('activate', self.on_change_columns)
			menu.append(item)


			menu.show_all()
			menu.popup(None, None, None, event.button, event.time)

	def on_add_row(self, action):
		selection = self.treeview.get_selection()
		model, iter = selection.get_selected()
		row = len(self.treeview.get_columns())*['']
		path = model.insert_after(iter, row)
		self.obj.set_modified(True)

	def on_clone_row(self, action):
		selection = self.treeview.get_selection()
		model, iter = selection.get_selected()
		path = model.get_path(iter)
		row = model[path[0]]
		model.insert_after(iter, row)
		self.obj.set_modified(True)

	def on_delete_row(self, action):
		selection = self.treeview.get_selection()
		model, iter = selection.get_selected()

		if len(model) > 1:
			model.remove(iter)
			self.obj.set_modified(True)
		else:
			md = gtk.MessageDialog(None, gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_WARNING, gtk.BUTTONS_CLOSE,
									_("The table must consist of at least on row!\n No deletion done."))
			md.run()
			md.destroy()


	def on_open_link(self, action, link):
		self.obj.emit('link-clicked', {'href': link})

	def on_change_columns(self, action):

		logger.fatal("change columns")
		model = self.treeview.get_model()

		self.obj.emit('edit-object', self.obj)

		#model, iter = selection.get_selected()
		#logger.fatal(model)
		#logger.fatal("change columns")
		pass



	# TODO: undo(), redo() stuff

	def on_cell_changed(self, cellrenderer, path, text, liststore, colid):
		# converts plain text to pango
		markup = CellFormatReplacer.input_to_cell(text, True)
		liststore[path][colid] = markup

	def on_cell_editing_started(self, cellrenderer, editable, path, liststore, colid):
		# converts pango to plain text
		markup = liststore[path][colid]
		markup = CellFormatReplacer.cell_to_input(markup, True)
		editable.set_text(markup)

	def on_row_activated(self, treemodel, row, col):
		logger.fatal("row-activated: nothing to do")
		pass
		#logger.fatal("--")
		#logger.fatal(treemodel)


	def sort_by_number_or_string(self, treemodel, iter1, iter2, colid):
		data1 = treemodel.get_value(iter1, colid)
		data2 = treemodel.get_value(iter2, colid)
		if data1.isdigit() and data2.isdigit():
			data1 = int(data1)
			data2 = int(data2)
		self.obj.set_modified(True)
		return cmp(data1, data2)


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
		column = gtk.TreeViewColumn(_('Wrap\nLine'), cell)
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
		iter = model.get_iter(path)
		val = model.get_value(iter, colid)
		model.set_value(iter, colid, not val)

	def on_alignment_changed(self, renderer, path, comboiter, model):
		''' Trigger for align-option (selectionbox with icon and alignment as text)'''
		combomodel = renderer.get_property('model')
		align = combomodel.get_value(comboiter, 0)
		alignimg = combomodel.get_value(comboiter, 1)
		aligntext = combomodel.get_value(comboiter, 2)

		iter = model.get_iter(path)
		model.set_value(iter, self.Col.align, align)
		model.set_value(iter, self.Col.alignicon, alignimg)
		model.set_value(iter, self.Col.aligntext, aligntext)

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
		(model, iter) = self.treeview.get_selection().get_selected()
		model.insert_after(iter, self.default_column_item)
		newiter = iter if iter else model.get_iter_first()
		self.treeview.get_selection().select_iter(newiter)

	def on_delete_column(self, btn):
		''' Trigger for deleting a column out of the table / it is a deleted row in the treeview '''
		self.autosave_title_cell()
		(model, iter) = self.treeview.get_selection().get_selected()

		if iter:
			if len(model) > 1:
				model.remove(iter)
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
		(model, iter) = self.treeview.get_selection().get_selected()

		if not iter:  # no selected item
			self.selection_info()

		path = model.get_path(iter)
		newpos = path[0] + direction
		if 0 > newpos or newpos > len(model):  # first item cannot be pushed forward, last not backwards
			return
		newiter = model.get_iter((newpos,))

		model.swap(iter, newiter)

	def selection_info(self):
		''' Info-Popup for selecting a cell before this action can be done '''
		md = gtk.MessageDialog(None, gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_WARNING, gtk.BUTTONS_CLOSE,
								_("Please select a row, before you push the button."))
		md.run()
		md.destroy()