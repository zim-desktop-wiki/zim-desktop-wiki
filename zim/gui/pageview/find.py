# Copyright 2008-2024 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains the classes which implement the "find" functionality

"Find" means a match of text in the text buffer of a given page or inline
object. This differs from "search" which means a more complex query over
many pages.
'''


from gi.repository import GObject
from gi.repository import Gtk

import re
import logging
import itertools

from typing import Optional

from zim.gui.widgets import Dialog, IconButton, InputEntry

from .constants import *


logger = logging.getLogger('zim.gui.pageview')


# Tag styles
FIND_HIGHLIGHT_TAG = 'find-highlight'
FIND_MATCH_TAG = 'find-match'


# Query options
FIND_CASE_SENSITIVE = 1 #: Constant to find case sensitive
FIND_WHOLE_WORD = 2 #: Constant to find whole words only
FIND_REGEX = 4 #: Constant to find based on regexes


class FindQuery():
	'''Object which represents a query for the find functionality

	"Find" is a direct match of text content in the buffer, therefore
	all queries can be represented as regular expressions.
	'''

	def __init__(self, string: str, flags: int = 0):
		self.string = string
		self.flags = flags
		self.regex = self._compile_regex(string, flags)

	def __eq__(self, other):
		return isinstance(other, self.__class__) and (self.string, self.flags) == (other.string, other.flags)

	def __bool__(self):
		return bool(self.string)

	@staticmethod
	def _compile_regex(string, flags):
		assert isinstance(string, str)
		assert isinstance(flags, int)

		if not flags & FIND_REGEX:
			string = re.escape(string)

		if flags & FIND_WHOLE_WORD:
			string = '\\b' + string + '\\b'

		if flags & FIND_CASE_SENSITIVE:
			return re.compile(string, re.U)
		else:
			return re.compile(string, re.U | re.I)


class FindInterface():
	'''Interface definition for the TextBuffer and inserted objects

	The interface implies a statefull model where a match is highlighted and this highlighting
	is reset on the next call or on L{find_clear()}. In addition the L{find_highlight_all()} method
	will highlight all matches. All of the operations L{find_next()}, L{find_previous()},
	L{find_replace_next()} and L{find_replace_all()} will reset the highlighting unless the query is
	the same as provided to L{find_highlight_all()}. This implies the object remembers the query
	used for highlighting.
	Vice versa, a change to the highlighting will reset any matches in the buffer or object.
	'''

	def find_has_active_match(self) -> bool:
		'''True if there is an active match on the current cursor location'''
		raise NotImplementedError

	def find_next(self, query: FindQuery, wrap: bool = True) -> bool:
		'''Go to the next match and highlight it
		If a match happens directly at the current cursor position, it will only match if
		not yet highlighted as a match.
		@param query: string with search query
		@param wrap: if C{True}, wrap around at the end of the buffer and match from the start
		@returns: C{True} if successful
		'''
		raise NotImplementedError

	def find_next_from_start(self, query: FindQuery) -> bool:
		'''Like C{find_next()} but intended for nested objects
		Behavior is statefull:
		If there is a match in the object, continue to find the next match from there;
		if there is no match in the object, look for a match from the start.
		Should not wrap around.
		'''
		raise NotImplementedError

	def find_previous(self, query: FindQuery, wrap: bool = True) -> bool:
		'''Go to the previous match and highlight it
		If a match happens directly at the current cursor position, it will only match if
		not yet highlighted as a match.
		@param query: string with search query
		@param wrap: if C{True}, wrap around at the start of the buffer and match from the end
		@returns: C{True} if successful
		'''
		raise NotImplementedError

	def find_previous_from_end(self, query: FindQuery) -> bool:
		'''Like C{find_previous()} but intended for nested objects
		Behavior is statefull:
		If there is a match in the object, continue to find the previous match from there;
		if there is no match in the object, look for a match from the start.
		Should not wrap around.
		'''
		raise NotImplementedError

	def find_highlight_all(self, query: FindQuery):
		'''Highlight all matches of the query
		@param query: string with search query
		'''
		raise NotImplementedError

	def find_clear():
		'''Clear all find highlighting and matches'''
		raise NotImplementedError

	def find_replace_at_cursor(self, query: FindQuery, replacement: str) -> bool:
		'''Replace match at cursor

		Replace a match but only if it occurs directly at the cursor. Typically this is combined
		with a find operation such that the user sees the match before pressing "replace" button.
		In case of a regex find and replace the string will be expanded with terms from the regex.

		@param query: string with search query
		@param replacement: new text to replace the match
		@returns: C{True} if successful
		'''
		raise NotImplementedError

	def find_replace_all(self, query: FindQuery, replacement: str) -> bool:
		'''Replace all matches

		In case of a regex find and replace the string will be expanded with terms from the regex.

		@param query: string with search query
		@param replacement: new text to replace the match
		@returns: C{True} if successful
		'''
		raise NotImplementedError


def _my_chain_reversed(*iters):
	# Bit inefficient because we need to iterate all to get the last match
	# but at least do it by iterator instead of all at once
	# Assume `find_previous()` used less often than `find_next()` and `find_highlight_all()`
	for myiter in iters:
		results = list(myiter)
		results.reverse()
		for r in results:
			yield r


class TextBufferFindMixin(FindInterface):
	'''Implemenation of the L{FindInterface} which can be combined with either a
	standard C{Gtk.TextBuffer}s or a zim specific L{TextBuffer}
	'''

	# Methods specific for the TextBuffer implemenation

	def __init__(self):
		if hasattr(self, 'tag_styles'):
			self._find_match_tag = self.create_tag(None, **self.tag_styles[FIND_MATCH_TAG])
			self._find_highlight_tag = self.create_tag(None, **self.tag_styles[FIND_HIGHLIGHT_TAG])
		else:
			# Bit of a hack to re-use same style definition
			from .textbuffer import TextBuffer
			self._find_match_tag = self.create_tag(None, **TextBuffer.tag_styles[FIND_MATCH_TAG])
			self._find_highlight_tag = self.create_tag(None, **TextBuffer.tag_styles[FIND_HIGHLIGHT_TAG])

		self._find_signals = ()
		self._find_highlight_all_query = None

	def _find_all_in_range(self, query, start, end):
		# Generator for all matches and objects in range
		# objects are yielded if they support FindInterface, but not checked for matches

		if query.flags & FIND_WHOLE_WORD:
			if start.inside_word() and not start.starts_word():
				start.forward_word_end()

			if end.inside_word() and not end.starts_word():
				end.backward_word_start()

		# See if there are objects supporting FindInterface
		text = start.get_slice(end)
		iobjects = []
		if hasattr(self, 'get_objectanchor'): # specific for zim TextBuffer
			i = text.find(PIXBUF_CHR)
			while i >= 0:
				iter = start.copy()
				iter.forward_chars(i)
				anchor = self.get_objectanchor(iter)
				if anchor:
					iobjects.append((i, anchor))
				i = text.find(PIXBUF_CHR, i+1)

		# Check for text matches in between the objects and yield results
		pos = 0
		iobjects.append((len(text), None)) # ensure last part also searched
		for endpos, iobject in iobjects:
			for match in query.regex.finditer(text, pos, endpos):
				mstart, mend = start.copy(), start.copy()
				mstart.forward_chars(match.start())
				mend.forward_chars(match.end())
				yield mstart, mend, match

			if isinstance(iobject, FindInterface):
				mstart, mend = start.copy(), start.copy()
				mstart.forward_chars(endpos)
				mend.forward_chars(endpos+1)
				yield mstart, mend, iobject

			pos = endpos + 1

	def _find_set_match(self, start, end):
		for id in self._find_signals:
			self.disconnect(id)

		self.apply_tag(self._find_match_tag, start, end)
		self.select_range(start, end)

		self._find_signals = tuple(
			self.connect(s, self._find_on_buffer_changed)
				for s in ('mark-set', 'changed'))

	def _find_on_buffer_changed(self, *a):
		if len(a) > 2 and isinstance(a[2], Gtk.TextMark) \
		and a[2] is not self.get_insert():
			# mark-set signal, but not for cursor
			return

		for id in self._find_signals:
			self.disconnect(id)
		self._find_signals = ()
		self.remove_tag(self._find_match_tag, *self.get_bounds())

	def _find_clear_on_new_query(self, query):
		if self._find_highlight_all_query and not self._find_highlight_all_query == query:
			self.find_clear()
		else:
			# just clear previous match
			self.remove_tag(self._find_match_tag, *self.get_bounds())

	# Implementation of FindInterface based on above methods

	def find_has_active_match(self):
		iter = self.get_iter_at_mark(self.get_insert())
		return self._find_match_tag in iter.get_toggled_tags(toggled_on=True)

	def find_next(self, query, wrap=True):
		assert isinstance(query, FindQuery)

		iter = self.get_iter_at_mark(self.get_insert())
		if self.find_has_active_match():
			iter.forward_char() # avoid match at current location
		elif hasattr(self, 'get_objectanchor'): # specific for zim TextBuffer
			# maybe last action was a find_previous with an object match,
			# check whether we are behind an object with an active match
			tmp = iter.copy()
			tmp.backward_char()
			anchor = self.get_objectanchor(tmp)
			if anchor and isinstance(anchor, FindInterface) \
				and anchor.find_has_active_match() and anchor.find_next(query, wrap=False):
					self._find_clear_on_new_query(query)
					return True

		self._find_clear_on_new_query(query)

		bstart, bend = self.get_bounds()
		if wrap:
			matches = itertools.chain(
				self._find_all_in_range(query, iter, bend),
				self._find_all_in_range(query, bstart, iter)
			)
		else:
			matches = self._find_all_in_range(query, iter, bend)

		for mstart, mend, match in matches:
			if isinstance(match, FindInterface):
				# Object match
				if match.find_next_from_start(query):
					self.place_cursor(mstart)
					return True
			else:
				# Regex text match
				self._find_set_match(mstart, mend)
				return True
		else:
			return False

	def find_next_from_start(self, query):
		if not self.find_has_active_match():
			self.place_cursor(self.get_start_iter())
		return self.find_next(query, wrap=False)

	def find_previous(self, query, wrap=True):
		assert isinstance(query, FindQuery)

		if hasattr(self, 'get_objectanchor'): # specific for zim TextBuffer
			# maybe last action was a find_next with an object match,
			# check whether we are in front of an object with an active match
			anchor = self.get_objectanchor_at_cursor()
			if anchor and isinstance(anchor, FindInterface) \
				and anchor.find_has_active_match() and anchor.find_previous(query, wrap=False):
					self._find_clear_on_new_query(query)
					return True

		self._find_clear_on_new_query(query)

		iter = self.get_iter_at_mark(self.get_insert())
		bstart, bend = self.get_bounds()
		if wrap:
			matches = _my_chain_reversed(
				self._find_all_in_range(query, bstart, iter),
				self._find_all_in_range(query, iter, bend)
			)
		else:
			matches = list(self._find_all_in_range(query, bstart, iter))
			matches.reverse()

		for mstart, mend, match in matches:
			if isinstance(match, FindInterface):
				# Object match
				if match.find_previous_from_end(query):
					self.place_cursor(mend)
					return True
			else:
				# Regex text match
				self._find_set_match(mstart, mend)
				return True
		else:
			return False

	def find_previous_from_end(self, query):
		if not self.find_has_active_match():
			self.place_cursor(self.get_end_iter())
		return self.find_previous(query, wrap=False)

	def find_highlight_all(self, query):
		assert isinstance(query, FindQuery)
		self.find_clear()
		self._find_highlight_all_query = query

		bstart, bend = self.get_bounds()
		for mstart, mend, match in self._find_all_in_range(query, bstart, bend):
			if isinstance(match, FindInterface):
				# Object match
				match.find_highlight_all(query)
			else:
				# Regex text match
				self.apply_tag(self._find_highlight_tag, mstart, mend)

	def find_clear(self):
		self.remove_tag(self._find_match_tag, *self.get_bounds())
		self.remove_tag(self._find_highlight_tag, *self.get_bounds())
		self._find_highlight_all_query = None
		if hasattr(self, 'list_objectanchors'): # specific for zim TextBuffer
			for _, anchor in self.list_objectanchors():
				if isinstance(anchor, FindInterface):
					anchor.find_clear()

	def find_replace_at_cursor(self, query, replacement):
		assert isinstance(query, FindQuery)
		self._find_clear_on_new_query(query)

		iter = self.get_iter_at_mark(self.get_insert())
		end = iter.copy()
		end.forward_to_line_end()
		mstart, mend, match = next(self._find_all_in_range(query, iter, end), (None, None, None))
		if match and mstart.equal(iter):
			if isinstance(match, FindInterface):
				# Object match
				return match.find_replace_at_cursor(query, replacement)
			else:
				# Regex text match
				if query.flags & FIND_REGEX:
					try:
						replacement = match.expand(replacement)
					except:
						logger.exception('error in regex expansion')

				offset = mstart.get_offset()

				self.begin_user_action()
				self.select_range(mstart, mend) # ensure editmode logic is used
				self.delete(mstart, mend)
				self.insert_at_cursor(replacement)
				self.end_user_action()

				rstart = self.get_iter_at_offset(offset)
				rend = self.get_iter_at_offset(offset + len(replacement))
				self.select_range(rstart, rend)

				return True
		else:
			return False # No match at cursor

	def find_replace_all(self, query, replacement):
		# NOTE: Avoid looping when replace value matches query
		assert isinstance(query, FindQuery)
		self._find_clear_on_new_query(query)

		matches = []
		for mstart, mend, match in self._find_all_in_range(query, *self.get_bounds()):
			if isinstance(match, FindInterface):
				# Object match
				match.find_replace_all(query, replacement)
			else:
				# Regex text match
				my_replacement = replacement
				if query.flags & FIND_REGEX:
					try:
						my_replacement = match.expand(replacement)
					except:
						logger.exception('error in regex expansion')

				matches.append((mstart.get_offset(), mend.get_offset(), my_replacement))

		matches.reverse() # work our way backward to keep offsets valid

		self.begin_user_action()
		for startoff, endoff, string in matches:
			start = self.get_iter_at_offset(startoff)
			end = self.get_iter_at_offset(endoff)
			self.delete(start, end)
			start = self.get_iter_at_offset(startoff)
			self.insert(start, string)
		self.end_user_action()

		return len(matches) > 0


FIND_HAS_MATCH = 1
FIND_HAS_HIGHLIGHT = 2
FIND_HAS_MATCH_CSS_CLASS = 'find_match'
FIND_HAS_HIGHLIGHT_CSS_CLASS = 'find_highlight'


class PluginInsertedObjectFindMixin(FindInterface):
	'''Implemenation of the L{FindInterface} for inserted objects from a plugin

	This class checks whether the model of the object supports the L{FindInterface} - e.g. if it is
	a nested C{TextBuffer} and if so will pass through the method calls.
	Otherwise this class treats the objects as "atomic" matches based on the object data and does not
	support replace.
	'''

	# Methods implementing logic specific for simple object

	_find_match_highlight_state = 0 # use class attrib to init instance attrib
	_find_match_query = None # use class attrib to init instance attrib

	def _find_set_match_highlight_state(self, state: int, query: Optional[FindQuery]):
		self._find_match_highlight_state = state
		self._find_match_query = query
		for widget in self.widgets:
			widget = widget._vbox # XXX
			context = widget.get_style_context()
			context.remove_class(FIND_HAS_MATCH_CSS_CLASS)
			context.remove_class(FIND_HAS_HIGHLIGHT_CSS_CLASS)
			if state & FIND_HAS_MATCH:
				context.add_class(FIND_HAS_MATCH_CSS_CLASS)
			elif state & FIND_HAS_HIGHLIGHT:
				context.add_class(FIND_HAS_HIGHLIGHT_CSS_CLASS)
			# else nothing

	def _find_simple_match(self, query: FindQuery) -> bool:
		'''Returns C{True} if current object matches the query'''
		if hasattr(self.objectmodel, 'find_simple_match'):
			return self.objectmodel.find_simple_match(query)
		else:
			attrib, data = self.objecttype.data_from_model(self.objectmodel)
			return (query.regex.search(data) is not None) if data else False

	# Implementation of FindInterface based on above methods

	def find_has_active_match(self):
		if isinstance(self.objectmodel, FindInterface):
			return self.objectmodel.find_has_active_match()
		else:
			return self._find_match_highlight_state & FIND_HAS_MATCH

	def find_next(self, query, wrap=True):
		if isinstance(self.objectmodel, FindInterface):
			return self.objectmodel.find_next(query, wrap)
		else:
			return self._find_any(query)

	def find_next_from_start(self, query):
		if isinstance(self.objectmodel, FindInterface):
			return self.objectmodel.find_next_from_start(query)
		else:
			return self._find_any(query)

	def find_previous(self, query, wrap=True):
		if isinstance(self.objectmodel, FindInterface):
			return self.objectmodel.find_previous(query, wrap)
		else:
			return self._find_any(query)

	def find_previous_from_end(self, query):
		if isinstance(self.objectmodel, FindInterface):
			return self.objectmodel.find_previous_from_end(query)
		else:
			return self._find_any(query)

	def _find_any(self, query):
		if self._find_match_highlight_state & FIND_HAS_MATCH \
			and self._find_match_query == query:
				ok = False # Skip if already matched
				self._find_set_match_highlight_state(self._find_match_highlight_state ^ FIND_HAS_MATCH, query)
		else:
			ok = self._find_simple_match(query)
			if ok:
				if self._find_match_highlight_state & FIND_HAS_HIGHLIGHT \
					and self._find_match_query == query:
						new_state = FIND_HAS_MATCH | FIND_HAS_HIGHLIGHT
				else:
					new_state = FIND_HAS_MATCH
				self._find_set_match_highlight_state(new_state, query)
			else:
				self._find_set_match_highlight_state(0, None)

		return ok

	def find_highlight_all(self, query):
		if isinstance(self.objectmodel, FindInterface):
			ok = self.objectmodel.find_highlight_all(query)
		else:
			if self._find_simple_match(query):
				self._find_set_match_highlight_state(FIND_HAS_HIGHLIGHT, query)
			else:
				self._find_set_match_highlight_state(0, None)

	def find_clear(self):
		if isinstance(self.objectmodel, FindInterface):
			self.objectmodel.find_clear()
		else:
			self._find_set_match_highlight_state(0, None)

	def find_replace_at_cursor(self, query, replacement):
		if isinstance(self.objectmodel, FindInterface):
			return self.objectmodel.find_replace_at_cursor(query, replacement)
		else:
			return False # Not supported

	def find_replace_all(self, query, replacement):
		if isinstance(self.objectmodel, FindInterface):
			return self.objectmodel.find_replace_all(query, replacement)
		else:
			return False # Not supported


class FindWidget(object):
	'''Base class for L{FindBar} and L{FindAndReplaceDialog}'''

	def __init__(self, textview):
		self.textview = textview

		self.find_entry = InputEntry(allow_whitespace=True)
		self.find_entry.connect_object(
			'changed', self.__class__.on_find_entry_changed, self)
		self.find_entry.connect_object(
			'activate', self.__class__.on_find_entry_activate, self)

		self.next_button = Gtk.Button.new_with_mnemonic(_('_Next'))
			# T: button in find bar and find & replace dialog
		self.next_button.connect_object(
			'clicked', self.__class__.find_next, self)
		self.next_button.set_sensitive(False)

		self.previous_button = Gtk.Button.new_with_mnemonic(_('_Previous'))
			# T: button in find bar and find & replace dialog
		self.previous_button.connect_object(
			'clicked', self.__class__.find_previous, self)
		self.previous_button.set_sensitive(False)

		self.case_option_checkbox = Gtk.CheckButton.new_with_mnemonic(_('Match _case'))
			# T: checkbox option in find bar and find & replace dialog
		self.case_option_checkbox.connect_object(
			'toggled', self.__class__.on_find_entry_changed, self)

		self.word_option_checkbox = Gtk.CheckButton.new_with_mnemonic(_('Whole _word'))
			# T: checkbox option in find bar and find & replace dialog
		self.word_option_checkbox.connect_object(
			'toggled', self.__class__.on_find_entry_changed, self)

		self.regex_option_checkbox = Gtk.CheckButton.new_with_mnemonic(_('_Regular expression'))
			# T: checkbox option in find bar and find & replace dialog
		self.regex_option_checkbox.connect_object(
			'toggled', self.__class__.on_find_entry_changed, self)

		self.highlight_checkbox = Gtk.CheckButton.new_with_mnemonic(_('_Highlight'))
			# T: checkbox option in find bar and find & replace dialog
		self.highlight_checkbox.connect_object(
			'toggled', self.__class__.on_highlight_toggled, self)

	def _get_query(self):
		string = self.find_entry.get_text()
		flags = 0
		if self.case_option_checkbox.get_active():
			flags = flags | FIND_CASE_SENSITIVE
		if self.word_option_checkbox.get_active():
			flags = flags | FIND_WHOLE_WORD
		if self.regex_option_checkbox.get_active():
			flags = flags | FIND_REGEX
		return FindQuery(string, flags)

	def on_find_entry_changed(self, match_at_cursor=True):
		query = self._get_query()
		buffer = self.textview.get_buffer()
		if match_at_cursor:
			buffer.find_clear() # prevent skipping past current cursor if cursor matches

		if not query:
			ok = False
			self.find_entry.set_input_valid(True)
			buffer.find_clear() # also clear highlight (if not done yet)
		else:
			ok = buffer.find_next(query)
			self.find_entry.set_input_valid(ok)
			if self.highlight_checkbox.get_active():
				buffer.find_highlight_all(query)

		for button in (self.next_button, self.previous_button):
			button.set_sensitive(ok)

		if ok:
			self.textview.scroll_to_mark(buffer.get_insert(), SCROLL_TO_MARK_MARGIN, False, 0, 0)

	def on_find_entry_activate(self):
		self.on_find_entry_changed(match_at_cursor=False)

	def on_highlight_toggled(self):
		buffer = self.textview.get_buffer()
		if self.highlight_checkbox.get_active():
			buffer.find_highlight_all(self._get_query())
		else:
			buffer.find_clear()

	def find(self, string, flags=0, highlight=False):
		self.find_entry.set_text(string)
		self.case_option_checkbox.set_active(flags & FIND_CASE_SENSITIVE)
		self.word_option_checkbox.set_active(flags & FIND_WHOLE_WORD)
		self.regex_option_checkbox.set_active(flags & FIND_REGEX)
		self.highlight_checkbox.set_active(highlight)
		self.on_find_entry_changed()

	def find_next(self):
		buffer = self.textview.get_buffer()
		ok = buffer.find_next(self._get_query())
		if ok:
			self.textview.scroll_to_mark(buffer.get_insert(), SCROLL_TO_MARK_MARGIN, False, 0, 0)

	def find_previous(self):
		buffer = self.textview.get_buffer()
		ok = buffer.find_previous(self._get_query())
		if ok:
			self.textview.scroll_to_mark(buffer.get_insert(), SCROLL_TO_MARK_MARGIN, False, 0, 0)


class FindBar(FindWidget, Gtk.ActionBar):
	'''Bar to be shown below the TextView for find functions'''

	# Ideas:
	# - support smaller buttons
	# - allow box to shrink further by putting buttons in a menu when to little space

	def __init__(self, textview):
		GObject.GObject.__init__(self)
		FindWidget.__init__(self, textview)

		self.pack_start(Gtk.Label(_('Find') + ': '))
			# T: label for input in find bar on bottom of page
		self.pack_start(self.find_entry)
		self.pack_start(self.previous_button)
		self.pack_start(self.next_button)
		self.pack_start(self.case_option_checkbox)
		self.pack_start(self.highlight_checkbox)

		close_button = IconButton(Gtk.STOCK_CLOSE, relief=False, size=Gtk.IconSize.MENU)
		close_button.connect_object('clicked', self.__class__.hide, self)
		self.pack_end(close_button)

	def grab_focus(self):
		self.find_entry.grab_focus()

	def show(self):
		if not self.get_visible():
			self.set_no_show_all(False)
			self.show_all()
			self.on_find_entry_changed(match_at_cursor=True)
		# else avoid changing state

	def hide(self):
		Gtk.ActionBar.hide(self)
		self.set_no_show_all(True)
		buffer = self.textview.get_buffer()
		buffer.find_clear()
		self.textview.grab_focus()


class FindAndReplaceDialog(FindWidget, Dialog):
	'''Dialog for find and replace'''

	def __init__(self, parent, textview):
		Dialog.__init__(self, parent,
			_('Find and Replace'), buttons=Gtk.ButtonsType.CLOSE) # T: Dialog title
		FindWidget.__init__(self, textview)

		hbox = Gtk.HBox(spacing=12)
		hbox.set_border_width(12)
		self.vbox.add(hbox)

		vbox = Gtk.VBox(spacing=5)
		hbox.pack_start(vbox, True, True, 0)

		label = Gtk.Label(label=_('Find what') + ': ')
			# T: input label in find & replace dialog
		label.set_alignment(0.0, 0.5)
		vbox.add(label)
		vbox.add(self.find_entry)
		vbox.add(self.case_option_checkbox)
		vbox.add(self.word_option_checkbox)
		vbox.add(self.regex_option_checkbox)
		vbox.add(self.highlight_checkbox)

		label = Gtk.Label(label=_('Replace with') + ': ')
			# T: input label in find & replace dialog
		label.set_alignment(0.0, 0.5)
		vbox.add(label)
		self.replace_entry = InputEntry(allow_whitespace=True)
		vbox.add(self.replace_entry)

		self.bbox = Gtk.ButtonBox(orientation=Gtk.Orientation.VERTICAL)
		self.bbox.set_layout(Gtk.ButtonBoxStyle.START)
		self.bbox.set_spacing(5)
		hbox.pack_start(self.bbox, False, False, 0)
		self.bbox.add(self.next_button)
		self.bbox.add(self.previous_button)

		replace_button = Gtk.Button.new_with_mnemonic(_('_Replace'))
			# T: Button in search & replace dialog
		replace_button.connect_object('clicked', self.__class__.replace, self)
		self.bbox.add(replace_button)

		all_button = Gtk.Button.new_with_mnemonic(_('Replace _All'))
			# T: Button in search & replace dialog
		all_button.connect_object('clicked', self.__class__.replace_all, self)
		self.bbox.add(all_button)

	def set_input(self, **inputs):
		# Hide implementation for test cases
		for key, value in list(inputs.items()):
			if key == 'query':
				self.find_entry.set_text(value)
			elif key == 'replacement':
				self.replace_entry.set_text(value)
			else:
				raise ValueError

	def replace(self):
		string = self.replace_entry.get_text()
		buffer = self.textview.get_buffer()
		query = self._get_query()
		if buffer.find_replace_at_cursor(query, string):
			buffer.find_next(query)

	def replace_all(self):
		string = self.replace_entry.get_text()
		buffer = self.textview.get_buffer()
		buffer.find_replace_all(self._get_query(), string)

	def do_response(self, id):
		Dialog.do_response(self, id)
		buffer = self.textview.get_buffer()
		buffer.find_clear()

