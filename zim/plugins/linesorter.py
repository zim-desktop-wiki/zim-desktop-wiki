
# Copyright 2011 NorfCran <norfcran@gmail.com>
# License:  same as zim (gpl)



from gi.repository import Gtk

from zim.errors import Error
from zim.plugins import PluginClass
from zim.actions import action
from zim.utils import natural_sort_key

from zim.gui.pageview import PageViewExtension
from zim.gui.widgets import MessageDialog


import logging

logger = logging.getLogger('zim.plugins.linesorter')


class LineSorterPlugin(PluginClass):

	plugin_info = {
		'name': _('Line Sorter'), # T: plugin name
		'description': _('''\
This plugin sorts selected lines in alphabetical order.
If the list is already sorted the order will be reversed
(A-Z to Z-A).
'''), # T: plugin description
		'author': 'NorfCran',
		'help': 'Plugins:Line Sorter',
	}


class NoSelectionError(Error):

	def __init__(self):
		Error.__init__(self, _('Please select more than one line of text'))
			# T: Error message for linesorter plugin


class LineSorterPageViewExtension(PageViewExtension):

	def _get_selected_lines(self, buffer):
		try:
			start, end = buffer.get_selection_bounds()
		except ValueError:
			raise NoSelectionError()

		first = start.get_line()
		last = end.get_line()
		if end.starts_line():
			last -= 1 # Visually includes trailing newline, but not next line
		return first, last

	def _get_iters_one_or_more_lines(self, buffer):
		try:
			first, last = self._get_selected_lines(buffer)
		except NoSelectionError:
			iter = buffer.get_insert_iter()
			start, end = buffer.get_line_bounds(iter.get_line())
		else:
			start, x = buffer.get_line_bounds(first)
			y, end = buffer.get_line_bounds(last)

		return start, end

	@action(_('_Sort lines'), menuhints='edit') # T: menu item
	def sort_selected_lines(self):
		buffer = self.pageview.textview.get_buffer()
		first_lineno, last_lineno = self._get_selected_lines(buffer)
		if first_lineno == last_lineno:
			raise NoSelectionError()

		with buffer.user_action:
			# Get iters for full selection
			iter_end_line = buffer.get_iter_at_line(last_lineno)
			iter_end_line.forward_line() # include \n at end of line
			if iter_end_line.is_end() and not iter_end_line.starts_line():
				# no \n at end of buffer, insert it
				buffer.insert(iter_end_line, '\n')
				iter_end_line = buffer.get_end_iter()
			iter_begin_line = buffer.get_iter_at_line(first_lineno)

			# Make a list of tuples, first element of each tuple is
			# text only sort key (no formatting), second element
			# is parsetree per line
			lines = []
			for line_nr in range(first_lineno, last_lineno + 1):
				start, end = buffer.get_line_bounds(line_nr)
				text = start.get_text(end)
				tree = buffer.get_parsetree(bounds=(start, end))
				lines.append((natural_sort_key(text), tree))
			#~ logger.debug("Content of selected lines (text, tree): %s", lines)

			# Sort the list of tuples
			sorted_lines = sorted(lines, key=lambda t: t[0])
			if lines == sorted_lines: # reverse if already sorted
				sorted_lines.reverse()
			#~ logger.debug("Sorted lines: %s",  sorted_lines)

			# Replace selection
			buffer.delete(iter_begin_line, iter_end_line)
			for line in sorted_lines:
				buffer.insert_parsetree_at_cursor(line[1])


	def move_line(self, offset):
		'''Move line at the current cursor position #offset lines down (up if offset is negative) '''
		buffer = self.pageview.textview.get_buffer()
		start, end = self._get_iters_one_or_more_lines(buffer)

		# do nothing if target is before begin or after end of document
		if (offset > 0 and end.is_end()) or (offset < 0 and start.is_start()):
			return

		# remember offset of cursor/selection bound
		has_selection = buffer.get_has_selection()
		if has_selection:
			sel_start, sel_end = buffer.get_selection_bounds()
			sel_start_offset = sel_start.get_line_offset()
			sel_end_offset = sel_end.get_line_offset()
			sel_end_lines = sel_end.get_line() - sel_start.get_line()
		else:
			cursor = buffer.get_insert_iter()
			cursor_offset = cursor.get_line_offset()

		# get copy tree
		tree = buffer.get_parsetree(bounds=(start, end), raw=True)

		with buffer.user_action:
			# delete lines and insert at target
			buffer.place_cursor(start)
			buffer.delete(start, end)
			iter = buffer.get_insert_iter()
			if offset > 0:
				iter.forward_lines(offset)
			else:
				iter.backward_lines(abs(offset))
			buffer.place_cursor(iter)
			insert_line = iter.get_line()
			buffer.insert_parsetree_at_cursor(tree)

			# redo selection/place cursor at same position
			if has_selection:
				start = buffer.get_iter_at_line_offset(insert_line, sel_start_offset)
				end = buffer.get_iter_at_line_offset(insert_line + sel_end_lines, sel_end_offset)
				buffer.select_range(start, end)
			else:
				iter = buffer.get_iter_at_line_offset(insert_line, cursor_offset)
				buffer.place_cursor(iter)


	@action(_('_Move Line Up'), accelerator='<Primary>Up', menuhints='edit')  # T: Menu item
	def move_line_up(self):
		'''Menu action to move line up'''
		self.move_line(-1)


	@action(_('_Move Line Down'), accelerator='<Primary>Down', menuhints='edit')  # T: Menu item
	def move_line_down(self):
		'''Menu action to move line down'''
		self.move_line(1)


	@action(_('_Duplicate Line'), accelerator='<Primary><Shift>D', menuhints='edit')  # T: Menu item
	def duplicate_line(self):
		'''Menu action to dublicate line'''
		buffer = self.pageview.textview.get_buffer()
		start, end = self._get_iters_one_or_more_lines(buffer)
		tree = buffer.get_parsetree(bounds=(start, end))
		with buffer.user_action:
			buffer.insert_parsetree(end, tree)


	@action(_('_Remove Line'), accelerator='<Primary><Shift>K', menuhints='edit')  # T: Menu item
	def remove_line(self):
		'''Menu action to remove line at the current cursor position'''
		buffer = self.pageview.textview.get_buffer()
		start, end = self._get_iters_one_or_more_lines(buffer)
		buffer.delete(start, end)
		buffer.set_modified(True)
		buffer.update_editmode()
