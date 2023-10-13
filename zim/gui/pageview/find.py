# Copyright 2008-2023 Jaap Karssenberg <jaap.karssenberg@gmail.com>


from gi.repository import GObject
from gi.repository import Gtk

import re
import logging

from zim.gui.widgets import Dialog, IconButton, InputEntry

from .constants import *


logger = logging.getLogger('zim.gui.pageview')



FIND_CASE_SENSITIVE = 1 #: Constant to find case sensitive
FIND_WHOLE_WORD = 2 #: Constant to find whole words only
FIND_REGEX = 4 #: Constant to find based on regexes


class TextFinder(object):
	'''This class handles finding text in the L{TextBuffer}

	Typically you should get an instance of this class from the
	L{TextBuffer.finder} attribute.
	'''

	def __init__(self, textbuffer):
		'''constructor

		@param textbuffer: a L{TextBuffer} object
		'''
		self.buffer = textbuffer
		self._signals = ()
		self.regex = None
		self.string = None
		self.flags = 0
		self.highlight = False

		self.highlight_tag = self.buffer.create_tag(
			None, **self.buffer.tag_styles['find-highlight'])
		self.match_tag = self.buffer.create_tag(
			None, **self.buffer.tag_styles['find-match'])

	def get_state(self):
		'''Get the query and any options. Used to copy the current state
		of find, can be restored later using L{set_state()}.

		@returns: a 3-tuple of the search string, the option flags, and
		the highlight state
		'''
		return self.string, self.flags, self.highlight

	def set_state(self, string, flags, highlight):
		'''Set the query and any options. Can be used to restore the
		state of a find action without triggering a find immediatly.

		@param string: the text (or regex) to find
		@param flags: a combination of C{FIND_CASE_SENSITIVE},
		C{FIND_WHOLE_WORD} & C{FIND_REGEX}
		@param highlight: highlight state C{True} or C{False}
		'''
		if not string is None:
			self._parse_query(string, flags)
			self.set_highlight(highlight)

	def find(self, string, flags=0):
		'''Find and select the next occurrence of a given string

		@param string: the text (or regex) to find
		@param flags: options, a combination of:
			- C{FIND_CASE_SENSITIVE}: check case of matches
			- C{FIND_WHOLE_WORD}: only match whole words
			- C{FIND_REGEX}: input is a regular expression
		@returns: C{True} if a match was found
		'''
		self._parse_query(string, flags)
		#~ print('!! FIND "%s" (%s, %s)' % (self.regex.pattern, string, flags))

		if self.highlight:
			self._update_highlight()

		iter = self.buffer.get_insert_iter()
		return self._find_next(iter)

	def _parse_query(self, string, flags):
		assert isinstance(string, str)
		self.string = string
		self.flags = flags

		if not flags & FIND_REGEX:
			string = re.escape(string)

		if flags & FIND_WHOLE_WORD:
			string = '\\b' + string + '\\b'

		if flags & FIND_CASE_SENSITIVE:
			self.regex = re.compile(string, re.U)
		else:
			self.regex = re.compile(string, re.U | re.I)

	def find_next(self):
		'''Skip to the next match and select it

		@returns: C{True} if a match was found
		'''
		iter = self.buffer.get_insert_iter()
		iter.forward_char() # Skip current position
		return self._find_next(iter)

	def _find_next(self, iter):
		# Common functionality between find() and find_next()
		# Looking for a match starting at iter
		if self.regex is None:
			self.unset_match()
			return False

		line = iter.get_line()
		lastline = self.buffer.get_end_iter().get_line()
		for start, end, _ in self._check_range(line, lastline, 1):
			if start.compare(iter) == -1:
				continue
			else:
				self.set_match(start, end)
				return True

		for start, end, _ in self._check_range(0, line, 1):
			self.set_match(start, end)
			return True

		self.unset_match()
		return False

	def find_previous(self):
		'''Go back to the previous match and select it

		@returns: C{True} if a match was found
		'''
		if self.regex is None:
			self.unset_match()
			return False

		iter = self.buffer.get_insert_iter()
		line = iter.get_line()
		lastline = self.buffer.get_end_iter().get_line()
		for start, end, _ in self._check_range(line, 0, -1):
			if start.compare(iter) != -1:
				continue
			else:
				self.set_match(start, end)
				return True
		for start, end, _ in self._check_range(lastline, line, -1):
			self.set_match(start, end)
			return True

		self.unset_match()
		return False

	def set_match(self, start, end):
		self._remove_tag()

		self.buffer.apply_tag(self.match_tag, start, end)
		self.buffer.select_range(start, end)

		self._signals = tuple(
			self.buffer.connect(s, self._remove_tag)
				for s in ('mark-set', 'changed'))

	def unset_match(self):
		self._remove_tag()
		self.buffer.unset_selection()

	def _remove_tag(self, *a):
		if len(a) > 2 and isinstance(a[2], Gtk.TextMark) \
		and a[2] is not self.buffer.get_insert():
			# mark-set signal, but not for cursor
			return

		for id in self._signals:
			self.buffer.disconnect(id)
		self._signals = ()
		self.buffer.remove_tag(self.match_tag, *self.buffer.get_bounds())

	def select_match(self):
		# Select last match
		bounds = self.match_bounds
		if not None in bounds:
			self.buffer.select_range(*bounds)

	def set_highlight(self, highlight):
		'''Toggle highlighting of matches in the L{TextBuffer}

		@param highlight: C{True} to enable highlighting, C{False} to
		disable
		'''
		self.highlight = highlight
		self._update_highlight()
		# TODO we could connect to buffer signals to update highlighting
		# when the buffer is modified.

	def _update_highlight(self, line=None):
		# Clear highlighting
		tag = self.highlight_tag
		if line is not None:
			start = self.buffer.get_iter_at_line(line)
			end = start.copy()
			if not start.ends_line():
				end.forward_to_line_end()
			firstline, lastline = line, line
		else:
			start, end = self.buffer.get_bounds()
			firstline, lastline = 0, end.get_line()

		self.buffer.remove_tag(tag, start, end)

		# Set highlighting
		if self.highlight:
			for start, end, _ in self._check_range(firstline, lastline, 1):
				self.buffer.apply_tag(tag, start, end)

	def _check_range(self, firstline, lastline, step):
		# Generator for matches in a line. Arguments are start and
		# end line numbers and a step size (1 or -1). If the step is
		# negative results are yielded in reversed order. Yields pair
		# of TextIter's for begin and end of the match as well as the
		# match object.
		assert self.regex
		for line in range(firstline, lastline + step, step):
			start = self.buffer.get_iter_at_line(line)
			if start.ends_line():
				continue

			end = start.copy()
			end.forward_to_line_end()
			text = start.get_slice(end)
			matches = self.regex.finditer(text)
			if step == -1:
				matches = list(matches)
				matches.reverse()
			for match in matches:
				startiter = self.buffer.get_iter_at_line_offset(
					line, match.start())
				enditer = self.buffer.get_iter_at_line_offset(
					line, match.end())
				yield startiter, enditer, match

	def replace(self, string):
		'''Replace current match

		@param string: the replacement string

		In case of a regex find and replace the string will be expanded
		with terms from the regex.

		@returns: C{True} is successful
		'''
		iter = self.buffer.get_insert_iter()
		if not self._find_next(iter):
			return False

		iter = self.buffer.get_insert_iter()
		line = iter.get_line()
		for start, end, match in self._check_range(line, line, 1):
			if start.equal(iter):
				if self.flags & FIND_REGEX:
					string = match.expand(string)

				offset = start.get_offset()

				with self.buffer.user_action:
					self.buffer.select_range(start, end) # ensure editmode logic is used
					self.buffer.delete(start, end)
					self.buffer.insert_at_cursor(string)

				start = self.buffer.get_iter_at_offset(offset)
				end = self.buffer.get_iter_at_offset(offset + len(string))
				self.buffer.select_range(start, end)

				self._update_highlight(line)
				return True
		else:
			return False


	def replace_all(self, string):
		'''Replace all matched

		Like L{replace()} but replaces all matches in the buffer

		@param string: the replacement string
		@returns: C{True} is successful
		'''
		# Avoid looping when replace value matches query

		matches = []
		orig = string
		lastline = self.buffer.get_end_iter().get_line()
		for start, end, match in self._check_range(0, lastline, 1):
			if self.flags & FIND_REGEX:
				string = match.expand(orig)
			matches.append((start.get_offset(), end.get_offset(), string))

		matches.reverse() # work our way back top keep offsets valid

		with self.buffer.user_action:
			for startoff, endoff, string in matches:
				start = self.buffer.get_iter_at_offset(startoff)
				end = self.buffer.get_iter_at_offset(endoff)
				if start.get_child_anchor() is not None:
					self._replace_in_widget(start, self.regex, string, True)
				else:
					self.buffer.delete(start, end)
					start = self.buffer.get_iter_at_offset(startoff)
					self.buffer.insert(start, string)

		self._update_highlight()



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

	@property
	def _flags(self):
		flags = 0
		if self.case_option_checkbox.get_active():
			flags = flags | FIND_CASE_SENSITIVE
		if self.word_option_checkbox.get_active():
			flags = flags | FIND_WHOLE_WORD
		if self.regex_option_checkbox.get_active():
			flags = flags | FIND_REGEX
		return flags

	def set_from_buffer(self):
		'''Copies settings from last find in the buffer. Uses the
		selected text for find if there is a selection.
		'''
		buffer = self.textview.get_buffer()
		string, flags, highlight = buffer.finder.get_state()
		bounds = buffer.get_selection_bounds()
		if bounds:
			start, end = bounds
			string = start.get_slice(end)
			if flags & FIND_REGEX:
				string = re.escape(string)
		self.find(string, flags, highlight)

	def on_find_entry_changed(self):
		string = self.find_entry.get_text()
		buffer = self.textview.get_buffer()
		ok = buffer.finder.find(string, flags=self._flags)

		if not string:
			self.find_entry.set_input_valid(True)
		else:
			self.find_entry.set_input_valid(ok)

		for button in (self.next_button, self.previous_button):
			button.set_sensitive(ok)

		if ok:
			self.textview.scroll_to_mark(buffer.get_insert(), SCROLL_TO_MARK_MARGIN, False, 0, 0)

	def on_find_entry_activate(self):
		self.on_find_entry_changed()

	def on_highlight_toggled(self):
		highlight = self.highlight_checkbox.get_active()
		buffer = self.textview.get_buffer()
		buffer.finder.set_highlight(highlight)

	def find(self, string, flags=0, highlight=False):
		if string:
			self.find_entry.set_text(string)
		self.case_option_checkbox.set_active(flags & FIND_CASE_SENSITIVE)
		self.word_option_checkbox.set_active(flags & FIND_WHOLE_WORD)
		self.regex_option_checkbox.set_active(flags & FIND_REGEX)
		self.highlight_checkbox.set_active(highlight)

		# Force update
		self.on_find_entry_changed()
		self.on_highlight_toggled()

	def find_next(self):
		buffer = self.textview.get_buffer()
		buffer.finder.find_next()
		self.textview.scroll_to_mark(buffer.get_insert(), SCROLL_TO_MARK_MARGIN, False, 0, 0)

	def find_previous(self):
		buffer = self.textview.get_buffer()
		buffer.finder.find_previous()
		self.textview.scroll_to_mark(buffer.get_insert(), SCROLL_TO_MARK_MARGIN, False, 0, 0)


class FindBar(FindWidget, Gtk.ActionBar):
	'''Bar to be shown below the TextView for find functions'''

	# TODO use smaller buttons ?

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
		# TODO allow box to shrink further by putting buttons in menu

		close_button = IconButton(Gtk.STOCK_CLOSE, relief=False, size=Gtk.IconSize.MENU)
		close_button.connect_object('clicked', self.__class__.hide, self)
		self.pack_end(close_button)

	def grab_focus(self):
		self.find_entry.grab_focus()

	def show(self):
		self.on_highlight_toggled()
		self.set_no_show_all(False)
		self.show_all()

	def hide(self):
		Gtk.ActionBar.hide(self)
		self.set_no_show_all(True)
		buffer = self.textview.get_buffer()
		buffer.finder.set_highlight(False)
		self.textview.grab_focus()

	def on_find_entry_activate(self):
		self.on_find_entry_changed()
		self.find_next()


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
		buffer.finder.replace(string)
		buffer.finder.find_next()

	def replace_all(self):
		string = self.replace_entry.get_text()
		buffer = self.textview.get_buffer()
		buffer.finder.replace_all(string)

	def do_response(self, id):
		Dialog.do_response(self, id)
		buffer = self.textview.get_buffer()
		buffer.finder.set_highlight(False)

