# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

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
from time import strftime

from zim.fs import *
from zim.notebook import Path, interwiki_link
from zim.parsing import link_type, Re, url_re
from zim.config import config_file
from zim.formats import get_format, \
	ParseTree, TreeBuilder, ParseTreeBuilder, \
	BULLET, CHECKED_BOX, UNCHECKED_BOX, XCHECKED_BOX
from zim.gui.widgets import Dialog, FileDialog, ErrorDialog, Button, IconButton, BrowserTreeView
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

FIND_IN_PLACE = 1
FIND_CASE_SENSITIVE = 2
FIND_WHOLE_WORD = 4

# Check the (undocumented) list of constants in gtk.keysyms to see all names
KEYVALS_HOME = map(gtk.gdk.keyval_from_name, ('Home', 'KP_Home'))
KEYVALS_ENTER = map(gtk.gdk.keyval_from_name, ('Return', 'KP_Enter', 'ISO_Enter'))
KEYVALS_BACKSPACE = map(gtk.gdk.keyval_from_name, ('BackSpace',))
KEYVALS_TAB = map(gtk.gdk.keyval_from_name, ('Tab', 'KP_Tab'))
KEYVALS_LEFT_TAB = map(gtk.gdk.keyval_from_name, ('ISO_Left_Tab',))

#~ CHARS_END_OF_WORD = (' ', ')', '>', '.', '!', '?')
CHARS_END_OF_WORD = (' ', ')', '>')
KEYVALS_END_OF_WORD = map(
	gtk.gdk.unicode_to_keyval, map(ord, CHARS_END_OF_WORD))

KEYVALS_ASTERISK = (
	gtk.gdk.unicode_to_keyval(ord('*')), gtk.gdk.keyval_from_name('KP_Multiply'))
KEYVALS_SLASH = (
	gtk.gdk.unicode_to_keyval(ord('/')), gtk.gdk.keyval_from_name('KP_Divide'))
KEYVALS_GT = (gtk.gdk.unicode_to_keyval(ord('>')),)
KEYVALS_SPACE = (gtk.gdk.unicode_to_keyval(ord(' ')),)

KEYVAL_ESC = gtk.gdk.keyval_from_name('Escape')


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
	('insert_text_from_file', None, _('Text From _File...'), '', '', False), # T: Menu item
	('insert_external_link', 'zim-link', _('E_xternal Link...'), '', '', False), # T: Menu item
	('insert_link', 'zim-link', _('_Link...'), '<ctrl>L', _('Insert Link'), False), # T: Menu item
	('clear_formatting', None, _('_Clear Formatting'), '<ctrl>0', '', False), # T: Menu item
	('show_find', 'gtk-find', _('_Find...'), '<ctrl>F', '', True), # T: Menu item
	('find_next', None, _('Find Ne_xt'), '<ctrl>G', '', True), # T: Menu item
	('find_previous', None, _('Find Pre_vious'), '<ctrl><shift>G', '', True), # T: Menu item
	('show_find_and_replace', 'gtk-find-and-replace', _('_Replace...'), '<ctrl>H', '', False), # T: Menu item
	('show_word_count', None, _('Word Count...'), '', '', True), # T: Menu item
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
	('recursive_checklist', 'bool', 'Editing',
		_('Checking a checkbox also change any sub-items'), False),
		# T: option in preferences dialog
)

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

PIXBUF_CHR = u'\uFFFC'

# Regexes used for autoformatting
heading_re = Re(r'^(={2,7})\s*(.*)\s*(\1)?$')
page_re = Re(r'''(
	  [\w\.\-\(\)]*(?: :[\w\.\-\(\)]{2,} )+:?
	| \+\w[\w\.\-\(\)]+(?: :[\w\.\-\(\)]{2,} )*:?
)$''', re.X) # e.g. namespace:page or +subpage, but not word without ':' or '+'
interwiki_re = Re(r'\w[\w\+\-\.]+\?\w\S+$') # name?page, where page can be any url style
file_re = Re(r'''(
	  ~/[^/\s]
	| ~[^/\s]*/
	| \.\.?/
	| /[^/\s]
)\S*$''', re.X) # ~xxx/ or ~name/xxx or ../xxx  or ./xxx  or /xxx

# These sets adjust to the current locale - so not same as "[a-z]" ..
# Must be kidding - no classes for this in the regex engine !?
classes = {
	'upper': string.uppercase,
	'lower': string.lowercase,
	'letters': string.letters
}
camelcase_re = Re(r'[%(upper)s]+[%(lower)s]+[%(upper)s]+\w*$' % classes)
twoletter_re = re.compile(r'[%(letters)s]{2}' % classes)
del classes

autoformat_bullets = {
	'*': BULLET,
	'[]': UNCHECKED_BOX,
	'[*]': CHECKED_BOX,
	'[x]': XCHECKED_BOX,
}


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


class TextBuffer(gtk.TextBuffer):
	'''Zim subclass of gtk.TextBuffer.

	This class manages the contents of a TextView widget. It can load a zim
	parsetree and after editing return a new parsetree. It manages images,
	links, bullet lists etc.

	The styles supported are given in the dict 'tag_styles'. These map to
	like named TextTags. For links anonymous TextTags are used. Not all tags
	are styles though, e.g. gtkspell uses it's own tags and tags may also
	be used to highlight search results etc.

	Signals:
		begin-insert-tree () - Emitted at the begin of a complex insert
		end-insert-tree () - Emitted at the end of a complex insert
		inserted-tree (start, end, tree, interactive) - Gives inserted tree after inserting it
		textstyle-changed (style) - Emitted when textstyle at the cursor changes
		indent-changed (level) - Emitted when the indent at the cursor changes
		clear - emitted to clear the whole buffer before destruction
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
		'indent-changed': (gobject.SIGNAL_RUN_LAST, None, (int,)),
		'clear': (gobject.SIGNAL_RUN_LAST, None, ())
	}

	# style attributes
	tabstop = 30 # pixels

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
		'link': {'foreground': 'blue'},
	}

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

		for k, v in self.tag_styles.items():
			tag = self.create_tag('style-'+k, **v)
			tag.zim_type = 'style'
			if k in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
				# This is needed to get proper output in get_parse_tree
				tag.zim_tag = 'h'
				tag.zim_attrib = {'level': int(k[1])}
			else:
				tag.zim_tag = k
				tag.zim_attrib = None

		self.textstyle = None
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
		self.set_textstyle(None)
		self.set_indent(None)
		self.delete(*self.get_bounds())

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
		self._place_cursor(iter)
		self.insert_parsetree_at_cursor(tree, interactive)
		self._restore_cursor()

	def _place_cursor(self, iter=None):
		self.create_mark('zim-textbuffer-orig-insert',
			self.get_iter_at_mark(self.get_insert()), True)
		self.place_cursor(iter)

	def _restore_cursor(self):
		mark = self.get_mark('zim-textbuffer-orig-insert')
		self.place_cursor(self.get_iter_at_mark(mark))
		self.delete_mark(mark)

	def insert_parsetree_at_cursor(self, tree, interactive=False):
		'''Like insert_parsetree() but inserts at the cursor'''
		#~ print 'INSERT AT CURSOR', tree.tostring()
		self.emit('begin-insert-tree')
		startoffset = self.get_iter_at_mark(self.get_insert()).get_offset()
		if not interactive:
			self._editmode_tags = ()

		tree.decode_urls()
		root = tree.getroot()
		if root.text:
			self.insert_at_cursor(root.text)
		self._insert_element_children(root)
		self.set_editmode_from_cursor()
		startiter = self.get_iter_at_offset(startoffset)
		enditer = self.get_iter_at_mark(self.get_insert())
		self.emit('end-insert-tree')
		self.emit('inserted-tree', startiter, enditer, tree, interactive)

	def do_begin_insert_tree(self):
		self._insert_tree_in_progress = True

	def do_end_insert_tree(self):
		self._insert_tree_in_progress = False
		self.set_editmode_from_cursor(force=True)
			# emitting textstyle-changed is skipped while loading the tree

	def _insert_element_children(self, node, list_level=-1, raw=False):
		# FIXME should load list_level from cursor position
		#~ list_level = get_indent --- with bullets at indent 0 this is not bullet proof...
		if node.tag == 'zim-tree' and 'raw' in node.attrib:
			raw = node.attrib['raw']
			if isinstance(raw, basestring):
				raw = (raw != 'False')

		def force_line_start():
			# Inserts a newline if we are not at the beginning of a line
			# makes pasting a tree halfway in a line more sane
			if not raw:
				iter = self.get_iter_at_mark( self.get_insert() )
				if not iter.starts_line():
					self.insert_at_cursor('\n')

		for element in node.getchildren():
			if element.tag == 'p':
				# No force line start here on purpose
				if 'indent' in element.attrib:
					self.set_indent(int(element.attrib['indent']))

				if element.text:
					self.insert_at_cursor(element.text)

				self._insert_element_children(element, list_level=list_level, raw=raw) # recurs

				self.set_indent(None)
			elif element.tag == 'ul':
				if element.text:
					self.insert_at_cursor(element.text)

				self._insert_element_children(element, list_level=list_level+1, raw=raw) # recurs
			elif element.tag == 'li':
				force_line_start()

				if list_level < 0:
					list_level = 0 # We skipped the <ul> - raw tree ?
				if 'indent' in element.attrib:
					list_level = int(element.attrib['indent'])
				self.set_indent(list_level)
				if 'bullet' in element.attrib and element.attrib['bullet'] != '*':
					bullet = element.attrib['bullet']
				else:
					bullet = BULLET # default to '*'

				self.insert_bullet_at_cursor(bullet, raw=raw)

				if element.text:
					self.insert_at_cursor(element.text)

				self._insert_element_children(element, list_level=list_level, raw=raw) # recurs
				self.set_indent(None)

				if not raw:
					self.insert_at_cursor('\n')

			elif element.tag == 'link':
				self.insert_link_at_cursor(element.text, **element.attrib)
			elif element.tag == 'img':
				file = element.attrib['_src_file']
				self.insert_image_at_cursor(file, alt=element.text, **element.attrib)
			else:
				# Text styles
				if element.tag == 'h':
					force_line_start()
					tag = 'h'+str(element.attrib['level'])
					self.set_textstyle(tag)
				elif element.tag in self.tag_styles:
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
		self._place_cursor(iter)
		self.insert_link_at_cursor(text, href, **attrib)
		self._restore_cursor()

	def insert_link_at_cursor(self, text, href=None, **attrib):
		'''Like insert_link() but inserts at the cursor'''
		tag = self.create_link_tag(text, href, **attrib)
		self._editmode_tags = \
			filter(_is_not_link_tag, self._editmode_tags) + (tag,)
		self.insert_at_cursor(text)
		self._editmode_tags = self._editmode_tags[:-1]

	def create_link_tag(self, text, href, **attrib):
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

	def insert_pixbuf(self, iter, pixbuf):
		# Make sure we always apply the correct tags when inserting a pixbuf
		if iter.equal(self.get_iter_at_mark(self.get_insert())):
			gtk.TextBuffer.insert_pixbuf(self, iter, pixbuf)
		else:
			mode = self._editmode_tags
			self.set_editmode_from_iter(iter)
			gtk.TextBuffer.insert_pixbuf(self, iter, pixbuf)
			self._editmode_tags = mode

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

	def insert_icon(self, iter, stock):
		widget = gtk.HBox() # Need *some* widget here...
		pixbuf = widget.render_icon(stock, gtk.ICON_SIZE_MENU)
		if pixbuf is None:
			logger.warn('Could not find icon: %s', stock)
			pixbuf = widget.render_icon(gtk.STOCK_MISSING_IMAGE, gtk.ICON_SIZE_MENU)
		pixbuf.zim_type = 'icon'
		pixbuf.zim_attrib = {'stock': stock}
		self.insert_pixbuf(iter, pixbuf)

	def insert_icon_at_cursor(self, stock):
		iter = self.get_iter_at_mark(self.get_insert())
		self.insert_icon(iter, stock)

	def insert_bullet(self, iter, bullet):
		self._place_cursor(iter)
		self.insert_bullet_at_cursor(bullet)
		self._restore_cursor()

	def insert_bullet_at_cursor(self, bullet, raw=False):
		'''Insert a bullet plus a space at the cursor position.
		If 'raw' is True the space will be omitted and the check that
		cursor position must be at the start of a line will not be
		enforced.
		'''
		if not raw:
			insert = self.get_iter_at_mark( self.get_insert() )
			assert insert.starts_line(), 'BUG: bullet not at line start'

		with self.user_action:
			if bullet == BULLET:
				if raw:
					self.insert_at_cursor(u'\u2022')
				else:
					self.insert_at_cursor(u'\u2022 ')
			elif bullet in bullet_types:
				stock = bullet_types[bullet]
				self.insert_icon_at_cursor(stock)
				if not raw:
					self.insert_at_cursor(' ')
			else:
				logger.warn('Unkown bullet type: %s', bullet)
				if raw:
					self.insert_at_cursor(u'\u2022')
				else:
					self.insert_at_cursor(u'\u2022 ')

			if not filter(_is_indent_tag, self._editmode_tags):
				iter = self.get_iter_at_mark(self.get_insert())
				self.set_indent_for_line(0, iter.get_line())
					# bullets always need indenting


	def set_textstyle(self, name):
		'''Sets the current text style. This style will be applied
		to text inserted at the cursor. Use 'set_textstyle(None)' to
		reset to normal text.
		'''
		self._editmode_tags = filter(_is_not_style_tag, self._editmode_tags)

		if not name is None:
			tag = self.get_tag_table().lookup('style-'+name)
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

	def set_editmode_from_cursor(self, force=False):
		iter = self.get_iter_at_mark(self.get_insert())
		self.set_editmode_from_iter(iter, force=force)

	def set_editmode_from_iter(self, iter, force=False):
		'''Updates the textstyle and indent from a text position.
		Triggered automatically when moving the cursor.
		'''
		tags = tuple(self.iter_get_zim_tags(iter))
		if force or not tags == self._editmode_tags:
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
		assumes inline tags (like 'strong', 'emphasis' etc.) have "left gravity".
		The "line based" tags (like 'indent', 'h', 'pre') gravitate both ways
		(but not at the same time). This method is used to determing which tags
		should be applied to newly inserted text at 'iter'.
		'''
		# For example:
		# <indent level=1>foo\n</indent><cursor><indent level=2>bar</indent>
		#	in this case new text should get indent level 2 -> right gravity
		# <indent level=1>foo\n</indent><indent level=2>bar</indent><cursor>\n
		#	in this case new text should also get indent level 2 -> left gravity
		start_tags = set(filter(_is_not_line_based_tag, iter.get_toggled_tags(True)))
		tags = filter(
			lambda tag: _is_zim_tag(tag) and not tag in start_tags,
			iter.get_tags() )

		end_tags = filter(_is_zim_tag, iter.get_toggled_tags(False))
		if filter(_is_line_based_tag, tags):
			# already have a right gravity line-based tag
			end_tags = filter(_is_not_line_based_tag, end_tags)
		tags.extend(end_tags)

		tags.sort(key=lambda tag: tag.get_priority())
		return tags

	def do_textstyle_changed(self, name):
		self.textstyle = name

	def toggle_textstyle(self, name, interactive=False):
		'''If there is a selection toggle the text style of the selection,
		otherwise toggle the text style of the cursor.
		'''
		if not self.get_has_selection():
			if self.textstyle == name:
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
			had_tag = self.range_has_tag(start, end, tag)
			self.remove_textstyle_tags(start, end)
			if not had_tag:
				self.apply_tag(tag, start, end)
			self.set_modified(True)
			if interactive:
				self.emit('end-user-action')

			self.set_editmode_from_cursor()

	def range_has_tag(self, start, end, tag):
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

	def remove_textstyle_tags(self, start, end):
		'''Removes all textstyle tags from a range'''
		self.smart_remove_tags(_is_style_tag, start, end)
		self.set_editmode_from_cursor()

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

	def set_indent(self, level):
		'''Sets the current indent level. This style will be applied
		to text inserted at the cursor. Set 'level' None to remove indenting.
		Indenting level 0 looks the same as normal text for most purposes but
		has slightly different wrap around behavior, assumes a list bullet at
		start of the line.
		'''
		self._editmode_tags = filter(_is_not_indent_tag, self._editmode_tags)

		if not level is None:
			assert level >= 0
			tag = self._get_indent_tag(level)
			self._editmode_tags = self._editmode_tags + (tag,)
		else:
			level = -1

		self.emit('indent-changed', level)

	def get_indent(self, iter=None):
		'''Returns the indent level at iter, or at cursor if 'iter' is None.'''
		if iter is None:
			iter = self.get_iter_at_mark(self.get_insert())
		tags = filter(_is_indent_tag, iter.get_tags())
		if tags:
			assert len(tags) == 1, 'BUG: overlapping indent tags'
			return tags[0].zim_attrib['indent']
		else:
			return 0

	def _get_indent_tag(self, level):
		name = 'indent-%i' % level
		tag = self.get_tag_table().lookup(name)
		if tag is None:
			margin = 12 + self.tabstop * level # offset from left side for all lines
			indent = -12 # offset for first line (bullet)
			#~ tag = self.create_tag(name, left_margin=margin, indent=indent, background='#ccc')
			tag = self.create_tag(name, left_margin=margin, indent=indent)
			tag.zim_type = 'indent'
			tag.zim_tag = 'indent'
			tag.zim_attrib = {'indent': level}
		return tag

	def set_indent_for_line(self, level, line):
		start = self.get_iter_at_line(line)
		if filter(_is_heading_tag, start.get_tags()):
			return False

		end = start.copy()
		end.forward_line()
		tags = filter(_is_indent_tag, start.get_tags())
		if tags:
			assert len(tags) == 1, 'BUG: overlapping indent tags'
			self.remove_tag(tags[0], start, end)
		tag = self._get_indent_tag(level)
		self.apply_tag(tag, start, end)
		self.set_modified(True)
		return True

	def increment_indent(self, iter):
		level = self.get_indent(iter)
		if self.set_indent_for_line(level+1, iter.get_line()):
			self.set_editmode_from_cursor() # also updates indent tag
			return True
		else:
			return False

	def decrement_indent(self, iter):
		level = self.get_indent(iter)
		if level > 0 and self.set_indent_for_line(level-1, iter.get_line()):
			self.set_editmode_from_cursor() # also updates indent tag
			return True
		else:
			return False

	def foreach_line_in_selection(self, func, userdata=None):
		'''Iterates over all lines covering the current selection and calls
		'func' for each line. The callback gets single argument, which is a
		TextIter for the start of the line. Optionally a second argument can
		be given by 'userdata'. Returns False if there is no selection.
		'''
		bounds = self.get_selection_bounds()
		if bounds:
			start, end = bounds
			self.foreach_line(start, end, func, userdata)
			return True
		else:
			return False

	def foreach_line(self, start, end, func, userdata=None):
		'''Iterates over all lines covering 'start' to 'end' and calls 'func'
		for each line. The callback gets single argument, which is a TextIter
		for the start of the line. Optionally a second argument can
		be given by 'userdata'.
		'''
		# first building list of lines because
		# iters might break when changing the buffer
		lines = []
		iter = self.get_iter_at_line(start.get_line())
		while iter.compare(end) == -1:
			lines.append(iter.get_line())
			if iter.forward_line():
				continue
			else:
				break

		if userdata is None:
			for line in lines:
				func(self.get_iter_at_line(line))
		else:
			for line in lines:
				func(self.get_iter_at_line(line), userdata)

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
		if mark.get_name() == 'insert':
			self.set_editmode_from_iter(iter)
		gtk.TextBuffer.do_mark_set(self, iter, mark)

	def do_insert_text(self, end, string, length):
		'''Signal handler for insert-text signal'''
		# First call parent for the actual insert
		if string == '\n':
			# Break tags that are not allowed to span over multiple lines
			self._editmode_tags = filter(_is_not_style_tag, self._editmode_tags)
			self._editmode_tags = filter(_is_not_link_tag, self._editmode_tags)
			# TODO make this more robust for multiline inserts
		elif string in CHARS_END_OF_WORD:
			# Break links if end-of-word char is typed at end of a link
			# without this you not insert text behind a link e.g. at the end of a line
			links = filter(_is_link_tag, self._editmode_tags)
			if links and end.ends_tag(links[0]):
				self._editmode_tags = filter(_is_not_link_tag, self._editmode_tags)
				# TODO this should go into the TextView, not here
				# Now it goes OK only because we only check single char inserts, but would break
				# for multi char inserts from the view - fixing that here breaks insert parsetree

		gtk.TextBuffer.do_insert_text(self, end, string, length)

		# Apply current text style
		length = len(unicode(string))
			# default function argument gives byte length :S
		start = end.copy()
		start.backward_chars(length)
		self.remove_all_tags(start, end)
		for tag in self._editmode_tags:
			self.apply_tag(tag, start, end)

	def do_delete_range(self, start, end):
		# Wrap actual delete to hook _do_lines_merged
		if start.get_line() != end.get_line():
			with self.user_action:
				mark = self.create_mark(None, start)
				gtk.TextBuffer.do_delete_range(self, start, end)
				iter = self.get_iter_at_mark(mark)
				self.delete_mark(mark)
				self._do_lines_merged(iter)
		else:
			gtk.TextBuffer.do_delete_range(self, start, end)

		self.set_editmode_from_cursor()
		# Delete formatted word + type should not show format again

	def _do_lines_merged(self, iter):
		# Enforce tags like 'h', 'pre' and 'indent' to be consistent over the line
		if iter.starts_line() or iter.ends_line():
			return

		end = iter.copy()
		end.forward_to_line_end()

		self.smart_remove_tags(_is_line_based_tag, iter, end)

		for tag in self.iter_get_zim_tags(iter):
			if _is_line_based_tag(tag):
				self.apply_tag(tag, iter, end)

		self.set_editmode_from_cursor()

	def do_insert_pixbuf(self, end, pixbuf):
		gtk.TextBuffer.do_insert_pixbuf(self, end, pixbuf)
		start = end.copy()
		start.backward_char()
		self.remove_all_tags(start, end)
		for tag in self._editmode_tags:
			self.apply_tag(tag, start, end)

	def get_bullet(self, line):
		iter = self.get_iter_at_line(line)
		return self._get_bullet(iter)

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

	def _iter_forward_past_bullet(self, iter, bullet):
		assert bullet in (BULLET, CHECKED_BOX, UNCHECKED_BOX, XCHECKED_BOX)
		# other bullet types might need to skip different number of char etc.
		iter.forward_char()
		bound = iter.copy()
		bound.forward_char()
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
		else:
			start, end = bounds

		if raw:
			builder = TreeBuilder()
			builder.start('zim-tree', {'raw': True})
		else:
			builder = ParseTreeBuilder()
			builder.start('zim-tree')

		open_tags = []
		def set_tags(iter, tags):
			'''This function changes the parse tree based on the TextTags in
			effect for the next section of text.
			'''
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
				for tag in tags[i:]:
					t, attrib = tag.zim_tag, tag.zim_attrib
					if t == 'indent':
						bullet = self._get_bullet_at_iter(iter)
						if bullet:
							t = 'li'
							attrib = attrib.copy() # break ref with tree
							attrib['bullet'] = bullet
							self._iter_forward_past_bullet(iter, bullet)
						elif not raw and not iter.starts_line():
							# Indent not visible if it does not start at begin of line
							t = '_ignore_'
						else:
							t = 'p'
					elif t == 'pre' and not raw and not iter.starts_line():
						# Without indenting 'pre' looks the same as 'code'
						# Prevent turning into a seperate paragraph here
						t = 'code'
					elif t == 'link':
						attrib = self.get_link_data(iter)
						assert attrib['href'], 'Links should have a href'
					builder.start(t, attrib)
					open_tags.append((tag, t))

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
		iter = self.get_iter_at_mark(self.get_insert())
		iter = self.get_iter_at_line(iter.get_line())
		end = iter.copy()
		end.forward_line()
		if end.get_line() != iter.get_line():
			end.backward_char()
		self.select_range(iter, end)

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
		self.set_editmode_from_cursor()

	def toggle_checkbox(self, iter, checkbox_type=CHECKED_BOX):
		bullet = self.get_bullet_at_iter(iter)
		if bullet in (UNCHECKED_BOX, CHECKED_BOX, XCHECKED_BOX):
			if bullet == checkbox_type:
				icon = bullet_types[UNCHECKED_BOX]
			else:
				icon = bullet_types[checkbox_type]
		else:
			return False

		with self.user_action:
			bound = iter.copy()
			bound.forward_char()
			self.delete(iter, bound)
			self.insert_icon(iter, icon)

		return True

	def find_forward(self, string, flags=None):
		'''Highlight the next occurence of 'string', returns True if
		the string was found.

		Flags can be:
			FIND_IN_PLACE - do not move forward if iter is at a match alread
			FIND_CASE_SENSITIVE - check case of matches
			FIND_WHOLE_WORD - only match whole words
		'''
		return self._find(1, string, flags)

	def find_backward(self, string, flags=None):
		'''Like find_forward() but in the opposite direction'''
		return self._find(-1, string, flags)

	def _find(self, direction, string, flags):
		# TODO fix real case insensitive search
		# need to replace gtk.TextIter.forward_search and
		# gtk.TextIter.backward_search with insensitive versions
		if not string or string.isspace():
			return False
		if flags is None:
			flags = 0
		checkcase = bool(flags & FIND_CASE_SENSITIVE)

		def check_iter(iter):
			bound = iter.copy()
			bound.forward_chars(len(string))
			match = iter.get_slice(bound)
			if (not checkcase and match.lower() == string.lower()) \
			or match == string:
				if flags & FIND_WHOLE_WORD \
				and not (iter.starts_word() and bound.ends_word()):
					return False

				self.select_range(iter, bound)
				return True
			else:
				return False

		iter = self.get_iter_at_mark(self.get_insert())
		if flags & FIND_IN_PLACE and check_iter(iter):
				return True

		start, end = self.get_bounds()
		if direction == 1: # forward
			iter.forward_char() # else will behave like FIND_IN_PLACE
			func = gtk.TextIter.forward_search
			part1 = (iter, end)
			part1 = (iter, end)
			part2 = (start, iter.copy())
		else: # backward
			func = gtk.TextIter.backward_search
			part1 = (iter, start)
			part2 = (end, iter.copy())

		iter, limit = part1
		bound = func(iter, string, flags=(), limit=limit)
		while bound and not check_iter(bound[0]):
			bound = func(bound[0], string, flags=(), limit=limit)

		if not bound:
			iter, limit = part2
			bound = func(iter, string, flags=(), limit=limit)
			while bound and not check_iter(bound[0]):
				bound = func(iter, string, flags=(), limit=limit)

		if not bound:
			self.unset_selection()
			return False
		else:
			return True

	def unset_selection(self):
		iter = self.get_iter_at_mark(self.get_insert())
		self.select_range(iter, iter)

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

	def get_has_selection(self):
		'''Returns boolean whether there is a selection or not.

		Method available in gtk.TextBuffer for gtk version >= 2.10
		reproduced here for backward compatibility.
		'''
		return bool(self.get_selection_bounds())

	def copy_clipboard(self, clipboard):
		bounds = self.get_selection_bounds()
		if bounds:
			tree = self.get_parsetree(bounds)
			Clipboard().set_parsetree(self.notebook, self.page, tree)

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
		clipboard.request_parsetree(self._paste_clipboard)

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

	def do_copy_clipboard(self):
		self.get_buffer().copy_clipboard(Clipboard())

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
		tree = parsetree_from_selectiondata(selectiondata)
		if tree is None:
			logger.warn('Could not drop data type "%s"', selectiondata.target)
			dragcontext.finish(False, False, timestamp) # NOK
			return

		x, y = self.window_to_buffer_coords(gtk.TEXT_WINDOW_WIDGET, x, y)
		iter = self.get_iter_at_location(x, y)
		self.get_buffer().insert_parsetree(iter, tree)
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
				self.click_link(iter) or buffer.toggle_checkbox(iter)
			elif event.button == 3:
				buffer.toggle_checkbox(iter, XCHECKED_BOX)
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
			realhome, ourhome = self.get_home_positions(insert)
			if insert.equal(ourhome): iter = realhome
			else: iter = ourhome
			if event.state & gtk.gdk.SHIFT_MASK:
				buffer.move_mark_by_name('insert', iter)
			else:
				buffer.place_cursor(iter)
			handled = True
		elif event.keyval in KEYVALS_TAB and not event.state:
			# Tab at start of line indents
			iter = buffer.get_iter_at_mark(buffer.get_insert())
			realhome, ourhome = self.get_home_positions(iter)
			if iter.compare(ourhome) < 1:
				iter = buffer.get_iter_at_mark(buffer.get_insert())
				iter = buffer.get_iter_at_line(iter.get_line())
				with buffer.user_action:
					buffer.increment_indent(iter)
				handled = True
		elif (event.keyval in KEYVALS_LEFT_TAB
		or (event.keyval in KEYVALS_BACKSPACE
			and self.preferences['unindent_on_backspace']) and not event.state):
			# Backspace or Ctrl-Tab unindents line
			iter = buffer.get_iter_at_mark(buffer.get_insert())
			realhome, ourhome = self.get_home_positions(iter)
			if iter.compare(ourhome) < 1:
				with buffer.user_action:
					iter = buffer.get_iter_at_line(iter.get_line())
					done = buffer.decrement_indent(iter)
				if event.keyval in KEYVALS_BACKSPACE and not done:
					handled = False # do a normal backspace
				else:
					handled = True
		elif event.keyval in KEYVALS_ENTER:
			# Enter can trigger links
			iter = buffer.get_iter_at_mark(buffer.get_insert())
			link = buffer.get_link_data(iter)
			if link:
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
			mark = buffer.create_mark(None, insert)
			iter = insert.copy()
			iter.backward_char()

			if event.keyval in KEYVALS_ENTER:
				char = '\n'
			else:
				char = unichr(gtk.gdk.keyval_to_unicode(event.keyval))

			if iter.get_text(insert) != char:
				return True

			# TODO How to tell the undo stack that we want this cursor back on the next undo ?
			with buffer.user_action:
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

		def decrement_indent():
			# For selection decrement first check if all lines have indent
			level = []
			buffer.strip_selection()
			buffer.foreach_line_in_selection(
				lambda i: level.append(buffer.get_indent(i)) )
			if level and min(level) > 0:
				return buffer.foreach_line_in_selection(buffer.decrement_indent)
			else:
				return False

		with buffer.user_action:
			if event.keyval in KEYVALS_TAB:
				buffer.foreach_line_in_selection(buffer.increment_indent)
			elif event.keyval in KEYVALS_LEFT_TAB:
				decrement_indent()
			elif event.keyval in KEYVALS_BACKSPACE \
			and self.preferences['unindent_on_backspace']:
				decremented = decrement_indent()
				if not decremented:
					handled = None # nothing happened, normal backspace
			elif event.keyval in KEYVALS_ASTERISK:
				def toggle_bullet(iter):
					bound = iter.copy()
					bound.forward_char()
					if iter.get_text(bound) == u'\u2022':
						bound = iter.copy()
						buffer.iter_forward_past_bullet(bound)
						buffer.delete(iter, bound)
					else:
						buffer.insert(iter, u'\u2022 ')
				buffer.foreach_line_in_selection(toggle_bullet)
			elif event.keyval in KEYVALS_GT:
				def email_quote(iter):
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

	def get_home_positions(self, iter):
		'''Returns two text iters. If we are on a word wrapped line, both point
		to the begin of the visual line (which is not the actual paragraph
		start). If the visual begin happens to be the real line start the first
		iter will give the real line start while the second will give the start
		of the actual content on the line (so after skipping bullets and
		whitespace) while the second. In that case the two iters specify a
		range that may contain bullets or whitespace at the start of the line.
		'''
		realhome = iter.copy()
		if not self.starts_display_line(realhome):
			self.backward_display_line_start(realhome)
		if realhome.starts_line():
			ourhome = realhome.copy()
			self.get_buffer().iter_forward_past_bullet(ourhome)
			bound = ourhome.copy()
			bound.forward_char()
			while ourhome.get_text(bound) in (' ', '\t'):
				if ourhome.forward_char():
					bound.forward_char()
				else:
					break
			return realhome, ourhome
		else:
			# only start visual line, not start of real line
			return realhome, realhome.copy()

	def do_end_of_word(self, start, end, word, char):
		buffer = self.get_buffer()
		handled = True
		#~ print 'WORD >>%s<<' % word

		if filter(_is_not_indent_tag, buffer.iter_get_zim_tags(start)) \
		or filter(_is_not_indent_tag, buffer.iter_get_zim_tags(end)):
			# DO not auto-format if any zim tags are applied except for indent
			return

		def apply_link(match):
			#~ print "LINK >>%s<<" % word
			start = end.copy()
			if filter(_is_not_indent_tag, buffer.iter_get_zim_tags(end)):
				return False
			if not start.backward_chars(len(match)):
				return False
			if filter(_is_not_indent_tag, buffer.iter_get_zim_tags(start)):
				return False

			tag = buffer.create_link_tag(match, match)
			buffer.apply_tag(tag, start, end)
			return True

		if char == ' ' and start.starts_line() and word in autoformat_bullets:
			# format bullet and checkboxes
			end.forward_char() # also overwrite the space triggering the action
			mark = buffer.create_mark(None, end)
			buffer.delete(start, end)
			buffer.insert_bullet(
				buffer.get_iter_at_mark(mark), autoformat_bullets[word])
			buffer.delete_mark(mark)
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
			ourhome = start.copy()
			buffer.iter_forward_past_bullet(ourhome)
			if ourhome.equal(end): # line with bullet but no text
				buffer.delete(start, end)
			else: # we are part of bullet list - set indent + bullet
				iter = end.copy()
				iter.forward_line()
				bullet = buffer.get_bullet_at_iter(start)
				buffer.insert_bullet(iter, bullet)

# Need to register classes defining gobject signals
gobject.type_register(TextView)


class UndoActionGroup(list):
	'''Container for a set of undo actions, will be undone, redone in a single step'''

	__slots__ = ('can_merge')

	def __init__(self):
		self.can_merge = False

	def reversed(self):
		'''Returns a new UndoActionGroup with the reverse actions of this group'''
		group = UndoActionGroup()
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
		'''Block listening to events from the textbuffer untill further notice.
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
				self.buffer.delete(iter, bound)
				# TODO - replace what is on the stack with what is being deleted
				# log warning BUG if the two do not match
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
		self._buffer_signals = []
		self.page = None
		self.readonly = True
		self.readonlyset = False
		self.secondairy = secondairy
		if secondairy:
			self.readonlyset = True
		self.undostack = None
		self.image_generator_plugins = {}

		self.preferences = self.ui.preferences['PageView']
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
		self.find_bar = gtk.HBox(spacing=5)
		self.find_bar.connect('key-press-event', self.on_find_bar_key_press_event)

		self.find_bar.pack_start(gtk.Label(_('Find')+': '), False)
			# T: label for input in find bar on bottom of page
		self.find_entry = gtk.Entry()
		self.find_entry.connect('changed', self.on_find_entry_changed)
		self.find_entry.connect('activate', self.on_find_entry_activate)
		self.find_bar.pack_start(self.find_entry, False)

		self.find_prev_button = Button(_('_Previous'), gtk.STOCK_GO_BACK)
			# T: button in find bar on bottom of page
		self.find_prev_button.connect_object('clicked', self.__class__.find_previous, self)
		self.find_prev_button.set_sensitive(False)
		self.find_bar.pack_start(self.find_prev_button, False)

		self.find_next_button = Button(_('_Next'), gtk.STOCK_GO_FORWARD)
			# T: button in find bar on bottom of page
		self.find_next_button.connect_object('clicked', self.__class__.find_next, self)
		self.find_next_button.set_sensitive(False)
		self.find_bar.pack_start(self.find_next_button, False)

		close_button = IconButton(gtk.STOCK_CLOSE, relief=False)
		close_button.connect_object('clicked', self.__class__.hide_find, self)
		self.find_bar.pack_end(close_button, False)

		self.find_bar.set_no_show_all(True)
		self.pack_end(self.find_bar, False)

		## setup GUI actions
		if self.secondairy:
			# HACK - divert actions from uimanager
			self.actiongroup = gtk.ActionGroup('SecondairyPageView')
		self.ui.add_actions(ui_actions, self)

		# format actions need some custom hooks
		actiongroup = self.ui.init_actiongroup(self)
		actiongroup.add_actions(ui_format_actions)
		actiongroup.add_toggle_actions(ui_format_toggle_actions)
		for name in [a[0] for a in ui_format_actions]:
			action = actiongroup.get_action(name)
			action.zim_readonly = False
			action.connect('activate', self.do_toggle_format_action)
		for name in [a[0] for a in ui_format_toggle_actions]:
			action = actiongroup.get_action(name)
			action.zim_readonly = False
			action.connect('activate', self.do_toggle_format_action)

		# extra keybinding - FIXME needs switch on read-only
		y = gtk.gdk.unicode_to_keyval(ord('y'))
		group = self.ui.uimanager.get_accel_group()
		group.connect_group( # <Ctrl>Y
				y, gtk.gdk.CONTROL_MASK, gtk.ACCEL_VISIBLE,
				lambda *a: self.redo())


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
		try:
			font = pango.FontDescription(self.style['TextView']['font'])
		except KeyError:
			self.view.modify_font(None)
		else:
			self.view.modify_font(font)

		if 'tabstop' in self.style['TextView'] \
		and isinstance(self.style['TextView']['tabstop'], int):
			tabstop = self.style['TextView']['tabstop']
			if tabstop > 0:
				TextBuffer.tabstop = tabstop

		if 'justify' in self.style['TextView']:
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

		def assert_not_modified(page, *a):
			if page == self.page:
				assert not self.view.get_buffer().get_modified(), \
					'BUG: page changed while buffer changed as well'

		for s in ('store-page', 'delete-page', 'move-page'):
			notebook.connect_after(s, assert_not_modified)

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
		for id in self._buffer_signals:
			self._prev_buffer.disconnect(id)
		self._buffer_signals = []
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

		try:
			self.set_parsetree(tree)
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

		self._buffer_signals.append(
			buffer.connect('textstyle-changed', self.do_textstyle_changed) )
		self._buffer_signals.append(
			buffer.connect('modified-changed',
				lambda o: self.on_modified_changed(o)) )

		self.undostack = UndoStackManager(buffer)
		self.set_readonly()

	def get_page(self): return self.page

	def on_modified_changed(self, buffer):
		# one-way traffic, set page modified after modifying the buffer
		# but not the other way
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

	def get_parsetree(self):
		buffer = self.view.get_buffer()
		if buffer.get_modified():
			self._parsetree = buffer.get_parsetree()
			buffer.set_modified(False)
		#~ print self._parsetree.tostring()
		return self._parsetree

	def set_parsetree(self, tree):
		buffer = self.view.get_buffer()
		assert not buffer.get_modified(), 'BUG: changing parsetree while buffer was changed as well'
		tree.resolve_images(self.ui.notebook, self.page)
		buffer.set_parsetree(tree)
		self._parsetree = tree

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

		# partly overrule logic in ui.set_readonly()
		for action in self.actiongroup.list_actions():
			if not action.zim_readonly:
				action.set_sensitive(not self.readonly)

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

	def do_textstyle_changed(self, buffer, style):
		# set statusbar
		if style: label = style.title()
		else: label = 'None'
		self.ui.mainwindow.statusbar_style_label.set_text(label)

		# set toolbar toggles
		for name in [a[0] for a in ui_format_toggle_actions]:
			action = self.actiongroup.get_action(name)
			self._show_toggle(action, False)

		if style:
			action = self.actiongroup.get_action('toggle_format_'+style)
			if not action is None:
				self._show_toggle(action, True)

	def _show_toggle(self, action, state):
		action.handler_block_by_func(self.do_toggle_format_action)
		action.set_active(state)
		action.handler_unblock_by_func(self.do_toggle_format_action)

	def do_link_enter(self, link):
		self.ui.mainwindow.statusbar.push(1, 'Go to "%s"' % link['href'])

	def do_link_leave(self, link):
		self.ui.mainwindow.statusbar.pop(1)

	def do_link_clicked(self, link):
		'''Handler for the link-clicked signal'''
		assert isinstance(link, dict)
		href = link['href']
		type = link_type(href)
		logger.debug('Link clicked: %s: %s' % (type, link['href']))

		if type == 'interwiki':
			href = interwiki_link(href)
			type = link_type(href)

		if type == 'page':
			path = self.ui.notebook.resolve_path(href, source=self.page)
			self.ui.open_page(path)
		elif type == 'file':
			path = self.ui.notebook.resolve_file(href, self.page)
			self.ui.open_file(path)
		else:
			self.ui.open_url(href)

	def do_populate_popup(self, menu):
		buffer = self.view.get_buffer()
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
			item.set_submenu(submenu)

		# open
		if type != 'image' and link:
			item = gtk.MenuItem(_('Open'))
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
		self._toggled_checkbox(CHECKED_BOX)

	def xtoggle_checkbox(self):
		self._toggled_checkbox(XCHECKED_BOX)

	def _toggled_checkbox(self, checkbox):
		buffer = self.view.get_buffer()
		if buffer.get_has_selection():
			buffer.foreach_line_in_selection(buffer.toggle_checkbox, checkbox)
		else:
			iter = buffer.get_iter_at_mark(buffer.get_insert())
			if not iter.starts_line():
				iter = buffer.get_iter_at_line(iter.get_line())
			buffer.toggle_checkbox(iter, checkbox)

	def edit_object(self, iter=None):
		buffer = self.view.get_buffer()
		if iter:
			buffer.place_cursor(iter)

		iter = buffer.get_iter_at_mark(buffer.get_insert())
		if buffer.get_link_tag(iter):
			return EditLinkDialog(self.ui, self).run()

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

		if not buffer.get_has_selection():
			if iter:
				buffer.place_cursor(iter)
			buffer.select_link()

		start, end = buffer.get_selection_bounds()
		buffer.remove_link(start, end)

	def insert_date(self):
		InsertDateDialog(self.ui, self.view.get_buffer()).run()

	def insert_image(self, file=None, type=None, interactive=True):
		if interactive:
			InsertImageDialog(self.ui, self.view.get_buffer(), self.page, file).run()
		else:
			assert isinstance(file, File)
			src = self.ui.notebook.relative_filepath(file, self.page) or file.uri
			self.view.get_buffer().insert_image_at_cursor(file, src, type=type)

	def insert_text_from_file(self):
		InsertTextFromFileDialog(self.ui, self.view.get_buffer()).run()

	def insert_external_link(self):
		InsertExternalLinkDialog(self.ui, self).run()

	def insert_links(self, links):
		'''Non-interactive method to insert one or more links plus
		line breaks or whitespace. Resolves file links to relative paths.
		'''
		links = list(links)
		for i in range(len(links)):
			if isinstance(links[i], File):
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
		has_selection = self.autoselect()

		buffer = self.view.get_buffer()
		if has_selection:
			start, end = buffer.get_selection_bounds()
			buffer.remove_textstyle_tags(start, end)
		else:
			buffer.set_textstyle(None)

	def do_toggle_format_action(self, action):
		'''Handler that catches all actions to apply and/or toggle formats'''
		name = action.get_name()
		logger.debug('Action: %s (toggle_format action)', name)
		if name.startswith('apply_format_'): style = name[13:]
		elif name.startswith('toggle_format_'): style = name[14:]
		else: assert False, "BUG: don't known this action"
		self.toggle_format(style)

	def toggle_format(self, format):
		buffer = self.view.get_buffer()
		if not buffer.textstyle == format:
			ishead = format in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6')
			self.autoselect(selectline=ishead)
		buffer.toggle_textstyle(format, interactive=True)

	def autoselect(self, selectline=False):
		buffer = self.view.get_buffer()
		if buffer.get_has_selection():
			return True
		elif self.preferences['autoselect']:
			if selectline:
				return buffer.select_line()
			else:
				return buffer.select_word()
		else:
			return False

	def show_find(self, string=None):
		self.find_bar.set_no_show_all(False)
		self.find_bar.show_all()

		if string is None:
			self.find_entry.grab_focus()
		else:
			self.find_entry.set_text(string)
			self.view.grab_focus()

	def hide_find(self):
		self.find_bar.hide_all()
		self.find_bar.set_no_show_all(True)
		self.view.grab_focus()

	def on_find_bar_key_press_event(self, widget, event):
		if event.keyval == KEYVAL_ESC:
			self.hide_find()
			return True
		else:
			return False

	def find_next(self):
		string = self.find_entry.get_text()
		buffer = self.view.get_buffer()
		buffer.find_forward(string)
		self.view.scroll_to_mark(buffer.get_insert(), 0.3)

	def find_previous(self):
		string = self.find_entry.get_text()
		buffer = self.view.get_buffer()
		buffer.find_backward(string)
		self.view.scroll_to_mark(buffer.get_insert(), 0.3)

	def on_find_entry_changed(self, entry):
		string = entry.get_text()
		buffer = self.view.get_buffer()
		ok = buffer.find_forward(string, flags=FIND_IN_PLACE)
		self.find_next_button.set_sensitive(ok)
		self.find_prev_button.set_sensitive(ok)
		if ok:
			self.view.scroll_to_mark(buffer.get_insert(), 0.3)

	def on_find_entry_activate(self, entry):
		self.on_find_entry_changed(entry)
		self.view.grab_focus()

	def show_find_and_replace(self):
		dialog = FindAndReplaceDialog.unique(self, self)
		dialog.present()

	def show_word_count(self):
		WordCountDialog(self).run()

# Need to register classes defining gobject signals
gobject.type_register(PageView)


class InsertDateDialog(Dialog):

	def __init__(self, ui, buffer):
		Dialog.__init__(self, ui, _('Insert Date and Time'), # T: Dialog title
			button=(_('_Insert'), 'gtk-ok') )  # T: Button label
		self.buffer = buffer

		self.uistate.setdefault('lastusedformat', '')
		self.uistate.setdefault('linkdate', False)

		model = gtk.ListStore(str, str) # format, data
		self.view = BrowserTreeView(model)
		self.vbox.add(self.view)

		cell_renderer = gtk.CellRendererText()
		column = gtk.TreeViewColumn('_date_', cell_renderer, text=1)
		self.view.append_column(column)
		self.view.set_headers_visible(False)

		self.linkbutton = gtk.CheckButton(_('_Link to date'))
			# T: check box in InsertDate dialog
		self.linkbutton.set_active(self.uistate['linkdate'])
		self.vbox.pack_start(self.linkbutton, False)

		date = strftime('%Y-%m-%d') # YYYY-MM-DD
		self.link = self.ui.notebook.suggest_link(self.ui.page, date)
		if not self.link:
			self.linkbutton.set_sensitive(False)

		lastused = None
		for line in config_file('dates.list'):
			line = line.strip()
			if line.startswith('#'): continue
			try:
				format = line
				date = strftime(format)
				iter = model.append((format, date))
				if format == self.uistate['lastusedformat']:
					lastused = iter
			except:
				logger.exception('Could not parse date: %s', line)

		if not lastused is None:
			path = model.get_path(lastused)
			self.view.get_selection().select_path(path)

		self.view.connect('row-activated',
			lambda *a: self.response(gtk.RESPONSE_OK) )

		# TODO edit button which allows editing the config file

	def save_uistate(self):
		model, iter = self.view.get_selection().get_selected()
		format = model[iter][0]
		self.uistate['lastusedformat'] = format
		self.uistate['linkdate'] = self.linkbutton.get_active()

	def do_response_ok(self):
		model, iter = self.view.get_selection().get_selected()
		text = model[iter][1]
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
		if file:
			self.set_file(file)

	def do_response_ok(self):
		file = self.get_file()
		if file is None: return False
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
		self._image_data = image_data
		self._iter = iter.get_offset()

		src = image_data['src']
		if '?' in src:
			i = src.find('?')
			src = src[:i]
		self.add_fields([
			('file', 'image', _('Location'), src), # T: Input in 'edit image' dialog
			('width', 'int', _('Width'), (0, 0, 0)), # T: Input in 'edit image' dialog
			('height', 'int', _('Height'), (0, 0, 0)) # T: Input in 'edit image' dialog
		])

		reset_button = gtk.Button(_('_Reset Size'))
			# T: Button in 'edit image' dialog
		hbox = gtk.HBox()
		hbox.pack_end(reset_button, False)
		self.vbox.add(hbox)

		reset_button.connect_object('clicked',
			self.__class__.reset_dimensions, self)
		#~ self.inputs['file'].connect_object('activate',
			#~ self.__class__.reset_dimensions, self)
		self.inputs['width'].connect_object('value-changed',
			self.__class__.do_width_changed, self)
		self.inputs['height'].connect_object('value-changed',
			self.__class__.do_height_changed, self)

		self._set_dimension = None
		image_data = image_data.copy()
		self.reset_dimensions()
		if 'width' in image_data:
			self.inputs['width'].set_value(int(image_data['width']))
		elif 'height' in image_data:
			self.inputs['height'].set_value(int(image_data['height']))

	def reset_dimensions(self):
		self._image_data.pop('width', None)
		self._image_data.pop('height', None)
		filename = self.get_field('file')
		file = self.ui.notebook.resolve_file(filename, self.path)
		try:
			info, w, h = gtk.gdk.pixbuf_get_file_info(file.path)
		except:
			logger.warn('Could not get size for image: %s', file.path)
			self.inputs['width'].set_sensitive(False)
			self.inputs['height'].set_sensitive(False)
		else:
			self.inputs['width'].set_sensitive(True)
			self.inputs['height'].set_sensitive(True)
			self._block = True
			self.inputs['width'].set_range(0, 4*w)
			self.inputs['width'].set_value(w)
			self.inputs['height'].set_range(0, 4*w)
			self.inputs['height'].set_value(h)
			self._block = False
			self._ratio = float(w)/ h

	def do_width_changed(self):
		if self._block: return
		self._image_data.pop('height', None)
		self._image_data['width'] = self.get_field('width')
		h = int(float(self._image_data['width']) / self._ratio)
		self._block = True
		self.inputs['height'].set_value(h)
		self._block = False

	def do_height_changed(self):
		if self._block: return
		self._image_data.pop('width', None)
		self._image_data['height'] = self.get_field('height')
		w = int(self._ratio * self._image_data['height'])
		self._block = True
		self.inputs['width'].set_value(w)
		self._block = False

	def do_response_ok(self):
		filename = self.get_field('file')
		file = self.ui.notebook.resolve_file(filename, self.path)
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
		Dialog.__init__(self, ui, _('Insert Link'), # T: Dialog title
					path_context=pageview.page,
					button=(_('_Link'), 'zim-link') )  # T: Dialog button
		self.pageview = pageview

		href, text = self._get_link()
		self.add_fields([
			('href', 'page', _('Link to'), href), # T: Input in 'insert link' dialog
			('text', 'string', _('Text'), text) # T: Input in 'insert link' dialog
		])

	def _get_link(self):
		href = ''
		text = ''
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

	def do_response_ok(self):
		entry = self.inputs['href']
		href = entry.get_text().strip()
			# Not using PageEntry.get_path() here - keep text as typed
		if not href:
			return False

		type = link_type(href)
		if type == 'file':
			file = File(href)
			page = self.pageview.page
			notebook = self.ui.notebook
			href = notebook.relative_filepath(file, page) or file.uri

		text = self.get_field('text') or href

		buffer = self.pageview.view.get_buffer()
		with buffer.user_action:
			if self._selection_bounds:
				start, end = map(
					buffer.get_iter_at_offset, self._selection_bounds)
				buffer.delete(start, end)
			buffer.insert_link_at_cursor(text, href)

		return True


class InsertExternalLinkDialog(InsertLinkDialog):

	def __init__(self, ui, pageview):
		Dialog.__init__(self, ui, _('Insert External Link'), # T: Dialog title
					button=(_('_Link'), 'zim-link') )  # T: Dialog button
		self.pageview = pageview

		href, text = self._get_link()
		self.add_fields([
			('href', 'file', _('Link to'), href), # T: Input in 'insert link' dialog
			('text', 'string', _('Text'), text), # T: Input in 'insert link' dialog
		])


class EditLinkDialog(InsertLinkDialog):

	def __init__(self, ui, pageview):
		Dialog.__init__(self, ui, _('Edit Link'), # T: Dialog title
					path_context=pageview.page,
					button=(_('_Link'), 'zim-link') )  # T: Dialog button
		self.pageview = pageview

		href, text = self._get_link()
		type = link_type(href)
		if type == 'file': input = 'file'
		else: input = 'page'
		self.add_fields([
			('href', input, _('Link to'), href), # T: Input in 'edit link' dialog
			('text', 'string', _('Text'), text), # T: Input in 'edit link' dialog
		])


class FindAndReplaceDialog(Dialog):

	def __init__(self, pageview):
		Dialog.__init__(self, pageview.ui,
			_('Find and Replace'), buttons=gtk.BUTTONS_CLOSE) # T: Dialog title
		self.view = pageview.view

		hbox = gtk.HBox(spacing=12)
		hbox.set_border_width(12)
		self.vbox.add(hbox)

		vbox = gtk.VBox(spacing=5)
		hbox.pack_start(vbox, False)

		label = gtk.Label(_('Find what')+': ')
			# T: input label in find & replace dialog
		label.set_alignment(0.0, 0.5)
		vbox.add(label)

		self.find_entry = gtk.Entry()
		self.find_entry.set_text( pageview.find_entry.get_text() )
		self.find_entry.connect('changed', self.on_find_entry_changed)
		self.find_entry.connect('activate', self.on_find_entry_changed)
		vbox.add(self.find_entry)

		self.case_option = gtk.CheckButton(_('Match c_ase'))
			# T: checkbox option in find & replace dialog
		self.case_option.connect('toggled', self.on_find_entry_changed)
		vbox.add(self.case_option)

		self.word_option = gtk.CheckButton(_('Whole _word'))
			# T: checkbox option in find & replace dialog
		self.word_option.connect('toggled', self.on_find_entry_changed)
		vbox.add(self.word_option)

		label = gtk.Label(_('Replace with')+': ')
			# T: input label in find & replace dialog
		label.set_alignment(0.0, 0.5)
		vbox.add(label)

		self.replace_entry = gtk.Entry()
		vbox.add(self.replace_entry)

		self.bbox = gtk.VButtonBox()
		hbox.add(self.bbox)

		next_button = Button(_('_Next'), gtk.STOCK_GO_FORWARD)
			# T: Button in search & replace dialog
		next_button.connect_object('clicked', self.__class__.find_next, self)
		self.bbox.add(next_button)

		prev_button = Button(_('_Previous'), gtk.STOCK_GO_BACK)
			# T: Button in search & replace dialog
		prev_button.connect_object('clicked', self.__class__.find_previous, self)
		self.bbox.add(prev_button)

		replace_button = Button(_('_Replace'), gtk.STOCK_FIND_AND_REPLACE)
			# T: Button in search & replace dialog
		replace_button.connect_object('clicked', self.__class__.replace, self)
		self.bbox.add(replace_button)

		all_button = Button(_('Replace _All'), gtk.STOCK_FIND_AND_REPLACE)
			# T: Button in search & replace dialog
		all_button.connect_object('clicked', self.__class__.replace_all, self)
		self.bbox.add(all_button)


	@property
	def _flags(self):
		flags = 0
		if self.case_option.get_active():
			flags = flags | FIND_CASE_SENSITIVE
		if self.word_option.get_active():
			flags = flags | FIND_WHOLE_WORD
		return flags

	def find_next(self):
		string = self.find_entry.get_text()
		self.view.get_buffer().find_forward(string, flags=self._flags)

	def find_previous(self):
		string = self.find_entry.get_text()
		self.view.get_buffer().find_backward(string, flags=self._flags)

	def on_find_entry_changed(self, widget):
		string = self.find_entry.get_text()
		flags= FIND_IN_PLACE | self._flags
		ok = self.view.get_buffer().find_forward(string, flags=flags)

		for button in self.bbox.get_children():
			if isinstance(button, gtk.Button):
				button.set_sensitive(ok)

	def replace(self):
		string = self.find_entry.get_text()
		flags= FIND_IN_PLACE | self._flags
		if self.view.get_buffer().find_forward(string, flags=flags):
			buffer = self.view.get_buffer()
			assert buffer.get_has_selection(), 'BUG: find returned OK, but no selection ?'
			with buffer.user_action:
				buffer.delete_selection(False, self.view.get_editable())
				buffer.insert_at_cursor(self.replace_entry.get_text())
			return True
		else:
			return False

	def replace_all(self):
		buffer = self.view.get_buffer()
		with buffer.user_action:
			while self.replace():
				continue


class WordCountDialog(Dialog):

	def __init__(self, pageview):
		Dialog.__init__(self, pageview.ui,
			_('Word Count'), buttons=gtk.BUTTONS_CLOSE) # T: Dialog title
		self.set_resizable(False)

		def count(buffer, bounds):
			start, end = bounds
			lines = end.get_line() - start.get_line() + 1
			iter = start.copy()
			words = 0
			while iter.compare(end) < 0:
				if iter.forward_word_end():
					words += 1
				else:
					break
			return words, lines

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
			selectioncount = (0, 0)

		table = gtk.Table(3, 4)
		table.set_row_spacings(5)
		table.set_col_spacings(12)
		self.vbox.add(table)

		plabel = gtk.Label(_('Page')) # T: label in word count dialog
		alabel = gtk.Label(_('Paragraph')) # T: label in word count dialog
		slabel = gtk.Label(_('Selection')) # T: label in word count dialog
		wlabel = gtk.Label('<b>'+_('Words')+'</b>:') # T: label in word count dialog
		wlabel.set_use_markup(True)
		llabel = gtk.Label('<b>'+_('Lines')+'</b>:') # T: label in word count dialog
		llabel.set_use_markup(True)

		# Heading
		table.attach(plabel, 1,2, 0,1)
		table.attach(alabel, 2,3, 0,1)
		table.attach(slabel, 3,4, 0,1)

		# Words
		table.attach(wlabel, 0,1, 1,2)
		table.attach(gtk.Label(str(buffercount[0])), 1,2, 1,2)
		table.attach(gtk.Label(str(paracount[0])), 2,3, 1,2)
		table.attach(gtk.Label(str(selectioncount[0])), 3,4, 1,2)

		# Lines
		table.attach(llabel, 0,1, 2,3)
		table.attach(gtk.Label(str(buffercount[1])), 1,2, 2,3)
		table.attach(gtk.Label(str(paracount[1])), 2,3, 2,3)
		table.attach(gtk.Label(str(selectioncount[1])), 3,4, 2,3)

