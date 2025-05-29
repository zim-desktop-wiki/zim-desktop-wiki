
# Copyright 2012-2025 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GObject
from gi.repository import Pango
from typing import List, Optional, Tuple

import logging

logger = logging.getLogger('zim.plugins.tableofcontents')


from zim.plugins import PluginClass
from zim.signals import ConnectorMixin, DelayedCallback, SIGNAL_AFTER
from zim.parse.tokenlist import tokens_to_text, collect_until_end_token
from zim.formats import HEADING, LINE

from zim.gui.clipboard import Clipboard, SelectionClipboard
from zim.gui.pageview import PageViewExtension
from zim.gui.widgets import LEFT_PANE, PANE_POSITIONS, BrowserTreeView, populate_popup_add_separator, \
	WindowSidePaneWidget, widget_set_css
from zim.gui.pageview import SCROLL_TO_MARK_MARGIN, LineSeparatorAnchor

LINE_LEVEL = 2  # assume level 1 is page heading, level 2 is topic break within page


def find_heading(buffer, n, include_hr):
	'''Find the C{n}th heading in the buffer
	@param buffer: the C{Gtk.TextBuffer}
	@param n: an integer
	@returns: a C{Gtk.TextIter} for the line start of the heading or C{None}
	'''
	if include_hr:
		check = lambda i: buffer.get_line_is_heading(i.get_line()) or buffer.get_anchor_object_at_iter(i, LineSeparatorAnchor)
	else:
		check = lambda i: buffer.get_line_is_heading(i.get_line())

	iter = buffer.get_start_iter()
	i = 1 if check(iter) else 0
	while i < n:
		iter.forward_line()
		while not check(iter):
			if not iter.forward_line():
				return None
		i += 1
	return iter


def select_heading(buffer, n, include_hr):
	'''Select the C{n}th heading in the buffer'''
	iter = find_heading(buffer, n, include_hr)
	if iter:
		buffer.place_cursor(iter)
		buffer.select_line()
		return True
	else:
		return False


def get_headings(buffer, include_hr):
	iter = buffer.get_start_iter()
	stack = [(0, None, None, [])] # level, text, line, children
	while True:
		level, text = buffer.get_heading(iter.get_line())
		if level is not None: # Is heading
			assert level > 0 # just to be sure
			while stack[-1][0] >= level:
				stack.pop()
			node = (level, text, iter.get_line(), [])
			stack[-1][-1].append(node)
			stack.append(node)
		elif include_hr and buffer.get_anchor_object_at_iter(iter, LineSeparatorAnchor):
			while stack[-1][0] >= LINE_LEVEL:
				stack.pop()
			node = (LINE_LEVEL, '\u2500\u2500\u2500\u2500', iter.get_line(), [])
				# \u2500 == "BOX DRAWINGS LIGHT HORIZONTAL"
			stack[-1][-1].append(node)
			stack.append(node)
		else:
			pass

		if not iter.forward_line():
			break

	return stack[0][-1]


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
		('include_hr', 'bool', _('Include horizontal lines in the ToC'), True),
			# T: option for plugin preferences
		('fontsize', 'int', _('Set ToC fontsize'), 0, (0, 24)),
			# T: option for plugin preferences
	)
	# TODO disable pane setting if not embedded


class ToCPageViewExtension(PageViewExtension):

	def __init__(self, plugin, pageview):
		PageViewExtension.__init__(self, plugin, pageview)
		self.tocwidget = None
		self.on_preferences_changed(plugin.preferences)
		self.connectto(plugin.preferences, 'changed', self.on_preferences_changed)

	def on_preferences_changed(self, preferences):
		widgetclass = FloatingToC if preferences['floating'] else SidePaneToC
		if not isinstance(self.tocwidget, widgetclass):
			if isinstance(self.tocwidget, SidePaneToC):
				self.remove_sidepane_widget(self.tocwidget)
			elif self.tocwidget:
				self.tocwidget.destroy()

			self.tocwidget = widgetclass(self.pageview)

			if isinstance(self.tocwidget, SidePaneToC):
				self.add_sidepane_widget(self.tocwidget, 'pane')

		self.tocwidget.set_preferences(
			preferences['show_h1'],
			preferences['include_hr'],
			preferences['fontsize']
		)


TEXT_COL = 0
LINE_COL = 1

class ToCTreeView(BrowserTreeView):

	def __init__(self, ellipsis, fontsize):
		BrowserTreeView.__init__(self, ToCTreeModel())
		self.set_headers_visible(False)
		self.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
			# Allow select multiple

		cell_renderer = Gtk.CellRendererText()
		if fontsize > 0:
			cell_renderer.set_property('size-points', fontsize)
		if ellipsis:
			cell_renderer.set_property('ellipsize', Pango.EllipsizeMode.END)
		column = Gtk.TreeViewColumn('_heading_', cell_renderer, text=TEXT_COL)
		column.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
			# Without this sizing, column width only grows and never shrinks
		self._cell_renderer = cell_renderer
		self.append_column(column)

	def set_fontsize(self, fontsize):
		if fontsize != 0:
			self._cell_renderer.set_property('size-points', fontsize)

	def select_heading_for_line(self, line: int):
		'''Select the heading to which C{line} belongs'''
		selection = self.get_selection()
		if selection is None:
			return # see bug #2772, not sure how this happens
		selection.unselect_all()
		model = self.get_model()

		previous = None
		for i in model.walk():
			if model[i][1] > line: # LINE_COL
				break
			else:
				previous = i

		if previous is not None:
			treepath = model.get_path(previous)
			selection.select_path(treepath)


class ToCTreeModel(Gtk.TreeStore):

	def __init__(self):
		Gtk.TreeStore.__init__(self, str, int) # TEXT_COL, LINE_COL
		self.is_empty = True
		self.hidden_h1 = False

	def clear(self):
		self.is_empty = True
		Gtk.TreeStore.clear(self)

	def walk(self, iter=None):
		if iter is not None:
			yield iter
			child = self.iter_children(iter)
		else:
			child = self.get_iter_first()

		while child:
			if self.iter_has_child(child):
				for i in self.walk(child):
					yield i
			else:
				yield child
			child = self.iter_next(child)

	def get_nth_heading(self, path):
		n = 1 if self.hidden_h1 else 0
		for iter in self.walk():
			n += 1
			if self.get_path(iter) == path:
				break
		return n

	def update(self, headings, show_h1):
		if not show_h1 \
		and len(headings) == 1 \
		and headings[0][0] == 1:
			# do not show first heading
			headings = headings[0][-1]
			self.hidden_h1 = True
		else:
			self.hidden_h1 = False

		if not headings:
			self.clear()
			return

		if self.is_empty:
			self._insert_headings(headings)
		else:
			self._update_headings(headings)

		self.is_empty = False

	def _update_headings(self, headings, parent=None):
		iter = self.iter_children(parent)
		for level, text, line, children in headings:
			if iter:
				# Compare to model
				self[iter] = (text, line) # TEXT_COL, LINE_COL
				if children:
					if self.iter_has_child(iter):
						self._update_headings(children, iter)
					else:
						self._insert_headings(children, iter)
				elif self.iter_has_child(iter):
					self._clear_children(iter)
				else:
					pass

				iter = self.iter_next(iter)
			else:
				# Model ran out
				myiter = self.append(parent, (text, line)) # TEXT_COL, LINE_COL
				if children:
					self._insert_headings(children, myiter)

		# Remove trailing items
		if iter:
			while self.remove(iter):
				pass

	def _clear_children(self, parent):
		iter = self.iter_children(parent)
		if iter:
			while self.remove(iter):
				pass

	def _insert_headings(self, headings, parent=None):
		for level, text, line, children in headings:
			iter = self.append(parent, (text, line)) # TEXT_COL, LINE_COL
			if children:
				self._insert_headings(children, iter)


class ToCWidget(ConnectorMixin, Gtk.ScrolledWindow):

	__gsignals__ = {
		'changed': (GObject.SignalFlags.RUN_LAST, None, ()),
	}

	def __init__(self, pageview, ellipsis, show_h1=False, include_hr=True, fontsize=0):
		GObject.GObject.__init__(self)
		self.show_h1 = show_h1
		self.include_hr = include_hr
		self.fontsize = fontsize
		self._active_line = None
		self._connected_to_textbuffer = False # HACK to ensure we initialize correctly

		self.treeview = ToCTreeView(ellipsis, fontsize)
		self.treeview.connect('row-activated', self.on_heading_activated)
		self.treeview.connect('populate-popup', self.on_populate_popup)
		self.add(self.treeview)

		self.pageview = pageview
		self.connectto(pageview, 'page-changed')
		self.connectto(pageview, 'textbuffer-changed')
		self.connectto(pageview.notebook, 'store-page')
		self.on_textbuffer_changed(self.pageview, None, self.pageview.textview.get_buffer())
		self.on_page_changed(self.pageview, self.pageview.page)

	def set_preferences(self, show_h1, include_hr, fontsize):
		changed = (show_h1, include_hr, fontsize) != (self.show_h1, self.include_hr, self.fontsize)
		self.show_h1 = show_h1
		self.include_hr = include_hr
		self.fontsize = fontsize
		self.treeview.set_fontsize(fontsize)
		if changed and self.pageview.page:
			self.load_page(self.pageview.page)

	def on_page_changed(self, pageview, page):
		self.load_page(page)
		self.treeview.expand_all()

	def on_store_page(self, notebook, page):
		if page == self.pageview.page:
			self.load_page(page)

	def load_page(self, page):
		model = self.treeview.get_model()
		if model is None:
			return
		textview = self.pageview.textview
		buffer = textview.get_buffer()
		if buffer.hascontent:
			model.update(get_headings(buffer, self.include_hr), self.show_h1)
			self.treeview.select_heading_for_line(buffer.get_insert_iter().get_line())
		else:
			model.clear()
		self.emit('changed')

	def on_textbuffer_changed(self, pageview, oldbuffer, newbuffer):
		if oldbuffer is not None:
			self.disconnect_from(oldbuffer)
		self.connectto(newbuffer, 'mark-set', order=SIGNAL_AFTER)

	def on_mark_set(self, textbuffer, iter, mark):
		# Update selection in widget, but avoid doing it unless line changed
		if mark.get_name() == 'insert' and iter.get_line() != self._active_line:
			self._active_line = iter.get_line()
			self.treeview.select_heading_for_line(self._active_line)

	def on_heading_activated(self, treeview, path, column):
		self.select_heading(path)

	def select_heading(self, path):
		'''Returns a C{Gtk.TextIter} for a C{Gtk.TreePath} pointing to a heading
		or C{None}.
		'''
		model = self.treeview.get_model()
		n = model.get_nth_heading(path)

		textview = self.pageview.textview
		buffer = textview.get_buffer()
		if select_heading(buffer, n, self.include_hr):
			textview.scroll_to_mark(buffer.get_insert(), SCROLL_TO_MARK_MARGIN, False, 0, 0)
			return True
		else:
			return False

	def select_section(self, buffer, path):
		'''Select all text between two headings
		@param buffer: the C{Gtk.TextBuffer} to select in
		@param path: the C{Gtk.TreePath} for the heading of the section
		'''
		model = self.treeview.get_model()
		n = model.get_nth_heading(path)

		textview = self.pageview.textview
		buffer = textview.get_buffer()
		start = find_heading(buffer, n, self.include_hr)
		if start is None:
			return
		end = find_heading(buffer, n + 1, self.include_hr)
		if end is None:
			end = buffer.get_end_iter()

		buffer.select_range(start, end)

	def on_copy_link_to_anchor(self, obj, anchor: str, heading_text: str):
		Clipboard.set_pagelink(self.pageview.notebook, self.pageview.page, anchor, heading_text)
		SelectionClipboard.set_pagelink(self.pageview.notebook, self.pageview.page, anchor, heading_text)
		return True

	def can_copy_link_to_anchor(self, paths: List[str]) -> Optional[Tuple[str,str]]:
		if not paths or len(paths) != 1:
			return None
		model = self.treeview.get_model()
		n = model.get_nth_heading(paths[0])
		textview = self.pageview.textview
		buffer = textview.get_buffer()
		hd_iter = find_heading(buffer, n, self.include_hr)
		if not hd_iter:
			return None
		anchor = buffer.get_anchor_for_location(hd_iter)
		if not anchor:
			return None
		lvl, heading_text = buffer.get_heading(hd_iter.get_line())
		if not heading_text:
			return None
		return anchor, heading_text

	def on_populate_popup(self, treeview, menu):
		model, paths = treeview.get_selection().get_selected_rows()
		if not paths:
			can_promote = False
			can_demote = False
		else:
			can_promote = self.can_promote(paths)
			can_demote = self.can_demote(paths)

		link_details = self.can_copy_link_to_anchor(paths)

		populate_popup_add_separator(menu, prepend=True)
		for text, sensitive, handler in (
			(_('Demote'), can_demote, self.on_demote),
				# T: action to lower level of heading in the text
			(_('Promote'), can_promote, self.on_promote),
				# T: action to raise level of heading in the text
		):
			item = Gtk.MenuItem.new_with_mnemonic(text)
			menu.prepend(item)
			if sensitive and link_details:  # exclude horizontal bars
				item.connect('activate', handler)
			else:
				item.set_sensitive(False)

		menu.append(Gtk.SeparatorMenuItem())

		item = Gtk.MenuItem.new_with_mnemonic(_('Copy _link to this location'))  # T: menu item
		menu.append(item)
		if link_details:
			item.connect('activate', self.on_copy_link_to_anchor, *link_details)
		else:
			item.set_sensitive(False)

		# open item in new window
		item = Gtk.MenuItem.new_with_mnemonic(_('Open in New _Window'))  # T: menu item
		menu.append(item)
		if link_details:
			item.connect('activate', self.on_open_in_new_window, *link_details)
		else:
			item.set_sensitive(False)

		menu.show_all()

	def on_open_in_new_window(self, obj, anchor: str, heading_text: str):
		self.pageview.navigation.open_page(self.pageview.page, anchor, new_window=True)

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
			for i in model.walk(iter):
				p = model.get_path(i)
				key = tuple(p)
				if key not in seen:
					if self.show_h1:
						newlevel = len(p) - 1
					else:
						newlevel = len(p)
					self._format(p, newlevel)
				seen.add(key)

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

		paths = list(map(tuple, paths))
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
			for i in model.walk(iter):
				p = model.get_path(i)
				key = tuple(p)
				if not key in seen:
					if self.show_h1:
						newlevel = len(p) + 1
					else:
						newlevel = len(p) + 2

					self._format(p, newlevel)
				seen.add(key)

		self.load_page(self.pageview.page)
		return True

	def _format(self, path, level):
		assert level > 0 and level < 7
		if self.select_heading(path):
			self.pageview.toggle_format('h' + str(level))
		else:
			logger.warning('Failed to select heading for path: %', path)


class SidePaneToC(ToCWidget, WindowSidePaneWidget):

	title = _('T_oC') # T: widget label

	def __init__(self, pageview):
		ToCWidget.__init__(self, pageview, ellipsis=True)
		self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
		self.set_shadow_type(Gtk.ShadowType.IN)
		self.set_size_request(-1, 200) # Fixed Height


class MyEventBox(Gtk.EventBox):

		def do_button_press_event(self, event):
			return True # Prevent propagating event to parent textview

		def do_button_release_event(self, event):
			return True # Prevent propagating event to parent textview


class FloatingToC(Gtk.VBox, ConnectorMixin):

	# This class puts the floating window in the pageview overlay layer
	# and adjusts it's size on the fly

	MARGIN_END = 12 # offset right side textview
	MARGIN_TOP = 12 # offset top textview
	SCROLL_MARGIN = 10 # margin inside the toc for scrollbars

	def __init__(self, pageview):
		GObject.GObject.__init__(self)

		self.head = Gtk.Label(label=_('ToC')) # T: small label above Table Of Contents
		self.head.set_padding(5, 1)

		self.tocwidget = ToCWidget(pageview, ellipsis=False)
		self.tocwidget.set_shadow_type(Gtk.ShadowType.NONE)

		self._head_event_box = MyEventBox()
		self._head_event_box.add(self.head)
		self._head_event_box.connect('button-release-event', self.on_toggle)
		self._head_event_box.get_style_context().add_class(Gtk.STYLE_CLASS_BACKGROUND)

		self.pack_start(self._head_event_box, False, True, 0)
		self.pack_start(self.tocwidget, True, True, 0)

		widget_set_css(self, 'zim-toc-widget', 'border: 1px solid @fg_color')
		widget_set_css(self.head, 'zim-toc-head', 'border-bottom: 1px solid @fg_color')

		self.set_halign(Gtk.Align.END)
		self.set_margin_end(self.MARGIN_END)
		self.set_valign(Gtk.Align.START)
		self.set_margin_top(self.MARGIN_TOP)
		pageview.overlay.add_overlay(self)

		self._textview = pageview.textview
		self.connectto(self._textview,
			'size-allocate',
			handler=DelayedCallback(10, self.update_size_and_position),
				# Callback wrapper to prevent glitches for fast resizing of the window
		)
		self.connectto(self.tocwidget, 'changed', handler=self.update_size_and_position_after_change)

		self.show_all()

	def set_preferences(self, show_h1, include_hr, fontsize):
		self.tocwidget.set_preferences(show_h1, include_hr, fontsize)

	def disconnect_all(self):
		self.tocwidget.disconnect_all()
		ConnectorMixin.disconnect_all(self)

	def on_toggle(self, *a):
		self.tocwidget.set_visible(
			not self.tocwidget.get_visible()
		)
		self.update_size_and_position()

	def update_size_and_position_after_change(self, *a):
		self.tocwidget.treeview.expand_all()
		self.update_size_and_position()

	def update_size_and_position(self, *a):
		model = self.tocwidget.treeview.get_model()
		if model is None or model.is_empty:
			self.hide()
			return
		else:
			self.show()

		text_window = self._textview.get_window(Gtk.TextWindowType.WIDGET)
		if text_window is None:
			return

		text_x, text_y, text_w, text_h = text_window.get_geometry()
		max_w = 0.5 * text_w - self.MARGIN_END
		max_h = 0.7 * text_h - self.MARGIN_TOP

		head_minimum, head_natural = self.head.get_preferred_width()
		view_minimum, view_natural = self.tocwidget.treeview.get_preferred_width()
		if self.tocwidget.get_visible():
			my_width = max(head_natural, view_natural + self.SCROLL_MARGIN)
			width = min(my_width, max_w)
		else:
			width = head_natural

		head_minimum, head_natural = self.head.get_preferred_height()
		view_minimum, view_natural = self.tocwidget.treeview.get_preferred_height()
		if self.tocwidget.get_visible():
			my_height = head_natural + view_natural + self.SCROLL_MARGIN
			height = min(my_height, max_h)
		else:
			height = head_natural

		self.set_size_request(width, height)
