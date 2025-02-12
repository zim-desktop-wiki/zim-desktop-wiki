# Copyright 2008-2023 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import logging


logger = logging.getLogger('zim.gui.pageview.undo')


from .serialize import *


class UndoActionGroup(list):
	'''Group of actions that should un-done or re-done in a single step

	Inherits from C{list}, so can be treates as a list of actions.
	See L{UndoStackManager} for more details on undo actions.

	@ivar can_merge: C{True} when this group can be merged with another
	group
	@ivar cursor: the position to restore the cursor afre un-/re-doning
	'''

	__slots__ = ('can_merge', 'cursor')

	def __init__(self):
		self.can_merge = False
		self.cursor = None

	def reversed(self):
		'''Returns a new UndoActionGroup with the reverse actions of
		this group.
		'''
		group = UndoActionGroup()
		group.cursor = self.cursor
		for action in self:
			# constants are defined such that negating them reverses the action
			action = (-action[0],) + action[1:]
			group.insert(0, action)
		return group


class UndoStackManager:
	'''Undo stack implementation for L{TextBuffer}. It records any
	changes to the buffer and allows undoing and redoing edits.

	The stack undostack will be folded when you undo a few steps and
	then start editing again. This means that even the 'undo' action
	is recorded in the undo stakc and can always be undone itself;
	so no data is discarded.

	Say you start with a certain buffer state "A", then make two edits
	("B" and "C") and then undo the last one, so you get back in state
	"B"::

	  State A --> State B --> State C
	                      <--
	                      undo

	when you now make a new edit ("D"), state "C" is not discarded, instead
	it is "folded" as follows::

	  State A --> State B --> State C --> State B --> State D

	so you can still go back to state "C" using Undo.

	Undo actions
	============

	Each action is recorded as a 4-tuple of:
	  - C{action_type}: one of C{ACTION_INSERT}, C{ACTION_DELETE},
	    C{ACTION_APPLY_TAG}, C{ACTION_REMOVE_TAG}
	  - C{start_iter}: a C{Gtk.TextIter}
	  - C{end_iter}: a C{Gtk.TextIter}
	  - C{data}: either a L{TextBufferInternalContents} or a C{Gtk.TextTag}

	These actions are low level operations, so they are

	Actions are collected as L{UndoActionGroup}s. When the user selects
	Undo or Redo we actually undo or redo a whole UndoActionGroup as a
	single step. E.g. inserting a link will consist of inserting the
	text and than applying the TextTag with the link data. These are
	technically two separate modifications of the TextBuffer, however
	when selecting Undo both are undone at once because they are
	combined in a single group.

	Typically when recording modifications the action groups are
	delimited by the begin-user-action and end-user-action signals of
	the L{TextBuffer}. (This is why we use the L{TextBuffer.user_action}
	attribute context manager in the TextBuffer code.)

	Also we try to group single-character inserts and deletes into words.
	This makes the stack more compact and makes the undo action more
	meaningful.
	'''

	# Each interactive action (e.g. every single key stroke) is wrapped
	# in a set of begin-user-action and end-user-action signals. We use
	# these signals to group actions. This implies that any sequence on
	# non-interactive actions will also end up in a single group. An
	# interactively created group consisting of a single character insert
	# or single character delete is a candidate for merging.

	MAX_UNDO = 100 #: Constant for the max number of undo steps to be remembered

	# Constants for action types - negating an action gives it opposite.
	ACTION_INSERT = 1 #: action type for inserting text
	ACTION_DELETE = -1 #: action type for deleting text
	ACTION_APPLY_TAG = 2 #: action type for applying a C{Gtk.TextTag}
	ACTION_REMOVE_TAG = -2 #: action type for removing a C{Gtk.TextTag}

	def __init__(self, textbuffer):
		'''Constructor

		@param textbuffer: a C{Gtk.TextBuffer}
		'''
		self.buffer = textbuffer
		self.stack = [] # stack of actions & action groups
		self.group = UndoActionGroup() # current group of actions
		self.interactive = False # interactive edit or not
		self.insert_pending = False # whether we need to call flush insert or not
		self.undo_count = 0 # number of undo steps that were done
		self.block_count = 0 # number of times block() was called
		self._insert_tree_start = None

		self.recording_handlers = [] # handlers to be blocked when not recording
		for signal, handler in (
			('undo-save-cursor', self.do_save_cursor),
			('insert-text', self.do_insert_text),
			('insert-pixbuf', self.do_insert_pixbuf),
			('insert-child-anchor', self.do_insert_pixbuf),
			('delete-range', self.do_delete_range),
			('begin-user-action', self.do_begin_user_action),
			('end-user-action', self.do_end_user_action),
		):
			self.recording_handlers.append(
				self.buffer.connect(signal, handler))

		for signal, handler in (
			('end-user-action', self.do_end_user_action),
		):
			self.recording_handlers.append(
				self.buffer.connect_after(signal, handler))

		for signal, action in (
			('apply-tag', self.ACTION_APPLY_TAG),
			('remove-tag', self.ACTION_REMOVE_TAG),
		):
			self.recording_handlers.append(
				self.buffer.connect(signal, self.do_change_tag, action))

		for signal, handler in (
			('begin-insert-tree', self.do_begin_insert_tree),
			('end-insert-tree', self.do_end_insert_tree),
		):
			self.buffer.connect_after(signal, handler)

		#~ self.buffer.connect_object('edit-textstyle-changed',
			#~ self.__class__._flush_if_typing, self)
		#~ self.buffer.connect_object('set-mark',
			#~ self.__class__._flush_if_typing, self)

	def clear_undostack(self):
		'''Clear all recorded information - intended for testing only'''
		self.stack = [] # stack of actions & action groups
		self.group = UndoActionGroup() # current group of actions
		self.interactive = False # interactive edit or not
		self.insert_pending = False # whether we need to call flush insert or not
		self.undo_count = 0 # number of undo steps that were done

	def block(self):
		'''Stop listening to events from the L{TextBuffer} until
		the next call to L{unblock()}. Any change in between will not
		be undo-able (and mess up the undo stack) unless it is recorded
		explicitly.

		The number of calls C{block()} and C{unblock()} is counted, so
		they can be called recursively.
		'''
		if self.block_count == 0:
			for id in self.recording_handlers:
				self.buffer.handler_block(id)
		self.block_count += 1

	def unblock(self):
		'''Start listening to events from the L{TextBuffer} again'''
		if self.block_count > 1:
			self.block_count -= 1
		else:
			for id in self.recording_handlers:
				self.buffer.handler_unblock(id)
			self.block_count = 0

	def do_save_cursor(self, buffer, iter):
		# Store the cursor position
		self.group.cursor = iter.get_offset()

	def do_begin_user_action(self, buffer):
		# Start a group of actions that will be undone as a single action
		if self.undo_count > 0:
			self.flush_redo_stack()

		if self.group:
			self.stack.append(self.group)
			self.group = UndoActionGroup()
			while len(self.stack) > self.MAX_UNDO:
				self.stack.pop(0)

		self.interactive = True

	def do_end_user_action(self, buffer):
		# End a group of actions that will be undone as a single action
		if self.group:
			self.stack.append(self.group)
			self.group = UndoActionGroup()
			while len(self.stack) > self.MAX_UNDO:
				self.stack.pop(0)

		self.interactive = False

	def do_begin_insert_tree(self, buffer, interactive):
		if self.block_count == 0:
			if self.undo_count > 0:
				self.flush_redo_stack()
			elif self.insert_pending:
				self.flush_insert()
			# Do not start new group here - insert tree can be part of bigger change

			self._insert_tree_start = buffer.get_insert_iter().get_offset()
		self.block()

	def do_end_insert_tree(self, buffer):
		self.unblock()
		if self.block_count == 0:
			start = self._insert_tree_start
			start_iter = buffer.get_iter_at_offset(start)
			end_iter = buffer.get_insert_iter()
			end = end_iter.get_offset()
			data = textbuffer_internal_serialize_range(self.buffer, start_iter, end_iter)
			self.group.append((self.ACTION_INSERT, start, end, data))

	def do_insert_text(self, buffer, iter, text, length):
		# Handle insert text event
		# Do not use length argument, it gives length in bytes, not characters
		length = len(text)
		if self.undo_count > 0:
			self.flush_redo_stack()

		start = iter.get_offset()
		end = start + length
		#~ print('INSERT at %i: "%s" (%i)' % (start, text, length))

		if length == 1 and not text.isspace() \
		and self.interactive and not self.group:
			# we can merge
			if self.stack and self.stack[-1].can_merge:
				previous = self.stack[-1][-1]
				if previous[0] == self.ACTION_INSERT \
				and previous[2] == start \
				and previous[3] is None:
					# so can previous group - let's merge
					self.group = self.stack.pop()
					self.group[-1] = (self.ACTION_INSERT, previous[1], end, None)
					return
			# we didn't merge - set flag for next
			self.group.can_merge = True

		self.group.append((self.ACTION_INSERT, start, end, None))
		self.insert_pending = True

	def do_insert_pixbuf(self, buffer, iter, pixbuf):
		# Handle insert pixbuf event
		if self.undo_count > 0:
			self.flush_redo_stack()
		elif self.insert_pending:
			self.flush_insert()

		start = iter.get_offset()
		end = start + 1
		#~ print('INSERT PIXBUF at %i' % start)
		self.group.append((self.ACTION_INSERT, start, end, None))
		self.group.can_merge = False
		self.insert_pending = True

	def flush_insert(self):
		'''Flush all pending actions and store them on the stack

		The reason for this method is that because of the possibility of
		merging actions we do not immediatly request the serialization for
		each single character insert. Instead we first group inserts
		based on cursor positions and then request the serialization for
		the group at once. This method proceses all such delayed
		requests.
		'''
		def _flush_group(group):
			for i in reversed(list(range(len(group)))):
				action, start, end, data = group[i]
				if action == self.ACTION_INSERT and data is None:
					bounds = (self.buffer.get_iter_at_offset(start),
								self.buffer.get_iter_at_offset(end))
					data = textbuffer_internal_serialize_range(self.buffer, *bounds)
					#~ print('FLUSH %i to %i\n\t%s' % (start, end, data))
					group[i] = (self.ACTION_INSERT, start, end, data)
				else:
					return False
			return True

		if _flush_group(self.group):
			for i in reversed(list(range(len(self.stack)))):
				if not _flush_group(self.stack[i]):
					break

		self.insert_pending = False

	def do_delete_range(self, buffer, start, end):
		# Handle deleting text
		if self.undo_count > 0:
			self.flush_redo_stack()
		elif self.insert_pending:
			self.flush_insert()

		data = textbuffer_internal_serialize_range(self.buffer, start, end)
		start, end = start.get_offset(), end.get_offset()
		#~ print('DELETE RANGE from %i to %i\n\t%s' % (start, end, data))
		self.group.append((self.ACTION_DELETE, start, end, data))
		self.group.can_merge = False

	def do_change_tag(self, buffer, tag, start, end, action):
		assert action in (self.ACTION_APPLY_TAG, self.ACTION_REMOVE_TAG)
		if not hasattr(tag, 'zim_tag'):
			return

		start, end = start.get_offset(), end.get_offset()
		if self.group \
		and self.group[-1][0] == self.ACTION_INSERT \
		and self.group[-1][1] <= start \
		and self.group[-1][2] >= end \
		and self.group[-1][3] is None:
			pass # for text that is not yet flushed tags will be in the tree
		else:
			if self.undo_count > 0:
				self.flush_redo_stack()
			elif self.insert_pending:
				self.flush_insert()

			#~ print('TAG CHANGED', start, end, tag)
			self.group.append((action, start, end, tag))
			self.group.can_merge = False

	def undo(self):
		'''Undo one user action'''
		if self.group:
			self.stack.append(self.group)
			self.group = UndoActionGroup()
		if self.insert_pending:
			self.flush_insert()

		#~ import pprint
		#~ pprint.pprint( self.stack )

		l = len(self.stack)
		if self.undo_count == l:
			return False
		else:
			self.undo_count += 1
			i = l - self.undo_count
			self._replay(self.stack[i].reversed())
			return True

	def flush_redo_stack(self):
		'''Fold the "redo" part of the stack, called before new actions
		are appended after some step was undone.
		'''
		i = len(self.stack) - self.undo_count
		fold = UndoActionGroup()
		for group in reversed(self.stack[i:]):
			fold.extend(group.reversed())
		self.stack.append(fold)
		self.undo_count = 0

	def redo(self):
		'''Redo one user action'''
		if self.undo_count == 0:
			return False
		else:
			assert not self.group, 'BUG: undo count should have been zero'
			i = len(self.stack) - self.undo_count
			self._replay(self.stack[i])
			self.undo_count -= 1
			return True

	def _replay(self, actiongroup):
		self.block()

		#print('='*80)
		for action, start, end, data in actiongroup:
			#print(action, start, end, data)
			iter = self.buffer.get_iter_at_offset(start)
			bound = self.buffer.get_iter_at_offset(end)

			if action == self.ACTION_INSERT:
				self.buffer.place_cursor(iter)
				textbuffer_internal_insert_at_cursor(self.buffer, data)
			elif action == self.ACTION_DELETE:
				self.buffer.place_cursor(iter)
				current_data = textbuffer_internal_serialize_range(self.buffer, iter, bound)
				if current_data != data:
					if current_data.to_xml() != data.to_xml():
						logger.warning('Mismatch in undo stack\nGOT: %s\nEXP: %s\n', current_data, data)
					else:
						pass # to_xml() flattens e.g. integer arguments to string, ignore such differences here
				with self.buffer.user_action:
					with self.buffer.do_pre_delete_range.blocked():
						with self.buffer.do_post_delete_range.blocked():
							self.buffer.delete(iter, bound)
			elif action == self.ACTION_APPLY_TAG:
				self.buffer.apply_tag(data, iter, bound)
				self.buffer.place_cursor(bound)
			elif action == self.ACTION_REMOVE_TAG:
				self.buffer.remove_tag(data, iter, bound)
				self.buffer.place_cursor(bound)
			else:
				assert False, 'BUG: unknown action type'

		if not actiongroup.cursor is None:
			iter = self.buffer.get_iter_at_offset(actiongroup.cursor)
			self.buffer.place_cursor(iter)

		self.unblock()

