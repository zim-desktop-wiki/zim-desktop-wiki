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
from zim.gui.widgets import Dialog, Button, InputEntry, ScrolledWindow
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
		PluginClass.__init__(self, config)
		self.connectto(self.preferences, 'changed', self.on_preferences_changed)

	def create_table(self, attrib, text):
		'''Factory method for Table objects'''
		obj = TableViewObject(attrib, text, self.preferences)
		return obj

	def on_preferences_changed(self, preferences):
		'''Update preferences on open objects'''
		for obj in ObjectManager.get_active_objects(OBJECT_TYPE):
			obj.preferences_changed()

	# TODO - remove this
	def load_file(self):
		self.symbols = {}
		self.symbol_order = []
		file = self.config.get_config_file('symbols.list')
		for line in file.readlines():
			line = line.strip()
			if not line or line.startswith('#'): continue
			try:
				if '#' in line:
					line, _ = line.split('#', 1)
					line = line.strip()
				shortcut, code = line.split()
				symbol = unichr(int(code))
				if not shortcut in self.symbols:
					self.symbols[shortcut] = symbol
					self.symbol_order.append(shortcut)
				else:
					logger.exception('Shortcut defined twice: %s', shortcut)
			except:
				logger.exception('Could not parse symbol: %s', line)
	# TODO - remove this
	def get_symbols(self):
		for shortcut in self.symbol_order:
			symbol = self.symbols[shortcut]
			yield symbol, shortcut


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
		</ui>
	'''

	def __init__(self, plugin, window):
		WindowExtension.__init__(self, plugin, window)
		ObjectManager.register_object(OBJECT_TYPE, self.plugin.create_table)
			# XXX use pageview attribute instead of singleton

	def teardown(self):
		ObjectManager.unregister_object(OBJECT_TYPE)

	@action(_('Table'), readonly=False) # T: menu item
	def insert_table(self):
		'''Run the InsertTableDialog'''
		InsertTableDialog(self.window, self.plugin, self.window.pageview).run()


class TableViewObject(CustomObjectClass):

	OBJECT_ATTR = {
		'type': String('table'),
	}

	def __init__(self, attrib, data, preferences):
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
				alig = 'center'
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

		for (wiki, pango, edit) in SYNTAX_WIKI_PANGO:
			pangopattern = re.compile(pango.replace(r'\1', '(.+?)').replace(r'\2', '(.+?)'))
			rows = [[pangopattern.sub(edit, r)] for row in rows for r in row]
			rows = [[r.replace('&amp;', '&').replace('&gt;', '>').replace('&lt;', '<')\
			.replace('&quot;', '"').replace('&apos;', "'")] for row in rows for r in row]

		#logger.fatal(rows)
		return headers, aligns, rows

	def dump(self, format, dumper, linker=None):
		#logger.fatal("DUMPING")
		return CustomObjectClass.dump(self, format, dumper, linker)


class TableViewWidget(CustomObjectWidget):


	def __init__(self, obj, data):


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

		# Add vbox and wrap it to have a shadow around it
		self.vbox = gtk.VBox() #: C{gtk.VBox} to contain widget contents
		win = ScrolledWindow(self.vbox, gtk.POLICY_NEVER, gtk.POLICY_NEVER, gtk.SHADOW_IN)
		self.add(win)

		self.set_has_cursor(True)

		self.treeview = self.create_treeview()
		win = ScrolledWindow(self.treeview, gtk.POLICY_AUTOMATIC, gtk.POLICY_NEVER, gtk.SHADOW_NONE)
		# only horizontal scroll
		self.vbox.pack_start(win)

		# Hook up signals
		self.treeview.connect('button-press-event', self.on_button_press_event)
		#self.treeview.connect('row-activated', self.on_row_activated)
		#self.treeview.connect('populate-popup', self.on_populate_popup)
		#self.view.connect('move-cursor', self.on_move_cursor)


	def get_treeview(self):
		return self.treeview

	def get_liststore(self):
		return self.liststore

	def create_treeview(self):
		tabledata = self.tabledata
		aligns = tabledata.get('cols').split(',')
		nrcols = len(aligns)
		cols = [str]*nrcols
		self.liststore = gtk.ListStore(*cols)
		liststore = self.liststore
		treeview = gtk.TreeView(liststore)

		align = None
		for i, headcol in enumerate(tabledata.findall('thead/th')):
			label = gtk.Label(headcol.text)
			label.show()
			tview_column = gtk.TreeViewColumn()
			tview_column.set_widget(label)
		


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
		logger.fatal("add row")
		pass

	def on_delete_row(self, action):
		logger.fatal("delete row")
		pass

	def on_open_link(self, action, link):
		self.obj.emit('link-clicked', {'href': link})

	def on_change_columns(self, action):
		logger.fatal("change columns")
		pass



	# TODO: undo(), redo() stuff

	def on_cell_changed(self, cellrenderer, path, text, colid):
		# converts plain text to pango
		markup = text.replace('&', '&amp;').replace('>', '&gt;').replace('<', '&lt;').replace('"', '&quot;')\
			.replace("'", '&apos;').replace('\\n','\n')
		for (wiki, pango, edit) in SYNTAX_WIKI_PANGO:
			# regular expression must be escaped
			edit = edit.replace(r'\1', '(.+?)').replace(r'\2', '(.+?)').replace('*', '\*').replace('[', '\[').replace(']', '\]')
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
		markup = markup.replace('&amp;', '&').replace('&gt;', '>').replace('&lt;', '<')\
			.replace('&quot;', '"').replace('&apos;', "'").replace('\n','\\n')
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

	def __init__(self, ui, plugin, pageview):
		Dialog.__init__(self, ui, _('Insert Table'), # T: Dialog title
			button=(_('_Insert'), 'gtk-ok'),  # T: Button label
			defaultwindowsize=(350, 400) )
		self.plugin = plugin
		self.pageview = pageview

		plugin.load_file()

		self.textentry = InputEntry()
		self.vbox.pack_start(self.textentry, False)

		# TODO make this iconview single-click
		model = gtk.ListStore(str, str) # text, shortcut
		self.iconview = gtk.IconView(model)
		self.iconview.set_text_column(0)
		self.iconview.set_column_spacing(0)
		self.iconview.set_row_spacing(0)
		if gtk.gtk_version >= (2, 12) \
		and gtk.pygtk_version >= (2, 12):
			self.iconview.set_property('has-tooltip', True)
			self.iconview.connect('query-tooltip', self.on_query_tooltip)
		self.iconview.connect('item-activated', self.on_activated)

		self.vbox.add(ScrolledWindow(self.iconview))

		button = gtk.Button(stock=gtk.STOCK_EDIT)
		button.connect('clicked', self.on_edit)
		self.action_area.add(button)
		self.action_area.reorder_child(button, 0)

		self.load_symbols()

	def load_symbols(self):
		model = self.iconview.get_model()
		model.clear()
		for symbol, shortcut in self.plugin.get_symbols():
			model.append((symbol, shortcut))

	def on_query_tooltip(self, iconview, x, y, keyboard, tooltip):
		if keyboard: return False

		x, y = iconview.convert_widget_to_bin_window_coords(x, y)
		path = iconview.get_path_at_pos(x, y)
		if path is None: return False

		model = iconview.get_model()
		iter = model.get_iter(path)
		text = model.get_value(iter, 1)
		if not text: return False

		tooltip.set_text(text)
		return True

	def on_activated(self, iconview, path):
		model = iconview.get_model()
		iter = model.get_iter(path)
		text = model.get_value(iter, 0)
		text = text.decode('utf-8')
		pos = self.textentry.get_position()
		self.textentry.insert_text(text, pos)
		self.textentry.set_position(pos + len(text))

	def on_edit(self, button):
		file = self.confg.get_config_file('symbols.list')
		if self.ui.edit_config_file(file):
			self.plugin.load_file()
			self.load_symbols()

	def run(self):
		self.iconview.grab_focus()
		Dialog.run(self)

	def do_response_ok(self):
		text = self.textentry.get_text()
		textview = self.pageview.view
		buffer = textview.get_buffer()
		buffer.insert_at_cursor(text)
		return True