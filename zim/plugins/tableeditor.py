# -*- coding: utf-8 -*-

# Copyright 2015 Tobias Haupenthal

import gtk
import pango
import logging
from xml.etree import ElementTree
import re
import gobject

logger = logging.getLogger('zim.plugin.tableeditor')

from zim.plugins import PluginClass, WindowExtension, extends
from zim.actions import action
from zim.plugins import PluginClass, extends, WindowExtension
from zim.utils import WeakSet
from zim.objectmanager import ObjectManager, CustomObjectClass
from zim.config import String, Boolean
from zim.gui.widgets import Dialog, Button, InputEntry, ScrolledWindow, IconButton
from zim.gui.objectmanager import CustomObjectWidget, TextViewWidget
from zim.formats.html import html_encode
from zim.config.dicts import ConfigDict, String
from zim.gui.pageview import PageView


OBJECT_TYPE = 'table'

# Wiki-Parsetree -> Pango (Table cell) -> TextView (Table cell editing)
SYNTAX_WIKI_PANGO = (
	(r'<strong>\1</strong>', r'<b>\1</b>', r'**\1**'),
	(r'<emphasis>\1</emphasis>', r'<i>\1</i>', r'//\1//'),
	(r'<mark>\1</mark>', r'<span background="yellow">\1</span>', r'__\1__'),
	(r'<code>\1</code>', r'<tt>\1</tt>', r"''\1''"),
	(r'<link href="\1">\2</link>', r'<span foreground="blue">\1</span>', r'[[\1]]')
)

SYNTAX_CHAR_REGEX = [
	('*', '\*'), ('[', '\['), (']', '\]'), (r'\1', '(.+?)'), (r'\2', '(.+?)')
]

SYNTAX_CELL_INPUT = [
	('&amp;', '&'), ('&gt;', '>'), ('&lt;', '<'), ('&quot;', '"'), ('&apos;', "'"), ('\n', '\\n')
]

class TableEditorPlugin(PluginClass):

	plugin_info = {
		'name': _('Table Editor'), # T: plugin name
		'description': _('''\
With this plugin you can embed a 'Table' into the wiki page. Tables will be shown as GTK TreeView widgets.
Exporting them to various formats (i.e. HTML/LaTeX) completes the feature set.
'''), # T: plugin description
		'object_types': (OBJECT_TYPE, ),
		'help': 'Plugins:Table Editor',
		'author': 'Tobias Haupenthal',
	}

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
		logger.fatal("Load plugin")
		PluginClass.__init__(self, config)
		self.connectto(self.preferences, 'changed', self.on_preferences_changed)

	def create_table(self, attrib, text):
		'''Factory method for Table objects'''
		obj = TableViewObject(attrib, text, self.preferences)
		return obj

	def on_preferences_changed(self, preferences):
		logger.fatal("update preferences")
		'''Update preferences on open objects'''
		for obj in ObjectManager.get_active_objects(OBJECT_TYPE):
			obj.preferences_changed()


class TableReplacer:
	@staticmethod
	def cell_to_input(text):
		for k, v in SYNTAX_CELL_INPUT:
			text = text.replace(k, v)
		return text

	@staticmethod
	def input_to_cell(text):
		for k, v in SYNTAX_CELL_INPUT:
			text = text.replace(v, k)
		return text

	@staticmethod
	def text_to_regex(text):
		for k, v in SYNTAX_CHAR_REGEX:
			text = text.replace(k, v)
		return text


@extends('MainWindow')
class MainWindowExtension(WindowExtension):

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
		logger.fatal("mainwindow extension")
		WindowExtension.__init__(self, plugin, window)

		ObjectManager.register_object(OBJECT_TYPE, self.plugin.create_table)

		# reload tables on current page after plugin activation
		if self.window.ui.page:
			self.window.ui.reload_page()


	def teardown(self):
		ObjectManager.unregister_object(OBJECT_TYPE)
		self.window.ui.reload_page()

	@action(_('Insert Table'), stock='zim-insert-table', readonly=False) # T: menu item
	def insert_table(self):
		'''Run the InsertTableDialog'''
		col_model = InsertTableDialog(self.window, self.plugin, self.window.pageview).run()
		logger.fatal("INSERTION OK")
		logger.fatal(col_model)
		#widget = TableViewWidget(self, self.tabledata)
		pass
		#model.append([id,"Benjamin", True, "left", gtk.STOCK_JUSTIFY_LEFT, "Left"])

	def convert_colmodel(self, col_model, replace=False):
		new_store = len(col_model) * []


class TableViewObject(CustomObjectClass):

	OBJECT_ATTR = {
		'type': String('table'),
	}

		def __init__(self, attrib,  , preferences):
		self._attrib = ConfigDict(attrib)
		self._attrib.define(self.OBJECT_ATTR)
		self.tabledata = data if data is not None else ''
		self.modified = False
		self.preferences = preferences
		self.treeview = None
		self._widgets = WeakSet()

	def get_widget(self):
		widget = TableViewWidget(self, self.tabledata)
		self.treeview = widget.get_treeview()
		self.liststore = widget.get_liststore()
		self.liststore.connect('row-changed', self.on_modified_changed)

		self._widgets.add(widget)

		widget.set_preferences(self.preferences)
		return widget

	def preferences_changed(self):
		for widget in self._widgets:
			widget.set_preferences(self.preferences)

	def on_sort_column_changed(self, liststore):
		self.set_modified(True)

	def on_modified_changed(self, treemodel, path, iter):
		logger.fatal("row-changed")
		self.set_modified(True)

	def get_data(self):
		'''Returns data as text.'''
		liststore = self.treeview.get_model()
		headers = []
		aligns = []
		rows = []
		for column in self.treeview.get_columns():
			val = column.get_title() if column.get_title() else ' '
			headers.append(val)
			alignment = column.get_alignment()
			if alignment == 0.0:
				align = 'left'
			elif alignment == 0.5:
				align = 'center'
			elif alignment == 1.0:
				align = 'right'
			else:
				align = 'normal'
			aligns.append(align)
		iter = liststore.get_iter_first()
		while iter is not None:
			row = []
			for colid in range(len(self.treeview.get_columns())):
				val = liststore.get_value(iter, colid) if liststore.get_value(iter, colid) else ' '
				row.append(val)
			rows.append(row)
			iter = liststore.iter_next(iter)

		#logger.fatal('get-data')
		#logger.fatal(rows)

		def map2dim(fun, rows):
			return [map(fun, row) for row in rows]

		def map3dim(fun, multiline_rows):
			return [[map(fun, row) for row in lines] for lines in multiline_rows]

		for (wiki, pango, edit) in SYNTAX_WIKI_PANGO:
			pangopattern = re.compile(pango.replace(r'\1', '(.+?)').replace(r'\2', '(.+?)'))
			rows = map2dim(lambda cell: pangopattern.sub(edit, cell), rows)
			logger.fatal(rows)

		rows = map2dim(TableReplacer.cell_to_input, rows)

		logger.fatal(rows)
		return headers, aligns, rows

	def dump(self, format, dumper, linker=None):
		#logger.fatal("DUMPING")
		return CustomObjectClass.dump(self, format, dumper, linker)




class TableViewWidget(CustomObjectWidget):


	def __init__(self, obj, data):
		self.set_size_request(-1,-1)

		self.obj = obj
		self.tabledata = data


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

		self.treeview = self.create_treeview()
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

		vmargin = view.get_left_margin() + view.get_right_margin() \
					+ 2 * self.get_border_width()

		# override size
		self.get_size_request()

		self.set_size_request(-1, -1)


	def get_treeview(self):
		return self.treeview

	def get_liststore(self):
		return self.liststore

	def create_treeview(self, tabledata=None):
		if not tabledata:
			tabledata = self.tabledata
		aligns = tabledata.get('aligns').split(',')
		wraps = map(int, tabledata.get('wraps').split(','))
		nrcols = len(aligns)
		cols = [str]*nrcols
		self.liststore = gtk.ListStore(*cols)
		liststore = self.liststore
		treeview = gtk.TreeView(liststore)
		logger.fatal("size")

		align = None
		for i, headcol in enumerate(tabledata.findall('thead/th')):
			tview_column = gtk.TreeViewColumn(headcol.text)
			#tview_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
			#tview_column.set_expand(False)
			treeview.append_column(tview_column)
			cell = gtk.CellRendererText()
			tview_column.pack_start(cell, True)

			# set sort function
			liststore.set_sort_func(i, self.sort_by_number_or_string, i)

			# set alignment
			if aligns[i] == 'left':
				align = 0.0
			elif aligns[i] == 'center':
				align = 0.5
			elif aligns[i] == 'right':
				align = 1.0
			else:
				align = None
			if align:
				tview_column.set_alignment(align)
				cell.set_alignment(align, 0.0)

			# set properties of column
			tview_column.set_attributes(cell, markup=i)
			tview_column.set_sort_column_id(i)

			# set properties of cell
			cell.set_property("editable", True)
			cell.connect("edited", self.on_cell_changed, i)
			cell.connect("editing-started", self.on_cell_editing_started, i)




		for trow in tabledata.findall('trow'):
			row = trow.findall('td')
			row = [ElementTree.tostring(r, 'utf-8').replace('<td>', '').replace('</td>', '') for r in row]

			rowtext = []
			for (wiki, pango, edit) in SYNTAX_WIKI_PANGO:
				wikipattern = re.compile(wiki.replace(r'\1', '(.+?)').replace(r'\2', '(.+?)'))
				row = [wikipattern.sub(pango, cell) for cell in row]

			rowtext = row
			logger.fatal(rowtext)

			liststore.append(rowtext)
			#TODO reformat to pango

		#logger.fatal(liststore[0][0])

		# Hook up signals
		#self.view.connect('populate-popup', self.on_populate_popup)
		#self.view.connect('move-cursor', self.on_move_cursor)

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

	def on_populate_popup(self, view, menu):
		menu.prepend(gtk.SeparatorMenuItem())

		item = gtk.CheckMenuItem(_('Show Line Numbers'))
			# T: preference option for tableeditor plugin
		item.set_active(self.obj._attrib['linenumbers'])
		#item.connect_after('activate', activate_linenumbers)
		menu.prepend(item)


		item = gtk.MenuItem(_('Syntax'))
		submenu = gtk.Menu()
		item.set_submenu(submenu)
		menu.prepend(item)

		menu.show_all()

	def fetch_cell_by_event(self, event):
		(xpos, ypos) = event.get_coords()
		(treepath, treecol, xrel, yrel) = self.treeview.get_path_at_pos(int(xpos), int(ypos))
		treeiter = self.liststore.get_iter(treepath)
		cellvalue = self.liststore.get_value(treeiter, self.treeview.get_columns().index(treecol))
		return cellvalue

	def get_linkurl(self, celltext):
		linkregex = r'<span foreground="blue">(.*?)</span>'
		matches = re.match(linkregex, celltext)
		linkvalue = matches.group(1) if matches else None
		return linkvalue

	def on_button_press_event(self, treeview, event):
		if event.type == gtk.gdk.BUTTON_PRESS and event.button == 1 and event.get_state() &  gtk.gdk.CONTROL_MASK:
			# With CTRL + LEFT-Mouse-Click link of cell is opened
			cellvalue = self.fetch_cell_by_event(event)
			linkvalue = self.get_linkurl(cellvalue)
			if linkvalue:
				logger.fatal(linkvalue)
				self.obj.emit('link-clicked', {'href': linkvalue})
			return


		#logger.fatal(treeviw)
		#(treemodel, iter) = treeview.get_selection().get_selected()
		#logger.fatal(iter)
		#logger.fatal(self.liststore.get_value(iter, 0))

		if event.type == gtk.gdk.BUTTON_PRESS and event.button == 3:
			cellvalue = self.fetch_cell_by_event(event)
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
		path = model.insert_after(iter,row)
		self.obj.set_modified(True)

	def on_delete_row(self, action):
		selection = self.treeview.get_selection()
		model, iter = selection.get_selected()

		if(len(model) > 1):
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
		pass



	# TODO: undo(), redo() stuff

	def on_cell_changed(self, cellrenderer, path, text, colid):
		# converts plain text to pango
		markup = TableReplacer.input_to_cell(text)
		for (wiki, pango, edit) in SYNTAX_WIKI_PANGO:
			# regular expression must be escaped
			edit = TableReplacer.text_to_regex(edit)
			logger.fatal(edit)
			editpattern = re.compile(edit)
			markup = editpattern.sub(pango, markup)
		#logger.fatal(markup)
		self.liststore[path][colid] = markup

	def on_cell_editing_started(self, cellrenderer, editable, path, colid):
		# converts pango to plain text
		# model, treeiter = self.treeview.get_selection().get_selected()
		logger.fatal(self.liststore[path][colid])
		markup = self.liststore[path][colid]
		for (wiki, pango, edit) in SYNTAX_WIKI_PANGO:
			pangopattern = re.compile(pango.replace(r'\1', '(.+?)').replace(r'\2', '(.+?)'))
			markup = pangopattern.sub(edit, markup)
		markup = TableReplacer.cell_to_input(markup)
		editable.set_text(markup)

	def on_row_activated(self, treemodel, row, col):
		logger.fatal("--")
		logger.fatal(treemodel)


	def sort_by_number_or_string(self, treemodel, iter1, iter2, colid):
		data1 = treemodel.get_value(iter1, colid)
		data2 = treemodel.get_value(iter2, colid)
		if data1.isdigit() and data2.isdigit():
			data1 = int(data1)
			data2 = int(data2)
		self.obj.set_modified(True)
		return cmp(data1, data2)

	def on_populate_popup(self, view, menu):
		menu.prepend(gtk.SeparatorMenuItem())

		def activate_linenumbers(item):
			self.obj.show_line_numbers(item.get_active())

		item = gtk.CheckMenuItem(_('Show Line Numbers'))
			# T: preference option for tableeditor plugin
		item.set_active(self.obj._attrib['linenumbers'])
		item.connect_after('activate', activate_linenumbers)
		menu.prepend(item)


		def activate_lang(item):
			self.obj.set_language(item.zim_sourceview_languageid)

		item = gtk.MenuItem(_('Syntax'))
		submenu = gtk.Menu()
		'''
		for lang in sorted(LANGUAGES, key=lambda k: k.lower()):
			langitem = gtk.MenuItem(lang)
			langitem.connect('activate', activate_lang)
			langitem.zim_sourceview_languageid = LANGUAGES[lang]
			submenu.append(langitem)
		item.set_submenu(submenu)
		'''
		menu.prepend(item)

		menu.show_all()


class InsertTableDialog(Dialog):
	class Col():
		id, title, wrapped, align, alignicon, aligntext = range(6)

	def __init__(self, ui, plugin, pageview, tablemodel=None):
		self.default_column_item = ["", False, "left", gtk.STOCK_JUSTIFY_LEFT, _("Left")]
		self.pageview = pageview

		model = gtk.ListStore(int, str, int, str, str, str)
		self.model = model

		model.append([0, "Benjamin", True, "left", gtk.STOCK_JUSTIFY_LEFT, "Left"])
		model.append([1, "Charles", False, "normal",gtk.STOCK_JUSTIFY_LEFT, "Normal"])
		model.append([2, "alfred", False, "right", gtk.STOCK_JUSTIFY_LEFT, "Right"])
		model.append([3, "Alfred", False, "normal", gtk.STOCK_JUSTIFY_LEFT, "Right"])
		model.append([4, "David", False, "normal", gtk.STOCK_JUSTIFY_LEFT, "Right"])
		model.append([5, "charles", False, "normal", gtk.STOCK_JUSTIFY_LEFT, "Right"])
		model.append([6, "david", False, "normal", gtk.STOCK_JUSTIFY_LEFT, "Right"])
		model.append([7, "benjamin", False, "normal", gtk.STOCK_JUSTIFY_LEFT, "Right"])

		self.maxid = max(id[0] for id in model)
		Dialog.__init__(self, ui, _('Insert Table'), # T: dialog title
		)

		self.set_default_size(380, 400)

		#self.set_help('Plugins:Table Editor');
		self.add_help_text(_('Managing table columns'))


		hbox = gtk.HBox(spacing=5)
		hbox.set_size_request(300, 300)
		self.vbox.pack_start(hbox, False)
		header_scrolled_area = ScrolledWindow(self.headcolumn_list())
		header_scrolled_area.set_size_request(200, -1)
		hbox.add(header_scrolled_area)
		hbox.add(self.button_box())

	def button_box(self):
		vbox = gtk.VBox(spacing=5)
		tooltips = gtk.Tooltips()
		for stock, handler, data, tooltip in (
			(gtk.STOCK_ADD, self.on_add, None, _('Add column')),
			(gtk.STOCK_DELETE, self.on_delete, None, _('Remove column')),
			(gtk.STOCK_GO_UP, self.on_move, -1, _('Move column ahead')),
			(gtk.STOCK_GO_DOWN, self.on_move, 1, _('Move column backward')),
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
		self.result = self.model
		return True

	def do_response_cancel(self):
		logger.fatal("cacnel")
		return True


	def headcolumn_list(self):
		model = self.model

		treeview = gtk.TreeView(model)
		self.treeview = treeview

		# 1. Column - Title
		cell = gtk.CellRendererText()
		cell.set_property('editable', True)
		column = gtk.TreeViewColumn(_('Title'), cell, text=self.Col.title)
		column.set_min_width(120)
		treeview.append_column(column)
		cell.connect("edited", self.on_cell_changed, model, self.Col.title)

		# 2. Column - Wrap Line
		cell = gtk.CellRendererToggle()
		cell.connect('toggled', self.on_cell_toggled, model, self.Col.wrapped)
		column = gtk.TreeViewColumn(_('Wrap\nLine'), cell)
		treeview.append_column(column)
		column.add_attribute(cell, 'active', self.Col.wrapped)

		# 3. Column - Alignment
		store = gtk.ListStore(str, str, str)
		store.append(['left', gtk.STOCK_JUSTIFY_LEFT, _('Left')])
		store.append(['center', gtk.STOCK_JUSTIFY_CENTER, _('Center')])
		store.append(['right', gtk.STOCK_JUSTIFY_RIGHT, _('Right')])

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
		cell.connect("changed", self.on_cell_combo_changed, model)
		treeview.append_column(column)

		return treeview

	def on_cell_editing_started(self, renderer, editable, path, model, colid):
		# converts pango to plain text
		text = model[path][colid]
		text = TableReplacer.cell_to_input(text)
		editable.set_text(text)

	def on_cell_changed(self, renderer, path, text, model, colid):
		model[path][colid] = TableReplacer.input_to_cell(text)

	def on_cell_toggled(self, renderer, path, model, colid):#
		iter = model.get_iter(path)
		val = model.get_value(iter, colid)
		model.set_value(iter, colid, not val)

	def on_cell_combo_changed(self, renderer, path, comboiter, model):
		combomodel = renderer.get_property('model')
		align = combomodel.get_value(comboiter, 0)
		alignimg = combomodel.get_value(comboiter, 1)
		aligntext = combomodel.get_value(comboiter, 2)

		iter = model.get_iter(path)
		model.set_value(iter, self.Col.align, align)
		model.set_value(iter, self.Col.alignicon, alignimg)
		model.set_value(iter, self.Col.aligntext, aligntext)

	def on_add(self, btn):
		(model, iter) = self.treeview.get_selection().get_selected()
		self.maxid += 1
		self.default_columns_item[self.Col.id] = self.maxid
		model.insert_after(iter, self.default_column_item)
		newiter = model.get_path(iter) if iter else model.get_iter_first()
		self.treeview.get_selection().select_iter(newiter)

	def on_delete(self, btn):
		(model, iter) = self.treeview.get_selection().get_selected()

		if iter:
			model.remove(iter)
		else:
			self.selection_info()

	def on_move(self, btn, direction):
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
			md = gtk.MessageDialog(None, gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_WARNING, gtk.BUTTONS_CLOSE,
									_("Please select a row, before you push the button."))
			md.run()
			md.destroy()