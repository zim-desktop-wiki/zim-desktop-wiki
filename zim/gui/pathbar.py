# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import gtk
import gobject

from zim.gui.widgets import encode_markup_text


# Constants
DIR_FORWARD = 1
DIR_BACKWARD = -1


class ScrolledHBox(gtk.HBox):
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

	# Actually wanted to inherit from gtk.Box instead of gtk.HBox, but seems
	# we can not call gtk.Box.__init__() to instantiate the object.

	__gsignals__ = {
		'size-request': 'override',
		'size-allocate': 'override',
	}

	initial_scroll_timeout = 300 # timeout before starting scrolling on button press
	scroll_timeout = 150 # timeout between scroll steps

	def __init__(self, spacing=0, homogeneous=False):
		gtk.HBox.__init__(self)
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
		# TODO looks like gtk.widget_push_composite_child is intended
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
		max = len(self.get_children()[2:])-1
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

		if index > max: index = max
		elif index < 0: index = 0

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
				gobject.timeout_add(self.initial_scroll_timeout, self.start_scrolling, direction)
				# indirect recurs
		else:
			self._scroll_timeout = \
				gobject.timeout_add(self.scroll_timeout, self.scroll, direction)

		return False # make sure we are only called once from a timeout

	def stop_scrolling(self):
		'''Stop continues scrolling. Does not do anything if we were not
		scrolling.
		'''
		if not self._scroll_timeout is None:
			gobject.source_remove(self._scroll_timeout)
			self._scroll_timeout = None

	def do_size_request(self, requisition):
		# Determine minimum size needed and store it in requisition
		# Minimum size should be enough to render the largest child with
		# scroll buttons on both sides + spacing + border

		child_wh_tuples = [c.size_request() for c in self.get_children()[2:]]
		if child_wh_tuples:
			width = max([c[0] for c in child_wh_tuples])
			height = max([c[1] for c in child_wh_tuples])
		else:
			width = 0
			height = 0

		spacing = self.get_spacing()
		for button in (self._forw_button, self._back_button):
			w, h = button.size_request()
			if h > height:
				height = h
			width += w + spacing

		border = self.get_border_width()
		width += 2 * border
		height += 2 * border

		#~ print "Requesting WxH: %i x %i" % (width, height)
		requisition.height = height
		requisition.width = width

	def do_size_allocate(self, allocation):
		# Assign the available space to the child widgets
		# See discussion of allocation algorithm above

		#~ print "Allocated WxH: %i x %i" % (allocation.width, allocation.height)
		#~ print "At X,Y: %i, %i" % (allocation.x, allocation.y)
		children = self.get_children()[2:]
		if not children:
			return # nothing to render

		direction, index = self._anchor or (DIR_FORWARD, len(children)-1)
		assert 0 <= index <= len(children)
		assert direction in (DIR_FORWARD, DIR_BACKWARD)
			# default (DIR_FORWARD, -1) should show the last item (right most)
			# and starts filling the space backward (to the left)

		spacing = self.get_spacing()
		border = self.get_border_width()

		widths = [c.get_child_requisition()[0] for c in children]
		total = reduce(int.__add__, widths) + len(widths) * spacing + 2 * border
		if total <= allocation.width:
			show_scroll_buttons = False
			first, last = 0, len(children)-1
		else:
			# determine which children to show
			show_scroll_buttons = True
			first, last = index, index
			available = allocation.width - widths[index]
			for button in (self._forw_button, self._back_button):
				available -= button.get_child_requisition()[0] + spacing
			if direction == DIR_FORWARD:
				# fill items from the direction we came from with last scroll
				for i in range(index-1, -1, -1):
					needed = widths[i] + spacing
					if needed > available:
						break
					else:
						first = i
						available -= needed
				# see if there is any space to fill items on the other side
				for i in range(index+1, len(children), 1):
					needed = widths[i] + spacing
					if needed > available:
						break
					else:
						last = i
						available -= needed
			else: # DIR_BACKWARD
				# fill items from the direction we came from with last scroll
				for i in range(index+1, len(children)):
					needed = widths[i] + spacing
					if needed > available:
						break
					else:
						last = i
						available -= needed
				# see if there is any space to fill items on the other side
				for i in range(index-1, -1, -1):
					needed = widths[i] + spacing
					if needed > available:
						break
					else:
						first = i
						available -= needed

		self._first, self._last = first, last

		# Allocate children
		y = allocation.y + border
		h = allocation.height - 2*border
		child_allocation = gtk.gdk.Rectangle(y=y, height=h)
			# y and height are the same for all
		if not self.get_direction() == gtk.TEXT_DIR_RTL:
			# Left to Right
			child_allocation.x = allocation.x + border

			if show_scroll_buttons and first != 0:
				child_allocation.width = self._back_button.get_child_requisition()[0]
				self._back_button.set_child_visible(True)
				self._back_button.size_allocate(child_allocation)
			else:
				self._back_button.set_child_visible(False)

			if show_scroll_buttons:
				# Reserve the space, even if hidden
				child_allocation.x += self._back_button.get_child_requisition()[0] + spacing

			for i in range(first, last+1):
				child_allocation.width = widths[i]
				children[i].set_child_visible(True)
				children[i].size_allocate(child_allocation)
				child_allocation.x += widths[i] + spacing # set x for next child

			if show_scroll_buttons and last != len(children)-1:
				# reset x - there may be space between last button and scroll button
				child_allocation.width = self._forw_button.get_child_requisition()[0]
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
				child_allocation.width = self._back_button.get_child_requisition()[0]
				child_allocation.x -= child_allocation.width
				self._back_button.set_child_visible(True)
				self._back_button.size_allocate(child_allocation)
				child_allocation.x -= spacing
			else:
				self._back_button.set_child_visible(False)
				if show_scroll_buttons:
					# Reserve the space, even if hidden
					child_allocation.x = self._back_button.get_child_requisition()[0] + spacing

			for i in range(first, last+1):
				child_allocation.width = widths[i]
				child_allocation.x -= child_allocation.width
				children[i].set_child_visible(True)
				children[i].size_allocate(child_allocation)
				child_allocation.x -= spacing # set x for next child

			if show_scroll_buttons and last != len(children)-1:
				# reset x - there may be space between last button and scroll button
				child_allocation.width = self._forw_button.get_child_requisition()[0]
				child_allocation.x = allocation.x + border
				self._forw_button.set_child_visible(True)
				self._forw_button.size_allocate(child_allocation)
			else:
				# hide scroll button
				self._forw_button.set_child_visible(False)

		# Hide remaining children
		for child in children[0:first]:
			child.set_child_visible(False)
		for child in children[last+1:]:
			child.set_child_visible(False)

	def do_focus(self, direction):
		# Overrule navigation for <Ctrl><Tab> while leaving
		# navigation with <Left> and <Right> in tact
		# (so do not "sub-navigate" with <Ctrl><Tab>).
		# Otherwise the user has to tab through all buttons before
		# he can tab to the next widget.
		if direction in (gtk.DIR_TAB_FORWARD, gtk.DIR_TAB_BACKWARD) \
		and self.focus_child is not None:
			return False # Let outer container go to next widget
		else:
			return gtk.HBox.do_focus(self, direction)

# Need to register classes defining gobject signals
gobject.type_register(ScrolledHBox)


class ScrollButton(gtk.Button):
	'''Arrow buttons used by ScrolledHBox'''

	def __init__(self, direction):
		gtk.Button.__init__(self)
		self.direction = direction
		if self.get_direction() != gtk.TEXT_DIR_RTL:
			# Left to Right
			if direction == DIR_FORWARD: arrow_dir = gtk.ARROW_RIGHT
			else: arrow_dir = gtk.ARROW_LEFT
		else:
			# Right to Left
			if direction == DIR_FORWARD: arrow_dir = gtk.ARROW_LEFT
			else: arrow_dir = gtk.ARROW_RIGHT

		self.add(gtk.Arrow(arrow_dir, gtk.SHADOW_OUT))
		self.set_relief(gtk.RELIEF_NONE)


class PathBar(ScrolledHBox):
	'''Base class for pathbars in the zim GUI, extends ScrolledHBox for usage
	with a list of ToggleButtons representing zim Path objects'''

	def __init__(self, ui, history=None, spacing=0, homogeneous=False):
		ScrolledHBox.__init__(self, spacing, homogeneous)
		self.ui = ui
		self.history = None
		self._selected = None
		if history:
			self.set_history(history)
		self.ui.connect_after('open-page', self._after_open_page)

	def set_history(self, history):
		self.history = history
		self.history.connect('changed', lambda o: self._update())
		self._update()
		self._select(history.get_current())

	def _after_open_page(self, ui, page, path):
		# Since we connect after open page, update has likely been done
		# already from the history 'changed' signal - if not trigger it here.
		self._select(path)
		if self._selected is None:
			self._update()
			self._select(path)

	def _update(self):
		if self.history is None:
			return

		for button in self.get_children()[2:]:
			self.remove(button)
		self._selected = None

		for path in self.get_paths():
			button = gtk.ToggleButton(label=path.basename)
			button.set_use_underline(False)
			button.zim_path = path
			button.connect('clicked', self.on_button_clicked)
			button.connect('popup-menu', self.on_button_popup_menu)
			button.connect('button-release-event', self.do_button_release_event)
			# TODO Drag n drop support also nice to have
			button.show()
			self.add(button)

		# FIXME tooltips seem not to work - not sure why
		if gtk.gtk_version >= (2, 12, 0):
			for button in self.get_children()[2:]:
				button.set_tooltip_text(button.zim_path.name)
		else:
			tooltips = gtk.Tooltips()
			for button in self.get_children()[2:]:
				tooltips.set_tip(button, button.zim_path.name)

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
				label.set_markup('<b>'+encode_markup_text(label.get_text())+'</b>')
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
		self.ui.open_page(button.zim_path)

	def do_button_release_event(self, button, event):
		'''Handler for button-release-event, triggers popup menu'''
		if event.button == 3:
			button.emit('popup-menu') # FIXME do we need to pass x/y and button ?
			return True

	def on_button_popup_menu(self, button):
		menu = gtk.Menu()
		self.ui.populate_popup('page_popup', menu, button.zim_path)
		menu.popup(None, None, None, 3, 0)
		return True

	def get_selected_path(self):
		'''Returns path currently selected or None'''
		if self._selected:
			return self._selected.zim_path
		else:
			return None

class HistoryPathBar(PathBar):

	# Get last X paths from history, add buttons
	# Clicking in the pathbar will always add another entry for that
	# path to the last position

	def get_paths(self):
		# TODO enforce max number of paths shown
		paths = list(self.history.get_history())
		paths.reverse()
		return paths


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


class RecentChangesPathBar(PathBar):

	def __init__(self, *arg, **kwarg):
		PathBar.__init__(self, *arg, **kwarg)
		self.ui.notebook.connect_after('stored-page', self.on_stored_page)

	def on_stored_page(self, *a):
		self._update()
		current = self.history.get_current()
		if current:
			self._select(current)

	def get_paths(self):
		index = self.ui.notebook.index
		return reversed(list(
			index.list_recent_pages(offset=0, limit=10)))


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


############################

class TestPath(object):

	def __init__(self, name):
		self.name = name
		self.basename = name

class TestPathBar(PathBar):

	def __init__(self):
		PathBar.__init__(self, None, None)
		self.history = 'XXX'
		self._update()

	def get_paths(self):
		for path in ('foo', 'bar', 'baz', 'looooooongggggggg item here', 'dus', 'ja', 'hmm'):
			yield TestPath(path)

if __name__ == '__main__':
	window = gtk.Window()
	window.connect('destroy', lambda o: gtk.main_quit())
	window.add(TestPathBar())
	window.show_all()
	gtk.main()
