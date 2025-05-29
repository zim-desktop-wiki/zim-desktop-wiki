# Copyright 2008-2023 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from gi.repository import GObject
from gi.repository import Gtk

import re
import weakref
import logging

import zim.formats

from zim.parse.links import url_link_re, match_url_link

from zim.gui.widgets import strip_boolean_result
from zim.gui.clipboard import Clipboard, SelectionClipboard
from zim.gui.insertedobjects import InsertedObjectWidget, POSITION_BEGIN, POSITION_END


from .constants import *
from .objectanchors import LineSeparatorAnchor
from .textbuffer import TextBuffer, increase_list_bullet, is_numbered_bullet_re
from .textbuffer import _is_link_tag, _is_link_tag_without_href # FIXME - remove need to import these, use API instead
from .lists import TextBufferList


logger = logging.getLogger('zim.gui.pageview.textview')


CURSOR_TEXT = Gdk.Cursor.new_from_name(Gdk.Display.get_default(), 'text')
CURSOR_LINK = Gdk.Cursor.new_from_name(Gdk.Display.get_default(), 'pointer')
CURSOR_WIDGET = Gdk.Cursor.new_from_name(Gdk.Display.get_default(), 'default')


# Regexes used for autoformatting
heading_re = re.compile(r'^(={2,7})\s*(.*?)(\s=+)?$')

link_to_page_re = re.compile(r'''(
	  [\w\.\-\(\)]*(?: :[\w\.\-\(\)]{2,} )+ (?: : | \#\w[\w_-]+)?
	| \+\w[\w\.\-\(\)]+(?: :[\w\.\-\(\)]{2,} )* (?: : | \#\w[\w_-]+)?
)$''', re.X | re.U)
	# e.g. namespace:page or +subpage, but not word without ':' or '+'
	#      optionally followed by anchor id
	#      links with only anchor id or page (without ':' or '+') and achor id are matched by 'link_to_anchor_re'

interwiki_re = re.compile(r'\w[\w\+\-\.]+\?\w\S+$', re.U) # name?page, where page can be any url style

file_re = re.compile(r'''(
	  ~/[^/\s]
	| ~[^/\s]*/
	| \.\.?/
	| /[^/\s]
)\S*$''', re.X | re.U) # ~xxx/ or ~name/xxx or ../xxx  or ./xxx  or /xxx

markup_re = [
	# All ending in "$" to match last sequence on end-of-word
	# the group captures the content to keep
	('style-strong', re.compile(r'\*\*(.*)\*\*$')),
	('style-emphasis', re.compile(r'\/\/(.*)\/\/$')),
	('style-mark', re.compile(r'__(.*)__$')),
	('style-code', re.compile(r'\'\'(.*)\'\'$')),
	('style-strike', re.compile(r'~~(.*)~~$')),
	('style-sup', re.compile(r'(?<=\w)\^\{(\S*)}$')),
	('style-sup', re.compile(r'(?<=\w)\^(\S*)$')),
	('style-sub', re.compile(r'(?<=\w)_\{(\S*)}$')),
]

link_to_anchor_re = re.compile(r'^([\w\.\-\(\)]*#\w[\w_-]+)$', re.U) # before the "#" can be a page name, needs to match logic in 'link_to_page_re'

anchor_re = re.compile(r'^(##\w[\w_-]+)$', re.U)

tag_re = re.compile(r'^(@\w+)$', re.U)

twoletter_re = re.compile(r'[^\W\d]{2}', re.U) # match letters but not numbers - not non-alphanumeric and not number


def camelcase(word):
	# To be CamelCase, a word needs to start uppercase, followed
	# by at least one lower case, followed by at least one uppercase.
	# As a result:
	# - CamelCase needs at least 3 characters
	# - first char needs to be upper case
	# - remainder of the text needs to be mixed case
	if len(word) < 3 \
	or not str.isalpha(word) \
	or not str.isupper(word[0]) \
	or str.islower(word[1:]) \
	or str.isupper(word[1:]):
		return False

	# Now do detailed check and check indeed lower case followed by
	# upper case and exclude e.g. "AAbb"
	# Also check that check that string does not contain letters that
	# are neither upper or lower case (e.g. some Arabic letters)
	upper = list(map(str.isupper, word))
	lower = list(map(str.islower, word))
	if not all(upper[i] or lower[i] for i in range(len(word))):
		return False

	count = 0
	for i in range(1, len(word)):
		if not upper[i - 1] and upper[i]:
			return True
	else:
		return False


class TextView(Gtk.TextView):
	'''Widget to display a L{TextBuffer} with page content. Implements
	zim specific behavior like additional key bindings, on-mouse-over
	signals for links, and the custom popup menu.

	@ivar preferences: dict with preferences

	@signal: C{link-clicked (link)}: Emitted when the user clicks a link
	@signal: C{link-enter (link)}: Emitted when the mouse pointer enters a link
	@signal: C{link-leave (link)}: Emitted when the mouse pointer leaves a link
	@signal: C{end-of-word (start, end, word, char, editmode)}:
	Emitted when the user typed a character like space that ends a word

	  - C{start}: a C{Gtk.TextIter} for the start of the word
	  - C{end}: a C{Gtk.TextIter} for the end of the word
	  - C{word}: the word as string
	  - C{char}: the character that caused the signal (a space, tab, etc.)
	  - C{editmode}: a list of constants for the formatting being in effect,
	    e.g. C{VERBATIM}

	Plugins that want to add auto-formatting logic can connect to this
	signal. If the handler matches the word it should stop the signal
	with C{stop_emission()} to prevent other hooks from formatting the
	same word.

	@signal: C{end-of-line (end)}: Emitted when the user typed a newline
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		# New signals
		'link-clicked': (GObject.SignalFlags.RUN_LAST, None, (object,)),
		'link-enter': (GObject.SignalFlags.RUN_LAST, None, (object,)),
		'link-leave': (GObject.SignalFlags.RUN_LAST, None, (object,)),
		'end-of-word': (GObject.SignalFlags.RUN_LAST, None, (object, object, object, object, object)),
		'end-of-line': (GObject.SignalFlags.RUN_LAST, None, (object,)),
	}

	def __init__(self, preferences):
		'''Constructor

		@param preferences: dict with preferences

		@todo: make sure code sets proper defaults for preferences
		& document preferences used
		'''
		GObject.GObject.__init__(self)
		self.set_buffer(TextBuffer(None, None))
		self.set_name('zim-pageview')
		self.set_size_request(24, 24)
		self._cursor = CURSOR_TEXT
		self._cursor_link = None
		self._object_widgets = weakref.WeakSet()
		self.set_left_margin(10)
		self.set_right_margin(5)
		self.set_wrap_mode(Gtk.WrapMode.WORD)
		self.preferences = preferences

		self._object_wrap_width = -1
		self.connect_after('size-allocate', self.__class__.on_size_allocate)
		self.connect_after('motion-notify-event', self.__class__.on_motion_notify_event)

		# Tooltips for images
		self.props.has_tooltip = True
		self.connect("query-tooltip", self.on_query_tooltip)

	def set_buffer(self, buffer):
		# Clear old widgets
		for child in self.get_children():
			if isinstance(child, InsertedObjectWidget):
				self._object_widgets.remove(child)
				self.remove(child)

		# Set new buffer
		Gtk.TextView.set_buffer(self, buffer)

		# Connect new widgets
		for iter, anchor in buffer.list_objectanchors():
			self.on_insert_object(buffer, anchor)

		buffer.connect('insert-objectanchor', self.on_insert_object)

	def on_insert_object(self, buffer, anchor):
		# Connect widget for this view to object
		widget = anchor.create_widget()
		assert isinstance(widget, InsertedObjectWidget)

		def on_release_cursor(widget, position, anchor):
			myiter = buffer.get_iter_at_child_anchor(anchor)
			if position == POSITION_END:
				myiter.forward_char()
			buffer.place_cursor(myiter)
			self.grab_focus()

		widget.connect('release-cursor', on_release_cursor, anchor)

		def widget_connect(signal):
			widget.connect(signal, lambda o, *a: self.emit(signal, *a))

		for signal in ('link-clicked', 'link-enter', 'link-leave'):
			widget_connect(signal)

		widget.set_textview_wrap_width(self._object_wrap_width)
			# TODO - compute indenting

		self.add_child_at_anchor(widget, anchor)
		self._object_widgets.add(widget)
		widget.show_all()

	def on_size_allocate(self, *a):
		# Update size request for widgets
		wrap_width = self._get_object_wrap_width()
		if wrap_width != self._object_wrap_width:
			for widget in self._object_widgets:
				widget.set_textview_wrap_width(wrap_width)
					# TODO - compute indenting
			self._object_wrap_width = wrap_width

	def _get_object_wrap_width(self):
		text_window = self.get_window(Gtk.TextWindowType.TEXT)
		if text_window:
			width = text_window.get_geometry()[2]
			hmargin = self.get_left_margin() + self.get_right_margin() + 5
				# the +5 is arbitrary, but without it we show a scrollbar anyway ..
			return width - hmargin
		else:
			return -1

	def do_copy_clipboard(self, format=None):
		# Overriden to force usage of our Textbuffer.copy_clipboard
		# over Gtk.TextBuffer.copy_clipboard
		format = format or self.preferences['copy_format']
		format = zim.formats.canonical_name(format)
		self.get_buffer().copy_clipboard(Clipboard, format)

	def do_cut_clipboard(self):
		# Overriden to force usage of our Textbuffer.cut_clipboard
		# over Gtk.TextBuffer.cut_clipboard
		self.get_buffer().cut_clipboard(Clipboard, self.get_editable())
		self.scroll_mark_onscreen(self.get_buffer().get_insert())

	def do_paste_clipboard(self, format=None):
		# Overriden to force usage of our Textbuffer.paste_clipboard
		# over Gtk.TextBuffer.paste_clipboard
		self.get_buffer().paste_clipboard(Clipboard, None, self.get_editable(), text_format=format)
		self.scroll_mark_onscreen(self.get_buffer().get_insert())

	#~ def do_drag_motion(self, context, *a):
		#~ # Method that echos drag data types - only enable for debugging
		#~ print context.targets

	def on_motion_notify_event(self, event):
		# Update the cursor type when the mouse moves
		x, y = event.get_coords()
		x, y = int(x), int(y) # avoid some strange DeprecationWarning
		coords = self.window_to_buffer_coords(Gtk.TextWindowType.TEXT, x, y)
		self.update_cursor(coords)

	def do_visibility_notify_event(self, event):
		# Update the cursor type when the window visibility changed
		self.update_cursor()
		return False # continue emit

	def do_move_cursor(self, step_size, count, extend_selection):
		# Overloaded signal handler for cursor movements which will
		# move cursor into any object that accept a cursor focus

		if step_size in (Gtk.MovementStep.LOGICAL_POSITIONS, Gtk.MovementStep.VISUAL_POSITIONS) \
		and count in (1, -1) and not extend_selection:
			# logic below only supports 1 char forward or 1 char backward movements

			buffer = self.get_buffer()
			iter = buffer.get_iter_at_mark(buffer.get_insert())
			if count == -1:
				iter.backward_char()
				position = POSITION_END # enter end of object
			else:
				position = POSITION_BEGIN

			anchor = iter.get_child_anchor()
			if iter.get_child_anchor():
				for widget in anchor.get_widgets():
					if widget.is_ancestor(self) and widget.has_cursor():
						widget.grab_cursor(position)
						return None

		return Gtk.TextView.do_move_cursor(self, step_size, count, extend_selection)

	def do_button_press_event(self, event):
		# Handle middle click for pasting and right click for context menu
		# Needed to override these because implementation details of
		# gtktextview.c do not use proper signals for these actions.
		#
		# Note that clicking links is in button-release to avoid
		# conflict with making selections
		buffer = self.get_buffer()

		if event.type == Gdk.EventType.BUTTON_PRESS:
			iter, coords = self._get_pointer_location()
			if event.button == 2 and iter and not buffer.get_has_selection():
				buffer.paste_clipboard(SelectionClipboard, iter, self.get_editable())
				return False
			elif Gdk.Event.triggers_context_menu(event):
				self._set_popup_menu_mark(iter) # allow iter to be None

		return Gtk.TextView.do_button_press_event(self, event)

	def do_button_release_event(self, event):
		# Handle clicking a link or checkbox
		cont = Gtk.TextView.do_button_release_event(self, event)
		if not self.get_buffer().get_has_selection():
			if self.get_editable():
				if event.button == 1:
					if self.preferences['cycle_checkbox_type']:
						# Cycle through all states - more useful for
						# single click input devices
						self.click_link() or self.click_checkbox() or self.click_anchor()
					else:
						self.click_link() or self.click_checkbox(CHECKED_BOX) or self.click_anchor()
			elif event.button == 1:
				# no changing checkboxes for read-only content
				self.click_link()

		return cont # continue emit ?

	def do_popup_menu(self):
		# Handler that gets called when user activates the popup-menu
		# by a keybinding (Shift-F10 or "menu" key).
		# Due to implementation details in gtktextview.c this method is
		# not called when a popup is triggered by a mouse click.
		buffer = self.get_buffer()
		iter = buffer.get_iter_at_mark(buffer.get_insert())
		self._set_popup_menu_mark(iter)
		return Gtk.TextView.do_popup_menu(self)

	def get_popup(self):
		'''Get the popup menu - intended for testing'''
		buffer = self.get_buffer()
		iter = buffer.get_iter_at_mark(buffer.get_insert())
		self._set_popup_menu_mark(iter)
		menu = Gtk.Menu()
		self.emit('populate-popup', menu)
		return menu

	def _set_popup_menu_mark(self, iter):
		# If iter is None, remove the mark
		buffer = self.get_buffer()
		mark = buffer.get_mark('zim-popup-menu')
		if iter:
			if mark:
				buffer.move_mark(mark, iter)
			else:
				mark = buffer.create_mark('zim-popup-menu', iter, True)
		elif mark:
			buffer.delete_mark(mark)
		else:
			pass

	def _get_popup_menu_mark(self):
		buffer = self.get_buffer()
		mark = buffer.get_mark('zim-popup-menu')
		return buffer.get_iter_at_mark(mark) if mark else None

	def do_key_press_event(self, event):
		keyval = strip_boolean_result(event.get_keyval())
		#print 'KEY %s (%r)' % (Gdk.keyval_name(keyval), keyval)
		event_state = event.get_state()
		#print 'STATE %s' % event_state

		run_post, handled = self._do_key_press_event(keyval, event_state)
		if not handled:
			handled = Gtk.TextView.do_key_press_event(self, event)

		if run_post and handled:
			self._post_key_press_event(keyval)

		return handled

	def test_key_press_event(self, keyval, event_state=0):
		run_post, handled = self._do_key_press_event(keyval, event_state)

		if not handled:
			if keyval in KEYVALS_BACKSPACE:
				self.emit('backspace')
			else:
				if keyval in KEYVALS_ENTER:
					char = '\n'
				elif keyval in KEYVALS_TAB:
					char = '\t'
				else:
					char = chr(Gdk.keyval_to_unicode(keyval))

				self.emit('insert-at-cursor', char)
			handled = True

		if run_post and handled:
			self._post_key_press_event(keyval)

		return handled

	def _do_key_press_event(self, keyval, event_state):
		buffer = self.get_buffer()
		if not self.get_editable():
			# Dispatch read-only mode
			return False, self._do_key_press_event_readonly(keyval, event_state)
		elif buffer.get_has_selection():
			# Dispatch selection mode
			return False, self._do_key_press_event_selection(keyval, event_state)
		else:
			return True, self._do_key_press_event_default(keyval, event_state)

	def _do_key_press_event_default(self, keyval, event_state):
		buffer = self.get_buffer()
		if (keyval in KEYVALS_HOME
		and not event_state & Gdk.ModifierType.CONTROL_MASK):
			# Smart Home key - can be combined with shift state
			insert = buffer.get_iter_at_mark(buffer.get_insert())
			home, ourhome = self.get_visual_home_positions(insert)
			if insert.equal(ourhome):
				iter = home
			else:
				iter = ourhome
			if event_state & Gdk.ModifierType.SHIFT_MASK:
				buffer.move_mark_by_name('insert', iter)
			else:
				buffer.place_cursor(iter)
			return True
		elif keyval in KEYVALS_TAB and not (event_state & KEYSTATES):
			# Tab at start of line indents
			iter = buffer.get_insert_iter()
			home, ourhome = self.get_visual_home_positions(iter)
			if home.starts_line() and iter.compare(ourhome) < 1 \
			and not buffer.get_iter_in_verbatim_block(iter):
				buffer.emit('undo-save-cursor', iter)
				row, mylist = TextBufferList.new_from_line(buffer, iter.get_line())
				if mylist and self.preferences['recursive_indentlist']:
					mylist.indent(row)
				else:
					buffer.indent(iter.get_line(), interactive=True)
				return True
		elif (keyval in KEYVALS_LEFT_TAB
			and not (event_state & KEYSTATES & ~Gdk.ModifierType.SHIFT_MASK)
		) or (keyval in KEYVALS_BACKSPACE
			and self.preferences['unindent_on_backspace']
			and not (event_state & KEYSTATES)
		):
			# Backspace or Ctrl-Tab unindents line
			# note that Shift-Tab give Left_Tab + Shift mask, so allow shift
			default = True if keyval in KEYVALS_LEFT_TAB else False
				# Prevent <Shift><Tab> to insert a Tab if unindent fails
			iter = buffer.get_iter_at_mark(buffer.get_insert())
			home, ourhome = self.get_visual_home_positions(iter)
			if home.starts_line() and iter.compare(ourhome) < 1 \
			and not buffer.get_iter_in_verbatim_block(iter):
				buffer.emit('undo-save-cursor', iter)
				bullet = buffer.get_bullet_at_iter(home)
				indent = buffer.get_indent(home.get_line())
				if keyval in KEYVALS_BACKSPACE \
				and bullet and indent == 0 and not iter.equal(home):
					# Delete bullet at start of line (if iter not before bullet)
					buffer.delete(home, ourhome)
					return True
				elif indent == 0 or indent is None:
					# Nothing to unindent
					return default
				elif bullet:
					# Unindent list maybe recursive
					row, mylist = TextBufferList.new_from_line(buffer, iter.get_line())
					if mylist and self.preferences['recursive_indentlist']:
						return bool(mylist.unindent(row)) or default
					else:
						return bool(buffer.unindent(iter.get_line(), interactive=True)) or default
				else:
					# Unindent normal text
					return bool(buffer.unindent(iter.get_line(), interactive=True)) or default

		elif keyval in KEYVALS_ENTER:
			# Enter can trigger links
			iter = buffer.get_iter_at_mark(buffer.get_insert())
			tag = buffer.get_link_tag(iter)
			if tag and not iter.begins_tag(tag):
				# get_link_tag() is left gravitating, we additionally
				# exclude the position in front of the link.
				# As a result you can not "Enter" a 1 character link,
				# this is by design.
				if (self.preferences['follow_on_enter']
				or event_state & Gdk.ModifierType.MOD1_MASK): # MOD1 == Alt
					self.click_link_at_iter(iter)
				# else do not insert newline, just ignore
				return True

	def _post_key_press_event(self, keyval):
		# Trigger end-of-line and/or end-of-word signals if char was
		# really inserted by parent class.
		#
		# We do it this way because in some cases e.g. a space is not
		# inserted but is used to select an option in an input mode e.g.
		# to select between various Chinese characters. See lp:460438

		if not (keyval in KEYVALS_END_OF_WORD or keyval in KEYVALS_ENTER):
			return

		buffer = self.get_buffer()
		insert = buffer.get_iter_at_mark(buffer.get_insert())
		mark = buffer.create_mark(None, insert, left_gravity=False)
		iter = insert.copy()
		iter.backward_char()

		if keyval in KEYVALS_ENTER:
			char = '\n'
		elif keyval in KEYVALS_TAB:
			char = '\t'
		else:
			char = chr(Gdk.keyval_to_unicode(keyval))

		if iter.get_text(insert) != char:
			return

		with buffer.user_action:
			buffer.emit('undo-save-cursor', insert)
			start = iter.copy()
			if buffer.iter_backward_word_start(start):
				word = start.get_text(iter)
				editmode = [t.zim_tag for t in buffer.iter_get_zim_tags(iter)]
				self.emit('end-of-word', start, iter, word, char, editmode)

			if keyval in KEYVALS_ENTER:
				# iter may be invalid by now because of end-of-word
				iter = buffer.get_iter_at_mark(mark)
				iter.backward_char()
				self.emit('end-of-line', iter)

		buffer.place_cursor(buffer.get_iter_at_mark(mark))
		self.scroll_mark_onscreen(mark)
		buffer.delete_mark(mark)

	def _do_key_press_event_readonly(self, keyval, event_state):
		# Key bindings in read-only mode:
		#   Space scrolls one page
		#   Shift-Space scrolls one page up
		if keyval in KEYVALS_SPACE:
			if event_state & Gdk.ModifierType.SHIFT_MASK:
				i = -1
			else:
				i = 1
			self.emit('move-cursor', Gtk.MovementStep.PAGES, i, False)
			return True
		else:
			return False

	def _do_key_press_event_selection(self, keyval, event_state):
		# Key bindings when there is an active selections:
		#   Tab indents whole selection
		#   Shift-Tab and optionally Backspace unindent whole selection
		#   * Turns whole selection in bullet list, or toggle back
		#   > Quotes whole selection with '>'
		handled = True
		buffer = self.get_buffer()

		def delete_char(line):
			# Deletes the character at the iterator position
			iter = buffer.get_iter_at_line(line)
			next = iter.copy()
			if next.forward_char():
				buffer.delete(iter, next)

		def decrement_indent(start, end):
			# Check if inside verbatim block AND entire selection without tag toggle
			if buffer.get_range_in_verbatim_block(start, end):
				# Handle indent in pre differently
				missing_tabs = []
				check_tab = lambda l: (buffer.get_iter_at_line(l).get_char() == '\t') or missing_tabs.append(1)
				buffer.foreach_line_in_selection(check_tab)
				if len(missing_tabs) == 0:
					return buffer.foreach_line_in_selection(delete_char)
				else:
					return False
			elif multi_line_indent(start, end):
				level = []
				buffer.foreach_line_in_selection(
					lambda l: level.append(buffer.get_indent(l)))
				if level and min(level) > 0:
					# All lines have some indent
					return buffer.foreach_line_in_selection(buffer.unindent)
				else:
					return False
			else:
				return False

		def multi_line_indent(start, end):
			# Check if:
			# a) one line selected from start till end or
			# b) multiple lines selected and selection starts at line start
			home, ourhome = self.get_visual_home_positions(start)
			if not (home.starts_line() and start.compare(ourhome) < 1):
				return False
			else:
				return end.ends_line() \
				or end.get_line() > start.get_line()

		start, end = buffer.get_selection_bounds()
		with buffer.user_action:
			if keyval in KEYVALS_TAB:
				if buffer.get_range_in_verbatim_block(start, end):
					# Handle indent in pre differently
					prepend_tab = lambda l: buffer.insert(buffer.get_iter_at_line(l), '\t')
					buffer.foreach_line_in_selection(prepend_tab)
				elif multi_line_indent(start, end):
					buffer.foreach_line_in_selection(buffer.indent)
				else:
					handled = False
			elif keyval in KEYVALS_LEFT_TAB:
				decrement_indent(start, end)
					# do not set handled = False when decrement failed -
					# LEFT_TAB should not do anything else
			elif keyval in KEYVALS_BACKSPACE \
			and self.preferences['unindent_on_backspace']:
				handled = decrement_indent(start, end)
			elif keyval in KEYVALS_ASTERISK + (KEYVAL_POUND,):
				def toggle_bullet(line, newbullet):
					bullet = buffer.get_bullet(line)
					if not bullet:
						buffer.set_bullet(line, newbullet)
					elif bullet == newbullet: # FIXME broken for numbered list
						buffer.set_bullet(line, None)
				if keyval == KEYVAL_POUND:
					buffer.foreach_line_in_selection(toggle_bullet, NUMBER_BULLET, skip_empty_lines=True)
				else:
					buffer.foreach_line_in_selection(toggle_bullet, BULLET, skip_empty_lines=True)
			elif keyval in KEYVALS_GT \
			and multi_line_indent(start, end):
				def email_quote(line):
					iter = buffer.get_iter_at_line(line)
					bound = iter.copy()
					bound.forward_char()
					if iter.get_text(bound) == '>':
						buffer.insert(iter, '>')
					else:
						buffer.insert(iter, '> ')
				buffer.foreach_line_in_selection(email_quote)
			else:
				handled = False

		return handled

	def _get_pointer_location(self):
		'''Get an iter and coordinates for the mouse pointer

		@returns: a 2-tuple of a C{Gtk.TextIter} and a C{(x, y)}
		tupple with coordinates for the mouse pointer.
		'''
		x, y = self.get_pointer()
		x, y = self.window_to_buffer_coords(Gtk.TextWindowType.TEXT, x, y)
		iter = strip_boolean_result(self.get_iter_at_location(x, y))
		return iter, (x, y)

	def _get_pixbuf_at_pointer(self, iter, coords):
		'''Returns the pixbuf that is under the mouse or C{None}. The
		parameters should be the TextIter and the (x, y) coordinates
		from L{_get_pointer_location()}. This method handles the special
		case where the pointer it on an iter next to the image but the
		mouse is visible above the image.
		'''
		pixbuf = iter.get_pixbuf()
		if not pixbuf:
			# right side of pixbuf will map to next iter
			iter = iter.copy()
			iter.backward_char()
			pixbuf = iter.get_pixbuf()

		if pixbuf and hasattr(pixbuf, 'zim_type'):
			# If we have a pixbuf double check the cursor is really
			# over the image and not actually on the next cursor position
			area = self.get_iter_location(iter)
			if (coords[0] >= area.x and coords[0] <= area.x + area.width
				and coords[1] >= area.y and coords[1] <= area.y + area.height):
				return pixbuf
			else:
				return None
		else:
			return None

	def update_cursor(self, coords=None):
		'''Update the mouse cursor type

		E.g. set a "hand" cursor when hovering over a link.

		@param coords: a tuple with C{(x, y)} position in buffer coords.
		Only give this argument if coords are known from an event,
		otherwise the current cursor position is used.

		@emits: link-enter
		@emits: link-leave
		'''
		if coords is None:
			iter, coords = self._get_pointer_location()
		else:
			iter = strip_boolean_result(self.get_iter_at_location(*coords))

		if iter is None:
			self._set_cursor(CURSOR_TEXT)
		else:
			pixbuf = self._get_pixbuf_at_pointer(iter, coords)
			if pixbuf:
				if pixbuf.zim_type == 'icon' and pixbuf.zim_attrib['stock'] in BULLETS_FROM_STOCK:
					self._set_cursor(CURSOR_WIDGET)
				elif pixbuf.zim_type == 'anchor':
					self._set_cursor(CURSOR_WIDGET)
				elif 'href' in pixbuf.zim_attrib:
					self._set_cursor(CURSOR_LINK, link={'href': pixbuf.zim_attrib['href']})
				else:
					self._set_cursor(CURSOR_TEXT)
			else:
				link = self.get_buffer().get_link_data(iter)
				if link:
					self._set_cursor(CURSOR_LINK, link=link)
				else:
					self._set_cursor(CURSOR_TEXT)

	def _set_cursor(self, cursor, link=None):
		if cursor != self._cursor:
			window = self.get_window(Gtk.TextWindowType.TEXT)
			window.set_cursor(cursor)

		# Check if we need to emit any events for hovering
		if self._cursor == CURSOR_LINK: # was over link before
			if cursor == CURSOR_LINK: # still over link
				if link != self._cursor_link:
					# but other link
					self.emit('link-leave', self._cursor_link)
					self.emit('link-enter', link)
			else:
				self.emit('link-leave', self._cursor_link)
		elif cursor == CURSOR_LINK: # was not over link, but is now
			self.emit('link-enter', link)

		self._cursor = cursor
		self._cursor_link = link

	def click_link(self):
		'''Activate the link under the mouse pointer, if any

		@emits: link-clicked
		@returns: C{True} when there was indeed a link
		'''
		iter, coords = self._get_pointer_location()
		if iter is None:
			return False

		pixbuf = self._get_pixbuf_at_pointer(iter, coords)
		if pixbuf and pixbuf.zim_attrib.get('href'):
			self.emit('link-clicked', {'href': pixbuf.zim_attrib['href']})
			return True
		elif iter:
			return self.click_link_at_iter(iter)

	def click_link_at_iter(self, iter):
		'''Activate the link at C{iter}, if any

		Like L{click_link()} but activates a link at a specific text
		iter location

		@emits: link-clicked
		@param iter: a C{Gtk.TextIter}
		@returns: C{True} when there was indeed a link
		'''
		link = self.get_buffer().get_link_data(iter)
		if link:
			self.emit('link-clicked', link)
			return True
		else:
			return False

	def click_checkbox(self, checkbox_type=None):
		'''Toggle the checkbox under the mouse pointer, if any

		@param checkbox_type: the checkbox type to toggle between, see
		L{TextBuffer.toggle_checkbox()} for details.
		@returns: C{True} for success, C{False} if no checkbox was found.
		'''
		iter, coords = self._get_pointer_location()
		if iter and iter.get_line_offset() < 2:
			# Only position 0 or 1 can map to a checkbox
			buffer = self.get_buffer()
			recurs = self.preferences['recursive_checklist']
			return buffer.toggle_checkbox(iter.get_line(), checkbox_type, recurs)
		else:
			return False

	def click_anchor(self):
		'''Show popover for anchor under the cursor'''
		iter, coords = self._get_pointer_location()
		if not iter:
			return False

		pixbuf = self._get_pixbuf_at_pointer(iter, coords)
		if not (pixbuf and hasattr(pixbuf, 'zim_type') and pixbuf.zim_type == 'anchor'):
			return False

		# Show popover with achor name and option to copy link
		popover = Gtk.Popover()
		popover.set_relative_to(self)
		rect = Gdk.Rectangle()
		rect.x, rect.y = self.get_pointer()
		rect.width, rect.height = 1, 1
		popover.set_pointing_to(rect)

		name =  pixbuf.zim_attrib['name']
		def _copy_link_to_anchor(o):
			buffer = self.get_buffer()
			notebook, page = buffer.notebook, buffer.page
			Clipboard.set_pagelink(notebook, page, name)
			SelectionClipboard.set_pagelink(notebook, page, name)
			popover.popdown()

		hbox = Gtk.Box(Gtk.Orientation.HORIZONTAL, 12)
		hbox.set_border_width(3)
		label = Gtk.Label()
		label.set_markup('#%s' %name)
		hbox.add(label)
		button = Gtk.Button.new_from_icon_name('edit-copy-symbolic', Gtk.IconSize.BUTTON)
		button.set_tooltip_text(_("Copy link to clipboard")) # T: tooltip for button in anchor popover
		button.connect('clicked', _copy_link_to_anchor)
		hbox.add(button)
		popover.add(hbox)
		popover.show_all()
		popover.popup()

		return True

	def get_visual_home_positions(self, iter):
		'''Get the TextIters for the visuale start of the line

		@param iter: a C{Gtk.TextIter}
		@returns: a 2-tuple with two C{Gtk.TextIter}

		The first iter is the start of the visual line - which can be
		the start of the line as the buffer sees it (which is also called
		the paragraph start in the view) or the iter at the place where
		the line is wrapped. The second iter is the start of the line
		after skipping any bullets and whitespace. For a wrapped line
		the second iter will be the same as the first.
		'''
		home = iter.copy()
		if not self.starts_display_line(home):
			self.backward_display_line_start(home)

		if home.starts_line():
			ourhome = home.copy()
			self.get_buffer().iter_forward_past_bullet(ourhome)
			bound = ourhome.copy()
			bound.forward_char()
			while ourhome.get_text(bound) in (' ', '\t'):
				if ourhome.forward_char():
					bound.forward_char()
				else:
					break
			return home, ourhome
		else:
			# only start visual line, not start of real line
			return home, home.copy()

	def do_end_of_word(self, start, end, word, char, editmode):
		# Default handler with built-in auto-formatting options
		buffer = self.get_buffer()
		non_nesting_tags = buffer.get_range_has_non_nesting_formatting(start, end)
		handled = False
		#print('WORD >>%s<< CHAR >>%s<< %r' % (word, char, non_nesting_tags))
		def apply_anchor(match):
			#print("ANCHOR >>%s<<" % word)
			if non_nesting_tags:
				return False
			name = match[2:]
			buffer.delete(start, end)
			buffer.insert_anchor(start, name)
			return True

		def apply_tag(match):
			#print("TAG >>%s<<" % word)
			start = end.copy()
			if not start.backward_chars(len(match)):
				return False
			elif non_nesting_tags:
				return False
			else:
				tag = buffer._create_tag_tag(match)
				buffer.apply_tag(tag, start, end)
				return True

		def apply_link(match, exclude_end=0):
			#print("LINK >>%s<<" % word)
			myend = end.copy()
			myend.backward_chars(exclude_end)
			start = myend.copy()
			if not start.backward_chars(len(match)):
				return False
			elif buffer.get_range_has_non_nesting_formatting(start, myend):
				return False # These do not allow overlap with link formatting
			elif buffer.range_has_tags(_is_link_tag, start, myend):
				if exclude_end > 0:
					# Force excluding end of match, even if already formatted as
					# a link - used to exclude trailing punctuation from a URL
					# link.
					buffer.smart_remove_tags(_is_link_tag, myend, end)
					return True
				else:
					return False # No link inside a link
			else:
				tag = buffer._create_link_tag(match, match)
				buffer.apply_tag(tag, start, myend)
				return True

		def allow_bullet(iter, is_replacement_numbered_bullet):
			if iter.starts_line():
				return True
			elif iter.get_line_offset() < 10:
				home = buffer.get_iter_at_line(iter.get_line())
				return buffer.iter_forward_past_bullet(home) \
				and start.equal(iter) \
				and not is_replacement_numbered_bullet # don't replace existing bullets with numbered bullets
			else:
				return False
		word_is_numbered_bullet = is_numbered_bullet_re.match(word)
		if (char == ' ' or char == '\t') \
		and not non_nesting_tags \
		and allow_bullet(start, word_is_numbered_bullet) \
		and (word in AUTOFORMAT_BULLETS or word_is_numbered_bullet):
			line = start.get_line()
			if buffer.get_line_is_heading(line):
				handled = False # No bullets in headings
			else:
				# format bullet and checkboxes
				end.forward_char() # also overwrite the space triggering the action
				buffer.delete(start, end)
				bullet = AUTOFORMAT_BULLETS.get(word) or word
				buffer.set_bullet(line, bullet) # takes care of replacing bullets as well
				handled = True
		elif tag_re.match(word):
			m = tag_re.match(word)
			handled = apply_tag(m.group(0))
		elif self.preferences['autolink_anchor'] and anchor_re.match(word):
			m = anchor_re.match(word)
			handled = apply_anchor(m.group(0))
		elif url_link_re.search(word):
			if char == ')':
				handled = False # to early to call
			else:
				m = url_link_re.search(word)
				url = match_url_link(m.group(0))
				tail = word[m.start()+len(url):]
				handled = apply_link(url, exclude_end=len(tail))
		elif self.preferences['autolink_anchor'] and link_to_anchor_re.match(word) and word.startswith('#'):
				handled = apply_link(word)
		elif self.preferences['autolink_page'] and \
				(link_to_page_re.match(word) or (link_to_anchor_re.match(word) and not word.startswith('#'))):
					# Do not link "10:20h", "10:20PM" etc. so check two letters before first ":"
					# these can still be linked with the InsertLinkDialog functionality
					parts = [p for p in word.split(':') if p] # get rid of empty lead element in case of ":Foo"
					if parts and twoletter_re.search(parts[0]):
						handled = apply_link(word)
					else:
						handled = False
		elif self.preferences['autolink_interwiki'] and interwiki_re.match(word):
			handled = apply_link(word)
		elif self.preferences['autolink_files'] and file_re.match(word):
			handled = apply_link(word)
		elif self.preferences['autolink_camelcase'] and camelcase(word):
			handled = apply_link(word)
		elif self.preferences['auto_reformat']:
			linestart = buffer.get_iter_at_line(end.get_line())
			partial_line = linestart.get_slice(end)
			for style, style_re in markup_re:
				m = style_re.search(partial_line)
				if m:
					matchstart = linestart.copy()
					matchstart.forward_chars(m.start())
					matchend = linestart.copy()
					matchend.forward_chars(m.end())
					if buffer.get_range_has_non_nesting_formatting(matchstart, matchend) \
						or buffer.range_has_tags(_is_link_tag_without_href, matchstart, matchend):
							break
					else:
						with buffer.tmp_cursor(matchstart):
							buffer.delete(matchstart, matchend)
							buffer.insert_with_tags_by_name(matchstart, m.group(1), style)
							handled = True
							break

		if handled:
			self.stop_emission('end-of-word')

	def do_end_of_line(self, end):
		# Default handler, takes care of cutting of formatting on the
		# line end, set indenting and bullet items on the new line etc.

		if end.starts_line():
			return # empty line

		buffer = self.get_buffer()
		start = buffer.get_iter_at_line(end.get_line())
		if buffer.get_iter_in_verbatim(start):
			logger.debug('pre-formatted code')
			return # pre-formatted

		line = start.get_text(end)
		#~ print('LINE >>%s<<' % line)
		l = len(line)
		is_hr = (l >= 3) and (line == '-' * l)

		m_head = heading_re.match(line)

		if is_hr:
			with buffer.user_action:
				offset = start.get_offset()
				buffer.delete(start, end)
				iter = buffer.get_iter_at_offset(offset)
				buffer.insert_objectanchor(iter, LineSeparatorAnchor())
		elif m_head:
			level = len(m_head.group(1)) - 1
			heading = m_head.group(2) + '\n'
			end.forward_line()
			mark = buffer.create_mark(None, end)
			buffer.delete(start, end)
			buffer.insert_with_tags_by_name(
				buffer.get_iter_at_mark(mark), heading, 'style-h' + str(level))
			buffer.delete_mark(mark)
		elif buffer.get_bullet_at_iter(start) is not None:
			# we are part of bullet list
			# FIXME should logic be handled by TextBufferList ?
			ourhome = start.copy()
			buffer.iter_forward_past_bullet(ourhome)
			newlinestart = end.copy()
			newlinestart.forward_line()
			if ourhome.equal(end) and newlinestart.ends_line():
				# line with bullet but no text - break list if no text on next line
				line, newline = start.get_line(), newlinestart.get_line()
				buffer.delete(start, end)
				buffer.set_indent(line, None)
				buffer.set_indent(newline, None)
			else:
				# determine indent
				start_sublist = False
				newline = newlinestart.get_line()
				indent = buffer.get_indent(start.get_line())
				nextlinestart = newlinestart.copy()
				if nextlinestart.forward_line() \
				and buffer.get_bullet_at_iter(nextlinestart):
					nextindent = buffer.get_indent(nextlinestart.get_line())
					if nextindent >= indent:
						# we are at the head of a sublist
						indent = nextindent
						start_sublist = True

				# add bullet on new line
				bulletiter = nextlinestart if start_sublist else start # Either look back or look forward
				bullet = buffer.get_bullet_at_iter(bulletiter)
				if bullet in (CHECKED_BOX, XCHECKED_BOX, MIGRATED_BOX, TRANSMIGRATED_BOX):
					bullet = UNCHECKED_BOX
				elif is_numbered_bullet_re.match(bullet):
					if not start_sublist:
						bullet = increase_list_bullet(bullet)
					# else copy number
				else:
					pass # Keep same bullet

				buffer.set_bullet(newline, bullet, indent=indent)
					# Set indent in one-go because setting before fails for
					# end of buffer while setting after messes up renumbering
					# of lists

			buffer.update_editmode() # also updates indent tag

	def on_query_tooltip(self, widget, x, y, keyboard_tip, tooltip):
		# Handle tooltip query event
		x,y = self.window_to_buffer_coords(Gtk.TextWindowType.TEXT, x, y)
		iter = strip_boolean_result(self.get_iter_at_location(x, y))
		if iter is not None:
			pixbuf = self._get_pixbuf_at_pointer(iter, (x, y))
			if pixbuf and hasattr(pixbuf, 'zim_type') and pixbuf.zim_type == 'image':
				data = pixbuf.zim_attrib.copy()
				text = data['src'] + '\n\n'
				if 'href' in data:
					text += '<b>%s:</b> %s\n' % (_('Link'), data['href']) # T: tooltip label for image with href
				if 'id' in data:
					text += '<b>%s:</b> %s\n' % (_('Id'), data['id']) # T: tooltip label for image with anchor id
				tooltip.set_markup(text.strip())
				return True
			elif pixbuf and hasattr(pixbuf, 'zim_type') and pixbuf.zim_type == 'anchor':
				text = '#' + pixbuf.zim_attrib['name']
				tooltip.set_markup(text)
				return True

		return False


