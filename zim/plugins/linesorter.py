# -*- coding: utf-8 -*-

# Copyright 2011 NorfCran <norfcran@gmail.com>
# License:  same as zim (gpl)

from __future__ import with_statement

import gtk

from zim.plugins import PluginClass, extends, WindowExtension
from zim.actions import action
from zim.gui.widgets import ui_environment, MessageDialog
from zim.utils import natural_sort_key

#from zim.gui.clipboard import parsetree_from_selectiondata

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


@extends('MainWindow')
class MainWindowExtension(WindowExtension):

	uimanager_xml = '''
	<ui>
		<menubar name='menubar'>
			<menu action='edit_menu'>
				<placeholder name='plugin_items'>
					<menuitem action='sort_selected_lines'/>
					<menuitem action='remove_line'/>
					<menuitem action='move_line_up'/>
					<menuitem action='move_line_down'/>
				</placeholder>
			</menu>
		</menubar>
	</ui>
	'''

	@action(_('_Sort lines'), stock='gtk-sort-ascending') # T: menu item
	def sort_selected_lines(self):
		buffer = self.window.pageview.view.get_buffer()
		try:
			sel_start, sel_end = buffer.get_selection_bounds()
		except ValueError:
			MessageDialog(self.ui,
				_('Please select more than one line of text, first.')).run()
				# T: Error message in "" dialog, %s will be replaced by application name
			return

		first_lineno = sel_start.get_line()
		last_lineno = sel_end.get_line()

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
			for line_nr in range(first_lineno, last_lineno+1):
				start, end = buffer.get_line_bounds(line_nr)
				text = buffer.get_text(start, end)
				tree = buffer.get_parsetree(bounds=(start, end))
				lines.append((natural_sort_key(text), tree))
			#~ logger.debug("Content of selected lines (text, tree): %s", lines)

			# Sort the list of tuples
			sorted_lines = sorted(lines)
			if lines == sorted_lines: # reverse if already sorted
				sorted_lines.reverse()
			#~ logger.debug("Sorted lines: %s",  sorted_lines)

			# Replace selection
			buffer.delete(iter_begin_line, iter_end_line)
			for line in sorted_lines:
				buffer.insert_parsetree_at_cursor(line[1])


	def move_line(self, offset):
		'''Move line at the current cursor position #offset lines down (up if offset is negative) '''
		buffer = self.window.pageview.view.get_buffer()
		iter = buffer.get_iter_at_mark(buffer.get_insert())
		line = iter.get_line()
		line_offset = iter.get_line_offset()
		last_line = buffer.get_end_iter().get_line()

		start, end = buffer.get_line_bounds(line)
		tree = buffer.get_parsetree(bounds=(start, end))
		target_line = line + offset

		# do nothing if target is before begin or after end of document
		if target_line < 0 or target_line >= last_line:
			return

		with buffer.user_action:
			buffer.delete(start, end)
			iter = buffer.get_iter_at_line(target_line)
			#scroll with one line margin on top/bottom
			scroll_target_iter = buffer.get_iter_at_line(target_line  - 1 * (offset < 0 and target_line > 0))
			buffer.place_cursor(iter)
			buffer.insert_parsetree_at_cursor(tree)
			iter = buffer.get_iter_at_line_offset(target_line, line_offset)
			buffer.place_cursor(iter)

			self.window.pageview.view.scroll_to_iter(scroll_target_iter, 0)


	@action(_('_Move Line Up'), accelerator='<Primary>Up', readonly=False)  # T: Menu item
	def move_line_up(self):
		'''Menu action to move line up'''
		self.move_line(-1)


	@action(_('_Move Line Down'), accelerator='<Primary>Down', readonly=False)  # T: Menu item
	def move_line_down(self):
		'''Menu action to move line down'''
		self.move_line(1)


	@action(_('_Remove Line'), accelerator='<Primary><Shift>D', readonly=False)  # T: Menu item
	def remove_line(self):
		'''Menu action to remove line at the current cursor position'''
		buffer = self.window.pageview.view.get_buffer()
		iter = buffer.get_iter_at_mark(buffer.get_insert())
		line = iter.get_line()
		start, end = buffer.get_line_bounds(line)
		buffer.delete(start, end)
		buffer.set_modified(True)
		buffer.update_editmode()

		iter = buffer.get_iter_at_line(max(0, line - 1))
		if line != 0:
			iter.forward_to_line_end()
		buffer.place_cursor(iter)

