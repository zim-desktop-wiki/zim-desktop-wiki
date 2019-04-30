
# Copyright 2008-2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>


from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import Gdk
import logging

from functools import reduce

from zim.plugins import PluginClass
from zim.actions import radio_action, radio_option
from zim.notebook.page import shortest_unique_names

from zim.gui.mainwindow import MainWindowExtension
from zim.gui.widgets import encode_markup_text, gtk_popup_at_pointer
from zim.gui.uiactions import UIActions, PAGE_ACCESS_ACTIONS
from zim.gui.clipboard import \
	INTERNAL_PAGELIST_TARGET_NAME, INTERNAL_PAGELIST_TARGET, \
	pack_urilist


logger = logging.getLogger('zim.gui')


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

	Note that this class does not (yet?) support packing options like
	'expand', 'fill' etc. All child widgets can just be added with 'add()'.

	TODO this class does not yet support homogeneous spacing
	'''

	# In order to display as many items as possible we use the following
	# scrolling algorithm:
	#
	# There is an attribute "anchor" which is a tuple of a direction and the index
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
	# The indices of the first and last visible items are put in the attributes
	# "_first" and "_last". In subsequent scroll actions the new anchor item can be
	# determined based on these indices.Keep in mind that whether the items are rendered
	# left-to-right or right-to-left depends on the current locale. So the first and
	# last items can either be on the left or on the right.
	#
	# Slide buttons are shown unless all children fit in the given space. So
	# the space is calculated either with or without sliders. At the end we
	# check if the sliders are really needed. We choose to hide the slider if
	# it can't be used to scroll more instead of making it insensitive because
	# the arrows do not show very clear when they are sensitive and when not.
	# The space that is freed when a slider is hidden is not recycled because
	# that would pose the risk of clicking on a button when the slider suddenly
	# disappears

	# We also add the two scroll buttons to our child widgets, so when dealing
	# with the widgets that are scrolled one should use "get_children()[2:]".
	# Not sure if there is a cleaner way to do this

	# Actually wanted to inherit from Gtk.Box instead of Gtk.HBox, but seems
	# we can not call GObject.GObject.__init__() to instantiate the object.

	__gsignals__ = {
		'size-allocate': 'override',
	}

	initial_scroll_timeout = 300 # timeout before starting scrolling on button press
	scroll_timeout = 150 # timeout between scroll steps

	def __init__(self, spacing=0, homogeneous=False):
		GObject.GObject.__init__(self)
		self.set_spacing(spacing)
		self.set_homogeneous(homogeneous)
		self._scroll_timeout = None
		self._anchor = None # tuple of (direction, n) - used in allocate
		self._first = None # int for first item - set in allocate
		self._last = None # int for last item - set in allocate
		self._forw_button = ScrollButton(DIR_FORWARD)
		self._back_button = ScrollButton(DIR_BACKWARD)
		for button in (self._forw_button, self._back_button):
			self.add(button)
			button.connect('button-press-event', self._on_button_press)
			button.connect('button-release-event', self._on_button_release)
			button.connect('clicked', self._on_button_clicked)
		# TODO looks like Gtk.widget_push_composite_child is intended
		# to flag internal children versus normal children
		# use this property + define forall to have sane API for these buttons

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

		index = None
		max = len(self.get_children()[2:]) - 1
		if direction == DIR_FORWARD:
			if self._last == max:
				return False
			else:
				index = self._last + n
		elif direction == DIR_BACKWARD:
			if self._first == 0:
				return False
			else:
				index = self._first - n
		else:
			assert False

		if index > max:
			index = max
		elif index < 0:
			index = 0

		self._anchor = (direction, index)
		self.queue_resize()
		return True

	def scroll_to_child(self, child):
		i = self.get_children()[2:].index(child)
		if i < self._first:
			self.scroll(DIR_BACKWARD, self._first - i)
		elif i > self._last:
			self.scroll(DIR_FORWARD, i - self._last)
		else:
			pass # child was visible already

	def start_scrolling(self, direction, initial_timeout=False):
		'''Start continues scrolling. Direction should be either
		DIR_FORWARD or DIR_BACKWARD. If we were scrolling already, stops
		this action before setting new scroll direction.
		'''
		self.stop_scrolling()
		if initial_timeout:
			self._scroll_timeout = \
				GObject.timeout_add(self.initial_scroll_timeout, self.start_scrolling, direction)
				# indirect recurs
		else:
			self._scroll_timeout = \
				GObject.timeout_add(self.scroll_timeout, self.scroll, direction)

		return False # make sure we are only called once from a timeout

	def stop_scrolling(self):
		'''Stop continues scrolling. Does not do anything if we were not
		scrolling.
		'''
		if not self._scroll_timeout is None:
			GObject.source_remove(self._scroll_timeout)
			self._scroll_timeout = None

	def do_get_preferred_width(self):
		w, h = self._old_size_request()
		return w, w

	def do_get_preferred_height(self):
		w, h = self._old_size_request()
		return h, h

	def _old_size_request(self):
		# Determine minimum size needed and store it in requisition
		# Minimum size should be enough to render the largest child with
		# scroll buttons on both sides + spacing + border

		child_requisitions = [c.size_request() for c in self.get_children()[2:]]
		if child_requisitions:
			width = max([c.width for c in child_requisitions])
			height = max([c.height for c in child_requisitions])
		else:
			width = 0
			height = 0

		spacing = self.get_spacing()
		for button in (self._forw_button, self._back_button):
			req = button.size_request()
			if req.height > height:
				height = req.height
			width += req.width + spacing

		border = self.get_border_width()
		width += 2 * border
		height += 2 * border

		#~ print("Requesting WxH: %i x %i" % (width, height))
		return width, height

	def do_size_allocate(self, allocation):
		# Assign the available space to the child widgets
		# See discussion of allocation algorithm above

		#~ print("Allocated WxH: %i x %i" % (allocation.width, allocation.height))
		#~ print("At X,Y: %i, %i" % (allocation.x, allocation.y))

		Gtk.HBox.do_size_allocate(self, allocation)

		children = self.get_children()[2:]
		if not children:
			self._forw_button.set_child_visible(False)
			self._back_button.set_child_visible(False)
			return # nothing to render



		direction, index = self._anchor or (DIR_FORWARD, len(children) - 1)
		assert 0 <= index <= len(children)
		assert direction in (DIR_FORWARD, DIR_BACKWARD)
			# default (DIR_FORWARD, -1) should show the last item (right most)
			# and starts filling the space backward (to the left)

		spacing = self.get_spacing()
		border = self.get_border_width()

		widths = [c.get_child_requisition().width for c in children]
		total = reduce(int.__add__, widths) + len(widths) * spacing + 2 * border
		if total <= allocation.width:
			show_scroll_buttons = False
			first, last = 0, len(children) - 1
		else:
			# determine which children to show
			show_scroll_buttons = True
			first, last = index, index
			available = allocation.width - widths[index]
			for button in (self._forw_button, self._back_button):
				available -= button.get_child_requisition().width + spacing
			if direction == DIR_FORWARD:
				# fill items from the direction we came from with last scroll
				for i in range(index - 1, -1, -1):
					needed = widths[i] + spacing
					if needed > available:
						break
					else:
						first = i
						available -= needed
				# see if there is any space to fill items on the other side
				for i in range(index + 1, len(children), 1):
					needed = widths[i] + spacing
					if needed > available:
						break
					else:
						last = i
						available -= needed
			else: # DIR_BACKWARD
				# fill items from the direction we came from with last scroll
				for i in range(index + 1, len(children)):
					needed = widths[i] + spacing
					if needed > available:
						break
					else:
						last = i
						available -= needed
				# see if there is any space to fill items on the other side
				for i in range(index - 1, -1, -1):
					needed = widths[i] + spacing
					if needed > available:
						break
					else:
						first = i
						available -= needed

		self._first, self._last = first, last

		# Allocate children - y and height are the same for all
		child_allocation = Gdk.Rectangle()
		child_allocation.y = allocation.y + border
		child_allocation.height = allocation.height - 2 * border
		if not self.get_direction() == Gtk.TextDirection.RTL:
			# Left to Right
			child_allocation.x = allocation.x + border

			if show_scroll_buttons and first != 0:
				child_allocation.width = self._back_button.get_child_requisition().width
				self._back_button.set_child_visible(True)
				self._back_button.size_allocate(child_allocation)
			else:
				self._back_button.set_child_visible(False)

			if show_scroll_buttons:
				# Reserve the space, even if hidden
				child_allocation.x += self._back_button.get_child_requisition().width + spacing

			for i in range(first, last + 1):
				child_allocation.width = widths[i]
				children[i].set_child_visible(True)
				children[i].size_allocate(child_allocation)
				child_allocation.x += widths[i] + spacing # set x for next child

			if show_scroll_buttons and last != len(children) - 1:
				# reset x - there may be space between last button and scroll button
				child_allocation.width = self._forw_button.get_child_requisition().width
				child_allocation.x = allocation.x + allocation.width - child_allocation.width - border
				self._forw_button.set_child_visible(True)
				self._forw_button.size_allocate(child_allocation)
			else:
				# hide scroll button
				self._forw_button.set_child_visible(False)
		else:
			# Right to Left
			child_allocation.x = allocation.x + allocation.width - border

			if show_scroll_buttons and first != 0:
				child_allocation.width = self._back_button.get_child_requisition().width
				child_allocation.x -= child_allocation.width
				self._back_button.set_child_visible(True)
				self._back_button.size_allocate(child_allocation)
				child_allocation.x -= spacing
			else:
				self._back_button.set_child_visible(False)
				if show_scroll_buttons:
					# Reserve the space, even if hidden
					child_allocation.x = self._back_button.get_child_requisition().width + spacing

			for i in range(first, last + 1):
				child_allocation.width = widths[i]
				child_allocation.x -= child_allocation.width
				children[i].set_child_visible(True)
				children[i].size_allocate(child_allocation)
				child_allocation.x -= spacing # set x for next child

			if show_scroll_buttons and last != len(children) - 1:
				# reset x - there may be space between last button and scroll button
				child_allocation.width = self._forw_button.get_child_requisition().width
				child_allocation.x = allocation.x + border
				self._forw_button.set_child_visible(True)
				self._forw_button.size_allocate(child_allocation)
			else:
				# hide scroll button
				self._forw_button.set_child_visible(False)

		# Hide remaining children
		for child in children[0:first]:
			child.set_child_visible(False)
		for child in children[last + 1:]:
			child.set_child_visible(False)


class ScrollButton(Gtk.Button):
	'''Arrow buttons used by ScrolledHBox'''

	def __init__(self, direction):
		GObject.GObject.__init__(self)
		self.direction = direction
		if self.get_direction() != Gtk.TextDirection.RTL:
			# Left to Right
			if direction == DIR_FORWARD:
				arrow_dir = Gtk.ArrowType.RIGHT
			else:
				arrow_dir = Gtk.ArrowType.LEFT
		else:
			# Right to Left
			if direction == DIR_FORWARD:
				arrow_dir = Gtk.ArrowType.LEFT
			else:
				arrow_dir = Gtk.ArrowType.RIGHT

		self.add(Gtk.Arrow(arrow_dir, Gtk.ShadowType.OUT))
		self.set_relief(Gtk.ReliefStyle.NONE)


class PathBar(ScrolledHBox):
	'''Base class for pathbars in the zim GUI, extends ScrolledHBox for usage
	with a list of ToggleButtons representing zim Path objects'''

	def __init__(self, history, notebook, navigation, spacing=0, homogeneous=False):
		ScrolledHBox.__init__(self, spacing, homogeneous)
		self.set_name('zim-pathbar')
		self.history = history
		self.notebook = notebook
		self.navigation = navigation
		self._selected = None
		self._update()
		self.history.connect('changed', self.on_history_changed)

	def set_page(self, page):
		self._select(page)
		if self._selected is None: # See if we missed an update
			self._update()
			self._select(page)

	def on_history_changed(self, history):
		self._update()
		self._select(history.get_current())

	def _update(self):
		for button in self.get_children()[2:]:
			self.remove(button)
		self._selected = None

		paths = list(self.get_paths())
		for path, label in zip(paths, shortest_unique_names(paths)):
			button = Gtk.ToggleButton(label=path.basename)
			button.set_use_underline(False)
			button.zim_path = path
			button.connect('clicked', self.on_button_clicked)
			button.connect('popup-menu', self.on_button_popup_menu)
			button.connect('button-release-event', self.do_button_release_event)
			button.connect('drag-data-get', self.on_drag_data_get)
			button.drag_source_set(
				Gdk.ModifierType.BUTTON1_MASK,
				(Gtk.TargetEntry.new(*INTERNAL_PAGELIST_TARGET),),
				Gdk.DragAction.LINK
			)
			button.show()
			self.add(button)

		for button in self.get_children()[2:]:
			button.set_tooltip_text(button.zim_path.name)

	def get_paths(self):
		'''To be implemented by the sub class, should return a list
		(or iterable) of notebook paths to show in the pathbar.
		'''
		raise NotImplemented

	def _select(self, path):
		def set_active(button, active):
			button.handler_block_by_func(self.on_button_clicked)
			button.set_active(active)
			label = button.get_child()
			if active:
				label.set_markup('<b>' + encode_markup_text(label.get_text()) + '</b>')
			else:
				label.set_text(label.get_text())
					# get_text() gives string without markup
			button.handler_unblock_by_func(self.on_button_clicked)

		if not self._selected is None:
			set_active(self._selected, False)

		for button in reversed(self.get_children()[2:]):
			if button.zim_path == path:
				self._selected = button
				break
		else:
			self._selected = None

		if not self._selected is None:
			set_active(self._selected, True)

	def on_button_clicked(self, button):
		self.navigation.open_page(button.zim_path)

	def do_button_release_event(self, button, event):
		'''Handler for button-release-event, triggers popup menu'''
		if event.button == 3:
			button.emit('popup-menu') # FIXME do we need to pass x/y and button ?
			return True

	def on_button_popup_menu(self, button):
		menu = Gtk.Menu()
		uiactions = UIActions(
			self,
			self.notebook,
			button.zim_path,
			self.navigation,
		)
		uiactions.populate_menu_with_actions(PAGE_ACCESS_ACTIONS, menu)
		gtk_popup_at_pointer(menu)
		return True

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
		# TODO enforce max number of paths shown
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
		# TODO enforce max number of paths shown
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


class TestPathBar(PathBar):

	def __init__(self):
		PathBar.__init__(self, MockHistory(), None, None, None)
		self._update()

	def get_paths(self):
		for path in ('foo', 'bar', 'baz', 'looooooongggggggg item here', 'dus', 'ja', 'hmm'):
			yield TestPath(path)


if __name__ == '__main__':
	window = Gtk.Window()
	window.connect('destroy', lambda o: Gtk.main_quit())
	window.add(TestPathBar())
	window.show_all()
	Gtk.main()
