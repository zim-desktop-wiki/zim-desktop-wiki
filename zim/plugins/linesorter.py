# -*- coding: utf-8 -*-

# Copyright 2011 NorfCran <norfcran@gmail.com>
# License:  same as zim (gpl)

import gtk

from zim.plugins import PluginClass
from zim.gui.widgets import ui_environment, MessageDialog

#from zim.gui.clipboard import parsetree_from_selectiondata

import logging

logger = logging.getLogger('zim.plugins.linesorter')

ui_xml = '''
<ui>
	<menubar name='menubar'>
		<menu action='edit_menu'>
			<placeholder name='plugin_items'>
				<menuitem action='sort_selected_lines'/>
			</placeholder>
		</menu>
	</menubar>
</ui>
'''

# in oder to provide dynamic key binding assignment the initiation is made in the plugin class
ui_actions = (
	# name, stock id, label, accelerator, tooltip, read only
	('sort_selected_lines', 'gtk-sort-ascending', _('_Sort lines'), '', '', False),
		# T: menu item for insert clipboard plugin
)


class LineSorterPlugin(PluginClass):
	'''FIXME'''

	plugin_info = {
		'name': _('Line Sorter'), # T: plugin name
		'description': _('''\
This plugin sorts selected lines in alphabetical order.
If the list is already sorted the order will be reversed
(A-Z to Z-A).
'''), # T: plugin description
		'author': 'NorfCran',
		'help': 'Plugins:Line sorter',
	}

	def __init__(self, ui):
		PluginClass.__init__(self, ui)

	def initialize_ui(self, ui):
		if self.ui.ui_type == 'gtk':
			self.ui.add_actions(ui_actions, self)
			self.ui.add_ui(ui_xml, self)

	def sort_selected_lines(self):
		buffer = self.ui.mainwindow.pageview.view.get_buffer()
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

			# 1/ build a list of formatted lines with get_parsetree()
			# 2/ make a list of tuples, first element of each tuple is
			#    text only (white space stripped etc.), second element
			#    is parsetree per line from step 1
			lines = []
			for line_nr in range(first_lineno, last_lineno+1):
				start, end = buffer.get_line_bounds(line_nr)
				text = buffer.get_text(start, end).lower().strip()
				tree = buffer.get_parsetree(bounds=(start, end))
				lines.append((text, tree))
			#logger.debug("Content of selected lines (text, tree): %s", lines)

			# 3/ sort this list of tuples, sort will look at first element of the tuple
			sorted_lines = sorted(lines, key=lambda lines: lines[0])
			# checks whether the list is sorted "a -> z", if so reverses its order
			if lines == sorted_lines:
				sorted_lines.reverse()
			# logger.debug("Sorted lines: %s",  sorted_lines)

			# 4/ for the replacement insert the parsetrees of the lines one by one
			buffer.delete(iter_begin_line, iter_end_line)
			for line in sorted_lines:
				buffer.insert_parsetree_at_cursor(line[1])
