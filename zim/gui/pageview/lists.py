# Copyright 2008-2026 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from .constants import *


def toggle_checkbox_interactive(textview, line: int|None=None, state=None):
	'''Convenience method for UI actions to toggle a checkbox

	This method is intended for UI actions that want to toggle a checkbox.
	It takes care of cursor and selection in the view and preference for recursive
	behavior of checkboxes.

	It will only affect lines that already contain a checkbox. To reformat other
	lines please refer to the L{PageView.apply_format_checkbox_list()} action.

	For multi-line it will only toggle unchecked boxes and not overwrite existing
	toggled stated. Unless `state` is `UNCHECKED_BOX`.

	It implements the `'recursive_checklist'` and `'cycle_checkbox_type'` preferences.
	The `'cycle_checkbox_type'` preference only applies for a single line, not for selections.

	@param textview: a L{TextView} object
	@param line: optional line number, if C{None} the cursor will be used
	@param state: optional checkbox state, if C{None} state will toggle to next logical state
	@returns: C{True} for success, C{False} if no checkbox was found.
	'''
	with textview.get_buffer().user_action:
		return _toggle_checkbox_interactive(textview, line, state)


def _toggle_checkbox_interactive(textview, line: int|None=None, state=None):
	# NOTE: when recursive_checklist is False we could optimize this function and remove the use
	# of the TextBufferList and directly call `buffer.set_bullet()`. Unless performance issues are
	# seen this is not needed. If performance issues are seen it would be best to address them in
	# the TextBufferList to make sure we can also performe with recursive_checklist is True.
	buffer = textview.get_buffer()
	recurs = textview.preferences['recursive_checklist']
	cycle = textview.preferences['cycle_checkbox_type']

	if buffer.get_has_selection() and line is None:
		# multi-line
		start, end = buffer.get_selection_bounds()
		clist = TextBufferList(buffer, start.get_line(), end.get_line(), recursive_checklist=recurs)

		if not clist:
			return False # nothing to do here

		if state is None:
			# look at first checkbox to decide what to do
			for row in clist:
				line, indent, bullet = row
				if bullet in CHECKBOXES:
					state = CHECKED_BOX if bullet == UNCHECKED_BOX else UNCHECKED_BOX
					break
			else:
				return False # no checkboxes in list

		def update_checkbox(line):
			bullet = buffer.get_bullet(line)
			if bullet in CHECKBOXES and (bullet == UNCHECKED_BOX or state == UNCHECKED_BOX):
				row = clist.get_row_at_line(line)
				clist.set_bullet(row, state)

		return buffer.foreach_line_in_selection(update_checkbox, skip_empty_lines=True)
	else:
		# single line
		line = buffer.get_insert_iter().get_line() if line is None else line
		bullet = buffer.get_bullet(line)
		if bullet not in CHECKBOXES:
			return False

		if state is None:
			if cycle:
				i = CHECKBOXES.index(bullet)
				j = (i + 1) % len(CHECKBOXES)
				state = CHECKBOXES[j]
			else:
				state = CHECKED_BOX if bullet == UNCHECKED_BOX else UNCHECKED_BOX

		clist = TextBufferList(buffer, line, recursive_checklist=recurs)
		clist.set_bullet(clist.get_row_at_line(line), state)
		return True


class TextBufferList(list):
	'''This class represents a bullet or checkbox list in a L{TextBuffer}.
	It is used to perform recursive actions on the list.

	While the L{TextBuffer} just treats list items as lines that start
	with a bullet, the TextBufferList maps to a number of lines that
	together form a list. It uses "row ids" to refer to specific
	items within this range.

	TextBufferList objects will become invalid after any modification
	to the buffer that changes the line count within the list. Using
	them after such modification will result in errors.
	'''

	# This class is a list of tuples, each tuple is a pair of
	# (linenumber, indentlevel, bullettype)

	LINE_COL = 0
	INDENT_COL = 1
	BULLET_COL = 2

	def __init__(self, textbuffer: 'TextBuffer', firstline: int, lastline: int|None=None, recursive_checklist: bool=True):
		'''Constructor

		Based on first and last line provided in this constructor it will capture all list content
		in between (potentially multiple lists) and extend in both directions if lines are in the
		middle of a list. The `firstline` and `lastline` attributes of the object will therefore
		often deviate from the values provided to the constructor.

		@param textbuffer: a L{TextBuffer} object
		@param firstline: the line number for the first line of the list
		@param lastline: the line number for the last line of the list - optional, if C{None} the
		list around `firstline` will be captured, if not C{None} the whole region between
		`firstline` and `lastline` is captured.
		@param recursive_checklist: if C{True} checking a box will affect child items
		and unchecking a box will affect parent items
		'''
		lastline = firstline if lastline is None else lastline
		self.buffer = textbuffer
		self.firstline = self._find_start_of_list(textbuffer, firstline, lastline)
		self.lastline = self._find_end_of_list(textbuffer, lastline, firstline)
		self.recursive_checklist = recursive_checklist
		if self.firstline is not None and self.lastline is not None:
			for line in range(self.firstline, self.lastline + 1):
				bullet = self.buffer.get_bullet(line)
				indent = self.buffer.get_indent(line)
				if bullet:
					self.append((line, indent, bullet))

	@staticmethod
	def _find_start_of_list(textbuffer, line, end):
		start = line

		if textbuffer.get_bullet(line) is None:
			# Walk down till we find bullet
			for myline in range(start, end + 1, 1):
				if textbuffer.get_bullet(myline) is not None:
					return myline
			else:
				return None
		else:
			# Walk up to find the start
			for myline in range(start, -1, -1):
				if textbuffer.get_bullet(myline) is None:
					break # TODO skip lines with whitespace / indented paragraph
				else:
					start = myline
			return start

	@staticmethod
	def _find_end_of_list(textbuffer, line, start):
		if textbuffer.get_bullet(line) is None:
			# Walk up till we find bullet
			for myline in range(line, start - 1, -1):
				if textbuffer.get_bullet(myline) is not None:
					return myline
			else:
				return None
		else:
			# Walk down to find end
			end = line
			lastline = textbuffer.get_end_iter().get_line()
			for myline in range(end, lastline + 1, 1):
				if textbuffer.get_bullet(myline) is None:
					break # TODO skip lines with whitespace / indented paragraph
				else:
					end = myline
			return end

	def get_row_at_line(self, line):
		'''Get the row in the list for a specific line

		@param line: the line number for a line in the L{TextBuffer}
		@returns: the row id for a row in the list or C{None} when
		the line was outside of the list
		'''
		for i in range(len(self)):
			if self[i][self.LINE_COL] == line:
				return i
		else:
			return None

	def can_indent(self, row):
		'''Check whether a specific item in the list can be indented

		List items can only be indented if they are on top of the list
		or when there is some node above them to serve as new parent node.
		This avoids indenting two levels below the parent.

		So e.g. in the case of::

		  * item a
		  * item b

		then "item b" can indent and become a child of "item a".
		However after indenting once::

		  * item a
		      * item b

		now "item b" can not be indented further because it is already
		one level below "item a".

		@param row: the row id
		@returns: C{True} when indenting is possible
		'''
		if row == 0:
			return True
		else:
			parents = self._parents(row)
			if row - 1 in parents:
				return False # we are first child
			else:
				return True

	def can_unindent(self, row):
		'''Check if a specific item in the list has indenting which
		can be reduced

		@param row: the row id
		@returns: C{True} when the item has indenting
		'''
		return self[row][self.INDENT_COL] > 0

	def indent(self, row):
		'''Indent a list item and all it's children

		For example, when indenting "item b" in this list::

		  * item a
		  * item b
		      * item C

		it will result in::

		  * item a
		      * item b
		          * item C

		@param row: the row id
		@returns: C{True} if successfulll
		'''
		if not self.can_indent(row):
			return False
		with self.buffer.user_action:
			self._indent(row, 1)
		return True

	def unindent(self, row):
		'''Un-indent a list item and it's children

		@param row: the row id
		@returns: C{True} if successfulll
		'''
		if not self.can_unindent(row):
			return False
		with self.buffer.user_action:
			self._indent(row, -1)
		return True

	def _indent(self, row, step):
		line, level, bullet = self[row]
		self._indent_row(row, step)

		if row == 0:
			# Indent the whole list
			for i in range(1, len(self)):
				if self[i][self.INDENT_COL] >= level:
					# double check implicit assumption that first item is at lowest level
					self._indent_row(i, step)
				else:
					break
		else:
			# Indent children
			for i in range(row + 1, len(self)):
				if self[i][self.INDENT_COL] > level:
					self._indent_row(i, step)
				else:
					break

			# Renumber - *after* children have been updated as well
			# Do not restrict to number bullets - we might be moving
			# a normal bullet into a numbered sub list
			# TODO - pull logic of renumber_list_after_indent here and use just renumber_list
			self.buffer.renumber_list_after_indent(line, level)

	def _indent_row(self, row, step):
		#~ print("(UN)INDENT", row, step)
		line, level, bullet = self[row]
		newlevel = level + step
		if self.buffer.set_indent(line, newlevel):
			self.buffer.update_editmode() # also updates indent tag
			self[row] = (line, newlevel, bullet)

	def set_bullet(self, row, bullet):
		'''Set the bullet type for a specific item and update parents
		and children accordingly

		Used to (un-)check the checkboxes and synchronize child
		nodes and parent nodes. When a box is checked, any open child
		nodes are checked. Also when this is the last checkbox on the
		given level to be checked, the parent box can be checked as
		well. When a box is un-checked, also the parent checkbox is
		un-checked. Both updating of children and parents is recursive.

		@param row: the row id
		@param bullet: the bullet type, which can be one of::
			BULLET
			CHECKED_BOX
			UNCHECKED_BOX
			XCHECKED_BOX
			MIGRATED_BOX
			TRANSMIGRATED_BOX
		'''
		assert bullet in BULLETS
		with self.buffer.user_action:
			self._change_bullet_type(row, bullet)
			if bullet == UNCHECKED_BOX and self.recursive_checklist:
				self._checkbox_unchecked(row)
			elif bullet in CHECKBOXES and self.recursive_checklist:
				self._checkbox_checked(row, bullet)
			else:
				pass

	def _checkbox_unchecked(self, row):
		# When a row is unchecked, it's children are untouched but
		# all parents will be unchecked as well
		for parent in self._parents(row):
			if self[parent][self.BULLET_COL] not in CHECKBOXES:
				continue # ignore non-checkbox bullet

			self._change_bullet_type(parent, UNCHECKED_BOX)

	def _checkbox_checked(self, row, state):
		# If a row is checked, all un-checked children are updated as
		# well. For parent nodes we first check consistency of all
		# children before we check them.

		# First synchronize down
		level = self[row][self.INDENT_COL]
		for i in range(row + 1, len(self)):
			if self[i][self.INDENT_COL] > level:
				if self[i][self.BULLET_COL] == UNCHECKED_BOX:
					self._change_bullet_type(i, state)
				else:
					# ignore non-checkbox bullet
					# ignore xchecked items etc.
					pass
			else:
				break

		# Then go up, checking direct children for each parent
		# if children are inconsistent, do not change the parent
		# and break off updating parents. Do overwrite parents that
		# are already checked with a different type.
		for parent in self._parents(row):
			if self[parent][self.BULLET_COL] not in CHECKBOXES:
				continue # ignore non-checkbox bullet

			consistent = True
			level = self[parent][self.INDENT_COL]
			for i in range(parent + 1, len(self)):
				if self[i][self.INDENT_COL] <= level:
					break
				elif self[i][self.INDENT_COL] == level + 1 \
				and self[i][self.BULLET_COL] in CHECKBOXES \
				and self[i][self.BULLET_COL] != state:
					consistent = False
					break

			if consistent:
				self._change_bullet_type(parent, state)
			else:
				break

	def _change_bullet_type(self, row, bullet):
		line, indent, _ = self[row]
		self.buffer.set_bullet(line, bullet)
		self[row] = (line, indent, bullet)

	def _parents(self, row):
		# Collect row ids of parent nodes
		parents = []
		level = self[row][self.INDENT_COL]
		for i in range(row, -1, -1):
			if self[i][self.INDENT_COL] < level:
				parents.append(i)
				level = self[i][self.INDENT_COL]
		return parents

