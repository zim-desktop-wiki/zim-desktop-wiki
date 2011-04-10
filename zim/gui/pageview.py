# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains the core of the interactive editor. It includes all
classes needed to display and edit a single page as well as related dialogs
like the dialogs to insert images, links etc.'''

from __future__ import with_statement

import logging

import gobject
import gtk
import pango
import re
import string
import datetime

import zim.fs
from zim.fs import *
from zim.errors import Error
from zim.notebook import Path, interwiki_link
from zim.parsing import link_type, Re, url_re
from zim.config import config_file
from zim.formats import get_format, \
	ParseTree, TreeBuilder, ParseTreeBuilder, \
	BULLET, CHECKED_BOX, UNCHECKED_BOX, XCHECKED_BOX
from zim.gui.widgets import ui_environment, \
	Dialog, FileDialog, ErrorDialog, \
	Button, IconButton, MenuButton, BrowserTreeView, InputEntry, \
	rotate_pixbuf
from zim.gui.applications import OpenWithMenu
from zim.gui.clipboard import Clipboard, \
	PARSETREE_ACCEPT_TARGETS, parsetree_from_selectiondata

logger = logging.getLogger('zim.gui.pageview')


STOCK_CHECKED_BOX = 'zim-checked-box'
STOCK_UNCHECKED_BOX = 'zim-unchecked-box'
STOCK_XCHECKED_BOX = 'zim-xchecked-box'

bullet_types = {
	CHECKED_BOX: STOCK_CHECKED_BOX,
	UNCHECKED_BOX: STOCK_UNCHECKED_BOX,
	XCHECKED_BOX: STOCK_XCHECKED_BOX,
}
# reverse dict
bullets = {}
for bullet in bullet_types:
	bullets[bullet_types[bullet]] = bullet

# E.g. Maemo devices have no hardware [] keys,
# so allow () to be used for the same purpose
autoformat_bullets = {
	'*': BULLET,
	'[]': UNCHECKED_BOX,
	'[*]': CHECKED_BOX,
	'[x]': XCHECKED_BOX,
	'()': UNCHECKED_BOX,
	'(*)': CHECKED_BOX,
	'(x)': XCHECKED_BOX,
}

BULLETS = (BULLET, UNCHECKED_BOX, CHECKED_BOX, XCHECKED_BOX)
CHECKBOXES = (UNCHECKED_BOX, CHECKED_BOX, XCHECKED_BOX)


# Check the (undocumented) list of constants in gtk.keysyms to see all names
KEYVALS_HOME = map(gtk.gdk.keyval_from_name, ('Home', 'KP_Home'))
KEYVALS_ENTER = map(gtk.gdk.keyval_from_name, ('Return', 'KP_Enter', 'ISO_Enter'))
KEYVALS_BACKSPACE = map(gtk.gdk.keyval_from_name, ('BackSpace',))
KEYVALS_TAB = map(gtk.gdk.keyval_from_name, ('Tab', 'KP_Tab'))
KEYVALS_LEFT_TAB = map(gtk.gdk.keyval_from_name, ('ISO_Left_Tab',))

#~ CHARS_END_OF_WORD = (' ', ')', '>', '.', '!', '?')
CHARS_END_OF_WORD = ('\t', ' ', ')', '>')
KEYVALS_END_OF_WORD = map(
	gtk.gdk.unicode_to_keyval, map(ord, CHARS_END_OF_WORD)) + KEYVALS_TAB

KEYVALS_ASTERISK = (
	gtk.gdk.unicode_to_keyval(ord('*')), gtk.gdk.keyval_from_name('KP_Multiply'))
KEYVALS_SLASH = (
	gtk.gdk.unicode_to_keyval(ord('/')), gtk.gdk.keyval_from_name('KP_Divide'))
KEYVALS_GT = (gtk.gdk.unicode_to_keyval(ord('>')),)
KEYVALS_SPACE = (gtk.gdk.unicode_to_keyval(ord(' ')),)

KEYVAL_ESC = gtk.gdk.keyval_from_name('Escape')

# States that influence keybindings - we use this to explicitly
# exclude other states. E.g. MOD2_MASK seems to be set when either
# numlock or fn keys are active, resulting in keybindings failing
KEYSTATES = (gtk.gdk.CONTROL_MASK, gtk.gdk.SHIFT_MASK, gtk.gdk.MOD1_MASK)

ui_actions = (
	# name, stock id, label, accelerator, tooltip, readonly
	('undo', 'gtk-undo', _('_Undo'), '<ctrl>Z', '', False), # T: Menu item
	('redo', 'gtk-redo', _('_Redo'), '<ctrl><shift>Z', '', False), # T: Menu item
	('cut', 'gtk-cut', _('Cu_t'), '<ctrl>X', '', False), # T: Menu item
	('copy', 'gtk-copy', _('_Copy'), '<ctrl>C', '', False), # T: Menu item
	('paste', 'gtk-paste', _('_Paste'), '<ctrl>V', '', False), # T: Menu item
	('delete', 'gtk-delete', _('_Delete'), '', '', False), # T: Menu item
	('toggle_checkbox', STOCK_CHECKED_BOX, _('Toggle Checkbox \'V\''), 'F12', '', False), # T: Menu item
	('xtoggle_checkbox', STOCK_XCHECKED_BOX, _('Toggle Checkbox \'X\''), '<shift>F12', '', False), # T: Menu item
	('edit_object', 'gtk-properties', _('_Edit Link or Object...'), '<ctrl>E', '', False), # T: Menu item
	('remove_link', None, _('_Remove Link'), '', '', False), # T: Menu item
	('insert_date', None, _('_Date and Time...'), '<ctrl>D', '', False), # T: Menu item
	('insert_image', None, _('_Image...'), '', '', False), # T: Menu item
	('insert_bullet_list', None, _('Bulle_t List'), '', '', False), # T: Menu item
	('insert_checkbox_list', None, _('Checkbo_x List'), '', '', False), # T: Menu item),
	('apply_format_bullet_list', None, _('Bulle_t List'), '', '', False), # T: Menu item),
	('apply_format_checkbox_list', None, _('Checkbo_x List'), '', '', False), # T: Menu item),
	('insert_text_from_file', None, _('Text From _File...'), '', '', False), # T: Menu item
	('insert_link', 'zim-link', _('_Link...'), '<ctrl>L', _('Insert Link'), False), # T: Menu item
	('clear_formatting', None, _('_Clear Formatting'), '<ctrl>9', '', False), # T: Menu item
	('show_find', 'gtk-find', _('_Find...'), '<ctrl>F', '', True), # T: Menu item
	('find_next', None, _('Find Ne_xt'), '<ctrl>G', '', True), # T: Menu item
	('find_previous', None, _('Find Pre_vious'), '<ctrl><shift>G', '', True), # T: Menu item
	('show_find_and_replace', 'gtk-find-and-replace', _('_Replace...'), '<ctrl>H', '', False), # T: Menu item
	('show_word_count', None, _('Word Count...'), '', '', True), # T: Menu item
	('zoom_in', 'gtk-zoom-in', _('_Zoom In'), '<ctrl>plus', '', True), # T: Menu item
	('zoom_out', 'gtk-zoom-out', _('Zoom _Out'), '<ctrl>minus', '', True), # T: Menu item
	('zoom_reset', 'gtk-zoom-100', _('_Normal Size'), '<ctrl>0', '', True), # T: Menu item to reset zoom
)

ui_format_actions = (
	# name, stock id, label, accelerator, tooltip
	('apply_format_h1', None, _('Heading _1'), '<ctrl>1', _('Heading 1')), # T: Menu item
	('apply_format_h2', None, _('Heading _2'), '<ctrl>2', _('Heading 2')), # T: Menu item
	('apply_format_h3', None, _('Heading _3'), '<ctrl>3', _('Heading 3')), # T: Menu item
	('apply_format_h4', None, _('Heading _4'), '<ctrl>4', _('Heading 4')), # T: Menu item
	('apply_format_h5', None, _('Heading _5'), '<ctrl>5', _('Heading 5')), # T: Menu item
	('apply_format_strong', 'gtk-bold', _('_Strong'), '<ctrl>B', _('Strong')), # T: Menu item
	('apply_format_emphasis', 'gtk-italic', _('_Emphasis'), '<ctrl>I', _('Emphasis')), # T: Menu item
	('apply_format_mark', 'gtk-underline', _('_Mark'), '<ctrl>U', _('Mark')), # T: Menu item
	('apply_format_strike', 'gtk-strikethrough', _('_Strike'), '<ctrl>K', _('Strike')), # T: Menu item
	('apply_format_sub', None, _('_Subscript'), '', _('_Subscript')), # T: Menu item
	('apply_format_sup', None, _('_Superscript'), '', _('_Superscript')), # T: Menu item
	('apply_format_code', None, _('_Verbatim'), '<ctrl>T', _('Verbatim')), # T: Menu item
)

ui_format_toggle_actions = (
	# name, stock id, label, accelerator, tooltip
	('toggle_format_strong', 'gtk-bold', _('_Strong'), '', _('Strong')),
	('toggle_format_emphasis', 'gtk-italic', _('_Emphasis'), '', _('Emphasis')),
	('toggle_format_mark', 'gtk-underline', _('_Mark'), '', _('Mark')),
	('toggle_format_strike', 'gtk-strikethrough', _('_Strike'), '', _('Strike')),
)

ui_preferences = (
	# key, type, category, label, default
	('follow_on_enter', 'bool', 'Interface',
		_('Use the <Enter> key to follow links\n(If disabled you can still use <Alt><Enter>)'), True),
		# T: option in preferences dialog
	('read_only_cursor', 'bool', 'Interface',
		_('Show the cursor also for pages that can not be edited'), False),
		# T: option in preferences dialog
	('autolink_camelcase', 'bool', 'Editing',
		_('Automatically turn "CamelCase" words into links'), True),
		# T: option in preferences dialog
	('autolink_files', 'bool', 'Editing',
		_('Automatically turn file paths into links'), True),
		# T: option in preferences dialog
	('autoselect', 'bool', 'Editing',
		_('Automatically select the current word when you apply formatting'), True),
		# T: option in preferences dialog
	('unindent_on_backspace', 'bool', 'Editing',
		_('Unindent on <BackSpace>\n(If disabled you can still use <Shift><Tab>)'), True),
		# T: option in preferences dialog
	('cycle_checkbox_type', 'bool', 'Editing',
		_('Repeated clicking a checkbox cyles through the checkbox states'), True),
		# T: option in preferences dialog
	('recursive_indentlist', 'bool', 'Editing',
		_('(Un-)Indenting a list item also change any sub-items'), True),
		# T: option in preferences dialog
	('recursive_checklist', 'bool', 'Editing',
		_('Checking a checkbox also change any sub-items'), False),
		# T: option in preferences dialog
	('auto_reformat', 'bool', 'Editing',
		_('Reformat wiki markup on the fly'), False),
		# T: option in preferences dialog
	('copy_format', 'choice', 'Editing',
		_('Default format for copying text to the clipboard'), 'Text', ('Text', 'Wiki')),
		# T: option in preferences dialog
)

if ui_environment['platform'] == 'maemo':
	# Manipulate preferences with Maemo specific settings
	ui_preferences = list(ui_preferences)
	for i in range(len(ui_preferences)):
		if ui_preferences[i][0] == 'follow_on_enter':
			ui_preferences[i] = \
				('follow_on_enter', 'bool', None, None, True)
				# There is no ALT key on maemo devices
		elif ui_preferences[i][0] == 'unindent_on_backspace':
			ui_preferences[i] = \
				('unindent_on_backspace', 'bool', None, None, True)
				# There is no hardware TAB key on maemo devices
	ui_preferences = tuple(ui_preferences)


_is_zim_tag = lambda tag: hasattr(tag, 'zim_type')
_is_indent_tag = lambda tag: _is_zim_tag(tag) and tag.zim_type == 'indent'
_is_not_indent_tag = lambda tag: _is_zim_tag(tag) and tag.zim_type != 'indent'
_is_heading_tag = lambda tag: hasattr(tag, 'zim_tag') and tag.zim_tag == 'h'
_is_pre_tag = lambda tag: hasattr(tag, 'zim_tag') and tag.zim_tag == 'pre'
_is_line_based_tag = lambda tag: _is_indent_tag(tag) or _is_heading_tag(tag) or _is_pre_tag(tag)
_is_not_line_based_tag = lambda tag: not _is_line_based_tag(tag)
_is_style_tag = lambda tag: _is_zim_tag(tag) and tag.zim_type == 'style'
_is_not_style_tag = lambda tag: not (_is_zim_tag(tag) and tag.zim_type == 'style')
_is_link_tag = lambda tag: _is_zim_tag(tag) and tag.zim_type == 'link'
_is_not_link_tag = lambda tag: not (_is_zim_tag(tag) and tag.zim_type == 'link')
_is_tag_tag = lambda tag: _is_zim_tag(tag) and tag.zim_type == 'tag'
_is_not_tag_tag = lambda tag: not (_is_zim_tag(tag) and tag.zim_type == 'tag')

PIXBUF_CHR = u'\uFFFC'

# Regexes used for autoformatting
heading_re = Re(r'^(={2,7})\s*(.*)\s*(\1)?$')
page_re = Re(r'''(
	  [\w\.\-\(\)]*(?: :[\w\.\-\(\)]{2,} )+:?
	| \+\w[\w\.\-\(\)]+(?: :[\w\.\-\(\)]{2,} )*:?
)$''', re.X | re.U) # e.g. namespace:page or +subpage, but not word without ':' or '+'
interwiki_re = Re(r'\w[\w\+\-\.]+\?\w\S+$', re.U) # name?page, where page can be any url style
file_re = Re(r'''(
	  ~/[^/\s]
	| ~[^/\s]*/
	| \.\.?/
	| /[^/\s]
)\S*$''', re.X | re.U) # ~xxx/ or ~name/xxx or ../xxx  or ./xxx  or /xxx

markup_re = {'style-strong' : Re(r'(\*{2})(.*)\1'),
	'style-emphasis' : Re(r'(\/{2})(.*)\1'),
	'style-mark' : Re(r'(_{2})(.*)\1'),
	'style-pre' : Re(r'(\'{2})(.*)\1'),
	'style-strike' : Re(r'(~{2})(.*)\1')}

tag_re = Re(r'^(@\w+)$')

# These sets adjust to the current locale - so not same as "[a-z]" ..
# Must be kidding - no classes for this in the regex engine !?
_classes = {
	'upper': string.uppercase,
	'lower': string.lowercase,
	'letters': string.letters
}
camelcase_re = Re(r'[%(upper)s]+[%(lower)s]+[%(upper)s]+\w*$' % _classes)
twoletter_re = re.compile(r'[%(letters)s]{2}' % _classes)
del _classes


class UserActionContext(object):
	'''Class used for the TextBuffer.user_action attribute.
	This allows syntax like:

		with buffer.user_action:
			buffer.insert(...)

	instead off:

		buffer.begin_user_action()
		buffer.insert(...)
		buffer.end_user_action()
	'''

	def __init__(self, buffer):
		self.buffer = buffer

	def __enter__(self):
		self.buffer.begin_user_action()

	def __exit__(self, *a):
		self.buffer.end_user_action()


class SaveCursorContext(object):
	'''Class used by TextBuffer.tmp_cursor().
	This allows syntax like:

		with buffer.tmp_cursor(iter):
			# some manipulation using iter as cursor position

		# old cursor position restored

	Basically it keeps a mark for the old cursor and restores it
	after exiting the context.
	'''

	def __init__(self, buffer, iter=None):
		self.buffer = buffer
		self.iter = iter
		self.mark = None

	def __enter__(self):
		buffer = self.buffer
		cursor = buffer.get_iter_at_mark(buffer.get_insert())
		self.mark = buffer.create_mark(None, cursor, left_gravity=True)
		if self.iter:
			buffer.place_cursor(self.iter)

	def __exit__(self, *a):
		buffer = self.buffer
		iter = buffer.get_iter_at_mark(self.mark)
		buffer.place_cursor(iter)
		buffer.delete_mark(self.mark)


class TextBuffer(gtk.TextBuffer):
	'''Zim subclass of gtk.TextBuffer.

	This class manages the contents of a TextView widget. It can load a zim
	parsetree and after editing return a new parsetree. It manages images,
	links, bullet lists etc.

	The styles supported are given in the dict 'tag_styles'. These map to
	like named TextTags. For links anonymous TextTags are used. Not all tags
	are styles though, e.g. gtkspell uses it's own tags and tags may also
	be used to highlight search results etc.

	As far as this class is concerned bullet and checkbox lists are just
	a number of lines that start with a bullet (checkboxes are also
	considered bullets) and that may have an indenting. There is some
	logic to keep list formatting nice but it only applies to one line
	at a time. For functionality affecting a list as a whole see the
	TextBufferList class.

	Signals:
		* begin-insert-tree ()
		  Emitted at the begin of a complex insert
		* end-insert-tree ()
		  Emitted at the end of a complex insert
		* inserted-tree (start, end, tree, interactive)
		  Gives inserted tree after inserting it
		* textstyle-changed (style)
		  Emitted when textstyle at the cursor changes
		* clear ()
		  emitted to clear the whole buffer before destruction
		* undo-save-cursor (iter)
		  emitted in some specific case where the undo stack should
		  lock the current cursor position
	'''

	# We rely on the priority of gtk TextTags to sort links before styles,
	# and styles before indenting. Since styles are initialized on init,
	# while indenting tags are created when needed, indenting tags always
	# have the higher priority. By explicitly lowering the priority of new
	# link tags to zero we keep those tags on the lower endof the scale.


	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'insert-text': 'override',
		'begin-insert-tree': (gobject.SIGNAL_RUN_LAST, None, ()),
		'end-insert-tree': (gobject.SIGNAL_RUN_LAST, None, ()),
		'inserted-tree': (gobject.SIGNAL_RUN_LAST, None, (object, object, object, object)),
		'textstyle-changed': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'clear': (gobject.SIGNAL_RUN_LAST, None, ()),
		'undo-save-cursor': (gobject.SIGNAL_RUN_LAST, None, (object,)),
	}

	# style attributes
	pixels_indent = 30

	# text tags supported by the editor and default stylesheet
	tag_styles = {
		'h1': {'weight': pango.WEIGHT_BOLD, 'scale': 1.15**4},
		'h2': {'weight': pango.WEIGHT_BOLD, 'scale': 1.15**3},
		'h3': {'weight': pango.WEIGHT_BOLD, 'scale': 1.15**2},
		'h4': {'weight': pango.WEIGHT_ULTRABOLD, 'scale': 1.15},
		'h5': {'weight': pango.WEIGHT_BOLD, 'scale': 1.15, 'style': 'italic'},
		'h6': {'weight': pango.WEIGHT_BOLD, 'scale': 1.15},
		'emphasis': {'style': 'italic'},
		'strong': {'weight': pango.WEIGHT_BOLD},
		'mark': {'background': 'yellow'},
		'strike': {'strikethrough': 'true', 'foreground': 'grey'},
		'code': {'family': 'monospace'},
		'pre': {'family': 'monospace', 'wrap-mode': 'none'},
		'sub': {'rise': -3500, 'scale':0.7},
		'sup': {'rise': 7500, 'scale':0.7},
		'link': {'foreground': 'blue'},
		'tag': {'foreground': '#ce5c00'},
		'indent': {},
		'bullet-list': {},
		'unchecked-checkbox': {},
		'checked-checkbox': {},
		'xchecked-checkbox': {},
		'find-highlight': {'background': 'orange'},
	}
	static_style_tags = (
		'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
		'emphasis', 'strong', 'mark', 'strike',
		'code', 'pre',
		'sub', 'sup'
	)

	# possible attributes for styles in tag_styles
	tag_attributes = set( (
		'weight', 'scale', 'style', 'background', 'foreground', 'strikethrough',
		'family', 'wrap-mode', 'indent', 'underline'
	) )

	def __init__(self, notebook=None, page=None):
		gtk.TextBuffer.__init__(self)
		self.notebook = notebook
		self.page = page
		self._insert_tree_in_progress = False
		self.user_action = UserActionContext(self)
		self.finder = TextFinder(self)

		for name in self.static_style_tags:
			tag = self.create_tag('style-'+name, **self.tag_styles[name])
			tag.zim_type = 'style'
			if name in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
				# This is needed to get proper output in get_parse_tree
				tag.zim_tag = 'h'
				tag.zim_attrib = {'level': int(name[1])}
			else:
				tag.zim_tag = name
				tag.zim_attrib = None

		self._editmode_tags = ()

		#~ import sys
		#~ for s in (
			#~ 'apply-tag', 'remove-tag',
			#~ 'delete-range', 'insert-pixbuf', 'insert-text',
			#~ 'mark-deleted', 'mark-set'
			#~ 'changed', , 'modified-changed',
		#~ ):
			#~ self.connect(s, lambda *a: sys.stderr.write('>>> %s\n' % a[-1]), s)

	def clear(self):
		'''Clear all content from the buffer'''
		self.emit('clear')

	def do_clear(self):
		self._editmode_tags = []
		self.delete(*self.get_bounds())

	def get_insert_iter(self):
		return self.get_iter_at_mark(self.get_insert())

	def tmp_cursor(self, iter=None):
		'''Returns a SaveCursorContext object'''
		return SaveCursorContext(self, iter)

	def set_parsetree(self, tree):
		'''Load a new ParseTree in the buffer, first flushes existing content'''
		self.clear()
		try:
			self.insert_parsetree_at_cursor(tree)
		except:
			# Prevent auto-save to kick in at any cost
			self.set_modified(False)
			raise
		else:
			self.set_modified(False)

	def insert_parsetree(self, iter, tree, interactive=False):
		'''Insert a ParseTree within the existing buffer at iter.

		The boolean 'interactive' determines how current state in
		the buffer is handled. If not interactive we break any existing
		tags and insert the tree, otherwise we insert using the
		formatting tags that that are present at iter.
		'''
		with self.tmp_cursor(iter):
			self.insert_parsetree_at_cursor(tree, interactive)

	def insert_parsetree_at_cursor(self, tree, interactive=False):
		'''Like insert_parsetree() but inserts at the cursor'''
		#~ print 'INSERT AT CURSOR', tree.tostring()

		# Check tree
		root = tree.getroot()
		assert root.tag == 'zim-tree'
		raw = root.attrib.get('raw')
		if isinstance(raw, basestring):
			raw = (raw != 'False')

		# Check if we are at a bullet or checkbox line
		iter = self.get_iter_at_mark(self.get_insert())
		if not raw and iter.starts_line() \
		and not tree.get_ends_with_newline():
			bullet = self._get_bullet_at_iter(iter)
			if bullet:
				self._iter_forward_past_bullet(iter, bullet)
				self.place_cursor(iter)

		# Prepare
		startoffset = iter.get_offset()
		if not interactive:
			self._editmode_tags = ()
		tree.decode_urls()

		# Actual insert
		modified = self.get_modified()
		try:
			self.emit('begin-insert-tree')
			if root.text:
				self.insert_at_cursor(root.text)
			self._insert_element_children(root, raw=raw)
		except:
			# Try to recover buffer state before raising
			self.update_editmode()
			startiter = self.get_iter_at_offset(startoffset)
			enditer = self.get_iter_at_mark(self.get_insert())
			self.delete(start, end)
			self.set_modified(modified)
			self.emit('end-insert-tree')
			raise
		else:
			# Signal the tree that was inserted
			self.update_editmode()
			startiter = self.get_iter_at_offset(startoffset)
			enditer = self.get_iter_at_mark(self.get_insert())
			self.emit('end-insert-tree')
			self.emit('inserted-tree', startiter, enditer, tree, interactive)

	def do_begin_insert_tree(self):
		self._insert_tree_in_progress = True

	def do_end_insert_tree(self):
		self._insert_tree_in_progress = False
		self.emit('textstyle-changed', self.get_textstyle())
			# emitting textstyle-changed is skipped while loading the tree

	def _insert_element_children(self, node, list_level=-1, raw=False):
		# FIXME should load list_level from cursor position
		#~ list_level = get_indent --- with bullets at indent 0 this is not bullet proof...

		def set_indent(level, bullet=None):
			# Need special set_indent() function here because the normal
			# function affects the whole line. THis has unwanted side
			# effects when we e.g. paste a multi-line tree in the
			# middle of a indented line.
			# In contrast to the normal set_indent we treat level=None
			# and level=0 as different cases.
			self._editmode_tags = filter(_is_not_indent_tag, self._editmode_tags)
			if level is None:
				return # Nothing more to do

			iter = self.get_insert_iter()
			if not iter.starts_line():
				# Check existing indent - may have bullet type while we have not
				tags = filter(_is_indent_tag, self.iter_get_zim_tags(iter))
				assert len(tags) <= 1, 'BUG: overlapping indent tags'
				if tags and int(tags[0].zim_attrib['indent']) == level:
					self._editmode_tags += (tags[0],)
					return # Re-use tag

			tag = self._get_indent_tag(level, bullet)
			self._editmode_tags += (tag,)

		def force_line_start():
			# Inserts a newline if we are not at the beginning of a line
			# makes pasting a tree halfway in a line more sane
			if not raw:
				iter = self.get_iter_at_mark( self.get_insert() )
				if not iter.starts_line():
					self.insert_at_cursor('\n')

		for element in node.getchildren():
			if element.tag in ('p', 'div'):
				# No force line start here on purpose
				if 'indent' in element.attrib:
					set_indent(int(element.attrib['indent']))
				else:
					set_indent(None)

				if element.text:
					self.insert_at_cursor(element.text)

				self._insert_element_children(element, list_level=list_level, raw=raw) # recurs

				set_indent(None)
			elif element.tag == 'ul':
				if 'indent' in element.attrib:
					indent = int(element.attrib['indent'])
					self._insert_element_children(element, list_level=indent, raw=raw) # recurs
				else:
					self._insert_element_children(element, list_level=list_level+1, raw=raw) # recurs

				set_indent(None)
			elif element.tag == 'li':
				force_line_start()

				if list_level < 0:
					list_level = 0 # We skipped the <ul> - raw tree ?
				if 'indent' in element.attrib:
					list_level = int(element.attrib['indent'])

				if 'bullet' in element.attrib and element.attrib['bullet'] != '*':
					bullet = element.attrib['bullet']
				else:
					bullet = BULLET # default to '*'

				set_indent(list_level, bullet)
				self._insert_bullet_at_cursor(bullet, raw=raw)

				if element.text:
					self.insert_at_cursor(element.text)

				self._insert_element_children(element, list_level=list_level, raw=raw) # recurs
				set_indent(None)

				if not raw:
					self.insert_at_cursor('\n')

			elif element.tag == 'link':
				self.set_textstyle(None) # Needed for interactive insert tree after paste
				self.insert_link_at_cursor(element.text, **element.attrib)
			elif element.tag == 'tag':
				self.set_textstyle(None) # Needed for interactive insert tree after paste
				self.insert_tag_at_cursor(element.text, **element.attrib)
			elif element.tag == 'img':
				file = element.attrib['_src_file']
				self.insert_image_at_cursor(file, alt=element.text, **element.attrib)
			elif element.tag == 'pre':
				if 'indent' in element.attrib:
					set_indent(int(element.attrib['indent']))
				self.set_textstyle(element.tag)
				if element.text:
					self.insert_at_cursor(element.text)
				self.set_textstyle(None)
				set_indent(None)
			else:
				# Text styles
				if element.tag == 'h':
					force_line_start()
					tag = 'h'+str(element.attrib['level'])
					self.set_textstyle(tag)
				elif element.tag in self.static_style_tags:
					self.set_textstyle(element.tag)
				else:
					assert False, 'Unknown tag: %s' % element.tag

				if element.text:
					self.insert_at_cursor(element.text)
				self.set_textstyle(None)

			if element.tail:
				self.insert_at_cursor(element.tail)

	def insert_link(self, iter, text, href, **attrib):
		'''Insert a link into the buffer at iter'''
		with self.tmp_cursor(iter):
			self.insert_link_at_cursor(text, href, **attrib)

	def insert_link_at_cursor(self, text, href=None, **attrib):
		'''Like insert_link() but inserts at the cursor'''
		tag = self.create_link_tag(text, href, **attrib)
		self._editmode_tags = \
			filter(_is_not_link_tag,
				filter(_is_not_style_tag, self._editmode_tags) ) + (tag,)
		self.insert_at_cursor(text)
		self._editmode_tags = self._editmode_tags[:-1]

	def create_link_tag(self, text, href, **attrib):
		if isinstance(href, File):
			href = href.uri
		assert isinstance(href, basestring)

		tag = self.create_tag(None, **self.tag_styles['link'])
		tag.set_priority(0) # force links to be below styles
		tag.zim_type = 'link'
		tag.zim_tag = 'link'
		tag.zim_attrib = attrib
		if href == text:
			tag.zim_attrib['href'] = None
		else:
			tag.zim_attrib['href'] = href
		return tag

	def get_link_tag(self, iter):
		# Explicitly left gravity, otherwise position behind the link
		# would alos be consifered part of the link. Position before the
		# link is included here.
		for tag in iter.get_tags():
			if hasattr(tag, 'zim_type') and tag.zim_type == 'link':
				return tag
		else:
			return None

	def get_link_data(self, iter):
		'''Returns the dict with link properties for a link at iter.
		Fails silently and returns None when there is no link at iter.
		'''
		tag = self.get_link_tag(iter)

		if tag:
			link = tag.zim_attrib.copy()
			if link['href'] is None:
				# Copy text content as href
				start = iter.copy()
				if not start.begins_tag(tag):
					start.backward_to_tag_toggle(tag)
				end = iter.copy()
				if not end.ends_tag(tag):
					end.forward_to_tag_toggle(tag)
				link['href'] = start.get_text(end)
			return link
		else:
			return None

	def insert_tag(self, iter, text, **attrib):
		'''Insert a tag into the buffer at iter'''
		with self.tmp_cursor(iter):
			self.insert_tag_at_cursor(text, **attrib)

	def insert_tag_at_cursor(self, text, **attrib):
		'''Like insert_tag() but inserts at the cursor'''
		tag = self.create_tag_tag(text, **attrib)
		self._editmode_tags = \
			filter(_is_not_tag_tag,
				filter(_is_not_style_tag, self._editmode_tags) ) + (tag,)
		self.insert_at_cursor(text)
		self._editmode_tags = self._editmode_tags[:-1]

	def create_tag_tag(self, text, **attrib):
		tag = self.create_tag(None, **self.tag_styles['tag'])
		tag.set_priority(0) # force tags to be below styles
		tag.zim_type = 'tag'
		tag.zim_tag = 'tag'
		tag.zim_attrib = attrib
		tag.zim_attrib['name'] = None
		return tag

	def get_tag_tag(self, iter):
		# Explicitly left gravity, otherwise position behind the tag
		# would alos be consifered part of the tag. Position before the
		# tag is included here.
		for tag in iter.get_tags():
			if hasattr(tag, 'zim_type') and tag.zim_type == 'tag':
				return tag
		else:
			return None

	def get_tag_data(self, iter):
		'''Returns the dict with tag properties for a tag at iter.
		Fails silently and returns None when there is no tag at iter.
		'''
		tag = self.get_tag_tag(iter)

		if tag:
			attrib = tag.zim_attrib.copy()
			# Copy text content as name
			start = iter.copy()
			if not start.begins_tag(tag):
				start.backward_to_tag_toggle(tag)
			end = iter.copy()
			if not end.ends_tag(tag):
				end.forward_to_tag_toggle(tag)
			attrib['name'] = start.get_text(end)[1:].strip()
			return attrib
		else:
			return None

	def insert_image(self, iter, file, src, **attrib):
		'''Insert an image linked to file 'file' but showing 'src' as link to
		the user.
		'''
		#~ If there is a property 'alt' in attrib we try to set a tooltip.
		#~ '''
		if isinstance(file, basestring):
			file = File(file)
		try:
			if 'width' in attrib or 'height' in attrib:
				w = int(attrib.get('width', -1))
				h = int(attrib.get('height', -1))
				pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(file.path, w, h)
			else:
				pixbuf = gtk.gdk.pixbuf_new_from_file(file.path)
			pixbuf = rotate_pixbuf(pixbuf)
		except:
			#~ logger.exception('Could not load image: %s', file)
			logger.warn('No such image: %s', file)
			widget = gtk.HBox() # Need *some* widget here...
			pixbuf = widget.render_icon(gtk.STOCK_MISSING_IMAGE, gtk.ICON_SIZE_DIALOG)
			pixbuf = pixbuf.copy() # need unique instance to set zim_attrib

		pixbuf.zim_type = 'image'
		pixbuf.zim_attrib = attrib
		pixbuf.zim_attrib['src'] = src
		pixbuf.zim_attrib['_src_file'] = file
		self.insert_pixbuf(iter, pixbuf)

	def insert_image_at_cursor(self, file, src, **attrib):
		iter = self.get_iter_at_mark(self.get_insert())
		self.insert_image(iter, file, src, **attrib)

	def get_image_data(self, iter):
		'''Returns data for a zim image at iter or None'''
		pixbuf = iter.get_pixbuf()
		if pixbuf and hasattr(pixbuf, 'zim_type') and pixbuf.zim_type == 'image':
			return pixbuf.zim_attrib.copy()
		else:
			return None

	def set_bullet(self, line, bullet):
		'''Sets the bullet type for a line, deleting the current bullet
		if any. Set bullet 'None' to remove any bullet at this line.
		'''
		iter = self.get_iter_at_line(line)
		with self.tmp_cursor():
			with self.user_action:
				bound = iter.copy()
				self.iter_forward_past_bullet(bound)
				self.delete(iter, bound)
				# Will trigger do_delete_range, which will update indent tag

				if not bullet is None:
					with self.tmp_cursor(iter):
						self._insert_bullet_at_cursor(bullet)

				self.update_indent(line, bullet)

	def _insert_bullet_at_cursor(self, bullet, raw=False):
		'''Insert a bullet plus a space at the cursor position.
		If 'raw' is True the space will be omitted and the check that
		cursor position must be at the start of a line will not be
		enforced.

		External interface should use set_bullet(line, bullet)
		instead of calling this method directly.
		'''
		assert bullet in BULLETS
		if not raw:
			insert = self.get_insert_iter()
			assert insert.starts_line(), 'BUG: bullet not at line start'

			if not filter(_is_indent_tag, self._editmode_tags):
				# Without indent get_parsetree will not recognize
				# the icon as a bullet item. THis will mess up
				# undo stack. If 'raw' we assume indent tag is set
				# already.
				tag = self._get_indent_tag(0, bullet)
				self._editmode_tags = self._editmode_tags + (tag,)

		with self.user_action:
			if bullet == BULLET:
				if raw:
					self.insert_at_cursor(u'\u2022')
				else:
					self.insert_at_cursor(u'\u2022 ')
			else:
				# Insert icon
				stock = bullet_types[bullet]
				widget = gtk.HBox() # Need *some* widget here...
				pixbuf = widget.render_icon(stock, gtk.ICON_SIZE_MENU)
				if pixbuf is None:
					logger.warn('Could not find icon: %s', stock)
					pixbuf = widget.render_icon(gtk.STOCK_MISSING_IMAGE, gtk.ICON_SIZE_MENU)
				pixbuf.zim_type = 'icon'
				pixbuf.zim_attrib = {'stock': stock}
				self.insert_pixbuf(self.get_insert_iter(), pixbuf)

				if not raw:
					self.insert_at_cursor(' ')

	def set_textstyle(self, name):
		'''Sets the current text style. This style will be applied
		to text inserted at the cursor. Use 'set_textstyle(None)' to
		reset to normal text.
		'''
		self._editmode_tags = filter(_is_not_style_tag, self._editmode_tags)

		if not name is None:
			tag = self.get_tag_table().lookup('style-'+name)
			if _is_heading_tag(tag):
				self._editmode_tags = \
					filter(_is_not_indent_tag, self._editmode_tags)
			self._editmode_tags = self._editmode_tags + (tag,)

		if not self._insert_tree_in_progress:
			self.emit('textstyle-changed', name)

	def get_textstyle(self):
		'''Returns current text style.'''
		tags = filter(_is_style_tag, self._editmode_tags)
		if tags:
			assert len(tags) == 1, 'BUG: can not have multiple text styles'
			return tags[0].get_property('name')[6:] # len('style-') == 6
		else:
			return None

	def update_editmode(self, force=False):
		'''Updates the textstyle and indent state.
		Triggered automatically when moving the cursor.
		'''
		bounds = self.get_selection_bounds()
		if bounds:
			# For selection we set editmode based on the whole range
			tags = []
			for tag in filter(_is_zim_tag, bounds[0].get_tags()):
				if self.whole_range_has_tag(tag, *bounds):
					tags.append(tag)
		else:
			# Otherwise base editmode on cursor position
			iter = self.get_insert_iter()
			tags = self.iter_get_zim_tags(iter)

		tags = tuple(tags)
		if not tags == self._editmode_tags:
			#~ print '>', [(t.zim_type, t.get_property('name')) for t in tags]
			self._editmode_tags = tags
			for tag in tags:
				if tag.zim_type == 'style':
					name = tag.get_property('name')[6:]
					self.emit('textstyle-changed', name)
					break
			else:
				self.emit('textstyle-changed', None)

	def iter_get_zim_tags(self, iter):
		'''Like gtk.TextIter.get_tags() but only returns our own tags and
		assumes inline tags (like 'strong', 'emphasis' etc.) have "left gravity"
		(which means that you copy formatting ending to the left of you but not
		formatting starting to the right of you). For "line based" tags
		(like 'indent', 'h', 'pre') some additional logic is used to keep them
		consistent on a line (so at the start of the line, we do copy formatting
		starting to the left of us for these tags) and not inadvertedly copy
		formatting from the previous line.

		This method is used to determing which tags should be applied to newly
		inserted text at 'iter'.
		'''
		# Current logic works without additional indent set in do_end_of_line due to
		# the fact that the "\n" also caries formatting. So putting a new \n at the end
		# of e.g. an indented line will result in two indent formatted \n characters.
		# The start of the new line is in between and has continious indent formatting.
		start_tags = filter(_is_zim_tag, iter.get_toggled_tags(True))
		tags = filter(_is_zim_tag, iter.get_tags())
		for tag in start_tags:
			if tag in tags:
				tags.remove(tag)
		end_tags = filter(_is_zim_tag, iter.get_toggled_tags(False))
		# So now we have 3 separate sets with tags ending here, starting here
		# and being continuous here. Result will be continuous tags and ending tags
		# but logic for line based tags can mix in tags starting here and filter out
		# tags ending here.

		if iter.starts_line():
			# Force only use tags from the right in order to prevent tag from previous
			# line "spilling over", allow starting tags to be used to prevent breaking
			# a line based tag on this line (e.g. type at start of heading should be
			# formatted as heading)
			tags += filter(_is_line_based_tag, start_tags)
			tags += filter(_is_not_line_based_tag, end_tags)
		elif iter.ends_line():
			# Force only use tags from the left in order to prevent tag from next
			# line "spilling over" (should not happen, since \n after end of line is
			# still formatted with same line based tag as rest of line, but handled
			# anyway to be robust to edge cases)
			tags += end_tags
		else:
			# Take any tag from left or right, with left taking precendence
			# HACK: We assume line based tags are mutually exclusive
			#       if this assumption breaks down need to check by tag type
			tags += end_tags
			if not filter(_is_line_based_tag, tags):
				tags += filter(_is_line_based_tag, start_tags)

		tags.sort(key=lambda tag: tag.get_priority())
		return tags

	def toggle_textstyle(self, name, interactive=False):
		'''If there is a selection toggle the text style of the selection,
		otherwise toggle the text style of the cursor.

		For selections we remove the tag if the whole range had the
		tag. If some part of the range does not have the tag we apply
		the tag. This is needed to be consistent with the format button
		behavior if a single tag applies to any range.
		'''
		if not self.get_has_selection():
			if name == self.get_textstyle():
				self.set_textstyle(None)
			else:
				self.set_textstyle(name)
		else:
			if interactive:
				self.emit('begin-user-action')
			start, end = self.get_selection_bounds()
			if name == 'code':
				text = start.get_text(end)
				if '\n' in text:
					name = 'pre'
			tag = self.get_tag_table().lookup('style-'+name)
			had_tag = self.whole_range_has_tag(tag, start, end)
			self.remove_textstyle_tags(start, end)
			if not had_tag:
				self.apply_tag(tag, start, end)
			self.set_modified(True)
			if interactive:
				self.emit('end-user-action')

			self.update_editmode()

	def whole_range_has_tag(self, tag, start, end):
		'''Check if a certain tag is applied to the whole range or not.'''
		if tag in start.get_tags() \
		and tag in self.iter_get_zim_tags(end):
			iter = start.copy()
			if iter.forward_to_tag_toggle(tag):
				return iter.compare(end) >= 0
			else:
				return True
		else:
			return False

	def range_has_tag(self, tag, start, end):
		'''Check if a certain tag appears anywhere in a certain range'''
		# test right gravity for start iter, but left gravity for end iter
		if tag in start.get_tags() \
		or tag in self.iter_get_zim_tags(end):
			return True
		else:
			iter = start.copy()
			if iter.forward_to_tag_toggle(tag):
				return iter.compare(end) < 0
			else:
				return False

 	def range_has_tags(self, func, start, end):
		'''Like range_has_tag() but uses a function to check for
		multiple tags.
		'''
		# test right gravity for start iter, but left gravity for end iter
		if any(filter(func, start.get_tags())) \
		or any(filter(func, self.iter_get_zim_tags(end))):
			return True
		else:
			iter = start.copy()
			iter.forward_to_tag_toggle(None)
			while iter.compare(end) == -1:
				if any(filter(func, iter.get_tags())):
					return True

				if not iter.forward_to_tag_toggle(None):
					return False

			return False

	def remove_textstyle_tags(self, start, end):
		'''Removes all textstyle tags from a range'''
		# Also remove links until we support links nested in tags
		self.smart_remove_tags(_is_style_tag, start, end)
		self.smart_remove_tags(_is_link_tag, start, end)
		self.update_editmode()

	def smart_remove_tags(self, func, start, end):
		'''This method removes tags over a range based on a function to test if a
		tag needs to be removed or not. This is needed because directly calling
		remove_tag() without knowing if a tag was present or not will trigger the
		UndoStackManager to assume the tag was there.
		'''
		with self.user_action:
			iter = start.copy()
			while iter.compare(end) == -1:
				for tag in filter(func, iter.get_tags()):
					bound = iter.copy()
					bound.forward_to_tag_toggle(tag)
					if not bound.compare(end) == -1:
						bound = end.copy()
					self.remove_tag(tag, iter, bound)
					self.set_modified(True)

				if not iter.forward_to_tag_toggle(None):
					break

	def get_indent_at_cursor(self):
		'''Returns the indent level at the cursor'''
		iter = self.get_iter_at_mark(self.get_insert())
		return self.get_indent(iter.get_line())

	def get_indent(self, line):
		'''Returns the indent level for a line'''
		iter = self.get_iter_at_line(line)
		tags = filter(_is_indent_tag, iter.get_tags())
		if tags:
			assert len(tags) == 1, 'BUG: overlapping indent tags'
			return int( tags[0].zim_attrib['indent'] )
		else:
			return 0

	def _get_indent_tag(self, level, bullet=None):
		name = 'indent-%i' % level
		if bullet:
			name += '-' + bullet
		tag = self.get_tag_table().lookup(name)
		if tag is None:
			if bullet:
				if bullet == BULLET: stylename = 'bullet-list'
				elif bullet == CHECKED_BOX: stylename = 'checked-checkbox'
				elif bullet == UNCHECKED_BOX: stylename = 'unchecked-checkbox'
				elif bullet == XCHECKED_BOX: stylename = 'xchecked-checkbox'
				else: raise AssertionError, 'BUG: Unkown bullet type'
				margin = 12 + self.pixels_indent * level # offset from left side for all lines
				indent = -12 # offset for first line (bullet)
				tag = self.create_tag(name, left_margin=margin, indent=indent, **self.tag_styles[stylename])
			else:
				margin = 12 + self.pixels_indent * level
				tag = self.create_tag(name, left_margin=margin, **self.tag_styles['indent'])
				# Note: I would think the + 12 is not needed here, but
				# the effect in the view is different than expected,
				# putting text all the way to the left against the
				# window border
			tag.zim_type = 'indent'
			tag.zim_tag = 'indent'
			tag.zim_attrib = {'indent': level}
		return tag

	def set_indent(self, line, level, interactive=False):
		'''Apply indenting to a specific line.
		Set 'level' to 0 (or None) to remove indenting.
		'''
		level = level or 0

		if interactive:
			# Without content effect of indenting is not visible
			# end-of-line gives content to empty line, but last line
			# may not have end-of-line.
			start, end = self.get_line_bounds(line)
			if start.equal(end) :
				with self.tmp_cursor():
					self.insert(end, '\n')
					start, end = self.get_line_bounds(line)

		bullet = self.get_bullet(line)
		ok = self._set_indent(line, level, bullet)
		if ok: self.set_modified(True)
		return ok

	def update_indent(self, line, bullet):
		'''Update the indent tag for line, should not change the indent
		level, only change the formatting if needed. Should be called
		after changing a checkbox type etc.
		'''
		level = self.get_indent(line)
		self._set_indent(line, level, bullet)

	def _set_indent(self, line, level, bullet):
		# Common code between set_indent() and update_indent()
		start, end = self.get_line_bounds(line)

		tags = filter(_is_indent_tag, start.get_tags())
		if tags:
			assert len(tags) == 1, 'BUG: overlapping indent tags'
			self.remove_tag(tags[0], start, end)

		if filter(_is_heading_tag, start.get_tags()):
			return level == 0 # False if you try to indent a header

		if level > 0 or bullet:
			# For bullets there is a 0-level tag, otherwise 0 means None
			tag = self._get_indent_tag(level, bullet)
			self.apply_tag(tag, start, end)

		self.update_editmode() # also updates indent tag
		return True

	def indent(self, line, interactive=False):
		'''Increase the indent for 'line'
		Can be used as function for foreach_line()
		'''
		level = self.get_indent(line)
		return self.set_indent(line, level+1, interactive)

	def unindent(self, line, interactive=False):
		'''Decrease the indent level for 'line'
		Can be used as function for foreach_line()
		'''
		level = self.get_indent(line)
		return self.set_indent(line, level-1, interactive)

	def foreach_line_in_selection(self, func, *args, **kwarg):
		'''Like foreach_line() but iterates over all lines covering
		the current selection.
		Returns False if there is no selection, True otherwise.
		'''
		bounds = self.get_selection_bounds()
		if bounds:
			start, end = bounds
			self.foreach_line(start.get_line(), end.get_line(), func, *args, **kwarg)
			return True
		else:
			return False

	def foreach_line(self, first, last, func, *args, **kwarg):
		'''Iterates over all lines covering 'first' to 'last' and calls
		'func' for each line. The callback gets one argument, which is
		the line number. Any additional arguments will also be passed
		along.
		'''
		for line in range(first, last+1):
			func(line, *args, **kwarg)

	def strip_selection(self):
		'''Limits the selection by excluding whitespace (e.g. empty lines) from
		the start end end of the selection.
		Returns True if we have a non-zero non-whitespace selection.
		Returns False if no selection or the whole selection is whitespace.
		'''
		bounds = self.get_selection_bounds()
		if bounds:
			start, end = bounds
		else:
			return False

		selected = start.get_slice(end)
		if selected.isspace():
			return False

		left = len(selected) - len(selected.lstrip())
		right = len(selected) - len(selected.rstrip())
		if left > 0:
			start.forward_chars(left)
		if right > 0:
			end.backward_chars(right)

		self.select_range(start, end)

	def do_mark_set(self, iter, mark):
		gtk.TextBuffer.do_mark_set(self, iter, mark)
		if mark.get_name() in ('insert', 'selection_bound'):
			self.update_editmode()

	def do_insert_text(self, iter, string, length):
		'''Signal handler for insert-text signal'''

		def end_or_protect_tags(string, length):
			tags = filter(_is_tag_tag, self._editmode_tags)
			if tags:
				if iter.ends_tag(tags[0]):
					# End tags if end-of-word char is typed at end of a tag
					# without this you not insert text behind a tag e.g. at the end of a line
					self._editmode_tags = filter(_is_not_tag_tag, self._editmode_tags)
				else:
					# Forbid breaking a tag
					return '', 0
				# TODO this should go into the TextView, not here
				# Now it goes OK only because we only check single char inserts, but would break
				# for multi char inserts from the view - fixing that here breaks insert parsetree
			return string, length

		# Check if we are at a bullet or checkbox line
		if not self._insert_tree_in_progress and iter.starts_line() \
		and not string.endswith('\n'):
			bullet = self._get_bullet_at_iter(iter)
			if bullet:
				self._iter_forward_past_bullet(iter, bullet)
				self.place_cursor(iter)

		# Check current formatting
		if string == '\n':
			# Break tags that are not allowed to span over multiple lines
			self._editmode_tags = filter(
				lambda tag: _is_pre_tag(tag) or _is_not_style_tag(tag),
				self._editmode_tags)
			self._editmode_tags = filter(_is_not_link_tag, self._editmode_tags)
			self.emit('textstyle-changed', None)
			# TODO make this more robust for multiline inserts

			string, length = end_or_protect_tags(string, length)

		elif string in CHARS_END_OF_WORD:
			# Break links if end-of-word char is typed at end of a link
			# without this you not insert text behind a link e.g. at the end of a line
			links = filter(_is_link_tag, self._editmode_tags)
			if links and iter.ends_tag(links[0]):
				self._editmode_tags = filter(_is_not_link_tag, self._editmode_tags)
				# TODO this should go into the TextView, not here
				# Now it goes OK only because we only check single char inserts, but would break
				# for multi char inserts from the view - fixing that here breaks insert parsetree

			string, length = end_or_protect_tags(string, length)


		# Call parent for the actual insert
		gtk.TextBuffer.do_insert_text(self, iter, string, length)

		# Apply current text style
		# Note: looks like parent call modified the TextIter
		# since it is still valid and now matched the end of the
		# inserted string and not the start.
		length = len(unicode(string))
			# default function argument gives byte length :S
		start = iter.copy()
		start.backward_chars(length)
		self.remove_all_tags(start, iter)
		for tag in self._editmode_tags:
			self.apply_tag(tag, start, iter)

	def insert_pixbuf(self, iter, pixbuf):
		# Make sure we always apply the correct tags when inserting a pixbuf
		if iter.equal(self.get_iter_at_mark(self.get_insert())):
			gtk.TextBuffer.insert_pixbuf(self, iter, pixbuf)
		else:
			with self.tmp_cursor(iter):
				gtk.TextBuffer.insert_pixbuf(self, iter, pixbuf)

	def do_insert_pixbuf(self, iter, pixbuf):
		# Like do_insert_text() but for pixbuf
		# however only apply indenting tags, ignore other
		gtk.TextBuffer.do_insert_pixbuf(self, iter, pixbuf)

		start = iter.copy()
		start.backward_char()
		self.remove_all_tags(start, iter)
		for tag in filter(_is_indent_tag, self._editmode_tags):
			self.apply_tag(tag, start, iter)

	def do_delete_range(self, start, end):
		# Wrap actual delete to hook _do_lines_merged
		with self.user_action:
			if start.get_line() != end.get_line():
				gtk.TextBuffer.do_delete_range(self, start, end)
				self._do_lines_merged(start)
			else:
				gtk.TextBuffer.do_delete_range(self, start, end)

			# Check if we have deleted some bullet item
			if start.starts_line() \
			and self.get_indent(start.get_line()) == 0 \
			and not self.get_bullet_at_iter(start):
				self.update_indent(start.get_line(), None)

		# Delete formatted word followed by typing should not show format again
		self.update_editmode()

	def _do_lines_merged(self, iter):
		# Enforce tags like 'h', 'pre' and 'indent' to be consistent over the line
		if iter.starts_line() or iter.ends_line():
			return

		end = iter.copy()
		end.forward_to_line_end()

		self.smart_remove_tags(_is_line_based_tag, iter, end)

		for tag in self.iter_get_zim_tags(iter):
			if _is_line_based_tag(tag):
				if tag.zim_tag == 'pre':
					self.smart_remove_tags(_is_zim_tag, iter, end)
				self.apply_tag(tag, iter, end)

		self.update_editmode()

	def get_bullet(self, line):
		iter = self.get_iter_at_line(line)
		return self._get_bullet_at_iter(iter)

	def get_bullet_at_iter(self, iter):
		if not iter.starts_line():
			return None
		else:
			return self._get_bullet_at_iter(iter)

	def _get_bullet_at_iter(self, iter):
		pixbuf = iter.get_pixbuf()
		if pixbuf:
			if hasattr(pixbuf, 'zim_type') and pixbuf.zim_type == 'icon' \
			and pixbuf.zim_attrib['stock'] in (
				STOCK_CHECKED_BOX, STOCK_UNCHECKED_BOX, STOCK_XCHECKED_BOX):
				return bullets[pixbuf.zim_attrib['stock']]
			else:
				return None
		else:
			bound = iter.copy()
			bound.forward_char()
			if iter.get_slice(bound) == u'\u2022':
				return BULLET
			else:
				return None

	def iter_forward_past_bullet(self, iter):
		bullet = self.get_bullet_at_iter(iter)
		if bullet:
			self._iter_forward_past_bullet(iter, bullet)
			return True
		else:
			return False

	def _iter_forward_past_bullet(self, iter, bullet, raw=False):
		assert bullet in (BULLET, CHECKED_BOX, UNCHECKED_BOX, XCHECKED_BOX)
		# other bullet types might need to skip different number of char etc.
		iter.forward_char()
		bound = iter.copy()
		bound.forward_char()
		if not raw:
			while iter.get_text(bound) == ' ':
				if iter.forward_char():
					bound.forward_char()
				else:
					break

	def get_parsetree(self, bounds=None, raw=False):
		'''Returns a parse tree for the page contents.

		If 'raw' is True you get a tree that is _not_ nicely cleaned up.
		This raw tree should result in the exact same contents in the buffer
		when reloaded so it can be used for e.g. by the undostack manager.
		Also this feature allows for testability of the cleanup routines.
		Raw parsetrees have an attribute to flag them as a raw tree, so on
		insert we can make sure they are inserted in the same way.
		'''
		if bounds is None:
			start, end = self.get_bounds()
			attrib = {}
		else:
			start, end = bounds
			attrib = {'partial': True}

		if raw:
			builder = TreeBuilder()
			attrib['raw'] = True
			builder.start('zim-tree', attrib)
		else:
			builder = ParseTreeBuilder()
			builder.start('zim-tree', attrib)

		open_tags = []
		def set_tags(iter, tags):
			# This function changes the parse tree based on the TextTags in
			# effect for the next section of text.
			# It does so be keeping the stack of open tags and compare it
			# with the new set of tags in order to decide which of the
			# tags can be closed and which new ones need to be opened.
			#
			# We assume that by definition we only get one tag for each tag
			# type and that we get tags in such an order that the one we get
			# first should be closed first while closing later ones breaks the
			# ones before. This is enforced using the priorities of the tags
			# in the TagTable.
			tags.sort(key=lambda tag: tag.get_priority(), reverse=True)

			i = 0
			while i < len(tags) and i < len(open_tags) \
			and tags[i] == open_tags[i][0]:
				i += 1

			# so i is the breakpoint where new stack is different
			while len(open_tags) > i:
				builder.end(open_tags[-1][1])
				open_tags.pop()

			# Convert some tags on the fly
			if tags:
				continue_attrib = {}
				for tag in tags[i:]:
					t, attrib = tag.zim_tag, tag.zim_attrib
					if t == 'indent':
						bullet = self._get_bullet_at_iter(iter)
						if bullet:
							t = 'li'
							attrib = attrib.copy() # break ref with tree
							attrib['bullet'] = bullet
							self._iter_forward_past_bullet(iter, bullet, raw=raw)
						elif not raw and not iter.starts_line():
							# Indent not visible if it does not start at begin of line
							t = '_ignore_'
						elif len(filter(lambda t: t.zim_tag == 'pre', tags[i:])):
							# Indent of 'pre' blocks handled in subsequent iteration
							continue_attrib.update(attrib)
							continue
						else:
							t = 'div'
					elif t == 'pre' and not raw and not iter.starts_line():
						# Without indenting 'pre' looks the same as 'code'
						# Prevent turning into a seperate paragraph here
						t = 'code'
					elif t == 'pre':
						if attrib:
							attrib.update(continue_attrib)
						else:
							attrib = continue_attrib
						continue_attrib = {}
					elif t == 'link':
						attrib = self.get_link_data(iter)
						assert attrib['href'], 'Links should have a href'
					elif t == 'tag':
						attrib = self.get_tag_data(iter)
						assert attrib['name'], 'Tags should have a name'
					builder.start(t, attrib)
					open_tags.append((tag, t))
					if t == 'li':
						break
						# HACK - ignore any other tags because we moved
						# the cursor - needs also a break_tags before
						# which is special cased below
						# TODO: cleaner solution for this issue -
						# maybe easier when tags for list and indent
						# are separated ?

		def break_tags(type):
			# Forces breaking the stack of open tags on the level of 'tag'
			# The next set_tags() will re-open any tags that are still open
			i = 0
			for i in range(len(open_tags)):
				if open_tags[i][1] == type:
					break

			# so i is the breakpoint
			while len(open_tags) > i:
				builder.end(open_tags[-1][1])
				open_tags.pop()

		# And now the actual loop going through the buffer
		iter = start.copy()
		set_tags(iter, filter(_is_zim_tag, iter.get_tags()))
		while iter.compare(end) == -1:
			pixbuf = iter.get_pixbuf()
			if pixbuf:
				if pixbuf.zim_type == 'icon':
					# Reset all tags - and let set_tags parse the bullet
					if open_tags:
						break_tags(open_tags[0][1])
					set_tags(iter, filter(_is_indent_tag, iter.get_tags()))
				else:
					pass # reset all tags except indenting
					set_tags(iter, filter(_is_indent_tag, iter.get_tags()))

				pixbuf = iter.get_pixbuf() # iter may have moved
				if pixbuf is None:
					continue

				if pixbuf.zim_type == 'icon':
					#~ raise AssertionError, 'BUG: Checkbox outside of indent ?'
					logger.warn('BUG: Checkbox outside of indent ?')
				elif pixbuf.zim_type == 'image':
					attrib = pixbuf.zim_attrib.copy()
					if 'alt' in attrib:
						text = attrib.pop('alt') or ''
						builder.start('img', attrib)
						builder.data(text)
						builder.end('img')
					else:
						builder.start('img', attrib)
						builder.end('img')
				else:
					assert False, 'BUG: unknown pixbuf type'

				iter.forward_char()
			# FUTURE: elif embedded widget
			else:
				# Set tags
				copy = iter.copy()

				bullet = self._get_bullet_at_iter(iter)
				if bullet:
					break_tags('indent')
					# This is part of the HACK for bullets in
					# set_tags()

				set_tags(iter, filter(_is_zim_tag, iter.get_tags()))
				if not iter.equal(copy): # iter moved
					continue

				# Find biggest slice without tags being toggled
				bound = iter.copy()
				toggled = []
				while not toggled:
					if not bound.is_end() and bound.forward_to_tag_toggle(None):
						# For some reason the not is_end check is needed
						# to prevent an odd corner case infinite loop
						toggled = filter(_is_zim_tag,
							bound.get_toggled_tags(False)
							+ bound.get_toggled_tags(True) )
					else:
						bound = end.copy() # just to be sure..
						break

				# But limit slice to first pixbuf
				# FUTURE: also limit slice to any embeddded widget
				text = iter.get_slice(bound)
				if text.startswith(PIXBUF_CHR):
					text = text[1:] # special case - we see this char, but get_pixbuf already returned None, so skip it

				if PIXBUF_CHR in text:
					i = text.index(PIXBUF_CHR)
					bound = iter.copy()
					bound.forward_chars(i)
					text = text[:i]

				# And limit to end
				if bound.compare(end) == 1:
					bound = end.copy()
					text = iter.get_slice(end)

				if filter(lambda t: t[1] == 'li', open_tags) \
				and bound.get_line() != iter.get_line():
					# And limit bullets to a single line
					orig = bound
					bound = iter.copy()
					bound.forward_line()
					assert bound.compare(orig) < 1
					text = iter.get_slice(bound).rstrip('\n')
					builder.data(text)
					break_tags('li')
					builder.data('\n') # add to tail
				else:
					# Else just inser text we got
					builder.data(text)

				iter = bound

		# close any open tags
		set_tags(end, [])

		builder.end('zim-tree')
		tree = ParseTree(builder.close())
		tree.encode_urls()
		#~ print tree.tostring()
		return tree

	def select_line(self):
		'''selects the line at the cursor'''
		# Differs from get_line_bounds because we exclude the trailing
		# line break while get_line_bounds selects these
		iter = self.get_iter_at_mark(self.get_insert())
		iter = self.get_iter_at_line(iter.get_line())
		if iter.ends_line():
			return False
		else:
			end = iter.copy()
			end.forward_to_line_end()
			self.select_range(iter, end)
			return True

	def select_word(self):
		'''Selects the word at the cursor, if any. Returns True for success'''
		insert = self.get_iter_at_mark(self.get_insert())
		if not insert.inside_word():
			return False

		bound = insert.copy()
		if not insert.ends_word():
			insert.forward_word_end()
		if not bound.starts_word():
			bound.backward_word_start()

		self.select_range(insert, bound)
		return True

	def select_link(self):
		'''Selects the link at the cursor, if any.
		Returns link data or None when there was no link at the cursor.
		'''
		insert = self.get_iter_at_mark(self.get_insert())
		tag = self.get_link_tag(insert)
		if tag is None:
			return None
		link = tag.zim_attrib.copy()

		bound = insert.copy()
		if not insert.ends_tag(tag):
			insert.forward_to_tag_toggle(tag)
		if not bound.begins_tag(tag):
			bound.backward_to_tag_toggle(tag)

		if link['href'] is None:
			link['href'] = bound.get_text(insert)

		self.select_range(insert, bound)
		return link

	def remove_link(self, start, end):
		'''Removes any links between start and end'''
		self.smart_remove_tags(_is_link_tag, start, end)
		self.update_editmode()

	def toggle_checkbox(self, line, checkbox_type=None, recursive=False):
		'''Toggles checkbox at a specific line. If checkbox_type is
		given, it toggles between this type and unchecked. Otherwise
		it rotates through unchecked, checked and xchecked.
		Returns True for success, False if no checkbox was found.
		'''
		# For mouse click no checkbox type is given, so we cycle
		# For <F12> and <Shift><F12> checkbox_type is given so we toggle
		# between the two
		bullet = self.get_bullet(line)
		if bullet in CHECKBOXES:
			if checkbox_type:
				if bullet == checkbox_type:
					newbullet = UNCHECKED_BOX
				else:
					newbullet = checkbox_type
			else:
				i = list(CHECKBOXES).index(bullet) # use list() to be python 2.5 compatible
				next = (i + 1) % len(CHECKBOXES)
				newbullet = CHECKBOXES[next]
		else:
			return False

		if recursive:
			row, clist = TextBufferList.new_from_line(self, line)
			clist.set_bullet(row, newbullet)
		else:
			self.set_bullet(line, newbullet)

		return True

	def toggle_checkbox_for_cursor_or_selection(self, checkbox_type=None, recursive=False):
		'''Like toggle_checkbox() but applies to current line or current selection.'''
		if self.get_has_selection():
			self.foreach_line_in_selection(self.toggle_checkbox, checkbox_type, recursive)
		else:
			line = self.get_insert_iter().get_line()
			return self.toggle_checkbox(line, checkbox_type, recursive)

	def iter_backward_word_start(self, iter):
		'''Like gtk.TextIter.backward_word_start() but less intelligent.
		This method does not take into account the language and just skips
		to either the last white space or the begin of line.
		Returns boolean for success.
		'''
		if iter.starts_line():
			return False

		# find start of word - either start of line or whitespace
		# the backward_word_start() method also stops at punctuation etc.
		orig = iter.copy()
		while True:
			if iter.starts_line():
				break
			else:
				bound = iter.copy()
				bound.backward_char()
				char = bound.get_slice(iter)
				if char == PIXBUF_CHR or char.isspace():
					break # whitespace or pixbuf before start iter
				else:
					iter.backward_char()

		return iter.compare(orig)

	def get_line_bounds(self, line):
		start = self.get_iter_at_line(line)
		end = start.copy()
		end.forward_line()
		return start, end

	def get_line_is_empty(self, line):
		start, end = self.get_line_bounds(line)
		return start.equal(end) or start.get_slice(end).isspace()

	def get_has_selection(self):
		'''Returns boolean whether there is a selection or not.

		Method available in gtk.TextBuffer for gtk version >= 2.10
		reproduced here for backward compatibility.
		'''
		return bool(self.get_selection_bounds())

	def iter_in_selection(self, iter):
		'''Returns True if 'iter' is within the current selection'''
		bounds = self.get_selection_bounds()
		return bounds \
			and bounds[0].compare(iter) <= 0 \
			and bounds[1].compare(iter) >= 0
		# not using iter.in_range to be inclusive of bounds

	def unset_selection(self):
		iter = self.get_iter_at_mark(self.get_insert())
		self.select_range(iter, iter)

	def copy_clipboard(self, clipboard, format='plain'):
		bounds = self.get_selection_bounds()
		if bounds:
			tree = self.get_parsetree(bounds)
			Clipboard().set_parsetree(self.notebook, self.page, tree, format)

	def cut_clipboard(self, clipboard, default_editable):
		if self.get_has_selection():
			self.copy_clipboard(clipboard)
			self.delete_selection(True, default_editable)

	def paste_clipboard(self, clipboard, iter, default_editable):
		if not default_editable: return

		if iter is None:
			iter = self.get_iter_at_mark(self.get_insert())
		elif self.get_has_selection():
			# unset selection if explicit iter is given
			bound = self.get_selection_bound()
			insert = self.get_insert()
			self.move_mark(bound, self.get_iter_at_mark(insert))

		mark = self.get_mark('zim-paste-position')
		if mark:
			self.move_mark(mark, iter)
		else:
			self.create_mark('zim-paste-position', iter, left_gravity=False)

		#~ clipboard.debug_dump_contents()
		clipboard.request_parsetree(self._paste_clipboard, self.notebook, self.page)

	def _paste_clipboard(self, parsetree):
		#~ print '!! PASTE', parsetree.tostring()
		with self.user_action:
			if self.get_has_selection():
				start, end = self.get_selection_bounds()
				self.delete(start, end)

			mark = self.get_mark('zim-paste-position')
			iter = self.get_iter_at_mark(mark)
			self.delete_mark(mark)

			self.place_cursor(iter)
			self.insert_parsetree_at_cursor(parsetree, interactive=True)

# Need to register classes defining gobject signals
gobject.type_register(TextBuffer)


class TextBufferList(list):
	'''This class represents a bullet or checkbox list in a TextBuffer.
	It is used to perform recursive actions on the list.

	TextBufferList objects will become invalid after any modification
	to the buffer that changes the line count within the list. Using
	them after such modification will result in errors.
	'''

	# This class is a list of tuples, each tuple is a pair of
	# (linenumber, indentlevel, bullettype)

	LINE_COL = 0
	INDENT_COL = 1
	BULLET_COL = 2

	@classmethod
	def new_from_line(self, textbuffer, line):
		'''Returns a row id and a TextBufferList object for the list
		around 'line'. Both will be None if 'line' is not part of a list.
		'''
		iter = textbuffer.get_iter_at_line(line)
		return self.new_from_iter(textbuffer, iter)

	@classmethod
	def new_from_iter(self, textbuffer, iter):
		'''Returns a row id and a TextBufferList object for the list
		around 'iter'. Both will be None if 'iter' is not part of a list.
		'''
		# check iter
		if textbuffer.get_bullet(iter.get_line()) is None:
			return None, None

		# find start of list
		start = iter.get_line()
		for line in range(start, -1, -1):
			if textbuffer.get_bullet(line) is None:
				break # TODO skip lines with whitespace
			else:
				start = line

		# find end of list
		end = iter.get_line()
		lastline = textbuffer.get_end_iter().get_line()
		for line in range(end, lastline+1, 1):
			if textbuffer.get_bullet(line) is None:
				break # TODO skip lines with whitespace
			else:
				end = line

		list = TextBufferList(textbuffer, start, end)
		row = list.get_row_at_line(iter.get_line())
		#~ print '!! LIST %i..%i ROW %i' % (start, end, row)
		return row, list

	def __init__(self, textbuffer, firstline, lastline):
		self.buffer = textbuffer
		self.firstline = firstline
		self.lastline = lastline
		for line in range(firstline, lastline+1):
			bullet = self.buffer.get_bullet(line)
			indent = self.buffer.get_indent(line)
			if bullet:
				self.append((line, indent, bullet))

	def get_row_at_line(self, line):
		'''Returns a row id for line number within the list range or None'''
		for i in range(len(self)):
			if self[i][self.LINE_COL] == line:
				return i
		else:
			return None

	def can_indent(self, row):
		'''Nodes can only be indented if they are on top of the list
		or when there is some node above them to serve as new parent node.
		This avoids indenting two levels below the parent.
		'''
		if row == 0:
			return True
		else:
			parents = self._parents(row)
			if row-1 in parents:
				return False # we are first child
			else:
				return True

	def can_unindent(self, row):
		'''Nodes can only unindent when they have indenting in the fist place'''
		return self[row][self.INDENT_COL] > 0

	def indent(self, row):
		'''Indent a row and all it's child nodes'''
		if not self.can_indent(row):
			return False
		with self.buffer.user_action:
			self._indent(row, 1)
		return True

	def unindent(self, row):
		'''Un-indent a row and all it's child nodes'''
		if not self.can_unindent(row):
			return False
		with self.buffer.user_action:
			self._indent(row, -1)
		return True

	def _indent(self, row, step):
		level = self[row][self.INDENT_COL]
		self._indent_row(row, step)
		if row == 0:
			# Indent the whole list
			for i in range(1, len(self)):
				self._indent_row(i, step)
		else:
			for i in range(row+1, len(self)):
				if self[i][self.INDENT_COL] > level:
					self._indent_row(i, step)
				else:
					break

	def _indent_row(self, row, step):
		line, level, bullet = self[row]
		newlevel = level + step
		if self.buffer.set_indent(line, newlevel):
			self.buffer.update_editmode() # also updates indent tag
			self[row] = (line, newlevel, bullet)

	def set_bullet(self, row, bullet):
		'''(Un-)Check the checkbox at a row and synchronize child
		nodes and parent nodes. The new 'bullet' can be any of
		BULLET, CHECKED_BOX, UNCHECKED_BOX, or XCHECKED_BOX.
		'''
		assert bullet in BULLETS
		with self.buffer.user_action:
			self._change_bullet_type(row, bullet)
			if bullet == BULLET:
				pass
			elif bullet == UNCHECKED_BOX:
				self._checkbox_unchecked(row)
			else: # CHECKED_BOX or XCHECKED_BOX
				self._checkbox_checked(row, bullet)

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
		for i in range(row+1, len(self)):
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
			for i in range(parent+1, len(self)):
				if self[i][self.INDENT_COL] <= level:
					break
				elif self[i][self.INDENT_COL] == level+1 \
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


FIND_CASE_SENSITIVE = 1
FIND_WHOLE_WORD = 2
FIND_REGEX = 4

class TextFinder(object):
	'''This class defines a helper object for the textbuffer which
	takes care of searching. You can get an instance of this class
	from the textbuffer.finder attribute.
	'''

	def __init__(self, textbuffer):
		self.buffer = textbuffer
		self.regex = None
		self.string = None
		self.flags = 0

		self.highlight = False
		self.highlight_tag = self.buffer.create_tag(
			None, **self.buffer.tag_styles['find-highlight'] )

	def get_state(self):
		'''Returns the current search string, flags and highlight state'''
		return self.string, self.flags, self.highlight

	def set_state(self, string, flags, highlight):
		if not string is None:
			self._parse_query(string, flags)
			self.set_highlight(highlight)

	def find(self, string, flags=0):
		'''Select the next occurence of 'string', returns True if
		the string was found.

		Flags can be:
			FIND_CASE_SENSITIVE - check case of matches
			FIND_WHOLE_WORD - only match whole words
			FIND_REGEX - input is a regular expression
		'''
		self._parse_query(string, flags)
		#~ print '!! FIND "%s" (%s, %s)' % (self.regex.pattern, string, flags)

		if self.highlight:
			self._update_highlight()

		iter = self.buffer.get_insert_iter()
		return self._find_next(iter)

	def _parse_query(self, string, flags):
		assert isinstance(string, basestring)
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
		'''Skip to the next match and select it'''
		iter = self.buffer.get_insert_iter()
		iter.forward_char() # Skip current position
		return self._find_next(iter)

	def _find_next(self, iter):
		# Common functionality between find() and find_next()
		# Looking for a match starting at iter
		if self.regex is None:
			self.buffer.unset_selection()
			return False


		line = iter.get_line()
		lastline = self.buffer.get_end_iter().get_line()
		for start, end, _ in self._check_range(line, lastline, 1):
			if start.compare(iter) == -1:
				continue
			else:
				self.buffer.select_range(start, end)
				return True
		for start, end, _ in self._check_range(0, line, 1):
			self.buffer.select_range(start, end)
			return True

		self.buffer.unset_selection()
		return False


	def find_previous(self):
		'''Skip back to the previous match and select it'''
		if self.regex is None:
			self.buffer.unset_selection()
			return False

		iter = self.buffer.get_insert_iter()
		line = iter.get_line()
		lastline = self.buffer.get_end_iter().get_line()
		for start, end, _ in self._check_range(line, 0, -1):
			if start.compare(iter) != -1:
				continue
			else:
				self.buffer.select_range(start, end)
				return True
		for start, end, _ in self._check_range(lastline, line, -1):
			self.buffer.select_range(start, end)
			return True

		self.buffer.unset_selection()
		return False

	def set_highlight(self, highlight):
		self.highlight = highlight
		self._update_highlight()
		# TODO we could connect to buffer signals to update highlighting
		# when the buffer is modified.

	def _update_highlight(self):
		# Clear highlighting
		tag = self.highlight_tag
		start, end = self.buffer.get_bounds()
		self.buffer.remove_tag(tag, start, end)

		# Set highlighting
		if self.highlight:
			lastline = end.get_line()
			for start, end, _ in self._check_range(0, lastline, 1):
				self.buffer.apply_tag(tag, start, end)

	def _check_range(self, firstline, lastline, step):
		# Generator for matches in a line. Arguments are start and
		# end line numbers and a step size (1 or -1). If the step is
		# negative results are yielded in reversed order. Yields pair
		# of TextIter's for begin and end of the match as well as the
		# match obejct.
		assert self.regex
		for line in range(firstline, lastline+step, step):
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
					line, match.start() )
				enditer = self.buffer.get_iter_at_line_offset(
					line, match.end() )
				yield startiter, enditer, match

	def replace(self, string):
		'''Replace current match with 'string'. In case of a regex
		find and replace the string will be expanded with terms from
		the regex. Returns boolean for success.
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
					self.buffer.delete(start, end)
					self.buffer.insert_at_cursor(string)

				start = self.buffer.get_iter_at_offset(offset)
				end = self.buffer.get_iter_at_offset(offset+len(string))
				self.buffer.select_range(start, end)

				return True
		else:
			return False

		self._update_highlight()

	def replace_all(self, string):
		'''Like replace() but replaces all matches in the buffer'''
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
			with self.buffer.tmp_cursor():
				for start, end, string in matches:
					start = self.buffer.get_iter_at_offset(start)
					end = self.buffer.get_iter_at_offset(end)
					self.buffer.delete(start, end)
					self.buffer.insert(start, string)

		self._update_highlight()


CURSOR_TEXT = gtk.gdk.Cursor(gtk.gdk.XTERM)
CURSOR_LINK = gtk.gdk.Cursor(gtk.gdk.HAND2)
CURSOR_WIDGET = gtk.gdk.Cursor(gtk.gdk.LEFT_PTR)

class TextView(gtk.TextView):
	'''Custom TextView class. Takes care of additional key bindings and on-mouse-over for links.

	Signals:
		link-clicked (link) - Emitted when the used clicks a link
		link-enter (link) - Emitted when the mouse pointer enters a link
		link-leave (link) - Emitted when the mouse pointer leaves a link
		end-of-word (start, end, word, char) - Emitted when the user typed a character like space that ends a word
		end-of-line (end) - Emitted when the user typed a newline

	Plugin writers that want to add auto-formatting logic should connect to
	'end-of-word'. If you recognize the word and format it you need
	to stop the signal with 'stop_emission()' to prevent other hooks from
	taking it as well.
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		# New signals
		'link-clicked': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'link-enter': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'link-leave': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'end-of-word': (gobject.SIGNAL_RUN_LAST, None, (object, object, object, object)),
		'end-of-line': (gobject.SIGNAL_RUN_LAST, None, (object,)),

		# Override clipboard interaction
		'copy-clipboard': 'override',
		'cut-clipboard': 'override',
		'paste-clipboard': 'override',

		# And some events we want to connect to
		'motion-notify-event': 'override',
		'visibility-notify-event': 'override',
		'button-press-event': 'override',
		'button-release-event': 'override',
		'key-press-event': 'override',
	}

	def __init__(self, preferences):
		gtk.TextView.__init__(self, TextBuffer(None, None))
		self.set_name('zim-pageview')
		self.cursor = CURSOR_TEXT
		self.cursor_link = None
		self.gtkspell = None
		self.set_left_margin(10)
		self.set_right_margin(5)
		self.set_wrap_mode(gtk.WRAP_WORD)
		self.preferences = preferences
		actions = gtk.gdk.ACTION_COPY | gtk.gdk.ACTION_MOVE | gtk.gdk.ACTION_LINK
		self.drag_dest_set(0, PARSETREE_ACCEPT_TARGETS, actions)
			# Flags is 0 because gtktextview does everything itself

	def set_buffer(self, buffer):
		if not self.gtkspell is None:
			# Hardcoded hook because usign signals here
			# seems to introduce lag
			self.gtkspell.detach()
			self.gtkspell = None
		gtk.TextView.set_buffer(self, buffer)

	def do_copy_clipboard(self, format=None):
		format = format or self.preferences['copy_format'].lower()
		if format == 'text': format = 'plain'
		self.get_buffer().copy_clipboard(Clipboard(), format)

	def do_cut_clipboard(self):
		self.get_buffer().cut_clipboard(Clipboard(), self.get_editable())
		self.scroll_mark_onscreen(self.get_buffer().get_insert())

	def do_paste_clipboard(self):
		self.get_buffer().paste_clipboard(Clipboard(), None, self.get_editable())
		self.scroll_mark_onscreen(self.get_buffer().get_insert())

	#~ def do_drag_motion(self, context, *a):
		#~ # Method that echos drag data types - only enable for debugging
		#~ print context.targets

	def do_drag_data_received(self, dragcontext, x, y, selectiondata, info, timestamp):
		if not self.get_editable():
			dragcontext.finish(False, False, timestamp)
			return

		logger.debug('Drag data received of type "%s"', selectiondata.target)
		buffer = self.get_buffer()
		tree = parsetree_from_selectiondata(selectiondata, buffer.notebook, buffer.page)
		if tree is None:
			logger.warn('Could not drop data type "%s"', selectiondata.target)
			dragcontext.finish(False, False, timestamp) # NOK
			return

		x, y = self.window_to_buffer_coords(gtk.TEXT_WINDOW_WIDGET, x, y)
		iter = self.get_iter_at_location(x, y)
		buffer.insert_parsetree(iter, tree)
		dragcontext.finish(True, False, timestamp) # OK

	def do_motion_notify_event(self, event):
		'''Event handler that triggers check_cursor_type()
		when the mouse moves
		'''
		cont = gtk.TextView.do_motion_notify_event(self, event)
		x, y = event.get_coords()
		x, y = int(x), int(y) # avoid some strange DeprecationWarning
		x, y = self.window_to_buffer_coords(gtk.TEXT_WINDOW_WIDGET, x, y)
		self.check_cursor_type(self.get_iter_at_location(x, y))
		return cont # continue emit ?

	def do_visibility_notify_event(self, event):
		'''Event handler that triggers check_cursor_type()
		when the window becomes visible
		'''
		self.check_cursor_type(self.get_iter_at_pointer())
		return False # continue emit

	def do_button_press_event(self, event):
		# Need to overload some button handling here because
		# implementation details of gtktextview.c do not use proper
		# signals for these handlers.
		buffer = self.get_buffer()

		if event.type == gtk.gdk.BUTTON_PRESS:
			if event.button == 2 and not buffer.get_has_selection():
				iter = self.get_iter_at_pointer()
				clipboard = Clipboard(selection='PRIMARY')
				buffer.paste_clipboard(clipboard, iter, self.get_editable())
				return False
			elif event.button == 3:
				iter = self.get_iter_at_pointer()
				self._set_popup_menu_mark(iter)

		return gtk.TextView.do_button_press_event(self, event)

	def do_button_release_event(self, event):
		cont = gtk.TextView.do_button_release_event(self, event)
		buffer = self.get_buffer()
		if not buffer.get_has_selection():
			iter = self.get_iter_at_pointer()
			if event.button == 1:
				if self.preferences['cycle_checkbox_type']:
					# Cycle through all states - more useful for
					# single click input devices
					self.click_link(iter) or self.click_checkbox(iter)
				else:
					self.click_link(iter) or self.click_checkbox(iter, CHECKED_BOX)
			elif event.button == 3:
				self.click_checkbox(iter, XCHECKED_BOX)
		return cont # continue emit ?

	def do_popup_menu(self):
		# Hack to get called when user activates the popup-menu
		# by a keybinding (Shift-F10 or "menu" key). Due to
		# implementation details in gtktextview.c this method is
		# not called when a popup is triggered by a mouse click.
		buffer = self.get_buffer()
		iter = buffer.get_iter_at_mark(buffer.get_insert())
		self._set_popup_menu_mark(iter)
		return gtk.TextView.do_popup_menu(self)

	def _set_popup_menu_mark(self, iter):
		buffer = self.get_buffer()
		mark = buffer.get_mark('zim-popup-menu')
		if mark:
			buffer.move_mark(mark, iter)
		else:
			mark = buffer.create_mark('zim-popup-menu', iter, True)

	def do_key_press_event(self, event):
		# This method defines extra key bindings for the standard input mode.
		# It also triggers end-of-word and end-of-line signals.
		# Calls in read-only mode or selection mode are dispatched to two
		# methods below. Returns boolean whether we handled the event, this
		# determines if the event is finished, or it should continue to be
		# emited to any other handlers.
		# Note that on maemo only TAB triggers this method, other keys avod it somehow

		handled = False
		buffer = self.get_buffer()
		#~ print 'KEY %s (%i)' % (gtk.gdk.keyval_name(event.keyval), event.keyval)
		#~ print 'STATE %s' % event.state

		if not self.get_editable():
			# Dispatch read-only mode
			if self._do_key_press_event_readonly(event):
				return True
			else:
				return gtk.TextView.do_key_press_event(self, event)
		elif buffer.get_has_selection():
			# Dispatch selection mode
			if self._do_key_press_event_selection(event):
				return True
			else:
				return gtk.TextView.do_key_press_event(self, event)

		elif (event.keyval in KEYVALS_HOME
		and not event.state & gtk.gdk.CONTROL_MASK):
			# Smart Home key - can be combined with shift state
			insert = buffer.get_iter_at_mark(buffer.get_insert())
			home, ourhome = self.get_visual_home_positions(insert)
			if insert.equal(ourhome): iter = home
			else: iter = ourhome
			if event.state & gtk.gdk.SHIFT_MASK:
				buffer.move_mark_by_name('insert', iter)
			else:
				buffer.place_cursor(iter)
			handled = True
		elif event.keyval in KEYVALS_TAB and not event.state in KEYSTATES:
			# Tab at start of line indents
			iter = buffer.get_insert_iter()
			home, ourhome = self.get_visual_home_positions(iter)
			if home.starts_line() and iter.compare(ourhome) < 1 \
			and not filter(_is_pre_tag, iter.get_tags()):
				row, list = TextBufferList.new_from_iter(buffer, iter)
				if list and self.preferences['recursive_indentlist']:
					list.indent(row)
				else:
					buffer.indent(iter.get_line(), interactive=True)
				handled = True
		elif event.keyval in KEYVALS_LEFT_TAB \
		or (event.keyval in KEYVALS_BACKSPACE
			and self.preferences['unindent_on_backspace']) \
		and not event.state in KEYSTATES:
			# Backspace or Ctrl-Tab unindents line
			iter = buffer.get_iter_at_mark(buffer.get_insert())
			home, ourhome = self.get_visual_home_positions(iter)
			if home.starts_line() and iter.compare(ourhome) < 1 \
			and not filter(_is_pre_tag, iter.get_tags()):
				bullet = buffer.get_bullet_at_iter(home)
				indent = buffer.get_indent(home.get_line())
				if event.keyval in KEYVALS_BACKSPACE \
				and bullet and indent == 0 and not iter.equal(home):
					# Delete bullet at start of line (if iter not before bullet)
					buffer.delete(home, ourhome)
					handled = True
				elif indent == 0 or indent is None:
					# Nothing to unindent
					pass
				elif bullet:
					# Unindent list maybe recursive
					row, list = TextBufferList.new_from_iter(buffer, iter)
					if list and self.preferences['recursive_indentlist']:
						handled = list.unindent(row)
					else:
						handled = buffer.unindent(iter.get_line(), interactive=True)
				else:
					# Unindent normal text
					handled = buffer.unindent(iter.get_line(), interactive=True)

			if event.keyval in KEYVALS_LEFT_TAB:
				handled = True # Prevent <Shift><Tab> to insert a Tab if unindent fails

		elif event.keyval in KEYVALS_ENTER:
			# Enter can trigger links
			iter = buffer.get_iter_at_mark(buffer.get_insert())
			tag = buffer.get_link_tag(iter)
			if tag and not iter.begins_tag(tag):
				# get_link_tag() is left gravitating, we additionally
				# exclude the position in front of the link.
				# As a result you can not "Enter" a 1 character link,
				# this is by design.
				if (self.preferences['follow_on_enter']
				or event.state & gtk.gdk.MOD1_MASK): # MOD1 == Alt
					self.click_link(iter)
				# else do not insert newline, just ignore
				handled = True

		if handled:
			return True # end of event chain
		elif not gtk.TextView.do_key_press_event(self, event):
			# Parent class also has no handler for this key
			return False

		elif (event.keyval in KEYVALS_END_OF_WORD
		or event.keyval in KEYVALS_ENTER):
			# Trigger end-of-line and/or end-of-word signals if char was
			# really inserted by parent class.
			#
			# We do it this way because in some cases e.g. a space is not
			# inserted but is used to select an option in an input mode e.g.
			# to select between various chinese characters. See lp:460438
			insert = buffer.get_iter_at_mark(buffer.get_insert())
			mark = buffer.create_mark(None, insert, left_gravity=False)
			iter = insert.copy()
			iter.backward_char()

			if event.keyval in KEYVALS_ENTER:
				char = '\n'
			elif event.keyval in KEYVALS_TAB:
				char = '\t'
			else:
				char = unichr(gtk.gdk.keyval_to_unicode(event.keyval))

			if iter.get_text(insert) != char:
				return True

			with buffer.user_action:
				buffer.emit('undo-save-cursor', insert)
				start = iter.copy()
				if buffer.iter_backward_word_start(start):
					word = start.get_text(iter)
					self.emit('end-of-word', start, iter, word, char)

				if event.keyval in KEYVALS_ENTER:
					# iter may be invalid by now because of end-of-word
					iter = buffer.get_iter_at_mark(mark)
					iter.backward_char()
					self.emit('end-of-line', iter)

			buffer.place_cursor(buffer.get_iter_at_mark(mark))
			self.scroll_mark_onscreen(mark)
			buffer.delete_mark(mark)

		return True

	def _do_key_press_event_readonly(self, event):
		# Key bindings in read-only mode:
		#   Space scrolls one page
		#   Shift-Space scrolls one page up
		handled = True
		if event.keyval in KEYVALS_SPACE:
			if event.state & gtk.gdk.SHIFT_MASK: i = -1
			else: i = 1
			self.emit('move-cursor', gtk.MOVEMENT_PAGES, i, False)
		else:
			handled = False
		return handled

	def _do_key_press_event_selection(self, event):
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

		def decrement_indent():
			# Check if inside verbatim block AND entire selection without tag toggle
			iter = buffer.get_insert_iter()
			if filter(_is_pre_tag, iter.get_tags()) \
			and not find_tag_toggle():
				missing_tabs = []
				check_tab = lambda l: (buffer.get_iter_at_line(l).get_char() == '\t') or missing_tabs.append(1)
				buffer.foreach_line_in_selection(check_tab)
				if len(missing_tabs) == 0:
					return buffer.foreach_line_in_selection(delete_char)
				else:
					return False
			else:
				# For selection decrement - first check if all lines have indent
				level = []
				buffer.strip_selection()
				buffer.foreach_line_in_selection(
					lambda l: level.append(buffer.get_indent(l)) )
				if level and min(level) > 0:
					return buffer.foreach_line_in_selection(buffer.unindent)
				else:
					return False

		def find_tag_toggle():
			# Checks if there are any tag changes within the selection
			start, end = buffer.get_selection_bounds()
			toggle = start.copy()
			toggle.forward_to_tag_toggle(None)
			return toggle.compare(end) < 0

		with buffer.user_action:
			if event.keyval in KEYVALS_TAB:
				# Check if inside verbatim block AND entire selection without tag toggle
				iter = buffer.get_insert_iter()
				if filter(_is_pre_tag, iter.get_tags()) \
				and not find_tag_toggle():
					prepend_tab = lambda l: buffer.insert(buffer.get_iter_at_line(l), '\t')
					buffer.foreach_line_in_selection(prepend_tab)
				else:
					buffer.foreach_line_in_selection(buffer.indent)
			elif event.keyval in KEYVALS_LEFT_TAB:
				decrement_indent()
			elif event.keyval in KEYVALS_BACKSPACE \
			and self.preferences['unindent_on_backspace']:
				decremented = decrement_indent()
				if not decremented:
					handled = None # nothing happened, normal backspace
			elif event.keyval in KEYVALS_ASTERISK:
				def toggle_bullet(line):
					bullet = buffer.get_bullet(line)
					if not bullet and not buffer.get_line_is_empty(line):
						buffer.set_bullet(line, BULLET)
					elif bullet == BULLET:
						buffer.set_bullet(line, None)
				buffer.foreach_line_in_selection(toggle_bullet)
			elif event.keyval in KEYVALS_GT:
				def email_quote(line):
					iter = buffer.get_iter_at_line()
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

	def get_iter_at_pointer(self):
		'''Returns the TextIter that is under the mouse'''
		x, y = self.get_pointer()
		x, y = self.window_to_buffer_coords(gtk.TEXT_WINDOW_WIDGET, x, y)
		return self.get_iter_at_location(x, y)

	def check_cursor_type(self, iter):
		'''Set the mouse cursor image according to content at 'iter'.
		E.g. set a "hand" cursor when hovering over a link. Also emits
		the link-enter and link-leave signals when apropriate.
		'''
		link = self.get_buffer().get_link_data(iter)

		if link:
			cursor = CURSOR_LINK
		else:
			pixbuf = iter.get_pixbuf()
			if not pixbuf:
				# right side of pixbuf will map to next iter
				iter.backward_char()
				pixbuf = iter.get_pixbuf()

			if pixbuf and pixbuf.zim_type == 'icon' \
			and pixbuf.zim_attrib['stock'] in (
				STOCK_CHECKED_BOX, STOCK_UNCHECKED_BOX, STOCK_XCHECKED_BOX):
				cursor = CURSOR_WIDGET
			else:
				cursor = CURSOR_TEXT

		if cursor != self.cursor:
			window = self.get_window(gtk.TEXT_WINDOW_TEXT)
			window.set_cursor(cursor)

		# Check if we need to emit any events for hovering
		if self.cursor == CURSOR_LINK: # was over link before
			if cursor == CURSOR_LINK: # still over link
				if link == self.cursor_link:
					pass
				else:
					# but other link
					self.emit('link-leave', self.cursor_link)
					self.emit('link-enter', link)
			else:
				self.emit('link-leave', self.cursor_link)
		elif cursor == CURSOR_LINK: # was not over link, but is now
			self.emit('link-enter', link)

		self.cursor = cursor
		self.cursor_link = link

	def click_link(self, iter):
		'''Emits the link-clicked signal if there is a link at iter.
		Returns True for success, returns False if no link was found.
		'''
		link = self.get_buffer().get_link_data(iter)
		if link:
			self.emit('link-clicked', link)
			return True
		else:
			return False

	def click_checkbox(self, iter, checkbox_type=None):
		'''If 'iter' or the position left of 'iter' is a checkbox this
		function will call toggle_checkbox() to effect a click on the
		checkbox.
		'''
		if iter.get_line_offset() < 2:
			# Only position 0 or 1 can map to a checkbox
			buffer = self.get_buffer()
			recurs = self.preferences['recursive_checklist']
			return buffer.toggle_checkbox(iter.get_line(), checkbox_type, recurs)
		else:
			return False

	def get_visual_home_positions(self, iter):
		'''Returns two text iters. If we are on a word wrapped line, both point
		to the begin of the visual line (which is not the actual paragraph
		start). If the visual begin happens to be the real line start the first
		iter will give the real line start while the second will give the start
		of the actual content on the line (so after skipping bullets and
		whitespace). In that case the two iters specify a range that may
		contain bullets or whitespace at the start of the line.
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

	def do_end_of_word(self, start, end, word, char):
		buffer = self.get_buffer()
		handled = True
		#~ print 'WORD >>%s<< CHAR >>%s<<' % (word, char)

		if filter(_is_not_indent_tag, buffer.iter_get_zim_tags(start)) \
		or filter(_is_not_indent_tag, buffer.iter_get_zim_tags(end)):
			# DO not auto-format if any zim tags are applied except for indent
			return

		def apply_tag(match):
			#~ print "TAG >>%s<<" % word
			start = end.copy()
			if not start.backward_chars(len(match)):
				return False
			if buffer.range_has_tags(_is_not_indent_tag, start, end):
				return False
			tag = buffer.create_tag_tag(match)
			buffer.apply_tag(tag, start, end)
			return True

		def apply_link(match):
			#~ print "LINK >>%s<<" % word
			start = end.copy()
			if not start.backward_chars(len(match)):
				return False
			if buffer.range_has_tags(_is_not_indent_tag, start, end):
				return False
			tag = buffer.create_link_tag(match, match)
			buffer.apply_tag(tag, start, end)
			return True

		if (char == ' ' or char == '\t') and start.starts_line() \
		and word in autoformat_bullets:
			# format bullet and checkboxes
			line = start.get_line()
			end.forward_char() # also overwrite the space triggering the action
			buffer.delete(start, end)
			buffer.set_bullet(line, autoformat_bullets[word])
		elif tag_re.match(word):
			apply_tag(tag_re[0])
		elif url_re.match(word):
			apply_link(url_re[0])
		elif page_re.match(word):
			# Do not link "10:20h", "10:20PM" etc. so check two letters before first ":"
			w = word.strip(':').split(':')
			if w and twoletter_re.search(w[0]):
				apply_link(page_re[0])
			else:
				handled = False
		elif interwiki_re.match(word):
			apply_link(interwiki_re[0])
		elif self.preferences['autolink_files'] and file_re.match(word):
			apply_link(file_re[0])
		elif self.preferences['autolink_camelcase'] and camelcase_re.match(word):
			apply_link(camelcase_re[0])
		elif self.preferences['auto_reformat']:
			handled = False
			linestart = buffer.get_iter_at_line(end.get_line())
			partial_line = linestart.get_slice(end)
			for style,re in markup_re.items():
				if not re.search(partial_line) == None:
					matchstart = linestart.copy()
					matchstart.forward_chars(re.start())
					matchend = linestart.copy()
					matchend.forward_chars(re.end())
					if filter(_is_not_indent_tag,buffer.iter_get_zim_tags(matchstart)) \
					or filter(_is_not_indent_tag,buffer.iter_get_zim_tags(matchend)):
						continue
					buffer.delete(matchstart,matchend)
					buffer.insert_with_tags_by_name(matchstart,re[2],style)
					handled_here = True
					break
		else:
			handled = False

		if handled:
			self.stop_emission('end-of-word')

	def do_end_of_line(self, end):
		buffer = self.get_buffer()

		if end.starts_line():
			return # empty line
		start = buffer.get_iter_at_line(end.get_line())
		line = start.get_text(end)
		#~ print 'LINE >>%s<<' % line

		if heading_re.match(line):
			level = len(heading_re[1])-1
			heading = heading_re[2]
			mark = buffer.create_mark(None, end)
			buffer.delete(start, end)
			buffer.insert_with_tags_by_name(
				buffer.get_iter_at_mark(mark), heading, 'style-h'+str(level))
			buffer.delete_mark(mark)
		elif not buffer.get_bullet_at_iter(start) is None:
			# we are part of bullet list
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
				newline = newlinestart.get_line()
				indent = buffer.get_indent(start.get_line())
				nextlinestart = newlinestart.copy()
				if nextlinestart.forward_line() \
				and buffer.get_bullet_at_iter(nextlinestart):
					nextindent = buffer.get_indent(nextlinestart.get_line())
					if nextindent >= indent:
						# we are at the head of a sublist
						indent = nextindent

				# add bullet on new line
				bullet = buffer.get_bullet_at_iter(start)
				if bullet in (CHECKED_BOX, XCHECKED_BOX):
					bullet = UNCHECKED_BOX
				buffer.set_bullet(newline, bullet)

				# apply indent
				buffer.set_indent(newline, indent)

			buffer.update_editmode() # also updates indent tag


# Need to register classes defining gobject signals
gobject.type_register(TextView)


class UndoActionGroup(list):
	'''Container for a set of undo actions, will be undone, redone in a single step'''

	__slots__ = ('can_merge', 'cursor')

	def __init__(self):
		self.can_merge = False
		self.cursor = None

	def reversed(self):
		'''Returns a new UndoActionGroup with the reverse actions of this group'''
		group = UndoActionGroup()
		group.cursor = self.cursor
		for action in self:
			# constants are defined such that negating them reverses the action
			action = (-action[0],) + action[1:]
			group.insert(0, action)
		return group


class UndoStackManager:
	'''This class implements a manager for the undo stack for our TextBuffer class.
	It records any changes and allows rolling back actions. Data in this undo stack
	is only valid as long as the asociated TextBuffer exists.

	When recording new actions after rolling back a previous action, the remaining
	stack will be 'folded'. This means that even the 'undo' action can always be
	undone and no data is discarded.

	We try to group single-character inserts and deletes into words. This makes
	the stack more compact and makes the undo action more meaningfull.
	'''

	MAX_UNDO = 100 # FIXME what is a sensible value here ?

	# We have 4 types of actions that can be recorded. Each action is recorded as
	# a tuple containing this constant as the first item, followed by the start
	# and end offsets in the buffer and a data structure (either a parse tree or a text tag).
	# Negating an action gives it opposite.

	ACTION_INSERT = 1
	ACTION_DELETE = -1
	ACTION_APPLY_TAG = 2
	ACTION_REMOVE_TAG = -2

	# Actions will be grouped on the stack by putting them inside lists. These lists
	# will be undone / redone recursively as single actions. When recording a group
	# will start and stop with the begin-user-action and end-user-action signals.
	# By definition these signals will not be emitted if a group is open already, so
	# groups will not be nested inside each other.

	# Each interactive action (e.g. every single key stroke) is wrapped in a set of
	# begin-user-action and end-user-action signals. We use these signals to group actions.
	# This implies that any sequence on non-interactive actions will also end up in a
	# single group. An interactively created group consisting of a single character insert
	# or single character delete is a candidate for merging*.

	# *) Merging: grouping various small actions into a meaningful action automatically.
	#    In this case we merge single character inserts into words so undo is a bit faster
	#    then just undoing one character at the time.

	# *) Folding: if the user presses undo a few times and starts typing we "fold" the
	#    actions that are on the redo stack into the undo stack. So this content is not
	#    dropped. Pressing undo again will first undo the typing, then undo (or redo) the
	#    previous undo actions and then proceed undoing the rest of the stack.
	#	FIXME: nice ascii diagram of how folding of the undo stack works...


	def __init__(self, textbuffer):
		self.buffer = textbuffer
		self.stack = [] # stack of actions & action groups
		self.group = UndoActionGroup() # current group of actions
		self.interactive = False # interactive edit or not
		self.insert_pending = False # whether we need to call flush insert or not
		self.undo_count = 0 # number of undo steps that were done
		self.block_count = 0 # number of times block() was called

		self.recording_handlers = [] # handlers to be blocked when not recording
		for signal, handler in (
			('undo-save-cursor', self.do_save_cursor),
			('insert-text', self.do_insert_text),
			#~ ('inserted-tree', self.do_insert_tree), # TODO
			('insert-pixbuf', self.do_insert_pixbuf),
			('delete-range', self.do_delete_range),
			('begin-user-action', self.do_begin_user_action),
			('end-user-action', self.do_end_user_action),
		):
			self.recording_handlers.append(
				self.buffer.connect(signal, handler) )

		for signal, action in (
			('apply-tag', self.ACTION_APPLY_TAG),
			('remove-tag', self.ACTION_REMOVE_TAG),
		):
			self.recording_handlers.append(
				self.buffer.connect(signal, self.do_change_tag, action) )

		#~ self.buffer.connect_object('begin-insert-tree',
			#~ self.__class__.block, self)
		#~ self.buffer.connect_object('end-insert-tree',
			#~ self.__class__.unblock, self)

		self.buffer.connect_object('clear',
			self.__class__.clear, self)

		#~ self.buffer.connect_object('edit-textstyle-changed',
			#~ self.__class__._flush_if_typing, self)
		#~ self.buffer.connect_object('set-mark',
			#~ self.__class__._flush_if_typing, self)

	def block(self):
		'''Block listening to events from the textbuffer until further notice.
		Any change in between will not be undo-able (and mess up the undo stack)
		unless it is recorded explicitly. Keeps count of number of calls to
		block() and unblock().
		'''
		# blocking / unblocking does not affect the state - just "pause"
		if self.block_count == 0:
			for id in self.recording_handlers:
				self.buffer.handler_block(id)
		self.block_count += 1

	def unblock(self):
		# blocking / unblocking does not affect the state - just "pause"
		if self.block_count > 1:
			self.block_count -= 1
		else:
			for id in self.recording_handlers:
				self.buffer.handler_unblock(id)
			self.block_count = 0

	def clear(self):
		self.stack = []
		self.group = UndoActionGroup()
		self.interactive = False
		self.insert_pending = False
		self.undo_count = 0
		self.block_count = 0
		self.block()

	def do_save_cursor(self, buffer, iter):
		self.group.cursor = iter.get_offset()

	def do_begin_user_action(self, buffer):
		'''Start a group of actions that will be undone / redone as a single action'''
		if self.undo_count > 0:
			self.flush_redo_stack()

		if self.group:
			self.stack.append(self.group)
			self.group = UndoActionGroup()
			while len(self.stack) > self.MAX_UNDO:
				self.stack.pop(0)

		self.interactive = True

	def do_end_user_action(self, buffer):
		'''End a group of actions that will be undone / redone as a single action'''
		if self.group:
			self.stack.append(self.group)
			self.group = UndoActionGroup()
			while len(self.stack) > self.MAX_UNDO:
				self.stack.pop(0)

		self.interactive = False

	#~ def do_inserted_tree(self, buffer, start, end, parsetree):
		#~ if self.undo_count > 0: self._flush_redo_stack()

		#~ start, end = start.get_offset(), end.get_offset()
		#~ self.group.append((self.ACTION_INSERT, start, end, tree))

	def do_insert_text(self, buffer, iter, text, length):
		# Do not use length argument, it gives length in bytes, not characters
		text = text.decode('utf-8')
		length = len(text)
		if self.undo_count > 0: self.flush_redo_stack()

		start = iter.get_offset()
		end = start + length
		#~ print 'INSERT at %i: "%s" (%i)' % (start, text, length)

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
		if self.undo_count > 0: self.flush_redo_stack()
		elif self.insert_pending: self.flush_insert()

		start = iter.get_offset()
		end = start + 1
		#~ print 'INSERT PIXBUF at %i' % start
		self.group.append((self.ACTION_INSERT, start, end, None))
		self.group.can_merge = False
		self.insert_pending = True

	def flush_insert(self):
		# For insert actually getting the tree is delayed when possible

		def _flush_group(group):
			for i in reversed(range(len(group))):
				action, start, end, tree = group[i]
				if action == self.ACTION_INSERT and tree is None:
					bounds = (self.buffer.get_iter_at_offset(start),
								self.buffer.get_iter_at_offset(end))
					tree = self.buffer.get_parsetree(bounds, raw=True)
					#~ print 'FLUSH %i to %i\n\t%s' % (start, end, tree.tostring())
					group[i] = (self.ACTION_INSERT, start, end, tree)
				else:
					return False
			return True

		if _flush_group(self.group):
			for i in reversed(range(len(self.stack))):
				if not _flush_group(self.stack[i]):
					break

		self.insert_pending = False

	def do_delete_range(self, buffer, start, end):
		if self.undo_count > 0: self.flush_redo_stack()
		elif self.insert_pending: self.flush_insert()

		bounds = (start, end)
		tree = self.buffer.get_parsetree(bounds, raw=True)
		start, end = start.get_offset(), end.get_offset()
		#~ print 'DELETE RANGE from %i to %i\n\t%s' % (start, end, tree.tostring())
		self.group.append((self.ACTION_DELETE, start, end, tree))
		self.group.can_merge = False

	def do_change_tag(self, buffer, tag, start, end, action):
		assert action in (self.ACTION_APPLY_TAG, self.ACTION_REMOVE_TAG)
		if not hasattr(tag, 'zim_type'):
			return

		start, end = start.get_offset(), end.get_offset()
		if self.group \
		and self.group[-1][0] == self.ACTION_INSERT \
		and self.group[-1][1] <= start \
		and self.group[-1][2] >= end \
		and self.group[-1][3] is None:
			pass # for text that is not yet flushed tags will be in the tree
		else:
			if self.undo_count > 0: self.flush_redo_stack()
			elif self.insert_pending: self.flush_insert()

			#~ print 'TAG CHANGED', start, end, tag
			self.group.append((action, start, end, tag))
			self.group.can_merge = False

	def undo(self):
		'''Undo one user action'''
		if self.group:
			self.stack.append(self.group)
			self.group = UndoActionGroup()
		if self.insert_pending: self.flush_insert()

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
		# fold stack so no data is lost, each undo step can now be undone
		# so instead of dropping forward stack, we add an new group for the undone
		# actions to the stack

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

		#~ print '='*80
		for action, start, end, data in actiongroup:
			iter = self.buffer.get_iter_at_offset(start)
			bound = self.buffer.get_iter_at_offset(end)

			if action == self.ACTION_INSERT:
				#~ print 'INSERTING', data.tostring()
				self.buffer.place_cursor(iter)
				self.buffer.insert_parsetree_at_cursor(data)
			elif action == self.ACTION_DELETE:
				#~ print 'DELETING'
				self.buffer.place_cursor(iter)
				tree = self.buffer.get_parsetree((iter, bound), raw=True)
				self.buffer.delete(iter, bound)
				if tree.tostring() != data.tostring():
					logger.warn('Mismatch in undo stack\n%s\n%s\n', tree.tostring(), data.tostring())
			elif action == self.ACTION_APPLY_TAG:
				#~ print 'APPLYING', data
				self.buffer.apply_tag(data, iter, bound)
				self.buffer.place_cursor(bound)
			elif action == self.ACTION_REMOVE_TAG:
				#~ print 'REMOVING', data
				self.buffer.remove_tag(data, iter, bound)
				self.buffer.place_cursor(bound)
			else:
				assert False, 'BUG: unknown action type'

		if not actiongroup.cursor is None:
			iter = self.buffer.get_iter_at_offset(actiongroup.cursor)
			self.buffer.place_cursor(iter)

		self.unblock()


class PageView(gtk.VBox):
	'''Wrapper for TextView which handles the application logic for menu items.
	Also adds a bar below the TextView with input for the 'find' action.
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'modified-changed': (gobject.SIGNAL_RUN_LAST, None, ()),
	}


	def __init__(self, ui, secondairy=False):
		gtk.VBox.__init__(self)
		self.ui = ui
		self._buffer_signals = ()
		self.page = None
		self.readonly = True
		self.readonlyset = False
		self.secondairy = secondairy
		if secondairy:
			self.readonlyset = True
		self.undostack = None
		self.image_generator_plugins = {}
		self._current_toggle_action = None
		self._showing_template = False

		self.preferences = self.ui.preferences['PageView']
		if not self.secondairy:
			# HACK avoid registerign a second time
			self.ui.register_preferences('PageView', ui_preferences)

		self.view = TextView(preferences=self.preferences)
		swindow = gtk.ScrolledWindow()
		swindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
		swindow.set_shadow_type(gtk.SHADOW_IN)
		swindow.add(self.view)
		self.add(swindow)

		self.view.connect_object('link-clicked', PageView.do_link_clicked, self)
		self.view.connect_object('link-enter', PageView.do_link_enter, self)
		self.view.connect_object('link-leave', PageView.do_link_leave, self)
		self.view.connect_object('populate-popup', PageView.do_populate_popup, self)

		## Create search box
		self.find_bar = FindBar(textview=self.view)
		self.pack_end(self.find_bar, False)
		self.find_bar.hide()

		## setup GUI actions
		if self.secondairy:
			# HACK - divert actions from uimanager
			self.actiongroup = gtk.ActionGroup('SecondairyPageView')
		self.ui.add_actions(ui_actions, self)

		# format actions need some custom hooks
		actiongroup = self.actiongroup
		actiongroup.add_actions(ui_format_actions)
		actiongroup.add_toggle_actions(ui_format_toggle_actions)

		for name in [a[0] for a in ui_format_actions]:
			action = actiongroup.get_action(name)
			action.zim_readonly = False
			#~ action.connect('activate', lambda o, *a: logger.warn(o.get_name()))
			action.connect('activate', self.do_toggle_format_action)

		for name in [a[0] for a in ui_format_toggle_actions]:
			action = actiongroup.get_action(name)
			action.zim_readonly = False
			#~ action.connect('activate', lambda o, *a: logger.warn(o.get_name()))
			action.connect('activate', self.do_toggle_format_action)

		# Extra keybinding for undo - default is <Shift><Ctrl>Z (see HIG)
		def do_undo(*a):
			if not self.readonly:
				self.redo()

		y = gtk.gdk.unicode_to_keyval(ord('y'))
		group = self.ui.uimanager.get_accel_group()
		group.connect_group( # <Ctrl>Y
				y, gtk.gdk.CONTROL_MASK, gtk.ACCEL_VISIBLE,
				do_undo)

		PageView.style = config_file('style.conf')
		self.on_preferences_changed(self.ui)
		self.ui.connect('preferences-changed', self.on_preferences_changed)

		self.ui.connect('open-notebook', self.on_open_notebook)
		self.ui.connect_object('readonly-changed', PageView.set_readonly, self)

	def grab_focus(self):
		self.view.grab_focus()

	def on_preferences_changed(self, ui):
		self.reload_style()
		self.view.set_cursor_visible(
			self.preferences['read_only_cursor'] or not self.readonly)

	def reload_style(self):
		'''(Re-)loads style definition from the config. While running this
		config is found as the class attribute 'style'.
		'''
		self.style['TextView'].setdefault('indent', TextBuffer.pixels_indent)
		self.style['TextView'].setdefault('tabs', None, int)
			# Don't set a default here as not to break pages that were
			# created before this setting was introduced.
		self.style['TextView'].setdefault('linespacing', 3)
		self.style['TextView'].setdefault('font', None, basestring)
		self.style['TextView'].setdefault('justify', None, basestring)
		#~ print self.style['TextView']

		TextBuffer.pixels_indent = self.style['TextView']['indent']

		if self.style['TextView']['tabs']:
			tabarray = pango.TabArray(1, True) # Initial size, position in pixels
			tabarray.set_tab(0, pango.TAB_LEFT, self.style['TextView']['tabs'])
				# We just set the size for one tab, apparently this gets
				# copied automaticlly when a new tab is created by the textbuffer
			self.view.set_tabs(tabarray)

		if self.style['TextView']['linespacing']:
			self.view.set_pixels_below_lines(self.style['TextView']['linespacing'])

		if self.style['TextView']['font']:
			font = pango.FontDescription(self.style['TextView']['font'])
			self.view.modify_font(font)
		else:
			self.view.modify_font(None)

		if self.style['TextView']['justify']:
			try:
				const = self.style['TextView']['justify']
				assert hasattr(gtk, const), 'No such constant: gtk.%s' % const
				self.view.set_justification(getattr(gtk, const))
			except:
				logger.exception('Exception while setting justification:')

		testbuffer = gtk.TextBuffer()
		for tag in [k[4:] for k in self.style.keys() if k.startswith('Tag ')]:
			try:
				assert tag in TextBuffer.tag_styles, 'No such tag: %s' % tag
				attrib = self.style['Tag '+tag].copy()
				for a in attrib.keys():
					assert a in TextBuffer.tag_attributes, 'No such tag attribute: %s' % a
					if isinstance(attrib[a], basestring):
						if attrib[a].startswith('PANGO_'):
							const = attrib[a][6:]
							assert hasattr(pango, const), 'No such constant: pango.%s' % const
							attrib[a] = getattr(pango, const)
						else:
							attrib[a] = str(attrib[a]) # pango doesn't like unicode attributes
				#~ print 'TAG', tag, attrib
				assert testbuffer.create_tag('style-'+tag, **attrib)
			except:
				logger.exception('Exception while parsing tag: %s:', tag)
			else:
				TextBuffer.tag_styles[tag] = attrib

	def on_open_notebook(self, ui, notebook):
		# HACK, this makes sure we do not hijack keybindings like
		# ^C and ^V while we are not focus (e.g. paste in find bar)
		# Put it here to ensure mainwindow is initialized.
		def set_actiongroup_sensitive(window, widget):
			#~ print '!! FOCUS SET:', widget
			sensitive = widget is self.view
			self.set_menuitems_sensitive(sensitive)

		window = self.get_toplevel()
		window.connect('set-focus', set_actiongroup_sensitive)

		def assert_not_modified(page, *a):
			if page == self.page \
			and self.view.get_buffer().get_modified():
				raise AssertionError, 'BUG: page changed while buffer changed as well'
				# not using assert here because it could be optimized away

		for s in ('stored-page', 'deleted-page', 'moved-page'):
			notebook.connect(s, assert_not_modified)

	def set_page(self, page):
		# unhook from previous page
		if self.page:
			self.page.set_ui_object(None)

		# for some reason keeping a copy of the previous buffer
		# prevents a number of segfaults ...
		# we do clear the old buffer to save some memory
		if self.undostack:
			self.undostack.block()
			self.undostack = None

		self._prev_buffer = self.view.get_buffer()
		finderstate = self._prev_buffer.finder.get_state()

		for id in self._buffer_signals:
			self._prev_buffer.disconnect(id)
		self._buffer_signals = ()
		self._prev_buffer.clear()

		# now create the new buffer
		self.page = page
		buffer = TextBuffer(self.ui.notebook, self.page)
		self.view.set_buffer(buffer)
		tree = page.get_parsetree()

		cursorpos = 0
		if tree is None:
			# TODO check read-only
			template = self.ui.notebook.get_template(page)
			tree = template.process_to_parsetree(self.ui.notebook, page)
			cursorpos = -1
		else:
			template = None

		try:
			self.set_parsetree(tree, bool(template))
			if not self.secondairy:
				page.set_ui_object(self) # only after succesful set tree in buffer
		except Exception, error:
			# Maybe corrupted parse tree - prevent page to be edited or saved back
			self.page.readonly = True
			self.set_readonly()
			ErrorDialog(self.ui, error).run()
			# TODO set error page e.g. zim.notebook.LoadingErrorPage
			# TODO add test for this catch - how to trigger this for testing ?

		if cursorpos != -1:
			buffer.place_cursor(buffer.get_iter_at_offset(cursorpos))

		self.view.scroll_to_mark(buffer.get_insert(), 0.3)

		self._buffer_signals = (
			buffer.connect('textstyle-changed', self.do_textstyle_changed),
			buffer.connect('modified-changed', lambda o: self.on_modified_changed(o) ),
			buffer.connect_after('mark-set', self.do_mark_set),
		)

		buffer.finder.set_state(*finderstate) # maintain state

		self.undostack = UndoStackManager(buffer)
		self.set_readonly() # initialize menu state

	def get_page(self): return self.page

	def on_modified_changed(self, buffer):
		# one-way traffic, set page modified after modifying the buffer
		# but not the other way
		self._showing_template = False
		if buffer.get_modified() and not self.page.modified:
			if self.readonly:
				logger.warn('Buffer edited while read-only - potential bug')
			else:
				self.page.modified = True
				self.emit('modified-changed')

	def clear(self):
		# Called e.g. by "discard changes" maybe due to an exception in
		# buffer.get_parse_tree() - so just drop everything...
		buffer = self.view.get_buffer()
		buffer.clear()
		buffer.set_modified(False)
		self._showing_template = False

	def get_parsetree(self):
		if self._showing_template:
			return None
		else:
			buffer = self.view.get_buffer()
			if buffer.get_modified():
				self._parsetree = buffer.get_parsetree()
				buffer.set_modified(False)
			#~ print self._parsetree.tostring()
			return self._parsetree

	def set_parsetree(self, tree, istemplate=False):
		buffer = self.view.get_buffer()
		assert not buffer.get_modified(), 'BUG: changing parsetree while buffer was changed as well'
		tree.resolve_images(self.ui.notebook, self.page)
		buffer.set_parsetree(tree)
		self._parsetree = tree
		self._showing_template = istemplate

	def set_readonly(self, readonly=None):
		if not readonly is None:
			self.readonlyset = readonly

		if self.readonlyset:
			self.readonly = True
		elif self.page:
			self.readonly = self.page.readonly or self.ui.readonly
		else:
			self.readonly = self.ui.readonly

		self.view.set_editable(not self.readonly)
		self.view.set_cursor_visible(
			self.preferences['read_only_cursor'] or not self.readonly)

		self.set_menuitems_sensitive(True)

	def set_menuitems_sensitive(self, sensitive):
		'''Batch update global menu sensitivity while respecting
		sensitivities set due to cursor position, readonly state etc.
		'''
		if sensitive:
			# partly overrule logic in ui.set_readonly()
			for action in self.actiongroup.list_actions():
				action.set_sensitive(
					action.zim_readonly or not self.readonly)

			# update state for menu items for checkboxes and links
			buffer = self.view.get_buffer()
			iter = buffer.get_insert_iter()
			mark = buffer.get_insert()
			self.do_mark_set(buffer, iter, mark)
		else:
			for action in self.actiongroup.list_actions():
				action.set_sensitive(False)

	def set_cursor_pos(self, pos):
		buffer = self.view.get_buffer()
		buffer.place_cursor(buffer.get_iter_at_offset(pos))
		self.view.scroll_to_mark(buffer.get_insert(), 0.2)

	def get_cursor_pos(self):
		buffer = self.view.get_buffer()
		iter = buffer.get_iter_at_mark(buffer.get_insert())
		return iter.get_offset()

	def set_scroll_pos(self, pos):
		pass # FIXME set scroll position

	def get_scroll_pos(self):
		pass # FIXME get scroll position

	def get_selection(self, format=None):
		'''Convenience method to get the current selection. If you
		specify 'format' (e.g. 'wiki' or 'html') the returned text
		is formatted.
		'''
		buffer = self.view.get_buffer()
		bounds = buffer.get_selection_bounds()
		if bounds:
			if format:
				tree = buffer.get_parsetree(bounds)
				dumper = get_format(format).Dumper()
				lines = dumper.dump(tree)
				return ''.join(lines)
			else:
				return bounds[0].get_text(bounds[1])
		else:
			return None

	def get_word(self, format=None):
		'''Convenience method to get the word that is under the cursor'''
		buffer = self.view.get_buffer()
		buffer.select_word()
		return self.get_selection(format)

	def register_image_generator_plugin(self, plugin, type):
		assert not 'type' in self.image_generator_plugins, \
			'Already have plugin for image type "%s"' % type
		self.image_generator_plugins[type] = plugin
		logger.debug('Registered plugin %s for image type "%s"', plugin, type)

	def unregister_image_generator_plugin(self, plugin):
		for type, obj in self.image_generator_plugins.items():
			if obj == plugin:
				self.image_generator_plugins.pop(type)
				logger.debug('Removed plugin %s for image type "%s"', plugin, type)


	def do_mark_set(self, buffer, iter, mark):
		if self.readonly or mark.get_name() != 'insert':
			return

		# Set sensitivity of various menu options
		line = iter.get_line()
		bullet = buffer.get_bullet(line)
		if bullet and bullet in CHECKBOXES:
			self.actiongroup.get_action('toggle_checkbox').set_sensitive(True)
			self.actiongroup.get_action('xtoggle_checkbox').set_sensitive(True)
		else:
			self.actiongroup.get_action('toggle_checkbox').set_sensitive(False)
			self.actiongroup.get_action('xtoggle_checkbox').set_sensitive(False)

		if buffer.get_link_tag(iter):
			self.actiongroup.get_action('remove_link').set_sensitive(True)
			self.actiongroup.get_action('edit_object').set_sensitive(True)
		elif buffer.get_image_data(iter):
			self.actiongroup.get_action('remove_link').set_sensitive(False)
			self.actiongroup.get_action('edit_object').set_sensitive(True)
		else:
			self.actiongroup.get_action('edit_object').set_sensitive(False)
			self.actiongroup.get_action('remove_link').set_sensitive(False)

	def do_textstyle_changed(self, buffer, style):
		#~ print '>>> SET STYLE', style

		# set statusbar
		if style: label = style.title()
		else: label = 'None'
		self.ui.mainwindow.statusbar_style_label.set_text(label)

		# set toolbar toggles
		if style:
			style_toggle = 'toggle_format_'+style
		else:
			style_toggle = None

		# Here we explicitly never change the toggle that initiated
		# the change (_current_toggle_action). Somehow touching this
		# toggle action will cause a new 'activate' signal to be fired,
		# *after* we go out of this function and thus after the unblock.
		# If we are lucky this second signal just undoes our current
		# action. If we are unlucky, it puts us in an infinite loop...
		# Not sure of the root cause, probably due to gtk+ internals.
		# There is no proper way to block it, so we need to avoid
		# calling it in the first place.
		for name in [a[0] for a in ui_format_toggle_actions]:
			action = self.actiongroup.get_action(name)
			if name == self._current_toggle_action:
				continue
			else:
				action.handler_block_by_func(self.do_toggle_format_action)
				action.set_active(name == style_toggle)
				action.handler_unblock_by_func(self.do_toggle_format_action)

		#~ print '<<<'

	def do_link_enter(self, link):
		self.ui.mainwindow.statusbar.push(1, 'Go to "%s"' % link['href'])

	def do_link_leave(self, link):
		self.ui.mainwindow.statusbar.pop(1)

	def do_link_clicked(self, link, new_window=False):
		'''Handler for the link-clicked signal'''
		assert isinstance(link, dict)
		href = link['href']
		type = link_type(href)
		logger.debug('Link clicked: %s: %s' % (type, link['href']))

		try:
			if type == 'interwiki':
				oldhref = href
				href = interwiki_link(href)
				if href:
					# could be file, url, or notebook
					type = link_type(href)
				else:
					if '?' in oldhref:
						oldhref, p = oldhref.split('?', 1)
					raise Error(_('No such wiki defined: %s') % oldhref)
					# T: error when unknown interwiki link is clicked

			if type == 'page':
				path = self.ui.notebook.resolve_path(href, source=self.page)
				if new_window:
					self.ui.open_new_window(path)
				else:
					self.ui.open_page(path)
			elif type == 'file':
				path = self.ui.notebook.resolve_file(href, self.page)
				self.ui.open_file(path)
			elif type == 'notebook':
				self.ui.open_notebook(href)
			else:
				self.ui.open_url(href)
		except Exception, error:
			ErrorDialog(self.ui, error).run()

	def do_populate_popup(self, menu):
		# Add custom tool
		# FIXME need way to (deep)copy widgets in the menu
		#~ toolmenu = self.ui.uimanager.get_widget('/text_popup')
		#~ tools = [tool for tool in toolmenu.get_children()
					#~ if not isinstance(tool, gtk.SeparatorMenuItem)]
		#~ print '>>> TOOLS', tools
		#~ if tools:
			#~ menu.prepend(gtk.SeparatorMenuItem())
			#~ for tool in tools:
				#~ tool.reparent(menu)

		buffer = self.view.get_buffer()

		### Copy As option ###
		default = self.preferences['copy_format']
		if default == 'Text':
			alternative = 'wiki'
			label = 'Wiki'
		else:
			alternative = 'plain'
			label = 'Text'
		item = gtk.MenuItem(_('Copy _As "%s"') % label) # T: menu item in preferences menu
		if buffer.get_has_selection():
			item.connect('activate',
				lambda o: self.view.do_copy_clipboard(alternative))
		else:
			item.set_sensitive(False)
		item.show_all()
		#~ menu.prepend(item)
		menu.insert(item, 2) # position after Copy in the standard menu - may not be robust...


		#### Check for images and links ###

		iter = buffer.get_iter_at_mark( buffer.get_mark('zim-popup-menu') )
			# This iter can be either cursor position or pointer
			# position, depending on how the menu was called
		link = buffer.get_link_data(iter)
		if link:
			type = link_type(link['href'])
			if type == 'file':
				file = link['href']
			else:
				file = None
		else:
			image = buffer.get_image_data(iter)
			if image is None:
				# Maybe we clicked right side of an image
				iter.backward_char()
				image = buffer.get_image_data(iter)

			if image:
				type = 'image'
				file = image['src']
				if 'type' in image \
				and image['type'] in self.image_generator_plugins:
					plugin = self.image_generator_plugins[image['type']]
					plugin.do_populate_popup(menu, buffer, iter, image)
					menu.show_all()
					return # plugin should decide about populating
			else:
				return # No link or image

		if file:
			file = self.ui.notebook.resolve_file(file, self.page)


		menu.prepend(gtk.SeparatorMenuItem())

		# remove link
		if link:
			item = gtk.MenuItem(_('_Remove Link'))
			item.connect('activate', lambda o: self.remove_link(iter=iter))
			item.set_sensitive(not self.readonly)
			menu.prepend(item)

		# edit
		if type == 'image':
			item = gtk.MenuItem(_('_Edit Properties')) # T: menu item in context menu for image
		else:
			item = gtk.MenuItem(_('_Edit Link')) # T: menu item in context menu
		item.connect('activate', lambda o: self.edit_object(iter=iter))
		item.set_sensitive(not self.readonly)
		menu.prepend(item)

		# copy
		def set_clipboards(o, text):
			for atom in ('PRIMARY', 'CLIPBOARD'):
				clipboard = gtk.Clipboard(selection=atom)
				clipboard.set_text(text)

		if type == 'mailto':
			item = gtk.MenuItem(_('Copy Email Address')) # T: context menu item
		else:
			item = gtk.MenuItem(_('Copy _Link')) # T: context menu item
		menu.prepend(item)

		if file:
			item.connect('activate', set_clipboards, file.path)
		elif link:
			item.connect('activate', set_clipboards, link['href'])

		menu.prepend(gtk.SeparatorMenuItem())

		# open with & open folder
		if type in ('file', 'image') and file:
			item = gtk.MenuItem(_('Open Folder'))
				# T: menu item to open containing folder of files
			menu.prepend(item)
			dir = file.dir
			if dir.exists():
				item.connect('activate', lambda o: self.ui.open_file(dir))
			else:
				item.set_sensitive(False)

			item = gtk.MenuItem(_('Open With...'))
				# T: menu item for sub menu with applications
			menu.prepend(item)
			if file.exists():
				submenu = OpenWithMenu(file)
				item.set_submenu(submenu)
			else:
				item.set_sensitive(False)
		elif type != 'page': # urls etc.
			item = gtk.MenuItem(_('Open With...'))
			menu.prepend(item)
			submenu = OpenWithMenu(link['href'], mimetype='text/html')
			if submenu.get_children():
				item.set_submenu(submenu)
			else:
				item.set_sensitive(False)

		# open in new window
		if type == 'page':
			item = gtk.MenuItem(_('Open in New _Window'))
				# T: menu item to open a link
			item.connect(
				'activate', lambda o: self.do_link_clicked(link, new_window=True))
			menu.prepend(item)

		# open
		if type == 'image':
			link = {'href': file.uri}

		item = gtk.MenuItem(_('_Open'))
			# T: menu item to open a link or file
		if file and not file.exists():
			item.set_sensitive(False)
		else:
			item.connect_object(
				'activate', PageView.do_link_clicked, self, link)
		menu.prepend(item)

		menu.show_all()

	def undo(self):
		self.undostack.undo()

	def redo(self):
		self.undostack.redo()

	def cut(self):
		self.view.emit('cut-clipboard')

	def copy(self):
		self.view.emit('copy-clipboard')

	def paste(self):
		self.view.emit('paste-clipboard')

	def delete(self):
		self.view.emit('delete-from-cursor', gtk.DELETE_CHARS, 1)

	def toggle_checkbox(self):
		buffer = self.view.get_buffer()
		recurs = self.preferences['recursive_checklist']
		buffer.toggle_checkbox_for_cursor_or_selection(CHECKED_BOX, recurs)

	def xtoggle_checkbox(self):
		buffer = self.view.get_buffer()
		recurs = self.preferences['recursive_checklist']
		buffer.toggle_checkbox_for_cursor_or_selection(XCHECKED_BOX, recurs)

	def edit_object(self, iter=None):
		buffer = self.view.get_buffer()
		if iter:
			buffer.place_cursor(iter)

		iter = buffer.get_iter_at_mark(buffer.get_insert())
		if buffer.get_link_tag(iter):
			return InsertLinkDialog(self.ui, self).run()

		image = buffer.get_image_data(iter)
		if not image:
			iter.backward_char() # maybe we clicked right side of an image
			image = buffer.get_image_data(iter)

		if image:
			if 'type' in image and image['type'] in self.image_generator_plugins:
				plugin = self.image_generator_plugins[image['type']]
				plugin.edit_object(buffer, iter, image)
			else:
				EditImageDialog(self.ui, buffer, self.page).run()
		else:
			return False

	def remove_link(self, iter=None):
		buffer = self.view.get_buffer()

		if not buffer.get_has_selection() \
		or (iter and not buffer.iter_in_selection(iter)):
			if iter:
				buffer.place_cursor(iter)
			buffer.select_link()

		start, end = buffer.get_selection_bounds()
		buffer.remove_link(start, end)

	def insert_date(self):
		InsertDateDialog(self.ui, self.view.get_buffer()).run()

	def insert_image(self, file=None, type=None, interactive=True):
		'''Insert an image in the text buffer at the cursor position.
		If 'interactive' is True we run the InsertImageDialog, otherwise
		the image is inserted immediatly. Returns True when image exists,
		is of a supported file type and insert was succesful, False
		otherwise.
		'''
		if interactive:
			InsertImageDialog(self.ui, self.view.get_buffer(), self.page, file).run()
		else:
			# Check if file is supported, otherwise unsupported file
			# results in broken image icon
			assert isinstance(file, File)
			if not (file.exists() and gtk.gdk.pixbuf_get_file_info(file.path)):
				return False

			src = self.ui.notebook.relative_filepath(file, self.page) or file.uri
			self.view.get_buffer().insert_image_at_cursor(file, src, type=type)
			return True

	def insert_bullet_list(self):
		self._start_bullet(BULLET)

	def insert_checkbox_list(self):
		self._start_bullet(UNCHECKED_BOX)

	def _start_bullet(self, bullet_type):
		buffer = self.view.get_buffer()
		line = buffer.get_insert_iter().get_line()

		with buffer.user_action:
			iter = buffer.get_iter_at_line(line)
			buffer.insert(iter, '\n')
			buffer.set_bullet(line, bullet_type)
			iter = buffer.get_iter_at_line(line)
			iter.forward_to_line_end()
			buffer.place_cursor(iter)

	def apply_format_bullet_list(self):
		self._apply_bullet(BULLET)

	def apply_format_checkbox_list(self):
		self._apply_bullet(UNCHECKED_BOX)

	def _apply_bullet(self, bullet_type):
		buffer = self.view.get_buffer()
		buffer.foreach_line_in_selection(buffer.set_bullet, bullet_type)

	def insert_text_from_file(self):
		InsertTextFromFileDialog(self.ui, self.view.get_buffer()).run()

	def insert_links(self, links):
		'''Non-interactive method to insert one or more links plus
		line breaks or whitespace. Resolves file links to relative paths.
		'''
		links = list(links)
		for i in range(len(links)):
			if isinstance(links[i], Path):
				links[i] = links[i].name
				continue
			elif isinstance(links[i], File):
				file = links[i]
			else:
				type = link_type(links[i])
				if type == 'file':
					file = File(links[i])
				else:
					continue # not a file
			links[i] = self.ui.notebook.relative_filepath(file, self.page) or file.uri

		if len(links) == 1: sep = ' '
		else: sep = '\n'

		buffer = self.view.get_buffer()
		with buffer.user_action:
			if buffer.get_has_selection():
				start, end = buffer.get_selection_bounds()
				self.buffer.delete(start, end)
			for link in links:
				buffer.insert_link_at_cursor(link, link)
				buffer.insert_at_cursor(sep)

	def insert_link(self):
		InsertLinkDialog(self.ui, self).run()

	def clear_formatting(self):
		buffer = self.view.get_buffer()
		mark = buffer.create_mark(None, buffer.get_insert_iter())
		selected = self.autoselect()

		if buffer.get_has_selection():
			start, end = buffer.get_selection_bounds()
			buffer.remove_textstyle_tags(start, end)
			if selected:
				# If we keep the selection we can not continue typing
				# so remove the selection and restore the cursor.
				buffer.unset_selection()
				buffer.place_cursor(buffer.get_iter_at_mark(mark))
		else:
			buffer.set_textstyle(None)

		buffer.delete_mark(mark)

	def do_toggle_format_action(self, action):
		'''Handler that catches all actions to apply and/or toggle formats'''
		name = action.get_name()
		logger.debug('Action: %s (toggle_format action)', name)
		self._current_toggle_action = name
		if name.startswith('apply_format_'): style = name[13:]
		elif name.startswith('toggle_format_'): style = name[14:]
		else: assert False, "BUG: don't known this action"
		self.toggle_format(style)
		self._current_toggle_action = None

	def toggle_format(self, format):
		buffer = self.view.get_buffer()
		selected = False
		mark = buffer.create_mark(None, buffer.get_insert_iter())

		if format != buffer.get_textstyle():
			# Only autoselect non formatted content - otherwise not
			# consistent when trying to break a formatted region
			# Could be improved by making autoselect refuse to select
			# formatted content
			ishead = format in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6')
			selected = self.autoselect(selectline=ishead)

		buffer.toggle_textstyle(format, interactive=True)

		if selected:
			# If we keep the selection we can not continue typing
			# so remove the selection and restore the cursor.
			buffer.unset_selection()
			buffer.place_cursor(buffer.get_iter_at_mark(mark))
		buffer.delete_mark(mark)

	def autoselect(self, selectline=False):
		'''Auto select either a word or a line. Returns True when this
		function changed the selection. Does not do anything if a
		selection is present already or when the preference for auto-
		select is set to False.
		'''
		buffer = self.view.get_buffer()
		if buffer.get_has_selection():
			return False
		elif self.preferences['autoselect']:
			if selectline:
				return buffer.select_line()
			else:
				return buffer.select_word()
		else:
			return False

	def find(self, string, flags=0):
		'''Find some string in the buffer, scroll there and select it'''
		self.hide_find() # remove previous highlighting etc.
		buffer = self.view.get_buffer()
		buffer.finder.find(string, flags)
		self.view.scroll_to_mark(buffer.get_insert(), 0.3)

	def show_find(self, string=None, flags=0, highlight=False):
		self.find_bar.show()
		if string:
			self.find_bar.find(string, flags, highlight)
			self.view.grab_focus()
		else:
			self.find_bar.set_from_buffer()
			self.find_bar.grab_focus()

	def hide_find(self):
		self.find_bar.hide()
		self.view.grab_focus()

	def find_next(self):
		self.find_bar.show()
		self.find_bar.find_next()

	def find_previous(self):
		self.find_bar.show()
		self.find_bar.find_previous()

	def show_find_and_replace(self):
		dialog = FindAndReplaceDialog.unique(self, self.ui, self.view)
		dialog.set_from_buffer()
		dialog.present()

	def show_word_count(self):
		WordCountDialog(self).run()

	def zoom_in(self):
		self._zoom_increase_decrease_font_size( +1 )

	def zoom_out(self):
		self._zoom_increase_decrease_font_size( -1 )

	def _zoom_increase_decrease_font_size(self,plus_or_minus):
		style = self.style
		if self.style['TextView']['font']:
			font = pango.FontDescription(self.style['TextView']['font'])
		else:
			logger.debug( 'Switching to custom font implicitly because of zoom action' )
			font = self.view.style.font_desc
			self.style['TextView']['font'] = font.to_string()

		font_size = font.get_size()
		if font_size <= 1*1024 and plus_or_minus < 0:
			return
		else:
			font_size_new = font_size + plus_or_minus * 1024
			font.set_size( font_size_new )
		self.style['TextView']['font'] = font.to_string()
		self.view.modify_font(font)

		self.style.write()

	def zoom_reset(self):
		if not self.style['TextView']['font']:
			return

		widget = TextView({}) # Get new widget
		default_font = widget.style.font_desc

		font = pango.FontDescription(self.style['TextView']['font'])
		font.set_size( default_font.get_size() )

		if font.to_string() == default_font.to_string():
			self.style['TextView']['font'] = None
			self.view.modify_font(None)
		else:
			self.style['TextView']['font'] = font.to_string()
			self.view.modify_font(font)

		self.style.write()

# Need to register classes defining gobject signals
gobject.type_register(PageView)


class InsertDateDialog(Dialog):

	FORMAT_COL = 0 # format string
	DATE_COL = 1 # strfime rendering of the format

	def __init__(self, ui, buffer):
		Dialog.__init__(self, ui, _('Insert Date and Time'), # T: Dialog title
			button=(_('_Insert'), 'gtk-ok') )  # T: Button label
		self.buffer = buffer
		self.date = datetime.datetime.now()

		self.uistate.setdefault('lastusedformat', '')
		self.uistate.setdefault('linkdate', False)
		self.uistate.setdefault('calendar_expanded', False)

		from zim.plugins.calendar import Calendar # FIXME put this in zim.gui.widgets

		self.calendar_expander = gtk.expander_new_with_mnemonic('<b>'+_("_Calendar")+'</b>')
			# T: expander label in "insert date" dialog
		self.calendar_expander.set_use_markup(True)
		self.calendar_expander.set_expanded(self.uistate['calendar_expanded'])
		self.calendar = Calendar()
		self.calendar.display_options(
			gtk.CALENDAR_SHOW_HEADING |
			gtk.CALENDAR_SHOW_DAY_NAMES |
			gtk.CALENDAR_SHOW_WEEK_NUMBERS )
		self.calendar.connect('day-selected', lambda c: self.set_date(c.get_date()))
		self.calendar_expander.add(self.calendar)
		self.vbox.pack_start(self.calendar_expander, False)

		label = gtk.Label()
		label.set_markup('<b>'+_("Format")+'</b>') # T: label in "insert date" dialog
		label.set_alignment(0.0, 0.5)
		self.vbox.pack_start((label), False)

		model = gtk.ListStore(str, str) # FORMAT_COL, DATE_COL
		self.view = BrowserTreeView(model)
		window = gtk.ScrolledWindow()
		window.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
		window.add(self.view)
		self.vbox.add(window)

		cell_renderer = gtk.CellRendererText()
		column = gtk.TreeViewColumn('_date_', cell_renderer, text=1)
		self.view.append_column(column)
		self.view.set_headers_visible(False)
		self.view.connect('row-activated',
			lambda *a: self.response(gtk.RESPONSE_OK) )

		self.linkbutton = gtk.CheckButton(_('_Link to date'))
			# T: check box in InsertDate dialog
		self.linkbutton.set_active(self.uistate['linkdate'])
		self.vbox.pack_start(self.linkbutton, False)

		button = gtk.Button(stock=gtk.STOCK_EDIT)
		button.connect('clicked', self.on_edit)
		self.action_area.add(button)
		self.action_area.reorder_child(button, 1)

		self.load_file()
		self.set_date(self.date)

	def load_file(self):
		lastused = None
		model = self.view.get_model()
		model.clear()
		for line in config_file('dates.list'):
			line = line.strip()
			if not line or line.startswith('#'): continue
			try:
				format = line
				iter = model.append((format, format))
				if format == self.uistate['lastusedformat']:
					lastused = iter
			except:
				logger.exception('Could not parse date: %s', line)

		if not lastused is None:
			path = model.get_path(lastused)
			self.view.get_selection().select_path(path)

	def set_date(self, date):
		self.date = date

		def update_date(model, path, iter):
			format = model[iter][self.FORMAT_COL]
			try:
				string = date.strftime(format)
			except ValueError:
				string = 'INVALID: ' + format
			model[iter][self.DATE_COL] = string

		model = self.view.get_model()
		model.foreach(update_date)

		link = date.strftime('%Y-%m-%d') # YYYY-MM-DD
		self.link = self.ui.notebook.suggest_link(self.ui.page, link)
		self.linkbutton.set_sensitive(not self.link is None)

	def save_uistate(self):
		model, iter = self.view.get_selection().get_selected()
		format = model[iter][self.FORMAT_COL]
		self.uistate['lastusedformat'] = format
		self.uistate['linkdate'] = self.linkbutton.get_active()
		self.uistate['calendar_expanded'] = self.calendar_expander.get_expanded()

	def on_edit(self, button):
		file = config_file('dates.list')
		if self.ui.edit_config_file(file):
			self.load_file()

	def do_response_ok(self):
		model, iter = self.view.get_selection().get_selected()
		text = model[iter][self.DATE_COL]
		if self.link and self.linkbutton.get_active():
			self.buffer.insert_link_at_cursor(text, self.link.name)
		else:
			self.buffer.insert_at_cursor(text)

		return True


class InsertImageDialog(FileDialog):

	def __init__(self, ui, buffer, path, file=None):
		FileDialog.__init__(
			self, ui, _('Insert Image'), gtk.FILE_CHOOSER_ACTION_OPEN)
			# T: Dialog title
		self.buffer = buffer
		self.path = path
		self.add_filter_images()

		self.uistate.setdefault('attach_inserted_images', False)
		checkbox = gtk.CheckButton(_('Attach image first'))
			# T: checkbox in the "Insert Image" dialog
		checkbox.set_active(self.uistate['attach_inserted_images'])
		self.filechooser.set_extra_widget(checkbox)
		self.uistate.setdefault('last_image_folder','~')
		self.filechooser.set_current_folder(self.uistate['last_image_folder'])

		if file:
			self.set_file(file)

	def do_response_ok(self):
		file = self.get_file()
		if file is None: return False

		if not gtk.gdk.pixbuf_get_file_info(file.path):
			ErrorDialog(self, _('File type not supported: %s' % file.get_mimetype())).run()
				# T: Error message when trying to insert a not supported file as image
			return False

		checkbox = self.filechooser.get_extra_widget()
		self.uistate['attach_inserted_images'] = checkbox.get_active()
		self.uistate['last_image_folder'] = self.filechooser.get_current_folder()
		if self.uistate['attach_inserted_images']:
			# Similar code in zim.gui.AttachFileDialog
			dir = self.ui.notebook.get_attachments_dir(self.path)
			if not file.dir == dir:
				file = self.ui.do_attach_file(self.path, file)
				if file is None:
					return False # Cancelled overwrite dialog

		src = self.ui.notebook.relative_filepath(file, self.path) or file.uri
		self.buffer.insert_image_at_cursor(file, src)
		return True


class EditImageDialog(Dialog):

	def __init__(self, ui, buffer, path):
		Dialog.__init__(self, ui, _('Edit Image')) # T: Dialog title
		self.buffer = buffer
		self.path = path

		iter = buffer.get_iter_at_mark(buffer.get_insert())
		image_data = self.buffer.get_image_data(iter)
		if image_data is None:
			iter.backward_char()
			image_data = self.buffer.get_image_data(iter)
			assert image_data, 'No image found'
		self._image_data = image_data.copy()
		self._iter = iter.get_offset()

		src = image_data['src']
		if '?' in src:
			i = src.find('?')
			src = src[:i]

		self.add_form( [
			('file', 'image', _('Location')), # T: Input in 'edit image' dialog
			('width', 'int', _('Width'), (0, 1)), # T: Input in 'edit image' dialog
			('height', 'int', _('Height'), (0, 1)) # T: Input in 'edit image' dialog
		],
			{'file': src}
			# range for width and height are set in set_ranges()
		)
		self.form.widgets['file'].set_use_relative_paths(ui.notebook, path)
			# Show relative paths

		reset_button = gtk.Button(_('_Reset Size'))
			# T: Button in 'edit image' dialog
		hbox = gtk.HBox()
		hbox.pack_end(reset_button, False)
		self.vbox.add(hbox)

		reset_button.connect_object('clicked',
			self.__class__.reset_dimensions, self)
		#~ self.form.widgets['file'].connect_object('activate',
			#~ self.__class__.reset_dimensions, self)
		self.form.widgets['width'].connect_object('value-changed',
			self.__class__.do_width_changed, self)
		self.form.widgets['height'].connect_object('value-changed',
			self.__class__.do_height_changed, self)

		# Init ranges based on original
		self.reset_dimensions()

		# Set current scale if any
		if 'width' in image_data:
			self.form.widgets['width'].set_value(int(image_data['width']))
		elif 'height' in image_data:
			self.form.widgets['height'].set_value(int(image_data['height']))

	def reset_dimensions(self):
		self._image_data.pop('width', None)
		self._image_data.pop('height', None)
		width = self.form.widgets['width']
		height = self.form.widgets['height']
		file = self.form['file']
		try:
			info, w, h = gtk.gdk.pixbuf_get_file_info(file.path)
		except:
			logger.warn('Could not get size for image: %s', file.path)
			width.set_sensitive(False)
			height.set_sensitive(False)
		else:
			width.set_sensitive(True)
			height.set_sensitive(True)
			self._block = True
			width.set_range(0, 4*w)
			width.set_value(w)
			height.set_range(0, 4*w)
			height.set_value(h)
			self._block = False
			self._ratio = float(w)/ h

	def do_width_changed(self):
		if self._block: return
		self._image_data.pop('height', None)
		self._image_data['width'] = int(self.form['width'])
		h = int(float(self._image_data['width']) / self._ratio)
		self._block = True
		self.form['height'] = h
		self._block = False

	def do_height_changed(self):
		if self._block: return
		self._image_data.pop('width', None)
		self._image_data['height'] = int(self.form['height'])
		w = int(self._ratio * float(self._image_data['height']))
		self._block = True
		self.form['width'] = w
		self._block = False

	def do_response_ok(self):
		file = self.form['file']
		attrib = self._image_data
		attrib['src'] = self.ui.notebook.relative_filepath(file, self.path) or file.uri

		iter = self.buffer.get_iter_at_offset(self._iter)
		bound = iter.copy()
		bound.forward_char()
		with self.buffer.user_action:
			self.buffer.delete(iter, bound)
			self.buffer.insert_image_at_cursor(file, **attrib)
		return True


class InsertTextFromFileDialog(FileDialog):

	def __init__(self, ui, buffer):
		FileDialog.__init__(
			self, ui, _('Insert Text From File'), gtk.FILE_CHOOSER_ACTION_OPEN)
			# T: Dialog title
		self.buffer = buffer

	def do_response_ok(self):
		file = self.get_file()
		if file is None: return False
		parser = get_format('plain').Parser()
		tree = parser.parse(file.readlines())
		self.buffer.insert_parsetree_at_cursor(tree)
		return True


class InsertLinkDialog(Dialog):

	def __init__(self, ui, pageview):
		self.pageview = pageview
		href, text = self._get_link_from_buffer()

		if href: title = _('Edit Link') # T: Dialog title
		else: title = _('Insert Link') # T: Dialog title

		Dialog.__init__(self, ui, title,
			button=(_('_Link'), 'zim-link') )  # T: Dialog button

		self.add_form([
			('href', 'link', _('Link to'), pageview.page), # T: Input in 'insert link' dialog
			('text', 'string', _('Text')) # T: Input in 'insert link' dialog
		], {
			'href': href,
			'text': text,
		} )

		# Hook text entry to copy text from link when apropriate
		self.form.widgets['href'].connect('changed', self.on_href_changed)
		self.form.widgets['text'].connect('changed', self.on_text_changed)
		if self._selection_bounds or (text and text != href):
			self._copy_text = False
		else:
			self._copy_text = True

	def _get_link_from_buffer(self):
		# Get link and text from the text buffer
		href, text = '', ''

		buffer = self.pageview.view.get_buffer()
		if not buffer.get_has_selection():
			link = buffer.select_link()
			if link:
				href = link['href']
			else:
				self.pageview.autoselect()

		if buffer.get_has_selection():
			start, end = buffer.get_selection_bounds()
			text = buffer.get_text(start, end)
			self._selection_bounds = (start.get_offset(), end.get_offset())
				# Interaction in the dialog causes buffer to loose selection
				# maybe due to clipboard focus !??
				# Anyway, need to remember bounds ourselves.
			if not href:
				href = text
		else:
			self._selection_bounds = None

		return href, text

	def on_href_changed(self, o):
		# Check if we can also update text
		if not self._copy_text: return

		self._copy_text = False # block on_text_changed()
		self.form['text'] = self.form['href']
		self._copy_text = True

	def on_text_changed(self, o):
		# Check if we should stop updating text
		if not self._copy_text: return

		self._copy_text = self.form['href'] == self.form['text']

	def do_response_ok(self):
		href = self.form['href']
		if not href:
			self.form.widgets['href'].set_input_valid(False)
			return False

		type = link_type(href)
		if type == 'file':
			# Try making the path relative
			file = self.form.widgets['href'].get_file()
			page = self.pageview.page
			notebook = self.ui.notebook
			href = notebook.relative_filepath(file, page) or file.uri

		text = self.form['text'] or href

		buffer = self.pageview.view.get_buffer()
		with buffer.user_action:
			if self._selection_bounds:
				start, end = map(
					buffer.get_iter_at_offset, self._selection_bounds)
				buffer.delete(start, end)
			buffer.insert_link_at_cursor(text, href)

		return True


class FindWidget(object):
	'''Base class for FindBar and FindAndReplaceDialog'''

	def __init__(self, textview):
		self.textview = textview

		self.find_entry = InputEntry()
		self.find_entry.connect_object(
			'changed', self.__class__.on_find_entry_changed, self)
		self.find_entry.connect_object(
			'activate', self.__class__.on_find_entry_activate, self)

		self.next_button = Button(_('_Next'), gtk.STOCK_GO_FORWARD)
			# T: button in find bar and find & replace dialog
		self.next_button.connect_object(
			'clicked', self.__class__.find_next, self)
		self.next_button.set_sensitive(False)

		self.previous_button = Button(_('_Previous'), gtk.STOCK_GO_BACK)
			# T: button in find bar and find & replace dialog
		self.previous_button.connect_object(
			'clicked', self.__class__.find_previous, self)
		self.previous_button.set_sensitive(False)

		self.case_option_checkbox = gtk.CheckButton(_('Match _case'))
			# T: checkbox option in find bar and find & replace dialog
		self.case_option_checkbox.connect_object(
			'toggled', self.__class__.on_find_entry_changed, self)

		self.word_option_checkbox = gtk.CheckButton(_('Whole _word'))
			# T: checkbox option in find bar and find & replace dialog
		self.word_option_checkbox.connect_object(
			'toggled', self.__class__.on_find_entry_changed, self)

		self.regex_option_checkbox = gtk.CheckButton(_('_Regular expression'))
			# T: checkbox option in find bar and find & replace dialog
		self.regex_option_checkbox.connect_object(
			'toggled', self.__class__.on_find_entry_changed, self)

		self.highlight_checkbox = gtk.CheckButton(_('_Highlight'))
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
			self.textview.scroll_to_mark(buffer.get_insert(), 0.3)

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
		self.textview.scroll_to_mark(buffer.get_insert(), 0.3)

	def find_previous(self):
		buffer = self.textview.get_buffer()
		buffer.finder.find_previous()
		self.textview.scroll_to_mark(buffer.get_insert(), 0.3)


class FindBar(FindWidget, gtk.HBox):

	# TODO use smaller buttons ?

	def __init__(self, textview):
		gtk.HBox.__init__(self, spacing=5)
		FindWidget.__init__(self, textview)

		self.pack_start(gtk.Label(_('Find')+': '), False)
			# T: label for input in find bar on bottom of page
		self.pack_start(self.find_entry, False)
		self.pack_start(self.previous_button, False)
		self.pack_start(self.next_button, False)
		if ui_environment['smallscreen']:
			# E.g. Maemo Nxx0 devices have not enough space for so many
			# widgets, so let's put options in a menu button.
			# FIXME need to rewrite this hack to integrate nicely with
			# the FindWidget base class
			# FIXME ideally behavior would switch on the fly based on
			# actual screensize - we can detect when these widgets
			# fit or not by using "x_size, y_size = mywidget.window.get_size()"
			# or "mywidget.get_allocation().width" to get the widgets and window size
			# and probably re-draw when the screensize or windowsize changes
			# by listening to window resize events.
			# Alternatively we can always put options in this menu
			menu = gtk.Menu()
			item = gtk.CheckMenuItem(self.case_option_checkbox.get_label())
			item.connect('toggled',
				lambda sender, me: me.case_option_checkbox.set_active(sender.get_active()), self)
			menu.append(item)
			item = gtk.CheckMenuItem(self.highlight_checkbox.get_label())
			item.connect('toggled',
				lambda sender, me: me.highlight_checkbox.set_active(sender.get_active()),self)
			menu.append(item)
			if ui_environment['platform'] == 'maemo':
				# maemo UI convention: up arrow button with no label
				button = MenuButton('', menu)
			else:
				button = MenuButton(_('Options'), menu) # T: Options button
			self.pack_start(button, False)
		else:
			self.pack_start(self.case_option_checkbox, False)
			self.pack_start(self.highlight_checkbox, False)

		close_button = IconButton(gtk.STOCK_CLOSE, relief=False)
		close_button.connect_object('clicked', self.__class__.hide, self)
		self.pack_end(close_button, False)

	def grab_focus(self):
		self.find_entry.grab_focus()

	def show(self):
		self.set_no_show_all(False)
		self.show_all()

	def hide(self):
		gtk.HBox.hide(self)
		self.set_no_show_all(True)
		buffer = self.textview.get_buffer()
		buffer.finder.set_highlight(False)

	def on_find_entry_activate(self):
		self.on_find_entry_changed()
		self.textview.grab_focus()

	def do_key_press_event(self, event):
		if event.keyval == KEYVAL_ESC:
			self.hide()
			return True
		else:
			return gtk.HBox.do_key_press_event(self, event)

# Need to register classes defining gobject signals
gobject.type_register(FindBar)


class FindAndReplaceDialog(FindWidget, Dialog):

	def __init__(self, ui, textview):
		Dialog.__init__(self, ui,
			_('Find and Replace'), buttons=gtk.BUTTONS_CLOSE) # T: Dialog title
		FindWidget.__init__(self, textview)

		hbox = gtk.HBox(spacing=12)
		hbox.set_border_width(12)
		self.vbox.add(hbox)

		vbox = gtk.VBox(spacing=5)
		hbox.pack_start(vbox, False)

		label = gtk.Label(_('Find what')+': ')
			# T: input label in find & replace dialog
		label.set_alignment(0.0, 0.5)
		vbox.add(label)
		vbox.add(self.find_entry)
		vbox.add(self.case_option_checkbox)
		vbox.add(self.word_option_checkbox)
		vbox.add(self.regex_option_checkbox)
		vbox.add(self.highlight_checkbox)

		label = gtk.Label(_('Replace with')+': ')
			# T: input label in find & replace dialog
		label.set_alignment(0.0, 0.5)
		vbox.add(label)
		self.replace_entry = InputEntry()
		vbox.add(self.replace_entry)

		self.bbox = gtk.VButtonBox()
		hbox.add(self.bbox)
		self.bbox.add(self.next_button)
		self.bbox.add(self.previous_button)

		replace_button = Button(_('_Replace'), gtk.STOCK_FIND_AND_REPLACE)
			# T: Button in search & replace dialog
		replace_button.connect_object('clicked', self.__class__.replace, self)
		self.bbox.add(replace_button)

		all_button = Button(_('Replace _All'), gtk.STOCK_FIND_AND_REPLACE)
			# T: Button in search & replace dialog
		all_button.connect_object('clicked', self.__class__.replace_all, self)
		self.bbox.add(all_button)

	def replace(self):
		string = self.replace_entry.get_text()
		buffer = self.textview.get_buffer()
		buffer.finder.replace(string)
		buffer.finder.find_next()

	def replace_all(self):
		string = self.replace_entry.get_text()
		buffer = self.textview.get_buffer()
		buffer.finder.replace_all(string)


class WordCountDialog(Dialog):

	def __init__(self, pageview):
		Dialog.__init__(self, pageview.ui,
			_('Word Count'), buttons=gtk.BUTTONS_CLOSE) # T: Dialog title
		self.set_resizable(False)

		def count(buffer, bounds):
			start, end = bounds
			lines = end.get_line() - start.get_line() + 1
			chars = end.get_offset() - start.get_offset()
			iter = start.copy()
			words = 0
			while iter.compare(end) < 0:
				if iter.forward_word_end():
					words += 1
				elif iter.compare(end) == 0:
					# When end is end of buffer forward_end_word returns False
					words += 1
					break
				else:
					break
			return lines, words, chars

		buffer = pageview.view.get_buffer()
		buffercount = count(buffer, buffer.get_bounds())
		insert = buffer.get_iter_at_mark(buffer.get_insert())
		start = buffer.get_iter_at_line(insert.get_line())
		end = start.copy()
		end.forward_line()
		paracount = count(buffer, (start, end))
		if buffer.get_has_selection():
			selectioncount = count(buffer, buffer.get_selection_bounds())
		else:
			selectioncount = (0, 0, 0)

		table = gtk.Table(3, 4)
		table.set_row_spacings(5)
		table.set_col_spacings(12)
		self.vbox.add(table)

		plabel = gtk.Label(_('Page')) # T: label in word count dialog
		alabel = gtk.Label(_('Paragraph')) # T: label in word count dialog
		slabel = gtk.Label(_('Selection')) # T: label in word count dialog
		wlabel = gtk.Label('<b>'+_('Words')+'</b>:') # T: label in word count dialog
		llabel = gtk.Label('<b>'+_('Lines')+'</b>:') # T: label in word count dialog
		clabel = gtk.Label('<b>'+_('Characters')+'</b>:') # T: label in word count dialog

		for label in (wlabel, llabel, clabel):
			label.set_use_markup(True)
			label.set_alignment(0.0, 0.5)

		# Heading
		table.attach(plabel, 1,2, 0,1)
		table.attach(alabel, 2,3, 0,1)
		table.attach(slabel, 3,4, 0,1)

		# Lines
		table.attach(llabel, 0,1, 1,2)
		table.attach(gtk.Label(str(buffercount[0])), 1,2, 1,2)
		table.attach(gtk.Label(str(paracount[0])), 2,3, 1,2)
		table.attach(gtk.Label(str(selectioncount[0])), 3,4, 1,2)

		# Words
		table.attach(wlabel, 0,1, 2,3)
		table.attach(gtk.Label(str(buffercount[1])), 1,2, 2,3)
		table.attach(gtk.Label(str(paracount[1])), 2,3, 2,3)
		table.attach(gtk.Label(str(selectioncount[1])), 3,4, 2,3)

		# Characters
		table.attach(clabel, 0,1, 3,4)
		table.attach(gtk.Label(str(buffercount[2])), 1,2, 3,4)
		table.attach(gtk.Label(str(paracount[2])), 2,3, 3,4)
		table.attach(gtk.Label(str(selectioncount[2])), 3,4, 3,4)
