
# Copyright 2008-2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import gi
gi.require_version('Gtk', '3.0')

from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import GLib
from gi.repository import Gdk
from gi.repository import Pango
import logging

from functools import reduce

from zim.plugins import PluginClass
from zim.actions import radio_action, radio_option
from zim.notebook.page import shortest_unique_names

from zim.gui.mainwindow import MainWindowExtension
from zim.gui.widgets import encode_markup_text, gtk_popup_at_pointer, widget_set_css
from zim.gui.uiactions import UIActions, PAGE_ACCESS_ACTIONS
from zim.gui.clipboard import \
	INTERNAL_PAGELIST_TARGET_NAME, INTERNAL_PAGELIST_TARGET, \
	pack_urilist


logger = logging.getLogger('zim.gui')


MAX_BUTTON_WIDTH = 250 # Prevent single button to fill whole screen
MIN_BUTTON_WIDTH = 50 # Prevent buttons smaller than ellipsize allows


class PathBarPlugin(PluginClass):

	plugin_info = {
		'name': _('Path Bar'), # T: plugin name
		'description': _('''\
This plugin adds a "path bar" to the top of the window.
This "path bar" can show the notebook path for the current page,
recent visited pages or recent edited pages.
'''), # T: plugin description
		'author': 'Jaap Karssenberg',
		'help': 'Plugins:PathBar',
	}


PATHBAR_NONE = 'none' #: Constant for no pathbar
PATHBAR_RECENT = 'recent' #: Constant for the recent pages pathbar
PATHBAR_RECENT_CHANGED = 'recent_changed' #: Constant for the recent pages pathbar
PATHBAR_HISTORY = 'history' #: Constant for the history pathbar
PATHBAR_PATH = 'path' #: Constant for the namespace pathbar
PATHBAR_TYPES = (PATHBAR_NONE, PATHBAR_RECENT, PATHBAR_RECENT_CHANGED, PATHBAR_HISTORY, PATHBAR_PATH)


class PathBarMainWindowExtension(MainWindowExtension):

	_klasses = {
		PATHBAR_NONE: None,
		# other classes are added below where they are defined
	}

	def __init__(self, plugin, window):
		MainWindowExtension.__init__(self, plugin, window)
		self.pathbar = None
		self.uistate.setdefault('pathbar_type', PATHBAR_RECENT, PATHBAR_TYPES)
		self.set_pathbar(self.uistate['pathbar_type'])
		self.connectto(window, 'page-changed')

	def on_page_changed(self, window, page):
		if self.pathbar is not None:
			self.pathbar.set_page(page)

	def teardown(self):
		if self.pathbar is not None:
			self.window.remove(self.pathbar)

	@radio_action(
		_('P_athbar'), # T: Menu title
		radio_option(PATHBAR_NONE, _('_None')),  # T: Menu option for View->Pathbar
		radio_option(PATHBAR_RECENT, _('_Recent pages')), # T: Menu option for View->Pathbar
		radio_option(PATHBAR_RECENT_CHANGED, _('Recently _Changed pages')), # T: Menu option for View->Pathbar
		radio_option(PATHBAR_HISTORY, _('_History')), # T: Menu option for View->Pathbar
		radio_option(PATHBAR_PATH, _('_Page Hierarchy')), # T: Menu option for View->Pathbar
		menuhints='view'
	)
	def set_pathbar(self, type):
		'''Set the pathbar type

		@param type: the type of pathbar, one of:
			- C{PATHBAR_NONE} to hide the pathbar
			- C{PATHBAR_RECENT} to show recent pages
			- C{PATHBAR_RECENT_CHANGED} to show recently changed pagesF
			- C{PATHBAR_HISTORY} to show the history
			- C{PATHBAR_PATH} to show the namespace path
		'''
		if self.pathbar is not None:
			try:
				self.window.remove(self.pathbar)
			except ValueError:
				pass
			self.pathbar = None

		klass = self._klasses[type]
		if klass is not None:
			self.pathbar = klass(
				self.window.history,
				self.window.notebook,
				self.window.navigation
			)
			self.pathbar.set_page(self.window.page)
			self.pathbar.set_border_width(1)
			self.pathbar.show_all()
			self.window.add_center_bar(self.pathbar)

		self.uistate['pathbar_type'] = type


# Constants
DIR_FORWARD = 1
DIR_BACKWARD = -1

class ScrolledHBox(Gtk.HBox):
	'''This class provides a widget that behaves like a HBox when there is
	enough space to render all child widgets. When space is limited it
	shows arrow buttons on the left and on the right to allow scrolling
	through the widgets.

	Note that this class does not support packing options like
	'expand', 'fill' etc. All child widgets can just be added with 'add()'.
	'''

	# In order to display as many items as possible we use the following
	# scrolling algorithm:
	#
	# There is an attribute "_anchor" which is a tuple of a direction and the index
	# of a child item. This anchor represents the last scrolling action.
	# We start filling the space by taking this anchor item as either left or right
	# side of the visible range (depending on the given direction) and start adding
	# other items from there. We can run out of items when we reach the end of the
	# item list, or we can run out of space when the next item is larger than the
	# space that is left.
	# Next we check if we can show more items by adding items in the opposite
	# direction. Possibly replacing our anchor as outer left or outer right item.
	# Once we know which items can be shown we start allocating space to the widgets.
	#
	# Slide buttons are shown unless all children fit in the given space. So
	# the space is calculated either with or without sliders. At the end we
	# check if the sliders are really needed.
	#
	# Even through we fix the size request of the buttons in "add()", button
	# sizes can differ subtly, e.g. due to different CSS rendering for the
	# first and last button. Therefore we keep a "_state" attribute to remember
	# the allocation outcome and prevent a "flcikering" state where we keep
	# re-calculating.

	# FIXME: Actually wanted to inherit from Gtk.Box instead of Gtk.HBox, but seems
	# we can not call GObject.GObject.__init__() to instantiate the object.

	__gsignals__ = {
		'size-allocate': 'override',
	}

	initial_scroll_timeout = 300 # timeout before starting scrolling on button press
	scroll_timeout = 150 # timeout between scroll steps

	def __init__(self):
		GObject.GObject.__init__(self)
		self.set_spacing(0)
		self.set_homogeneous(False)
		self._scroll_timeout = None
		self._minwidth = MIN_BUTTON_WIDTH
		self._anchor = None # tuple of (direction, n) - used in allocate
		self._state = None # tuple of (allocation width, show scrollbars, first item, last item) - used in allocation
		self._forw_button = ScrollButton(DIR_FORWARD)
		self._back_button = ScrollButton(DIR_BACKWARD)
		for button in (self._back_button, self._forw_button):
			Gtk.HBox.add(self, button)
			button.connect('button-press-event', self._on_button_press)
			button.connect('button-release-event', self._on_button_release)
			button.connect('clicked', self._on_button_clicked)

		context = self.get_style_context()
		context.add_class("linked")

	def add(self, child):
		self._state = None
		widget_set_css(child, 'zim-pathbar-path-button', 'padding: 2px 6px 2px 6px;')
			# Make buttons a bit smaller (but keep some horizontal padding)
		req = child.get_preferred_size()[1]
		child.set_size_request(min(req.width, MAX_BUTTON_WIDTH), req.height)
			# Try to force the size to remain stable over state changes
		Gtk.HBox.add(self, child)
		self.reorder_child(self._forw_button, -1) # Shuffle to the end

	def remove(self, child):
		self._state = None
		Gtk.HBox.remove(self, child)

	def pack_start(*a):
		raise NotImplementedError

	def pack_end(*a):
		raise NotImplementedError

	def get_scrolled_children(self):
		return self.get_children()[1:-1] # exclude scroll buttons

	def get_visible_children(self):
		first, last = self._state[-2:] if self._state else (0, 0)
		return self.get_children()[1:-1][first, last]

	def __del__(self):
		self.stop_scrolling()

	def _on_button_press(self, button, event):
		if event.button == 1:
			self.start_scrolling(button.direction, initial_timeout=True)

	def _on_button_release(self, button, event):
		self.stop_scrolling()

	def _on_button_clicked(self, button):
		self.scroll(button.direction)

	def scroll(self, direction, n=1):
		'''Scroll n items in either direction. Direction should be either
		DIR_FORWARD or DIR_BACKWARD, while n should be integer.
		Returns boolean for success.
		'''
		# returning boolean also controls timeout behavior

		first, last = self._state[-2:] if self._state else (0, 0)
		if direction == DIR_FORWARD:
			last_in_list = len(self.get_scrolled_children()) - 1
			if last == last_in_list:
				return False
			else:
				i = min(last + n, last_in_list)
		elif direction == DIR_BACKWARD:
			if first == 0:
				return False
			else:
				i = max(first - n, 0)
		else:
			raise ValueError('Invalid direction argument')

		self._anchor = (direction, i)
		self.queue_resize()
		return True

	def scroll_to_child(self, child):
		i = self.get_scrolled_children().index(child)
		first, last = self._state[-2:] if self._state else (0, 0)
		if i <= first: # "<=" because first item might be ellipsized
			self._anchor = (DIR_BACKWARD, i)
		elif i >= last: # ">=" because last item might be ellipsized
			self._anchor = (DIR_FORWARD, i)
		else:
			pass # child was visible already, keep anchor
		self.queue_resize()

	def start_scrolling(self, direction, initial_timeout=False):
		'''Start continues scrolling. Direction should be either
		DIR_FORWARD or DIR_BACKWARD. If we were scrolling already, stops
		this action before setting new scroll direction.
		'''
		self.stop_scrolling()
		if initial_timeout:
			self._scroll_timeout = \
				GLib.timeout_add(self.initial_scroll_timeout, self.start_scrolling, direction)
				# indirect recurs
		else:
			self._scroll_timeout = \
				GLib.timeout_add(self.scroll_timeout, self.scroll, direction)

		return False # make sure we are only called once from a timeout

	def stop_scrolling(self):
		'''Stop continues scrolling. Does not do anything if we were not
		scrolling.
		'''
		if not self._scroll_timeout is None:
			GLib.source_remove(self._scroll_timeout)
			self._scroll_timeout = None

	def do_get_preferred_width(self):
		widths = [
			min(b.get_preferred_width()[1], MAX_BUTTON_WIDTH)
				for b in self.get_scrolled_children()]
		border = 2 * self.get_border_width()
		if not widths:
			return border, border
		scrolled = \
			self._forw_button.get_preferred_width()[0] + \
			self._back_button.get_preferred_width()[0] + \
			max(widths) + \
			border
		natural = sum(widths) + border
		minimum = min(natural, scrolled)
		return minimum, natural

	def do_get_preferred_height(self):
		height = max(c.get_preferred_height()[1] for c in self.get_children()) \
					+ 2 * self.get_border_width()
		return height, height

	def do_size_allocate(self, allocation):
		# Assign the available space to the child widgets
		# See discussion of allocation algorithm above

		Gtk.HBox.do_size_allocate(self, allocation)

		children = self.get_scrolled_children()
		if not children:
			return # nothing to render

		direction, anchor = self._anchor or (DIR_FORWARD, 0)
		assert 0 <= anchor <= len(children)
		assert direction in (DIR_FORWARD, DIR_BACKWARD)
			# default (DIR_FORWARD, -1) should show the last item (right most)
			# and starts filling the space backward (to the left)

		border = self.get_border_width()

		widths = [
			min(b.get_preferred_width()[1], MAX_BUTTON_WIDTH)
				for b in children]
		total = reduce(int.__add__, widths) + 2 * border
		if self._state and self._state[0] == allocation.width:
			show_scroll_buttons = self._state[1]
			if not show_scroll_buttons and allocation.width < total:
				# Some child changed state since last allocation - assume minor
				# delta (e.g. 1px) and absorb delta in item on opposite side from anchor
				i = 0 if DIR_FORWARD else -1
				widths[i] -= total - allocation.width
		else:
			show_scroll_buttons = allocation.width < total

		if not show_scroll_buttons:
			first, last = 0, len(children) - 1
		else:
			# determine which children to show
			first, last = anchor, anchor
			available = allocation.width - widths[anchor] - 2 * border
			for button in (self._forw_button, self._back_button):
				available -= button.get_preferred_size()[0].width

			if direction == DIR_FORWARD:
				forw_iter = range(anchor - 1, -1, -1)
				back_iter = range(anchor + 1, len(children))
			else:
				forw_iter = range(anchor + 1, len(children))
				back_iter = range(anchor - 1, -1, -1)

			for i in forw_iter:
				if widths[i] > available:
					if available > MIN_BUTTON_WIDTH:
						first = i
						widths[i] = available
					else:
						self._distribute_size(available, widths, first, last)
					break
				else:
					first = i
					available -= widths[i]
			else:
				# exhausted iter - fill with items from the other direction
				for i in back_iter:
					if widths[i] > available:
						if available > MIN_BUTTON_WIDTH:
							last = i
							widths[i] = available
						else:
							self._distribute_size(available, widths, first, last)
						break
					else:
						last = i
						available -= widths[i]

		if first > last:
			first, last = last, first # Depends on DIR_FORWARD vs DIR_BACKWARD

		self._state = (allocation.width, show_scroll_buttons, first, last)

		if show_scroll_buttons:
			self._back_button.show()
			self._back_button.set_sensitive(first != 0)
			self._forw_button.show()
			self._forw_button.set_sensitive(last != len(children) - 1)
		else:
			# Hack: first show, then hide is needed to force re-drawing the
			#       "linked" css style of the buttons correctly
			self._back_button.show()
			self._back_button.hide()
			self._forw_button.show()
			self._forw_button.hide()

		# Allocate children - y and height are the same for all
		child_allocation = Gdk.Rectangle()
		child_allocation.y = allocation.y + border
		child_allocation.height = allocation.height - 2 * border
		if self.get_direction() != Gtk.TextDirection.RTL:
			# Left to Right
			child_allocation.x = allocation.x + border

			if show_scroll_buttons:
				child_allocation.width = self._back_button.get_preferred_size()[0].width
				self._back_button.size_allocate(child_allocation)
				child_allocation.x += child_allocation.width # set x for next child

			for i in range(first, last + 1):
				child_allocation.width = widths[i]
				children[i].set_child_visible(True)
				children[i].size_allocate(child_allocation)
				child_allocation.x += child_allocation.width # set x for next child

			if show_scroll_buttons:
				child_allocation.width = self._forw_button.get_preferred_size()[0].width
				self._forw_button.size_allocate(child_allocation)
		else:
			# Right to Left
			child_allocation.x = allocation.x + allocation.width - border

			if show_scroll_buttons:
				child_allocation.width = self._back_button.get_preferred_size()[0].width
				child_allocation.x -= child_allocation.width
				self._back_button.size_allocate(child_allocation)

			for i in range(first, last + 1):
				child_allocation.width = widths[i]
				child_allocation.x -= child_allocation.width
				children[i].set_child_visible(True)
				children[i].size_allocate(child_allocation)

			if show_scroll_buttons:
				child_allocation.width = self._forw_button.get_preferred_size()[0].width
				child_allocation.x -= child_allocation.width
				self._forw_button.size_allocate(child_allocation)

		# Hide remaining children
		for child in children[0:first]:
			child.set_child_visible(False)
		for child in children[last + 1:]:
			child.set_child_visible(False)

	def _distribute_size(self, available, widths, first, last):
		if first > last:
			first, last = last, first # Depends on DIR_FORWARD vs DIR_BACKWARD
		n = last - first + 1
		w = int(available / n)
		r = available - (n * w)
		for i in range(first, last + 1):
			widths[i] += w
		widths[last] += r


class ScrollButton(Gtk.Button):
	'''Arrow buttons used by ScrolledHBox'''

	def __init__(self, direction):
		GObject.GObject.__init__(self)
		self.direction = direction
		icon = 'pan-end-symbolic' if direction == DIR_FORWARD else 'pan-start-symbolic'
		self.add(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU))
		widget_set_css(self, 'zim-pathbar-scroll-button', 'padding: 2px 2px 2px 2px;')
			# Make button bit smaller


class PathBar(ScrolledHBox):
	'''Base class for pathbars in the zim GUI, extends ScrolledHBox for usage
	with a list of ToggleButtons representing zim Path objects'''

	def __init__(self, history, notebook, navigation):
		ScrolledHBox.__init__(self)
		self.set_name('zim-pathbar')
		self.history = history
		self.notebook = notebook
		self.page = None
		self.navigation = navigation
		self._update()
		if self.history is not None:
			self.history.connect('changed', self._update)

	def set_page(self, page):
		self.page = page
		self._select(page)
		for button in reversed(self.get_scrolled_children()):
			if button.zim_path == page:
				self.scroll_to_child(button)
				break

	def _update(self, *a):
		for button in self.get_scrolled_children():
			self.remove(button)

		paths = list(self.get_paths())
		for path, label in zip(paths, shortest_unique_names(paths)):
			button = Gtk.ToggleButton(label=label, use_underline=False)
			button.set_tooltip_text(path.name)
			button.get_child().set_ellipsize(Pango.EllipsizeMode.MIDDLE)
			button.zim_path = path
			button.connect('clicked', self.on_button_clicked)
			button.connect('popup-menu', self.on_button_popup_menu)
			button.connect('button-release-event', self.on_button_release_event)
			button.connect('drag-data-get', self.on_drag_data_get)
			button.drag_source_set(
				Gdk.ModifierType.BUTTON1_MASK,
				(Gtk.TargetEntry.new(*INTERNAL_PAGELIST_TARGET),),
				Gdk.DragAction.LINK
			)
			button.show_all()
			self.add(button)

		if self.page is not None:
			self._select(self.page)

	def get_paths(self):
		'''To be implemented by the sub class, should return a list
		(or iterable) of notebook paths to show in the pathbar.
		'''
		raise NotImplemented

	def _select(self, path):
		for button in self.get_scrolled_children():
			active = button.zim_path == path
			if button.get_active() != active:
				button.handler_block_by_func(self.on_button_clicked)
				button.set_active(active)
				label = button.get_child()
				if active:
					label.set_markup('<b>' + encode_markup_text(label.get_text()) + '</b>')
				else:
					label.set_text(label.get_text())
						# get_text() gives string without markup
				button.handler_unblock_by_func(self.on_button_clicked)

	def on_button_clicked(self, button):
		self.navigation.open_page(button.zim_path)

	def on_button_release_event(self, button, event):
		if Gdk.Event.triggers_context_menu(event):
			button.emit('popup-menu') # FIXME do we need to pass x/y and button ?
			return True

	def on_button_popup_menu(self, button):
		menu = self.get_button_popup(button)
		gtk_popup_at_pointer(menu)
		return True

	def get_button_popup(self, button):
		menu = Gtk.Menu()
		uiactions = UIActions(
			self,
			self.notebook,
			button.zim_path,
			self.navigation,
		)
		uiactions.populate_menu_with_actions(PAGE_ACCESS_ACTIONS, menu)
		return menu

	def on_drag_data_get(self, button, context, selectiondata, info, time):
		assert selectiondata.get_target().name() == INTERNAL_PAGELIST_TARGET_NAME
		path = button.zim_path
		logger.debug('Drag data requested from PathBar, we have internal path "%s"', path.name)
		data = pack_urilist((path.name,))
		selectiondata.set(selectiondata.get_target(), 8, data)


class HistoryPathBar(PathBar):

	# Get last X paths from history, add buttons
	# Clicking in the pathbar will always add another entry for that
	# path to the last position

	def get_paths(self):
		paths = list(self.history.get_history())
		paths.reverse()
		return paths

PathBarMainWindowExtension._klasses[PATHBAR_HISTORY] = HistoryPathBar


class RecentPathBar(PathBar):

	# Get last X unique paths from history, add buttons
	# When a button is clicked we do not want to change the view
	# So on open page we need to check if the page was in the list
	# already or not

	def get_paths(self):
		paths = list(self.history.get_recent())
		paths.reverse()
		return paths

PathBarMainWindowExtension._klasses[PATHBAR_RECENT] = RecentPathBar


class RecentChangesPathBar(PathBar):

	def __init__(self, *arg, **kwarg):
		PathBar.__init__(self, *arg, **kwarg)
		self.notebook.connect_after('stored-page', self.on_stored_page)

	def on_stored_page(self, *a):
		self._update()
		current = self.history.get_current()
		if current:
			self._select(current)

	def get_paths(self):
		return reversed(list(
				self.notebook.pages.list_recent_changes(limit=10)))

PathBarMainWindowExtension._klasses[PATHBAR_RECENT_CHANGED] = RecentChangesPathBar


class NamespacePathBar(PathBar):

	# Add buttons for namespace up to and including current page
	# Use history to query for sub-pages to show as well
	# Clicking a button in the pathbar should not change the view

	def get_paths(self):
		# no need to enforce a max number of paths here
		current = self.history.get_current()
		if not current:
			return []
		path = self.history.get_grandchild(current) or current
		paths = list(path.parents())
		paths.reverse()
		paths.pop(0) # remove root
		paths.append(path) # add leaf
		return paths

PathBarMainWindowExtension._klasses[PATHBAR_PATH] = NamespacePathBar


############################
# Allow testing visuals of scrolled box

class TestPath(object):

	def __init__(self, name):
		self.name = name
		self.basename = name


class MockHistory(object):

	def connect(self, *a):
		pass


class MockNavigation(object):

	def open_page(self, *a):
		pass


class TestPathBar(PathBar):

	def __init__(self):
		PathBar.__init__(self, MockHistory(), None, MockNavigation())
		self.set_border_width(5)
		self._update()

	def get_paths(self):
		for path in ('Aaa', 'Bbb', 'Ccccccccc', 'DDDD a looooooongggggggg item here', 'Eeee', 'F', 'GGGGGGGGGG'):
			yield TestPath(path)


if __name__ == '__main__':
	window = Gtk.Window()
	window.connect('destroy', lambda o: Gtk.main_quit())
	vbox = Gtk.VBox()
	window.add(vbox)
	vbox.pack_start(Gtk.Label(label='Default locale:'), False, True, 0)
	vbox.pack_start(TestPathBar(), False, True, 0)
	vbox.pack_start(Gtk.Label(label='LTR (arrows may be switched):'), False, True, 0)
	ltr = TestPathBar()
	ltr.set_direction(Gtk.TextDirection.RTL)
	vbox.pack_start(ltr, False, True, 0)
	window.show_all()
	Gtk.main()
