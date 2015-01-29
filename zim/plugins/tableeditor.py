# -*- coding: utf-8 -*-

# Copyright 2015 Tobias Haupenthal

import gtk
import pango
import logging
from xml.etree import ElementTree
import re

logger = logging.getLogger('zim.plugin.tableeditor')

from zim.plugins import PluginClass, WindowExtension, extends
from zim.actions import action
from zim.utils import WeakSet
from zim.objectmanager import ObjectManager, CustomObjectClass
from zim.config import String, Boolean
from zim.gui.widgets import Dialog, ScrolledWindow
from zim.gui.objectmanager import CustomObjectWidget, TextViewWidget
from zim.formats.html import html_encode
from zim.config.dicts import ConfigDict, String


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
**IN DEVELOPMENT**
This plugin allows inserting 'Tables' in the page. These will be shown as TreeView widgets.
Exporting them to various formats (i.e. HTML/LaTeX) completes the feature set.
'''), # T: plugin description
		'object_types': (OBJECT_TYPE, ),
		'help': 'Plugins:Table Editor',
		'author': 'Tobias Haupenthal',
	}

	plugin_preferences = (
		# key, type, label, default
		('auto_indent', 'bool', _('Auto indenting'), True),
			# T: preference option for sourceview plugin
		('smart_home_end', 'bool', _('Smart Home key'), True),
			# T: preference option for sourceview plugin
		('highlight_current_line', 'bool', _('Highlight current line'), False),
			# T: preference option for sourceview plugin
		('show_right_margin', 'bool', _('Show right margin'), False),
			# T: preference option for sourceview plugin
		('right_margin_position', 'int', _('Right margin position'), 72, (1, 1000)),
			# T: preference option for sourceview plugin
		('tab_width', 'int', _('Tab width'), 4, (1, 80)),
			# T: preference option for sourceview plugin
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
		'''Inserts new SourceView'''
		logger.fatal("InsertTableDialog")
		#lang = InsertCodeBlockDialog(self.window.ui).run() # XXX
		lang = "php"
		if not lang:
			return # dialog cancelled
		else:
			obj = self.plugin.create_table({'type': OBJECT_TYPE}, '')
			pageview = self.window.pageview
			pageview.insert_table_at_cursor(obj)


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

		logger.fatal('get-data')
		logger.fatal(rows)

		for (wiki, pango, edit) in SYNTAX_WIKI_PANGO:
			pangopattern = re.compile(pango.replace(r'\1', '(.+?)').replace(r'\2', '(.+?)'))
			rows = [[pangopattern.sub(edit, r)] for row in rows for r in row]
			rows = [[r.replace('&amp;', '&').replace('&gt;', '>').replace('&lt;', '<')\
			.replace('&quot;', '"').replace('&apos;', "'")] for row in rows for r in row]

		logger.fatal(rows)
		return headers, aligns, rows

	def dump(self, format, dumper, linker=None):
		logger.fatal("DUMPING")
		return CustomObjectClass.dump(self, format, dumper, linker)


class TableViewWidget(CustomObjectWidget):

	def __init__(self, obj, data):
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


		#logger.fatal(self.obj)



		#self.view = self.create_treeview()

		# simple toolbar
		#~ bar = gtk.HBox() # FIXME: use gtk.Toolbar stuff
		#~ lang_selector = gtk.combo_box_new_text()
		#~ lang_selector.append_text('(None)')
		#~ for l in lang_names: lang_selector.append_text(l)
		#~ try:
			#~ lang_selector.set_active(lang_ids.index(self._attrib['lang'])+1)
			#~ self.set_language(self._attrib['lang'] or None, False)
		#~ except (ValueError, KeyError):
			#~ lang_selector.set_active(0)
			#~ self.set_language(None, False)
		#~ lang_selector.connect('changed', self.on_lang_changed)
		#~ bar.pack_start(lang_selector, False, False)

		#~ line_numbers = gtk.ToggleButton('Line numbers')
		#~ try:
			#~ line_numbers.set_active(self._attrib['linenumbers']=='true')
			#~ self.show_line_numbers(self._attrib['linenumbers'], False)
		#~ except (ValueError, KeyError):
			#~ line_numbers.set_active(True)
			#~ self.show_line_numbers(True, False)
		#~ line_numbers.connect('toggled', self.on_line_numbers_toggled)
		#~ bar.pack_start(line_numbers, False, False)

		# TODO: other toolbar options
		# TODO: autohide toolbar if textbuffer is not active

		# Pack everything
		#~ self.vbox.pack_start(bar, False, False)


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
			tview_column = gtk.TreeViewColumn(headcol.text)
			treeview.append_column(tview_column)
			cell = gtk.CellRendererText()
			tview_column.pack_start(cell, True)

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
			row = [ElementTree.tostring(r).replace('<td>', '').replace('</td>', '') for r in row]

			rowtext = []
			for (wiki, pango, edit) in SYNTAX_WIKI_PANGO:
				wikipattern = re.compile(wiki.replace(r'\1', '(.+?)').replace(r'\2', '(.+?)'))
				row = [wikipattern.sub(pango, cell) for cell in row]

			rowtext = row
			logger.fatal(rowtext)

			liststore.append(rowtext)
			#TODO reformat to pango

		logger.fatal(liststore[0][0])

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
		logger.fatal(markup)
		self.liststore[path][colid] = markup

	def on_cell_editing_started(self, cellrenderer, editable, path, colid):
		# converts pango to plain text
		# model, treeiter = self.treeview.get_selection().get_selected()
		markup = self.liststore[path][colid]
		for (wiki, pango, edit) in SYNTAX_WIKI_PANGO:
			pangopattern = re.compile(pango.replace(r'\1', '(.+?)').replace(r'\2', '(.+?)'))
			markup = pangopattern.sub(edit, markup)
		markup = markup.replace('&amp;', '&').replace('&gt;', '>').replace('&lt;', '<')\
			.replace('&quot;', '"').replace('&apos;', "'").replace('\n','\\n')
		editable.set_text(markup)
