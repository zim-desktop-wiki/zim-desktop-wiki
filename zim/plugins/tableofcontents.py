# -*- coding: utf-8 -*-

# Copyright 2012, 2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement

import gobject
import gtk
import pango

import re
import datetime

from zim.plugins import PluginClass, WindowExtension, extends
from zim.notebook import Path
from zim.formats import HEADING
from zim.gui.widgets import LEFT_PANE, PANE_POSITIONS, BrowserTreeView, populate_popup_add_separator
from zim.gui.pageview import FIND_REGEX, SCROLL_TO_MARK_MARGIN, _is_heading_tag
from zim.signals import ConnectorMixin


# FIXME, these methods should be supported by pageview - need anchors - now it is a HACK
_is_heading = lambda iter: bool(filter(_is_heading_tag, iter.get_tags()))

def find_heading(buffer, heading):
	'''Find a heading
	@param buffer: the C{gtk.TextBuffer}
	@param heading: text of the heading
	@returns: a C{gtk.TextIter} for the new cursor position or C{None}
	'''
	regex = "^%s$" % re.escape(heading)
	with buffer.tmp_cursor():
		if buffer.finder.find(regex, FIND_REGEX):
			iter = buffer.get_insert_iter()
			start = iter.get_offset()
		else:
			return None

		while not _is_heading(iter):
			if buffer.finder.find_next():
				iter = buffer.get_insert_iter()
				if iter.get_offset() == start:
					return None # break infinite loop
			else:
				return None

		if _is_heading(iter):
			return iter
		else:
			return None


def select_heading(buffer, heading):
	iter = find_heading(buffer, heading)
	if iter:
		buffer.place_cursor(iter)
		buffer.select_line()
		return True
	else:
		return False


class ToCPlugin(PluginClass):

	plugin_info = {
		'name': _('Table of Contents'), # T: plugin name
		'description': _('''\
This plugin adds an extra widget showing a table of
contents for the current page.

This is a core plugin shipping with zim.
'''), # T: plugin description
		'author': 'Jaap Karssenberg',
		'help': 'Plugins:Table Of Contents',
	}
	# TODO add controls for changing levels in ToC

	plugin_preferences = (
		# key, type, label, default
		('pane', 'choice', _('Position in the window'), LEFT_PANE, PANE_POSITIONS),
			# T: option for plugin preferences
		('floating', 'bool', _('Show ToC as floating widget instead of in sidepane'), True),
			# T: option for plugin preferences
		('show_h1', 'bool', _('Show the page title heading in the ToC'), False),
			# T: option for plugin preferences
	)
	# TODO disable pane setting if not embedded

	def __init__(self, config=None):
		PluginClass.__init__(self, config)
		self.on_preferences_changed(self.preferences)
		self.preferences.connect('changed', self.on_preferences_changed)

	def on_preferences_changed(self, preferences):
		if preferences['floating']:
			self.set_extension_class('MainWindow', MainWindowExtensionFloating)
		else:
			self.set_extension_class('MainWindow', MainWindowExtensionEmbedded)


@extends('MainWindow', autoload=False)
class MainWindowExtensionEmbedded(WindowExtension):

	def __init__(self, plugin, window):
		WindowExtension.__init__(self, plugin, window)
		self.widget = SidePaneToC(self.window.ui, self.window.pageview) # XXX

		self.on_preferences_changed(plugin.preferences)
		self.connectto(plugin.preferences, 'changed', self.on_preferences_changed)

	def on_preferences_changed(self, preferences):
		if self.widget is None:
			return

		try:
			self.window.remove(self.widget)
		except ValueError:
			pass

		self.window.add_tab(
			_('ToC'), self.widget, preferences['pane'])
			# T: widget label
		self.widget.show_all()

		self.widget.set_show_h1(preferences['show_h1'])

	def teardown(self):
		self.window.remove(self.widget)
		self.widget.disconnect_all()
		self.widget = None


@extends('MainWindow', autoload=False)
class MainWindowExtensionFloating(WindowExtension):

	def __init__(self, plugin, window):
		WindowExtension.__init__(self, plugin, window)
		self.widget = FloatingToC(self.window.ui, self.window.pageview) # XXX

		self.on_preferences_changed(plugin.preferences)
		self.connectto(plugin.preferences, 'changed', self.on_preferences_changed)

	def on_preferences_changed(self, preferences):
		self.widget.set_show_h1(preferences['show_h1'])

	def teardown(self):
		self.widget.disconnect_all()
		self.widget.destroy()



TEXT_COL = 0


class ToCTreeView(BrowserTreeView):

	def __init__(self, ellipsis):
		BrowserTreeView.__init__(self, ToCTreeModel())
		self.set_headers_visible(False)
		self.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
			# Allow select multiple

		cell_renderer = gtk.CellRendererText()
		if ellipsis:
			cell_renderer.set_property('ellipsize', pango.ELLIPSIZE_END)
		column = gtk.TreeViewColumn('_heading_', cell_renderer, text=TEXT_COL)
		column.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
			# Without this sizing, column width only grows and never shrinks
		self.append_column(column)



class ToCTreeModel(gtk.TreeStore):

	def __init__(self):
		gtk.TreeStore.__init__(self, str) # TEXT_COL

	def populate(self, parsetree, show_h1):
		self.clear()
		headings = []
		for heading in parsetree.findall(HEADING):
			headings.append( (int(heading.attrib['level']), heading.gettext()) )


		if not show_h1 \
		and headings \
		and headings[0][0] == 1 \
		and all(h[0] > 1 for h in headings[1:]):
			headings.pop(0) # do not show first heading

		stack = [(-1, None)]
		for level, text in headings:
			assert level > -1 # just to be sure
			while stack[-1][0] >= level:
				stack.pop()
			parent = stack[-1][1]
			iter = self.append(parent, (text,))
			stack.append((level, iter))




class ToCWidget(ConnectorMixin, gtk.ScrolledWindow):

	def __init__(self, ui, pageview, ellipsis, show_h1=False):
		gtk.ScrolledWindow.__init__(self)
		self.show_h1 = show_h1

		self.treeview = ToCTreeView(ellipsis)
		self.treeview.connect('row-activated', self.on_heading_activated)
		self.treeview.connect('populate-popup', self.on_populate_popup)
		self.add(self.treeview)

		# XXX remove ui - use signals from pageview for this
		self.connectto(ui, 'open-page')
		self.connectto(ui.notebook, 'stored-page')

		self.pageview = pageview
		if self.pageview.page:
			self.load_page(self.pageview.page)

	def set_show_h1(self, show_h1):
		if show_h1 != self.show_h1:
			self.show_h1 = show_h1
			if self.pageview.page:
				self.load_page(self.pageview.page)

	def on_open_page(self, ui, page, path):
		self.load_page(page)

	def on_stored_page(self, notebook, page):
		if page == self.pageview.page:
			self.load_page(page)

	def load_page(self, page):
		model = self.treeview.get_model()
		tree = page.get_parsetree()
		if tree is None:
			model.clear()
		else:
			model.populate(tree, self.show_h1)
		self.treeview.expand_all()

	def on_heading_activated(self, treeview, path, column):
		self.select_heading(path)

	def select_heading(self, path):
		'''Returns a C{gtk.TextIter} for a C{gtk.TreePath} pointing to a heading
		or C{None}.
		'''
		model = self.treeview.get_model()
		text = model[path][TEXT_COL].decode('utf-8')

		textview = self.pageview.view
		buffer = textview.get_buffer()
		if select_heading(buffer, text):
			textview.scroll_to_mark(buffer.get_insert(), SCROLL_TO_MARK_MARGIN)
			return True
		else:
			return False

	def select_section(self, buffer, path):
		'''Select all text between two headings
		@param buffer: the C{gtk.TextBuffer} to select in
		@param path: the C{gtk.TreePath} for the heading of the section
		'''
		model = self.treeview.get_model()
		starttext = model[path][TEXT_COL].decode('utf-8')

		nextpath = path[:-1] + (path[-1]+1,)
		if nextpath in model:
			endtext = model[nextpath][TEXT_COL].decode('utf-8')
		else:
			endtext = None

		textview = self.pageview.view
		buffer = textview.get_buffer()
		start = find_heading(buffer, starttext)
		if endtext:
			end = find_heading(buffer, endtext)
		else:
			end = buffer.get_end_iter()

		if start and end:
			buffer.select_range(start, end)

	def on_populate_popup(self, treeview, menu):
		model, paths = treeview.get_selection().get_selected_rows()
		if not paths:
			can_promote = False
			can_demote = False
		else:
			can_promote = self.can_promote(paths)
			can_demote = self.can_demote(paths)

		populate_popup_add_separator(menu, prepend=True)
		for text, sensitive, handler in (
			(_('Demote'), can_demote, self.on_demote),
				# T: action to lower level of heading in the text
			(_('Promote'), can_promote, self.on_promote),
				# T: action to raise level of heading in the text
		):
			item = gtk.MenuItem(text)
			menu.prepend(item)
			if sensitive:
				item.connect('activate', handler)
			else:
				item.set_sensitive(False)

	def can_promote(self, paths):
		# All headings have level larger than 1
		return paths and all(len(p) > 1 for p in paths)

	def on_promote(self, *a):
		# Promote selected paths and all their children
		model, paths = self.treeview.get_selection().get_selected_rows()
		if not self.can_promote(paths):
			return False

		seen = set()
		for path in paths:
			iter = model.get_iter(path)
			for i in self._walk(model, iter):
				p = model.get_path(i)
				if not p in seen:
					if self.show_h1:
						newlevel = len(p) - 1
					else:
						newlevel = len(p)
					self._format(p, newlevel)
				seen.add(p)

		self.load_page(self.pageview.page)
		return True

	def can_demote(self, paths):
		# All headings below max level and all have a potential parent
		# Potential parents should be on the same level above the selected
		# path, so as long as the path is not the first on it's level it
		# has one.
		# Or the current parent path also has to be in the list
		if not paths \
		or any(len(p) >= 6 for p in paths):
			return False

		for p in paths:
			if p[-1] == 0 and not p[:-1] in paths:
					return False
		else:
			return True

	def on_demote(self, *a):
		# Demote selected paths and all their children
		# note can not demote below level 6
		model, paths = self.treeview.get_selection().get_selected_rows()
		if not self.can_demote(paths):
			return False

		seen = set()
		for path in paths:
			# FIXME parent may have different real level if levels are
			# inconsistent - this should result in an offset being applied
			# But need to check actual heading tags being used to know for sure
			iter = model.get_iter(path)
			for i in self._walk(model, iter):
				p = model.get_path(i)
				if not p in seen:
					if self.show_h1:
						newlevel = len(p) + 1
					else:
						newlevel = len(p) + 2

					self._format(p, newlevel)
				seen.add(p)

		self.load_page(self.pageview.page)
		return True


	def _walk(self, model, iter):
		# yield iter and all its (grand)children
		yield iter
		child = model.iter_children(iter)
		while child:
			for i in self._walk(model, child):
				yield i
			child = model.iter_next(child)

	def _format(self, path, level):
		assert level > 0 and level < 7
		if self.select_heading(path):
			self.pageview.toggle_format('h' + str(level))


class SidePaneToC(ToCWidget):

	def __init__(self, ui, pageview):
		ToCWidget.__init__(self, ui, pageview, ellipsis=True)
		self.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
		self.set_shadow_type(gtk.SHADOW_IN)
		self.set_size_request(-1, 200) # Fixed Height


class BoxWidget(gtk.VBox):

	# Tried to implement somthing like this from scratch,
	# but found that I need to inherit from a concrete gtk.Container
	# implementation because I couldn't figure out how to override
	# / implement the forall() method from python

	BORDER = 0
	LINE = 1

	def __init__(self):
		gtk.VBox.__init__(self)
		self.set_border_width(self.BORDER + self.LINE)
		self.set_spacing(2 * self.BORDER + self.LINE)
		self.set_redraw_on_allocate(True)

	def do_expose_event(self, event):
		self.foreach(self._expose_child, event)
		return True

	def _expose_child(self, child, event):
		# Draw box around child, then draw child
		# Widget must ensure there is space arount the child

		line = self.LINE
		border = self.BORDER

		if child.is_drawable():
			self.style.paint_flat_box(
				event.window, gtk.STATE_ACTIVE, gtk.SHADOW_NONE, None, self, None,
				child.allocation.x - border - line,
				child.allocation.y - border - line,
				child.allocation.width + 2*border + 2*line,
				child.allocation.height + 2*border + 2*line,
			)
			self.style.paint_flat_box(
				event.window, gtk.STATE_NORMAL, gtk.SHADOW_NONE, None, self, None,
				child.allocation.x - border,
				child.allocation.y - border,
				child.allocation.width + 2*border,
				child.allocation.height + 2*border,
			)
		gtk.Container.propagate_expose(self, child, event)


# Need to register classes defining gobject signals
gobject.type_register(BoxWidget)


class FloatingToC(BoxWidget, ConnectorMixin):

	# This class does all the work to keep the floating window in
	# the right place, and with the right size
	# Depends on BoxWidget to draw nice line border around it

	TEXTVIEW_OFFSET = 5

	def __init__(self, ui, pageview):
		BoxWidget.__init__(self)

		hscroll = gtk.HScrollbar(gtk.Adjustment())
		self._hscroll_height = hscroll.size_request()[1]

		self.head = gtk.Label(_('ToC'))
		self.head.set_padding(5, 1)

		self.widget = ToCWidget(ui, pageview, ellipsis=False)
		self.widget.set_shadow_type(gtk.SHADOW_NONE)
		self.widget.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
			# Setting horizontal scroll automatic as well
			# makes the scrollbars visible at all times once they are shown once
			# custom control implemented below

		self._head_event_box = gtk.EventBox()
		self._head_event_box.add(self.head)
		self._head_event_box.connect('button-release-event', self.on_toggle)

		self.pack_start(self._head_event_box, False)
		self.pack_start(self.widget)

		## Add self to textview
		# Need to wrap in event box to make widget visible
		# probably because Containers normally don't have their own
		# gdk window. So would paint directly on background window.
		self.textview = pageview.view
		self._text_view_allocation = (
			self.textview.allocation.width,
			self.textview.allocation.height
		)
		self._event_box = gtk.EventBox()
		self._event_box.add(self)

		self.textview.add_child_in_window(self._event_box, gtk.TEXT_WINDOW_WIDGET, 0, 0)
		self.connectto(self.textview,
			'size-allocate',
			handler=self.on_size_allocate_textview,
		)
		self.connectto(self,
			'size-allocate',
			handler=self.update_position,
		)

		self._event_box.show_all()

	def set_show_h1(self, show_h1):
		self.widget.set_show_h1(show_h1)

	def disconnect_all(self):
		self.widget.disconnect_all()
		ConnectorMixin.disconnect_all(self)

	def destroy(self):
		self._event_box.destroy()
		BoxWidget.destroy(self)

	def on_toggle(self, *a):
		self.widget.set_property('visible',
			not self.widget.get_property('visible')
		)
		self.queue_draw()

	def do_size_request(self, requisition):
		# Base size request on the actual treeview, not on the
		# scrolled window. If we limit the size, assume the scrolled
		# window to take care of it

		text_window = self.textview.get_window(gtk.TEXT_WINDOW_WIDGET)
		if text_window is None:
			# Textview not yet initialized (?)
			return BoxWidget.do_size_request(self, requisition)

		text_x, text_y, text_w, text_h, text_z = text_window.get_geometry()

		head_w, head_h = self.head.size_request()
		border = self.get_border_width()
		spacing = self.get_spacing()

		if self.widget.get_property('visible'):
			tree_w, tree_h = self.widget.treeview.size_request()
			tree_h = max(tree_h, head_h) # always show empty space if no content
			tree_w += 1 # Allow minimal frame for scrolledwindow
			tree_h += 1
			total_w = max(head_w, tree_w) + 2 * border
			total_h = head_h + tree_h + 2 * border + spacing
		else:
			total_w = head_w + 2 * border
			total_h = head_h + 2 * border

		max_w = 0.5 * text_w - self.TEXTVIEW_OFFSET
		max_h = 0.7 * text_h - self.TEXTVIEW_OFFSET

		if total_w > max_w:
			# We are going to show a srollbar at the bottom
			# the +3 is a hack to give enough space so vscroll is
			# not triggered unnecessary
			total_h += self._hscroll_height + 3

		requisition.width = min(max_w, total_w)
		requisition.height = min(max_h, total_h)

	def do_size_allocate(self, allocation):
		# Need to overload this one as well, to make sure we get what
		# we wanted
		self.allocation=allocation

		border = self.get_border_width()
		spacing = self.get_spacing()
		head_height = self.head.get_child_requisition()[1]
		tree_w, tree_h = self.widget.treeview.get_child_requisition()

		self._head_event_box.size_allocate(gtk.gdk.Rectangle(
			x=allocation.x + border,
			y=allocation.y + border,
			width=allocation.width - 2*border,
			height=head_height
		))

		if self.widget.get_property('visible'):
			body_w = allocation.width - 2*border
			body_h = allocation.height - 2*border - spacing - head_height

			h_policy = gtk.POLICY_ALWAYS if tree_w > body_w else gtk.POLICY_NEVER
			self.widget.set_policy(h_policy, gtk.POLICY_AUTOMATIC)

			self.widget.size_allocate(gtk.gdk.Rectangle(
				x=allocation.x + border,
				y=allocation.y + border + head_height + spacing,
				width=body_w,
				height=body_h
			))

	def on_size_allocate_textview(self, textview, a):
		new_allocation = (a.width, a.height)
		if new_allocation != self._text_view_allocation:
			self.queue_resize()
			# resize results in size_allocate, which results in update_position
		self._text_view_allocation = new_allocation

	def update_position(self, *a):
		text_window = self.textview.get_window(gtk.TEXT_WINDOW_WIDGET)
		if text_window is not None:
			text_x, text_y, text_w, text_h, text_z = text_window.get_geometry()
			x = text_w - self.allocation.width - self.TEXTVIEW_OFFSET
			y = self.TEXTVIEW_OFFSET
			self.textview.move_child(self._event_box, x, y)
		else:
			pass # Textview not yet initialized (?)

# Need to register classes defining gobject signals
gobject.type_register(FloatingToC)
