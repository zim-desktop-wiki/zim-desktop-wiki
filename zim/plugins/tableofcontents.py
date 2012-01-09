# -*- coding: utf-8 -*-

# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import gobject
import gtk
import pango

import re
import datetime

from zim.plugins import PluginClass
from zim.notebook import Path
from zim.gui.widgets import LEFT_PANE, TOP, BrowserTreeView
from zim.gui.pageview import FIND_REGEX


class ToCPlugin(PluginClass):

	plugin_info = {
		'name': _('Table of Contents'), # T: plugin name
		'description': _('''\
This plugin adds an extra widget showing a table of
contents for the current page.

This is a core plugin shipping with zim.
'''), # T: plugin description
		'author': 'Jaap Karssenberg',
	}
	# TODO add controls for changing levels in ToC

	plugin_preferences = (
		# key, type, label, default
		('floating', 'bool', _('Show ToC as floating widget instead of in sidepane'), False),
			# T: preference for Table-Of-Contents plugin
	)

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		self.floating_widget = None
		self.sidepane_widget = None

	def finalize_notebook(self, ui):
		self.do_preferences_changed()

	def disconnect(self):
		self.disconnect_sidepane()
		self.disconnect_floating()
		PluginClass.disconnect(self)

	def do_preferences_changed(self):
		if self.ui.ui_type != 'gtk':
			return

		if self.preferences['floating']:
			self.disconnect_sidepane()
			self.connect_floating()
		else:
			self.disconnect_floating()
			self.connect_sidepane()

	def connect_sidepane(self):
		if not self.sidepane_widget:
			self.sidepane_widget = ToCWidget(self.ui)
			self.ui.mainwindow.add_tab(
				_('ToC'), self.sidepane_widget, LEFT_PANE)
				# T: widget label
			self.sidepane_widget.show_all() # FIXME - should not be needed

	def disconnect_sidepane(self):
		if self.sidepane_widget:
			self.ui.mainwindow.remove(self.sidepane_widget)
			self.sidepane_widget.destroy()
			self.sidepane_widget = None

	def connect_floating(self):
		if not self.floating_widget:
			textview = self.ui.mainwindow.pageview.view
			self.floating_widget = FloatingToC(self.ui)
			self.floating_widget.attach(textview)

	def disconnect_floating(self):
		if self.floating_widget:
			self.floating_widget.destroy()
			self.floating_widget = None

TEXT_COL = 0

class FloatingToC(gtk.Frame):

	# TODO make dragble - see gtk tutorial
	# TODO connect to window resize and line-out at fixed distance from right edge

	def __init__(self, ui):
		gtk.Frame.__init__(self)
		self.set_shadow_type(gtk.SHADOW_OUT)
		self.set_size_request(250, -1) # Fixed width

		exp = gtk.Expander(_('ToC'))
		# TODO add mnemonic
		self.add(exp)
		exp.add(ToCWidget(ui))

	def attach(self, textview):
		# Need to wrap in event box to make widget visible - not sure why
		event_box = gtk.EventBox()
		#~ event_box.add_events(gtk.gdk.BUTTON_PRESS_MASK |
			#~ gtk.gdk.BUTTON_RELEASE_MASK |
			#~ gtk.gdk.POINTER_MOTION_MASK |
			#~ gtk.gdk.POINTER_MOTION_HINT_MASK)

		#~ color = TestText.colormap.alloc_color(0xffff, 0, 0)
		#~ event_box.modify_bg(gtk.STATE_NORMAL, color)
		event_box.add(self)
		event_box.show_all()

		textview.add_child_in_window(event_box, gtk.TEXT_WINDOW_WIDGET, 300, 10)


class ToCWidget(gtk.ScrolledWindow):

	def __init__(self, ui):
		gtk.ScrolledWindow.__init__(self)
		self.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
		self.set_shadow_type(gtk.SHADOW_IN)
		self.set_size_request(-1, 200) # Fixed Height

		self.ui = ui
		self.page = None

		self.treeview = ToCTreeView()
		self.add(self.treeview)

		self.treeview.connect('row-activated', self.on_heading_activated)
		ui.connect('open-page', self.on_open_page)
		ui.notebook.connect('stored-page', self.on_stored_page)

		if ui.page:
			self.on_open_page(ui, ui.page, Path(ui.page.name))

	def on_open_page(self, ui, page, path):
		self.page = path
		self._load_page(page)

	def on_stored_page(self, notebook, page):
		if page == self.page:
			self._load_page(page)

	def _load_page(self, page):
		model = self.treeview.get_model()
		tree = page.get_parsetree()
		if tree:
			model.populate(tree)
		else:
			model.clear()
		self.treeview.expand_all()

	def on_heading_activated(self, treeview, path, column):
		model = treeview.get_model()
		text = model[path][TEXT_COL].decode('utf-8')
		textview = self.ui.mainwindow.pageview.view # FIXME nicer interface for this
		buffer = textview.get_buffer()
		iter = buffer.get_insert_iter()
		# hack to detect only headers.
		# heading information is not available in buffer, therefore
		# search for lines that contain only the header text.
		text_regex = "^%s$" % re.escape(text)
		buffer.finder.find(text_regex, FIND_REGEX)
		textview.scroll_to_mark(buffer.get_insert(), 0.3)


class ToCTreeView(BrowserTreeView):

	def __init__(self):
		BrowserTreeView.__init__(self, ToCTreeModel())
		self.set_headers_visible(False)

		cell_renderer = gtk.CellRendererText()
		cell_renderer.set_property('ellipsize', pango.ELLIPSIZE_END)
		column = gtk.TreeViewColumn('_heading_', cell_renderer, text=TEXT_COL)
		self.append_column(column)


class ToCTreeModel(gtk.TreeStore):

	def __init__(self):
		gtk.TreeStore.__init__(self, str) # TEXT_COL

	def populate(self, parsetree):
		self.clear()
		headings = []
		for el in parsetree.findall('h'):
			headings.append( (int(el.attrib['level']), el.text) )

		stack = [(-1, None)]
		for level, text in headings:
			assert level > -1 # just to be sure
			while stack[-1][0] >= level:
				stack.pop()
			parent = stack[-1][1]
			iter = self.append(parent, (text,))
			stack.append((level, iter))
