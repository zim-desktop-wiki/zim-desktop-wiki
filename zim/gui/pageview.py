
# Copyright 2008-2019 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains the main text editor widget.
It includes all classes needed to display and edit a single page as well
as related dialogs like the dialogs to insert images, links etc.

The main widget accessed by the rest of the application is the
L{PageView} class. This wraps a L{TextView} widget which actually
shows the page. The L{TextBuffer} class is the data model used by the
L{TextView}.

@todo: for documentation group functions in more logical order
'''



import logging

from gi.repository import GObject
from gi.repository import GLib
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GdkPixbuf
from gi.repository import Pango

import re
import string
import zim.datetimetz as datetime

import zim.formats
import zim.errors

from zim.fs import File, Dir, normalize_file_uris, FilePath, adapt_from_newfs
from zim.errors import Error
from zim.config import String, Float, Integer, Boolean, Choice, ConfigManager
from zim.notebook import Path, interwiki_link, HRef, PageNotFoundError
from zim.notebook.operations import NotebookState, ongoing_operation
from zim.parsing import link_type, Re, url_re
from zim.formats import get_format, increase_list_iter, \
	ParseTree, ElementTreeModule, OldParseTreeBuilder, \
	BULLET, CHECKED_BOX, UNCHECKED_BOX, XCHECKED_BOX, MIGRATED_BOX, LINE, OBJECT
from zim.actions import get_gtk_actiongroup, action, toggle_action
from zim.gui.widgets import \
	Dialog, FileDialog, QuestionDialog, ErrorDialog, \
	IconButton, MenuButton, BrowserTreeView, InputEntry, \
	ScrolledWindow, \
	rotate_pixbuf, populate_popup_add_separator, strip_boolean_result
from zim.gui.applications import OpenWithMenu, open_url, open_file, edit_config_file
from zim.gui.clipboard import Clipboard, SelectionClipboard, \
	textbuffer_register_serialize_formats
from zim.gui.uiactions import attach_file
from zim.gui.insertedobjects import \
	InsertedObjectWidget, UnknownInsertedObject, UnknownInsertedImageObject, \
	POSITION_BEGIN, POSITION_END
from zim.utils import WeakSet
from zim.signals import callback
from zim.formats import get_dumper
from zim.formats.wiki import Dumper as WikiDumper
from zim.plugins import PluginManager


logger = logging.getLogger('zim.gui.pageview')


class LineSeparator(InsertedObjectWidget):
	'''Class to create a separation line.'''

	def __init__(self):
		InsertedObjectWidget.__init__(self)
		widget = Gtk.Box()
		widget.get_style_context().add_class(Gtk.STYLE_CLASS_BACKGROUND)
		widget.set_size_request(-1, 3)
		self.add(widget)


def is_line(line):
	'''Function used for line autoformatting.'''
	length = len(line)
	return (line == '-' * length) and (length > 4)


STOCK_CHECKED_BOX = 'zim-checked-box'
STOCK_UNCHECKED_BOX = 'zim-unchecked-box'
STOCK_XCHECKED_BOX = 'zim-xchecked-box'
STOCK_MIGRATED_BOX = 'zim-migrated-box'

bullet_types = {
	CHECKED_BOX: STOCK_CHECKED_BOX,
	UNCHECKED_BOX: STOCK_UNCHECKED_BOX,
	XCHECKED_BOX: STOCK_XCHECKED_BOX,
	MIGRATED_BOX: STOCK_MIGRATED_BOX,
}

# reverse dict
bullets = {}
for bullet in bullet_types:
	bullets[bullet_types[bullet]] = bullet

autoformat_bullets = {
	'*': BULLET,
	'[]': UNCHECKED_BOX,
	'[ ]': UNCHECKED_BOX,
	'[*]': CHECKED_BOX,
	'[x]': XCHECKED_BOX,
	'[>]': MIGRATED_BOX,
	'()': UNCHECKED_BOX,
	'( )': UNCHECKED_BOX,
	'(*)': CHECKED_BOX,
	'(x)': XCHECKED_BOX,
	'(>)': MIGRATED_BOX,
}

BULLETS = (BULLET, UNCHECKED_BOX, CHECKED_BOX, XCHECKED_BOX, MIGRATED_BOX)
CHECKBOXES = (UNCHECKED_BOX, CHECKED_BOX, XCHECKED_BOX, MIGRATED_BOX)

NUMBER_BULLET = '#.' # Special case for autonumbering
is_numbered_bullet_re = re.compile('^(\d+|\w|#)\.$')
	#: This regular expression is used to test whether a bullet belongs to a numbered list or not

# Check the (undocumented) list of constants in Gtk.keysyms to see all names
KEYVALS_HOME = list(map(Gdk.keyval_from_name, ('Home', 'KP_Home')))
KEYVALS_ENTER = list(map(Gdk.keyval_from_name, ('Return', 'KP_Enter', 'ISO_Enter')))
KEYVALS_BACKSPACE = list(map(Gdk.keyval_from_name, ('BackSpace',)))
KEYVALS_TAB = list(map(Gdk.keyval_from_name, ('Tab', 'KP_Tab')))
KEYVALS_LEFT_TAB = list(map(Gdk.keyval_from_name, ('ISO_Left_Tab',)))

#~ CHARS_END_OF_WORD = (' ', ')', '>', '.', '!', '?')
CHARS_END_OF_WORD = ('\t', ' ', ')', '>', ';')
KEYVALS_END_OF_WORD = list(map(
	Gdk.unicode_to_keyval, list(map(ord, CHARS_END_OF_WORD)))) + KEYVALS_TAB

KEYVALS_ASTERISK = (
	Gdk.unicode_to_keyval(ord('*')), Gdk.keyval_from_name('KP_Multiply'))
KEYVALS_SLASH = (
	Gdk.unicode_to_keyval(ord('/')), Gdk.keyval_from_name('KP_Divide'))
KEYVALS_GT = (Gdk.unicode_to_keyval(ord('>')),)
KEYVALS_SPACE = (Gdk.unicode_to_keyval(ord(' ')),)

KEYVAL_ESC = Gdk.keyval_from_name('Escape')
KEYVAL_POUND = Gdk.unicode_to_keyval(ord('#'))

# States that influence keybindings - we use this to explicitly
# exclude other states. E.g. MOD2_MASK seems to be set when either
# numlock or fn keys are active, resulting in keybindings failing
KEYSTATES = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.META_MASK | Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.MOD1_MASK

MENU_ACTIONS = (
	# name, stock id, label
	('insert_new_file_menu', None, _('New _Attachment')), # T: Menu title
)

ui_format_actions = (
	# name, stock id, label, accelerator, tooltip
	('apply_format_h1', None, _('Heading _1'), '<Primary>1', _('Heading 1')), # T: Menu item
	('apply_format_h2', None, _('Heading _2'), '<Primary>2', _('Heading 2')), # T: Menu item
	('apply_format_h3', None, _('Heading _3'), '<Primary>3', _('Heading 3')), # T: Menu item
	('apply_format_h4', None, _('Heading _4'), '<Primary>4', _('Heading 4')), # T: Menu item
	('apply_format_h5', None, _('Heading _5'), '<Primary>5', _('Heading 5')), # T: Menu item
	('apply_format_strong', 'gtk-bold', _('_Strong'), '<Primary>B', _('Strong')), # T: Menu item
	('apply_format_emphasis', 'gtk-italic', _('_Emphasis'), '<Primary>I', _('Emphasis')), # T: Menu item
	('apply_format_mark', 'gtk-underline', _('_Mark'), '<Primary>U', _('Mark')), # T: Menu item
	('apply_format_strike', 'gtk-strikethrough', _('_Strike'), '<Primary>K', _('Strike')), # T: Menu item
	('apply_format_sub', None, _('_Subscript'), '<Primary><Shift>b', _('_Subscript')), # T: Menu item
	('apply_format_sup', None, _('_Superscript'), '<Primary><Shift>p', _('_Superscript')), # T: Menu item
	('apply_format_code', None, _('_Verbatim'), '<Primary>T', _('Verbatim')), # T: Menu item
)

ui_format_toggle_actions = (
	# name, stock id, label, accelerator, tooltip
	('toggle_format_strong', 'gtk-bold', _('_Strong'), '', _('Strong')),
	('toggle_format_emphasis', 'gtk-italic', _('_Emphasis'), '', _('Emphasis')),
	('toggle_format_mark', 'gtk-underline', _('_Mark'), '', _('Mark')),
	('toggle_format_strike', 'gtk-strikethrough', _('_Strike'), '', _('Strike')),
)

COPY_FORMATS = zim.formats.list_formats(zim.formats.TEXT_FORMAT)
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
		_('Repeated clicking a checkbox cycles through the checkbox states'), True),
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
		_('Default format for copying text to the clipboard'), 'Text', COPY_FORMATS),
		# T: option in preferences dialog
	('file_templates_folder', 'dir', 'Editing',
		_('Folder with templates for attachment files'), '~/Templates'),
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
_is_tag_tag = lambda tag: _is_zim_tag(tag) and tag.zim_type == 'tag'
_is_not_tag_tag = lambda tag: not (_is_zim_tag(tag) and tag.zim_type == 'tag')

PIXBUF_CHR = '\uFFFC'

# Minimal distance from mark to window border after scroll_to_mark()
SCROLL_TO_MARK_MARGIN = 0.2

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

markup_re = {'style-strong': Re(r'(\*{2})(.*)\1'),
	'style-emphasis': Re(r'(\/{2})(.*)\1'),
	'style-mark': Re(r'(_{2})(.*)\1'),
	'style-pre': Re(r'(\'{2})(.*)\1'),
	'style-strike': Re(r'(~{2})(.*)\1')}

tag_re = Re(r'^(@\w+)$', re.U)

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


def increase_list_bullet(bullet):
	'''Like L{increase_list_iter()}, but handles bullet string directly
	@param bullet: a numbered list bullet, e.g. C{"1."}
	@returns: the next bullet, e.g. C{"2."} or C{None}
	'''
	next = increase_list_iter(bullet.rstrip('.'))
	if next:
		return next + '.'
	else:
		return None


class AsciiString(String):

	# pango doesn't like unicode attributes

	def check(self, value):
		value = String.check(self, value)
		if isinstance(value, str):
			return str(value)
		else:
			return value



class ConfigDefinitionConstant(String):

	def __init__(self, default, group, prefix):
		self.group = group
		self.prefix = prefix
		String.__init__(self, default=default)

	def check(self, value):
		value = String.check(self, value)
		if isinstance(value, str):
			value = value.upper()
			for prefix in (self.prefix, self.prefix.split('_', 1)[1]):
				# e.g. PANGO_WEIGHT_BOLD --> BOLD but also WEIGHT_BOLD --> BOLD
				if value.startswith(prefix):
					value = value[len(prefix):]
				value = value.lstrip('_')

			if hasattr(self.group, value):
				return getattr(self.group, value)
			else:
				raise ValueError('No such constant: %s_%s' % (self.prefix, value))
		else:
			return value

	def tostring(self, value):
		if hasattr(value, 'value_name'):
			return value.value_name
		else:
			return str(value)



class UserActionContext(object):
	'''Context manager to wrap actions in proper user-action signals

	This class used for the L{TextBuffer.user_action} attribute

	This allows syntax like::

		with buffer.user_action:
			buffer.insert(...)

	instead off::

		buffer.begin_user_action()
		buffer.insert(...)
		buffer.end_user_action()

	By wrapping actions in this "user-action" block the
	L{UndoStackManager} will see it as a single action and make it
	undo-able in a single step.
	'''

	def __init__(self, buffer):
		self.buffer = buffer

	def __enter__(self):
		self.buffer.begin_user_action()

	def __exit__(self, *a):
		self.buffer.end_user_action()


GRAVITY_RIGHT = 'right'
GRAVITY_LEFT = 'left'

class SaveCursorContext(object):
	'''Context manager used by L{TextBuffer.tmp_cursor()}

	This allows syntax like::

		with buffer.tmp_cursor(iter):
			# some manipulation using iter as cursor position

		# old cursor position restored

	Basically it keeps a mark for the old cursor and restores it
	after exiting the context.
	'''

	def __init__(self, buffer, iter=None, gravity=GRAVITY_LEFT):
		self.buffer = buffer
		self.iter = iter
		self.mark = None
		self.gravity = gravity

	def __enter__(self):
		buffer = self.buffer
		cursor = buffer.get_iter_at_mark(buffer.get_insert())
		self.mark = buffer.create_mark(None, cursor, left_gravity=(self.gravity == GRAVITY_LEFT))
		if self.iter:
			buffer.place_cursor(self.iter)

	def __exit__(self, *a):
		buffer = self.buffer
		iter = buffer.get_iter_at_mark(self.mark)
		buffer.place_cursor(iter)
		buffer.delete_mark(self.mark)


class TextBuffer(Gtk.TextBuffer):
	'''Data model for the editor widget

	This sub-class of C{Gtk.TextBuffer} manages the contents of
	the L{TextView} widget. It has an internal data model that allows
	to manipulate the formatted text by cursor positions. It manages
	images, links, bullet lists etc. The methods L{set_parsetree()}
	and L{get_parsetree()} can exchange the formatted text as a
	L{ParseTree} object which can be parsed by the L{zim.formats}
	modules.

	Styles
	======

	Formatting styles like bold, italic etc. as well as functional
	text objects like links and tags are represented by C{Gtk.TextTags}.
	For static styles these TextTags have the same name as the style.
	For links and tag anonymous TextTags are used. Be aware though that
	not all TextTags in the model are managed by us, e.g. gtkspell
	uses it's own tags. TextTags that are managed by us have an
	additional attribute C{zim_type} which gives the format type
	for this tag. All TextTags without this attribute are not ours.
	All TextTags that have a C{zim_type} attribute also have an
	C{zim_attrib} attribute, which can be either C{None} or contain
	some properties, like the C{href} property for a link. See the
	parsetree documentation for what properties to expect.

	The buffer keeps an internal state for what tags should be applied
	to new text and applies these automatically when text is inserted.
	E.g. when you place the cursor at the end of a bold area and
	start typing the new text will be bold as well. However when you
	move to the beginning of the area it will not be bold.

	One limitation is that the current code supposes only one format
	style can be applied to a part of text at the same time. This
	means you can not overlap e.g. bold and italic styles. But it
	makes the code simpler because we only deal with one style at a
	time.

	Images
	======

	Embedded images and icons are handled by C{GdkPixbuf.Pixbuf} object.
	Again the ones that are handled by us have the extry C{zim_type} and
	C{zim_attrib} attributes.

	Lists
	=====

	As far as this class is concerned bullet and checkbox lists are just
	a number of lines that start with a bullet (checkboxes are rendered
	with small images or icons, but are also considered bullets).
	There is some logic to keep list formatting nicely but it only
	applies to one line at a time. For functionality affecting a list
	as a whole see the L{TextBufferList} class.

	@todo: The buffer needs a reference to the notebook and page objects
	for the text that is being shown to make sure that e.g. serializing
	links works correctly. Check if we can get rid of page and notebook
	here and just put provide them as arguments when needed.

	@cvar tag_styles: This dict defines the formatting styles supported
	by the editor. The style properties are overruled by the values
	from the X{style.conf} config file.

	@ivar notebook: The L{Notebook} object
	@ivar page: The L{Page} object
	@ivar user_action: A L{UserActionContext} context manager
	@ivar finder: A L{TextFinder} for this buffer

	@signal: C{begin-insert-tree ()}:
	Emitted at the begin of a complex insert
	@signal: C{end-insert-tree ()}:
	Emitted at the end of a complex insert
	@signal: C{inserted-tree (start, end, tree, interactive)}:
	Gives inserted tree after inserting it
	@signal: C{textstyle-changed (style)}:
	Emitted when textstyle at the cursor changes
	@signal: C{link-clicked ()}:
	Emitted when a link is clicked; for example within a table cell
	@signal: C{clear ()}:
	emitted to clear the whole buffer before destruction
	@signal: C{undo-save-cursor (iter)}:
	emitted in some specific case where the undo stack should
	lock the current cursor position
	@signal: C{insert-objectanchor (achor)}: emitted when an object
	is inserted, should trigger L{TextView} to attach a widget

	@todo: document tag styles that are supported
	'''

	# We rely on the priority of gtk TextTags to sort links before styles,
	# and styles before indenting. Since styles are initialized on init,
	# while indenting tags are created when needed, indenting tags always
	# have the higher priority. By explicitly lowering the priority of new
	# link tags to zero we keep those tags on the lower endof the scale.


	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'insert-text': 'override',
		'begin-insert-tree': (GObject.SignalFlags.RUN_LAST, None, ()),
		'end-insert-tree': (GObject.SignalFlags.RUN_LAST, None, ()),
		'inserted-tree': (GObject.SignalFlags.RUN_LAST, None, (object, object, object, object)),
		'textstyle-changed': (GObject.SignalFlags.RUN_LAST, None, (object,)),
		'clear': (GObject.SignalFlags.RUN_LAST, None, ()),
		'undo-save-cursor': (GObject.SignalFlags.RUN_LAST, None, (object,)),
		'insert-objectanchor': (GObject.SignalFlags.RUN_LAST, None, (object,)),
		'link-clicked': (GObject.SignalFlags.RUN_LAST, None, (object,)),
	}

	# style attributes
	pixels_indent = 30 #: pixels indent for a single indent level
	bullet_icon_size = Gtk.IconSize.MENU #: constant for icon size of checkboxes etc.

	#: text styles supported by the editor
	tag_styles = {
		'h1': {'weight': Pango.Weight.BOLD, 'scale': 1.15**4},
		'h2': {'weight': Pango.Weight.BOLD, 'scale': 1.15**3},
		'h3': {'weight': Pango.Weight.BOLD, 'scale': 1.15**2},
		'h4': {'weight': Pango.Weight.ULTRABOLD, 'scale': 1.15},
		'h5': {'weight': Pango.Weight.BOLD, 'scale': 1.15, 'style': Pango.Style.ITALIC},
		'h6': {'weight': Pango.Weight.BOLD, 'scale': 1.15},
		'emphasis': {'style': Pango.Style.ITALIC},
		'strong': {'weight': Pango.Weight.BOLD},
		'mark': {'background': 'yellow'},
		'strike': {'strikethrough': True, 'foreground': 'grey'},
		'code': {'family': 'monospace'},
		'pre': {'family': 'monospace', 'wrap-mode': Gtk.WrapMode.NONE},
		'sub': {'rise': -3500, 'scale': 0.7},
		'sup': {'rise': 7500, 'scale': 0.7},
		'link': {'foreground': 'blue'},
		'tag': {'foreground': '#ce5c00'},
		'indent': {},
		'bullet-list': {},
		'numbered-list': {},
		'unchecked-checkbox': {},
		'checked-checkbox': {},
		'xchecked-checkbox': {},
		'migrated-checkbox': {},
		'find-highlight': {'background': 'magenta', 'foreground': 'white'},
		'find-match': {'background': '#38d878', 'foreground': 'white'}
	}
	#: tags that can be mapped to named TextTags
	_static_style_tags = (
		'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
		'emphasis', 'strong', 'mark', 'strike',
		'code', 'pre',
		'sub', 'sup'
	)

	tag_attributes = {
		'weight': ConfigDefinitionConstant(None, Pango.Weight, 'PANGO_WEIGHT'),
		'scale': Float(None),
		'style': ConfigDefinitionConstant(None, Pango.Style, 'PANGO_STYLE'),
		'background': AsciiString(None),
		'foreground': AsciiString(None),
		'strikethrough': Boolean(None),
		'font': AsciiString(None),
		'family': AsciiString(None),
		'wrap-mode': ConfigDefinitionConstant(None, Gtk.WrapMode, 'GTK_WRAP'),
		'indent': Integer(None),
		'underline': ConfigDefinitionConstant(None, Pango.Underline, 'PANGO_UNDERLINE'),
		'linespacing': Integer(None),
		'rise': Integer(None),
	} #: Valid properties for a style in tag_styles

	def __init__(self, notebook, page):
		'''Constructor

		@param notebook: a L{Notebook} object
		@param page: a L{Page} object
		'''
		GObject.GObject.__init__(self)
		self.notebook = notebook
		self.page = page
		self._insert_tree_in_progress = False
		self._check_edit_mode = False
		self._check_renumber = []
		self._renumbering = False
		self.user_action = UserActionContext(self)
		self.finder = TextFinder(self)

		for name in self._static_style_tags:
			tag = self.create_tag('style-' + name, **self.tag_styles[name])
			tag.zim_type = 'style'
			if name in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
				# This is needed to get proper output in get_parse_tree
				tag.zim_tag = 'h'
				tag.zim_attrib = {'level': int(name[1])}
			else:
				tag.zim_tag = name
				tag.zim_attrib = None

		self._editmode_tags = []

		textbuffer_register_serialize_formats(self, notebook, page)

		self.connect_after('delete-range', self.__class__.do_post_delete_range)

	#~ def do_begin_user_action(self):
		#~ print('>>>> USER ACTION')
		#~ pass

	def do_end_user_action(self):
		#~ print('<<<< USER ACTION')
		if self._check_edit_mode:
			self.update_editmode()
			# This flag can e.g. indicate a delete happened in this
			# user action, but we did not yet update edit mode -
			# so we do it here so we are all set for the next action

		if True: # not self._renumbering:
			lines = list(self._check_renumber)
				# copy to avoid infinite loop when updating bullet triggers new delete
			self._renumbering = True
			for line in lines:
				self.renumber_list(line)
				# This flag means we deleted a line, and now we need
				# to check if the numbering is still valid.
				# It is delayed till here because this logic only applies
				# to interactive actions.
			self._renumbering = False
			self._check_renumber = []

	def clear(self):
		'''Clear all content from the buffer'''
		self.emit('clear')

	def do_clear(self):
		self._editmode_tags = []
		self.delete(*self.get_bounds())

	def get_insert_iter(self):
		'''Get a C{Gtk.TextIter} for the current cursor position'''
		return self.get_iter_at_mark(self.get_insert())

	def tmp_cursor(self, iter=None, gravity=GRAVITY_LEFT):
		'''Get a L{SaveCursorContext} object

		@param iter: a C{Gtk.TextIter} for the new (temporary) cursor
		position
		@param gravity: give mark left or right "gravity" compared to new
		inserted text, default is "left" which means new text goes after the
		cursor position
		'''
		return SaveCursorContext(self, iter, gravity)

	def set_parsetree(self, tree):
		'''Load a new L{ParseTree} in the buffer

		This method replaces any content in the buffer with the new
		parser tree.

		@param tree: a L{ParseTree} object
		'''
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
		'''Insert a L{ParseTree} in the buffer

		This method inserts a parsetree at a specific place in the
		buffer.

		@param iter: a C{Gtk.TextIter} for the insert position
		@param tree: a L{ParseTree} object
		@param interactive: Boolean which determines how current state
		in the buffer is handled. If not interactive we break any
		existing tags and insert the tree, otherwise we insert using the
		formatting tags that that are present at iter.

		For example when a parsetree is inserted because the user pastes
		content from the clipboard C{interactive} should be C{True}.
		'''
		with self.tmp_cursor(iter):
			self.insert_parsetree_at_cursor(tree, interactive)

	def insert_parsetree_at_cursor(self, tree, interactive=False):
		'''Insert a L{ParseTree} in the buffer

		Like L{insert_parsetree()} but inserts at the current cursor
		position.

		@param tree: a L{ParseTree} object
		@param interactive: Boolean which determines how current state
		in the buffer is handled.
		'''
		#~ print('INSERT AT CURSOR', tree.tostring())

		# Check tree
		root = tree._etree.getroot() # HACK - switch to new interface !
		assert root.tag == 'zim-tree'
		raw = root.attrib.get('raw')
		if isinstance(raw, str):
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
			self._editmode_tags = []
		tree.decode_urls()

		# Actual insert
		modified = self.get_modified()
		try:
			self.emit('begin-insert-tree')
			if root.text:
				self.insert_at_cursor(root.text)
			self._insert_element_children(root, raw=raw)

			# Fix partial tree inserts
			startiter = self.get_iter_at_offset(startoffset)
			if not startiter.starts_line():
				self._do_lines_merged(startiter)

			enditer = self.get_iter_at_mark(self.get_insert())
			if not enditer.ends_line():
				self._do_lines_merged(enditer)

			# Fix text direction of indent tags
			for line in range(startiter.get_line(), enditer.get_line() + 1):
				iter = self.get_iter_at_line(line)
				tags = list(filter(_is_indent_tag, iter.get_tags()))
				if tags:
					dir = self._find_base_dir(line)
					if dir == 'RTL':
						bullet = self.get_bullet(line)
						level = self.get_indent(line)
						self._set_indent(line, level, bullet, dir=dir)
					# else pass, LTR is the default
		except:
			# Try to recover buffer state before raising
			self.update_editmode()
			startiter = self.get_iter_at_offset(startoffset)
			enditer = self.get_iter_at_mark(self.get_insert())
			self.delete(startiter, enditer)
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

	def _insert_element_children(self, node, list_level=-1, list_type=None, list_start='0', raw=False):
		# FIXME should load list_level from cursor position
		#~ list_level = get_indent --- with bullets at indent 0 this is not bullet proof...
		list_iter = list_start

		def set_indent(level, bullet=None):
			# Need special set_indent() function here because the normal
			# function affects the whole line. THis has unwanted side
			# effects when we e.g. paste a multi-line tree in the
			# middle of a indented line.
			# In contrast to the normal set_indent we treat level=None
			# and level=0 as different cases.
			self._editmode_tags = list(filter(_is_not_indent_tag, self._editmode_tags))
			if level is None:
				return # Nothing more to do

			iter = self.get_insert_iter()
			if not iter.starts_line():
				# Check existing indent - may have bullet type while we have not
				tags = list(filter(_is_indent_tag, self.iter_get_zim_tags(iter)))
				if len(tags) > 1:
					logger.warn('BUG: overlapping indent tags')
				if tags and int(tags[0].zim_attrib['indent']) == level:
					self._editmode_tags.append(tags[0])
					return # Re-use tag

			tag = self._get_indent_tag(level, bullet)
				# We don't set the LTR / RTL direction here
				# instead we update all indent tags after the full
				# insert is done.
			self._editmode_tags.append(tag)

		def force_line_start():
			# Inserts a newline if we are not at the beginning of a line
			# makes pasting a tree halfway in a line more sane
			if not raw:
				iter = self.get_iter_at_mark(self.get_insert())
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
			elif element.tag in ('ul', 'ol'):
				start = element.attrib.get('start')
				if 'indent' in element.attrib:
					level = int(element.attrib['indent'])
				else:
					level = list_level + 1
				self._insert_element_children(element, list_level=level, list_type=element.tag, list_start=start, raw=raw) # recurs
				set_indent(None)
			elif element.tag == 'li':
				force_line_start()

				if 'indent' in element.attrib:
					list_level = int(element.attrib['indent'])
				elif list_level < 0:
					list_level = 0 # We skipped the <ul> - raw tree ?

				if list_type == 'ol':
					bullet = list_iter + '.'
					list_iter = increase_list_iter(list_iter)
				elif 'bullet' in element.attrib and element.attrib['bullet'] != '*':
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
				self.insert_image_at_cursor(file, **element.attrib)
			elif element.tag == 'pre':
				if 'indent' in element.attrib:
					set_indent(int(element.attrib['indent']))
				self.set_textstyle(element.tag)
				if element.text:
					self.insert_at_cursor(element.text)
				self.set_textstyle(None)
				set_indent(None)
			elif element.tag == 'table':
				if 'indent' in element.attrib:
					set_indent(int(element.attrib['indent']))
				self.insert_table_element_at_cursor(element)
				set_indent(None)
			elif element.tag == 'line':
				anchor = LineSeparatorAnchor()
				self.insert_objectanchor_at_cursor(anchor)

			elif element.tag == 'object':
				if 'indent' in element.attrib:
					set_indent(int(element.attrib['indent']))
				self.insert_object_at_cursor(element.attrib, element.text)
				set_indent(None)
			else:
				# Text styles
				if element.tag == 'h':
					force_line_start()
					tag = 'h' + str(element.attrib['level'])
					self.set_textstyle(tag)
				elif element.tag in self._static_style_tags:
					self.set_textstyle(element.tag)
				elif element.tag == '_ignore_':
					# raw tree from undo can contain these
					self._insert_element_children(element, list_level=list_level, raw=raw) # recurs
				else:
					logger.debug("Unknown tag : %s, %s, %s", element.tag,
								element.attrib, element.text)
					assert False, 'Unknown tag: %s' % element.tag

				if element.text:
					self.insert_at_cursor(element.text)
				self.set_textstyle(None)

			if element.tail:
				self.insert_at_cursor(element.tail)

	def insert_link(self, iter, text, href, **attrib):
		'''Insert a link into the buffer

		@param iter: a C{Gtk.TextIter} for the insert position
		@param text: the text for the link as string
		@param href: the target (URL, pagename) of the link as string
		@param attrib: any other link attributes
		'''
		with self.tmp_cursor(iter):
			self.insert_link_at_cursor(text, href, **attrib)

	def insert_link_at_cursor(self, text, href=None, **attrib):
		'''Insert a link into the buffer

		Like insert_link() but inserts at the current cursor position

		@param text: the text for the link as string
		@param href: the target (URL, pagename) of the link as string
		@param attrib: any other link attributes
		'''
		tag = self._create_link_tag(text, href, **attrib)
		self._editmode_tags = \
			list(filter(_is_not_link_tag,
				list(filter(_is_not_style_tag, self._editmode_tags)))) + [tag]
		self.insert_at_cursor(text)
		self._editmode_tags = self._editmode_tags[:-1]

	def _create_link_tag(self, text, href, **attrib):
		'''Creates an anonymouse TextTag for a link'''
		if isinstance(href, File):
			href = href.uri
		assert isinstance(href, str)

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
		'''Get the C{Gtk.TextTag} for a link at a specific position, if any

		@param iter: a C{Gtk.TextIter}
		@returns: a C{Gtk.TextTag} if there is a link at C{iter},
		C{None} otherwise
		'''
		# Explicitly left gravity, otherwise position behind the link
		# would also be considered part of the link. Position before the
		# link is included here.
		for tag in iter.get_tags():
			if hasattr(tag, 'zim_type') and tag.zim_type == 'link':
				return tag
		else:
			return None

	def get_link_data(self, iter):
		'''Get the link attributes for a link at a specific position, if any

		@param iter: a C{Gtk.TextIter}
		@returns: a dict with link properties if there is a link
		at C{iter}, C{None} otherwise
		'''
		tag = self.get_link_tag(iter)

		if tag:
			link = tag.zim_attrib.copy()
			if link['href'] is None:
				# Copy text content as href
				start, end = self.get_tag_bounds(iter, tag)
				link['href'] = start.get_text(end)
			return link
		else:
			return None

	def get_tag_bounds(self, iter, tag):
		start = iter.copy()
		if not start.begins_tag(tag):
			start.backward_to_tag_toggle(tag)
		end = iter.copy()
		if not end.ends_tag(tag):
			end.forward_to_tag_toggle(tag)
		return start, end

	def insert_tag(self, iter, text, **attrib):
		'''Insert a tag into the buffer

		Insert a tag in the buffer (not a TextTag, but a tag
		like "@foo")

		@param iter: a C{Gtk.TextIter} object
		@param text: The text for the tag
		@param attrib: any other tag attributes
		'''
		with self.tmp_cursor(iter):
			self.insert_tag_at_cursor(text, **attrib)

	def insert_tag_at_cursor(self, text, **attrib):
		'''Insert a tag into the buffer

		Like C{insert_tag()} but inserts at the current cursor position

		@param text: The text for the tag
		@param attrib: any other tag attributes
		'''
		tag = self._create_tag_tag(text, **attrib)
		self._editmode_tags = \
			list(filter(_is_not_tag_tag,
				list(filter(_is_not_style_tag, self._editmode_tags)))) + [tag]
		self.insert_at_cursor(text)
		self._editmode_tags = self._editmode_tags[:-1]

	def _create_tag_tag(self, text, **attrib):
		'''Creates an annonymous TextTag for a tag'''
		tag = self.create_tag(None, **self.tag_styles['tag'])
		tag.set_priority(0) # force tags to be below styles
		tag.zim_type = 'tag'
		tag.zim_tag = 'tag'
		tag.zim_attrib = attrib
		tag.zim_attrib['name'] = None
		return tag

	def get_tag_tag(self, iter):
		'''Get the C{Gtk.TextTag} for a tag at a specific position, if any

		@param iter: a C{Gtk.TextIter}
		@returns: a C{Gtk.TextTag} if there is a tag at C{iter},
		C{None} otherwise
		'''
		# Explicitly left gravity, otherwise position behind the tag
		# would also be considered part of the tag. Position before the
		# tag is included here.
		for tag in iter.get_tags():
			if hasattr(tag, 'zim_type') and tag.zim_type == 'tag':
				return tag
		else:
			return None

	def get_tag_data(self, iter):
		'''Get the attributes for a tag at a specific position, if any

		@param iter: a C{Gtk.TextIter}
		@returns: a dict with tag properties if there is a link
		at C{iter}, C{None} otherwise
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
			attrib['name'] = start.get_text(end).lstrip('@').strip()
			return attrib
		else:
			return None

	def insert_image(self, iter, file, src, **attrib):
		'''Insert an image in the buffer

		@param iter: a C{Gtk.TextIter} for the insert position
		@param file: a L{File} object or a file path or URI
		@param src: the file path the show to the user

		If the image is e.g. specified in the page source as a relative
		link, C{file} should give the absolute path the link resolves
		to, while C{src} gives the relative path.

		@param attrib: any other image properties
		'''
		#~ If there is a property 'alt' in attrib we try to set a tooltip.
		#~ '''
		if isinstance(file, str):
			file = File(file)
		try:
			if 'width' in attrib or 'height' in attrib:
				w = int(attrib.get('width', -1))
				h = int(attrib.get('height', -1))
				pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(file.path, w, h)
			else:
				pixbuf = GdkPixbuf.Pixbuf.new_from_file(file.path)
			pixbuf = rotate_pixbuf(pixbuf)
		except:
			#~ logger.exception('Could not load image: %s', file)
			logger.warn('No such image: %s', file)
			widget = Gtk.HBox() # Need *some* widget here...
			pixbuf = widget.render_icon(Gtk.STOCK_MISSING_IMAGE, Gtk.IconSize.DIALOG)
			pixbuf = pixbuf.copy() # need unique instance to set zim_attrib

		pixbuf.zim_type = 'image'
		pixbuf.zim_attrib = attrib
		pixbuf.zim_attrib['src'] = src
		pixbuf.zim_attrib['_src_file'] = file
		self.insert_pixbuf(iter, pixbuf)

	def insert_image_at_cursor(self, file, src, **attrib):
		'''Insert an image in the buffer

		Like L{insert_image()} but inserts at the current cursor
		position

		@param file: a L{File} object or a file path or URI
		@param src: the file path the show to the user
		@param attrib: any other image properties
		'''
		iter = self.get_iter_at_mark(self.get_insert())
		self.insert_image(iter, file, src, **attrib)

	def get_image_data(self, iter):
		'''Get the attributes for an image at a specific position, if any

		@param iter: a C{Gtk.TextIter} object
		@returns: a dict with image properties or C{None}
		'''
		pixbuf = iter.get_pixbuf()
		if pixbuf and hasattr(pixbuf, 'zim_type') and pixbuf.zim_type == 'image':
			return pixbuf.zim_attrib.copy()
		else:
			return None

	def insert_object_at_cursor(self, attrib, data):
		'''Inserts a custom object in the page
		@param attrib: dict with object attributes
		@param data: string data of object
		'''
		try:
			objecttype = PluginManager.insertedobjects[attrib['type']]
		except KeyError:
			if attrib['type'].startswith('image+'):
				# Fallback for backward compatibility of image generators < zim 0.70
				objecttype = UnknownInsertedImageObject()
			else:
				objecttype = UnknownInsertedObject()

		model = objecttype.model_from_data(self.notebook, self.page, attrib, data)
		self.insert_object_model_at_cursor(objecttype, model)

	def insert_object_model_at_cursor(self, objecttype, model):
		from zim.plugins.tableeditor import TableViewObjectType # XXX

		model.connect('changed', lambda o: self.set_modified(True))

		if isinstance(objecttype, TableViewObjectType):
			anchor = TableAnchor(objecttype, model)
		else:
			anchor = PluginInsertedObjectAnchor(objecttype, model)

		self.insert_objectanchor_at_cursor(anchor)

	def insert_table_element_at_cursor(self, element):
		try:
			obj = PluginManager.insertedobjects['table']
		except KeyError:
			# HACK - if table plugin is not loaded - show table as plain text
			tree = ParseTree(element)
			lines = get_dumper('wiki').dump(tree)
			self.insert_object_at_cursor({'type': 'table'}, ''.join(lines))
		else:
			model = obj.model_from_element(element.attrib, element)
			model.connect('changed', lambda o: self.set_modified(True))

			anchor = TableAnchor(obj, model)
			self.insert_objectanchor_at_cursor(anchor)

	def insert_objectanchor_at_cursor(self, anchor):
		iter = self.get_insert_iter()
		self.insert_objectanchor(iter, anchor)

	def insert_objectanchor(self, iter, anchor):
		self.insert_child_anchor(iter, anchor)
		self.emit('insert-objectanchor', anchor)

	def get_objectanchor_at_cursor(self):
		iter = self.get_insert_iter()
		return self.get_object_achor(iter)

	def get_objectanchor(self, iter):
		anchor = iter.get_child_anchor()
		if anchor and isinstance(anchor, InsertedObjectAnchor):
			return anchor
		else:
			return None

	def set_bullet(self, line, bullet, indent=None):
		'''Sets the bullet type for a line

		Replaces any bullet that may already be present on the line.
		Set bullet C{None} to remove any bullet at this line.

		@param line: the line number
		@param bullet: the bullet type, one of::
			BULLET
			UNCHECKED_BOX
			CHECKED_BOX
			XCHECKED_BOX
			MIGRATED_BOX
			NUMBER_BULLET
			None
		or a numbered bullet, like C{"1."}
		@param indent: optional indent to set after inserting the bullet,
		but before renumbering
		'''
		if bullet == NUMBER_BULLET:
			indent = self.get_indent(line)
			_, prev = self._search_bullet(line, indent, -1)
			if prev and is_numbered_bullet_re.match(prev):
				bullet = increase_list_bullet(prev)
			else:
				bullet = '1.'

		with self.user_action:
			self._replace_bullet(line, bullet)
			if indent is not None:
				self.set_indent(line, indent)
			if bullet and is_numbered_bullet_re.match(bullet):
				self.renumber_list(line)

	def _replace_bullet(self, line, bullet):
		indent = self.get_indent(line)
		with self.tmp_cursor(gravity=GRAVITY_RIGHT):
			iter = self.get_iter_at_line(line)
			bound = iter.copy()
			self.iter_forward_past_bullet(bound)
			self.delete(iter, bound)
			# Will trigger do_delete_range, which will update indent tag

			if not bullet is None:
				iter = self.get_iter_at_line(line)
				self.place_cursor(iter) # update editmode
				self._insert_bullet_at_cursor(bullet)

			#~ self.update_indent_tag(line, bullet)
			self._set_indent(line, indent, bullet)

	def _insert_bullet_at_cursor(self, bullet, raw=False):
		'''Insert a bullet plus a space at the cursor position.
		If 'raw' is True the space will be omitted and the check that
		cursor position must be at the start of a line will not be
		enforced.

		External interface should use set_bullet(line, bullet)
		instead of calling this method directly.
		'''
		assert bullet in BULLETS or is_numbered_bullet_re.match(bullet), 'Bullet: >>%s<<' % bullet
		if not raw:
			insert = self.get_insert_iter()
			assert insert.starts_line(), 'BUG: bullet not at line start'

			if not list(filter(_is_indent_tag, self._editmode_tags)):
				# Without indent get_parsetree will not recognize
				# the icon as a bullet item. This will mess up
				# undo stack. If 'raw' we assume indent tag is set
				# already.
				dir = self._find_base_dir(insert.get_line())
				tag = self._get_indent_tag(0, bullet, dir=dir)
				self._editmode_tags.append(tag)

		with self.user_action:
			if bullet == BULLET:
				if raw:
					self.insert_at_cursor('\u2022')
				else:
					self.insert_at_cursor('\u2022 ')
			elif bullet in bullet_types:
				# Insert icon
				stock = bullet_types[bullet]
				widget = Gtk.HBox() # Need *some* widget here...
				pixbuf = widget.render_icon(stock, self.bullet_icon_size)
				if pixbuf is None:
					logger.warn('Could not find icon: %s', stock)
					pixbuf = widget.render_icon(Gtk.STOCK_MISSING_IMAGE, self.bullet_icon_size)
				pixbuf.zim_type = 'icon'
				pixbuf.zim_attrib = {'stock': stock}
				self.insert_pixbuf(self.get_insert_iter(), pixbuf)

				if not raw:
					self.insert_at_cursor(' ')
			else:
				# Numbered
				if raw:
					self.insert_at_cursor(bullet)
				else:
					self.insert_at_cursor(bullet + ' ')

	def renumber_list(self, line):
		'''Renumber list from this line downward

		This method is called when the user just typed a new bullet or
		when we suspect the user deleted some line(s) that are part
		of a numbered list. Typically there is no need to call this
		method directly, but it is exposed for testing.

		It implements the following rules:

		- If there is a numered list item above on the same level, number down
		  from there
		- Else if the line itself has a numbered bullet (and thus is top of a
		  numbered list) number down
		- Stop renumbering at the end of the list, or when a non-numeric bullet
		  is encountered on the same list level

		@param line: line number to start updating
		'''
		indent = self.get_indent(line)
		bullet = self.get_bullet(line)
		if bullet is None or not is_numbered_bullet_re.match(bullet):
			return

		_, prev = self._search_bullet(line, indent, -1)
		if prev and is_numbered_bullet_re.match(prev):
			newbullet = increase_list_bullet(prev)
		else:
			newbullet = bullet

		self._renumber_list(line, indent, newbullet)

	def renumber_list_after_indent(self, line, old_indent):
		'''Like L{renumber_list()}, but more complex rules because indent
		change has different heuristics.

		It implements the following rules:

		- If the bullet type is a checkbox, never change it (else information is
		  lost on the checkbox state)
		- Check for bullet style of the item above on the same level, else
		  the item below on the same level
		- If the bullet became part of a numbered list, renumber that list
		  either from the item above, or copying starting number from below
		- If the bullet became part of a bullet or checkbox list, change it to
		  match the list
		- If there are no other bullets on the same level and the bullet was
		  a numbered bullet, switch bullet style (number vs letter) and reset
		  the count
		- Else keep the bullet as it was

		Also, if the bullet was a numbered bullet, also renumber the
		list level where it came from.
		'''
		indent = self.get_indent(line)
		bullet = self.get_bullet(line)
		if bullet is None or bullet in CHECKBOXES:
			return

		_, prev = self._search_bullet(line, indent, -1)
		if prev:
			newbullet = increase_list_bullet(prev) or prev
		else:
			_, newbullet = self._search_bullet(line, indent, +1)
			if not newbullet:
				if not is_numbered_bullet_re.match(bullet):
					return
				elif bullet.rstrip('.') in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz':
					newbullet = '1.' # switch e.g. "a." -> "1."
				else:
					newbullet = 'a.' # switch "1." -> "a."

		if is_numbered_bullet_re.match(newbullet):
			self._renumber_list(line, indent, newbullet)
		else:
			if newbullet in CHECKBOXES:
				newbullet = UNCHECKED_BOX
			self._replace_bullet(line, newbullet)

		if is_numbered_bullet_re.match(bullet):
			# Also update old list level
			newline, newbullet = self._search_bullet(line+1, old_indent, -1)
			if newbullet and is_numbered_bullet_re.match(newbullet):
				self._renumber_list(newline, old_indent, newbullet)
			else:
				# If no item above on old level, was top or middle on old level,
				# so reset count
				newline, newbullet = self._search_bullet(line, old_indent, +1)
				if newbullet and is_numbered_bullet_re.match(newbullet):
					if newbullet.rstrip('.') in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz':
						self._renumber_list(newline, old_indent, 'a.')
					else:
						self._renumber_list(newline, old_indent, '1.')

	def _search_bullet(self, line, indent, step):
		# Return bullet for previous/next bullet item at same level
		while True:
			line += step
			try:
				mybullet = self.get_bullet(line)
				myindent = self.get_indent(line)
			except ValueError:
				return None, None

			if not mybullet or myindent < indent:
				return None, None
			elif myindent == indent:
				return line, mybullet
			# else mybullet and myindent > indent

	def _renumber_list(self, line, indent, newbullet):
		# Actually renumber for a given line downward
		assert is_numbered_bullet_re.match(newbullet)

		while True:
			try:
				mybullet = self.get_bullet(line)
				myindent = self.get_indent(line)
			except ValueError:
				break

			if not mybullet or myindent < indent:
				break
			elif myindent == indent:
				if not is_numbered_bullet_re.match(mybullet):
					break # Do not replace other bullet types
				elif mybullet != newbullet:
					self._replace_bullet(line, newbullet)
				newbullet = increase_list_bullet(newbullet)
			else:
				pass # mybullet and myindent > indent

			line += 1

	def set_textstyle(self, name):
		'''Sets the current text format style.

		@param name: the name of the format style

		This style will be applied to text inserted at the cursor.
		Use C{set_textstyle(None)} to reset to normal text.
		'''
		self._editmode_tags = list(filter(_is_not_style_tag, self._editmode_tags))

		if not name is None:
			tag = self.get_tag_table().lookup('style-' + name)
			if _is_heading_tag(tag):
				self._editmode_tags = \
					list(filter(_is_not_indent_tag, self._editmode_tags))
			self._editmode_tags.append(tag)

		if not self._insert_tree_in_progress:
			self.emit('textstyle-changed', name)

	def get_textstyle(self):
		'''Get the name of the formatting style that will be applied
		to newly inserted text

		This style may change as soon as the cursor position changes,
		so only relevant for current cursor position.
		'''
		tags = list(filter(_is_style_tag, self._editmode_tags))
		if tags:
			assert len(tags) == 1, 'BUG: can not have multiple text styles'
			return tags[0].get_property('name')[6:] # len('style-') == 6
		else:
			return None

	def update_editmode(self):
		'''Updates the text style and indenting applied to newly inderted
		text based on the current cursor position

		This method is triggered automatically when the cursor is moved,
		but there are some cases where you may need to call it manually
		to force a consistent state.
		'''
		self._check_edit_mode = False

		bounds = self.get_selection_bounds()
		if bounds:
			# For selection we set editmode based on left hand side and looking forward
			# so counting tags that apply to start of selection
			tags = list(filter(_is_zim_tag, bounds[0].get_tags()))
		else:
			# Otherwise base editmode on cursor position (looking backward)
			iter = self.get_insert_iter()
			tags = self.iter_get_zim_tags(iter)

		tags = list(tags)
		if not tags == self._editmode_tags:
			#~ print('>', [(t.zim_type, t.get_property('name')) for t in tags])
			self._editmode_tags = tags
			for tag in tags:
				if tag.zim_type == 'style':
					name = tag.get_property('name')[6:]
					self.emit('textstyle-changed', name)
					break
			else:
				self.emit('textstyle-changed', None)

	def iter_get_zim_tags(self, iter):
		'''Replacement for C{Gtk.TextIter.get_tags()} which returns
		zim specific tags

		In contrast to C{Gtk.TextIter.get_tags()} this method assumes
		"left gravity" for TextTags. This means that it returns TextTags
		ending to the left of the iter position but not TextTags starting
		to the right.

		For TextTags that should be applied per line (like 'indent', 'h',
		'pre') some additional logic is used to keep them consistent.
		So at the start of the line, we do copy TextTags starting to
		the right and not inadvertently copy formatting from the
		previous line which ends on the left.

		This method is for exampel used by L{update_editmode()} to
		determine which TextTags should be applied to newly inserted
		text at at a specific location.

		@param iter: a C{Gtk.TextIter}
		@returns: a list of C{Gtk.TextTag}s (sorted by priority)
		'''
		# Current logic works without additional indent set in
		# do_end_of_line due to the fact that the "\n" also caries
		# formatting. So putting a new \n at the end of e.g. an indented
		# line will result in two indent formatted \n characters.
		# The start of the new line is in between and has continuous
		# indent formatting.
		start_tags = list(filter(_is_zim_tag, iter.get_toggled_tags(True)))
		tags = list(filter(_is_zim_tag, iter.get_tags()))
		for tag in start_tags:
			if tag in tags:
				tags.remove(tag)
		end_tags = list(filter(_is_zim_tag, iter.get_toggled_tags(False)))
		# So now we have 3 separate sets with tags ending here,
		# starting here and being continuous here. Result will be
		# continuous tags and ending tags but logic for line based
		# tags can mix in tags starting here and filter out
		# tags ending here.

		if iter.starts_line():
			tags += list(filter(_is_line_based_tag, start_tags))
			tags += list(filter(_is_not_line_based_tag, end_tags))
		elif iter.ends_line():
			# Force only use tags from the left in order to prevent tag
			# from next line "spilling over" (should not happen, since
			# \n after end of line is still formatted with same line
			# based tag as rest of line, but handled anyway to be
			# robust to edge cases)
			tags += end_tags
		else:
			# Take any tag from left or right, with left taking precendence
			#
			# HACK: We assume line based tags are mutually exclusive
			# if this assumption breaks down need to check by tag type
			tags += end_tags
			if not list(filter(_is_line_based_tag, tags)):
				tags += list(filter(_is_line_based_tag, start_tags))

		tags.sort(key=lambda tag: tag.get_priority())
		return tags

	def toggle_textstyle(self, name):
		'''Toggle the current textstyle

		If there is a selection toggle the text style of the selection,
		otherwise toggle the text style for newly inserted text.

		This method is mainly to change the behavior for
		interactive editing. E.g. it is called indirectly when the
		user clicks one of the formatting buttons in the toolbar.

		For selections we remove the format if the whole range has the
		format already. If some part of the range does not have the
		format we apply the format to the whole tange. This makes the
		behavior of the format buttons consistent if a single tag
		applies to any range.

		@param name: the format style name
		'''
		if not self.get_has_selection():
			if name == self.get_textstyle():
				self.set_textstyle(None)
			else:
				self.set_textstyle(name)
		else:
			with self.user_action:
				start, end = self.get_selection_bounds()
				if name == 'code' and start.starts_line() \
					and end.get_line() != start.get_line():
						name = 'pre'
						tag = self.get_tag_table().lookup('style-' + name)
						if not self.whole_range_has_tag(tag, start, end):
							start, end = self._fix_pre_selection(start, end)
				elif name in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
					for line in range(start.get_line(), end.get_line()+1):
						self._remove_indent(line)

				tag = self.get_tag_table().lookup('style-' + name)
				had_tag = self.whole_range_has_tag(tag, start, end)
				self.remove_textstyle_tags(start, end)
				if not had_tag:
					self.apply_tag(tag, start, end)
				self.set_modified(True)

			self.update_editmode()

	def _fix_pre_selection(self, start, end):
		# This method converts indent back into TAB before a region is
		# formatted as "pre"
		start_mark = self.create_mark(None, start, True)
		end_mark = self.create_mark(None, end, True)

		lines = range(*sorted([start.get_line(), end.get_line()+1]))
		min_indent = min(self.get_indent(line) for line in lines)

		for line in lines:
			indent = self.get_indent(line)
			if indent > min_indent:
				self.set_indent(line, min_indent)
				n_tabs = indent - min_indent
				iter = self.get_iter_at_line(line)
				self.insert(iter, "\t"*n_tabs)

		start = self.get_iter_at_mark(start_mark)
		end = self.get_iter_at_mark(end_mark)
		self.delete_mark(start_mark)
		self.delete_mark(end_mark)
		return start, end

	def whole_range_has_tag(self, tag, start, end):
		'''Check if a certain TextTag is applied to the whole range or
		not

		@param tag: a C{Gtk.TextTag}
		@param start: a C{Gtk.TextIter}
		@param end: a C{Gtk.TextIter}
		'''
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
		'''Check if a certain TextTag appears anywhere in a range

		@param tag: a C{Gtk.TextTag}
		@param start: a C{Gtk.TextIter}
		@param end: a C{Gtk.TextIter}
		'''
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
		'''Like L{range_has_tag()} but uses a function to check for
		multiple tags. The function gets called for each TextTag in the
		range and the method returns as soon as the function returns
		C{True} for any tag. There are a number of lambda functions
		defined in the module to test categories of TextTags.

		@param func: a function that is called as: C{func(tag)} for each
		TextTag in the range
		@param start: a C{Gtk.TextIter}
		@param end: a C{Gtk.TextIter}
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
		'''Removes all format style TexTags from a range

		@param start: a C{Gtk.TextIter}
		@param end: a C{Gtk.TextIter}
		'''
		# Also remove links until we support links nested in tags
		self.smart_remove_tags(_is_style_tag, start, end)
		self.smart_remove_tags(_is_link_tag, start, end)
		self.smart_remove_tags(_is_tag_tag, start, end)
		self.update_editmode()

	def smart_remove_tags(self, func, start, end):
		'''This method removes tags over a range based on a function

		So L{range_has_tags()} for a details on such a test function.

		Please use this method instead of C{remove_tag()} when you
		are not sure if specific tags are present in the first place.
		Calling C{remove_tag()} will emit signals which make the
		L{UndoStackManager} assume the tag was there. If this was not
		the case the undo stack gets messed up.
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
		'''Get the indent level at the cursor

		@returns: a number for the indenting level
		'''
		iter = self.get_iter_at_mark(self.get_insert())
		return self.get_indent(iter.get_line())

	def get_indent(self, line):
		'''Get the indent level for a specific line

		@param line: the line number
		@returns: a number for the indenting level
		'''
		iter = self.get_iter_at_line(line)
		tags = list(filter(_is_indent_tag, iter.get_tags()))
		if tags:
			if len(tags) > 1:
				logger.warn('BUG: overlapping indent tags')
			return int(tags[0].zim_attrib['indent'])
		else:
			return 0

	def _get_indent_tag(self, level, bullet=None, dir='LTR'):
		if dir is None:
			dir = 'LTR' # Assume western default direction - FIXME need system default
		name = 'indent-%s-%i' % (dir, level)
		if bullet:
			name += '-' + bullet
		tag = self.get_tag_table().lookup(name)
		if tag is None:
			if bullet:
				if bullet == BULLET:
					stylename = 'bullet-list'
				elif bullet == CHECKED_BOX:
					stylename = 'checked-checkbox'
				elif bullet == UNCHECKED_BOX:
					stylename = 'unchecked-checkbox'
				elif bullet == XCHECKED_BOX:
					stylename = 'xchecked-checkbox'
				elif bullet == MIGRATED_BOX:
					stylename = 'migrated-checkbox'
				elif is_numbered_bullet_re.match(bullet):
					stylename = 'numbered-list'
				else:
					raise AssertionError('BUG: Unknown bullet type')
				margin = 12 + self.pixels_indent * level # offset from left side for all lines
				indent = -12 # offset for first line (bullet)
				if dir == 'LTR':
					tag = self.create_tag(name,
						left_margin=margin, indent=indent,
						**self.tag_styles[stylename])
				else: # RTL
					tag = self.create_tag(name,
						right_margin=margin, indent=indent,
						**self.tag_styles[stylename])
			else:
				margin = 12 + self.pixels_indent * level
				# Note: I would think the + 12 is not needed here, but
				# the effect in the view is different than expected,
				# putting text all the way to the left against the
				# window border
				if dir == 'LTR':
					tag = self.create_tag(name,
						left_margin=margin,
						**self.tag_styles['indent'])
				else: # RTL
					tag = self.create_tag(name,
						right_margin=margin,
						**self.tag_styles['indent'])

			tag.zim_type = 'indent'
			tag.zim_tag = 'indent'
			tag.zim_attrib = {'indent': level, '_bullet': (bullet is not None)}
		return tag

	def _find_base_dir(self, line):
		# Look for basedir of current line, else previous line
		# till start of paragraph
		# FIXME: anyway to actually find out what the TextView will render ??
		while line >= 0:
			start, end = self.get_line_bounds(line)
			text = start.get_slice(start)
			if not text or text.isspace():
				break

			dir = Pango.find_base_dir(text, len(text))
			if dir == Pango.DIRECTION_LTR:
				return 'LTR'
			elif dir == Pango.DIRECTION_RTL:
				return 'RTL'
			else:
				line -= 1
		else:
			return 'LTR' # default

	def set_indent(self, line, level, interactive=False):
		'''Set the indenting for a specific line.

		May also trigger renumbering for numbered lists.

		@param line: the line number
		@param level: the indenting level as a number, C{0} for no
		indenting, C{1} for the equivalent of 1 tab, etc.
		@param interactive: hint if indenting is result of user
		interaction, or automatic action

		If interactive, the line will be forced to end with a newline.
		Reason is that if the last line of the buffer is empty and
		does not end with a newline, the indenting will not be visible,
		giving the impression that it failed.

		@returns: C{True} for success (e.g. indenting a heading is not
		allowed, if you try it will fail and return C{False} here)
		'''
		level = level or 0

		if interactive:
			# Without content effect of indenting is not visible
			# end-of-line gives content to empty line, but last line
			# may not have end-of-line.
			start, end = self.get_line_bounds(line)
			bufferend = self.get_end_iter()
			if start.equal(end) or end.equal(bufferend):
				with self.tmp_cursor():
					self.insert(end, '\n')
					start, end = self.get_line_bounds(line)

		bullet = self.get_bullet(line)
		ok = self._set_indent(line, level, bullet)

		if ok:
			self.set_modified(True)
		return ok

	def update_indent_tag(self, line, bullet):
		'''Update the indent TextTag for a given line

		The TextTags used for indenting differ between normal indented
		paragraphs and indented items in a bullet list. The reason for
		this is that the line wrap behavior of list items should be
		slightly different to align wrapped text with the bullet.

		This method does not change the indent level for a specific line,
		but it makes sure the correct TextTag is applied. Typically
		called e.g. after inserting or deleting a bullet.

		@param line: the line number
		@param bullet: the bullet type for this line, or C{None}
		'''
		level = self.get_indent(line)
		self._set_indent(line, level, bullet)

	def _set_indent(self, line, level, bullet, dir=None):
		# Common code between set_indent() and update_indent_tag()
		self._remove_indent(line)

		start, end = self.get_line_bounds(line)
		if list(filter(_is_heading_tag, start.get_tags())):
			return level == 0 # False if you try to indent a header

		if level > 0 or bullet is not None:
			# For bullets there is a 0-level tag, otherwise 0 means None
			if dir is None:
				dir = self._find_base_dir(line)
			tag = self._get_indent_tag(level, bullet, dir=dir)
			self.apply_tag(tag, start, end)

		self.update_editmode() # also updates indent tag
		return True

	def _remove_indent(self, line):
		start, end = self.get_line_bounds(line)
		for tag in filter(_is_indent_tag, start.get_tags()):
			self.remove_tag(tag, start, end)

	def indent(self, line, interactive=False):
		'''Increase the indent for a given line

		Can be used as function for L{foreach_line_in_selection()}.

		@param line: the line number
		@param interactive: hint if indenting is result of user
		interaction, or automatic action

		@returns: C{True} if successful
		'''
		level = self.get_indent(line)
		return self.set_indent(line, level + 1, interactive)

	def unindent(self, line, interactive=False):
		'''Decrease the indent level for a given line

		Can be used as function for L{foreach_line_in_selection()}.

		@param line: the line number
		@param interactive: hint if indenting is result of user
		interaction, or automatic action

		@returns: C{True} if successful
		'''
		level = self.get_indent(line)
		return self.set_indent(line, level - 1, interactive)

	def foreach_line_in_selection(self, func, *args, **kwarg):
		'''Convenience function to call a function for each line that
		is currently selected

		@param func: function which will be called as::

			func(line, *args, **kwargs)

		where C{line} is the line number
		@param args: additional argument for C{func}
		@param kwarg: additional keyword argument for C{func}

		@returns: C{False} if there is no selection, C{True} otherwise
		'''
		bounds = self.get_selection_bounds()
		if bounds:
			start, end = bounds
			if end.starts_line():
				# exclude last line if selection ends at newline
				# because line is not visually part of selection
				end.backward_char()
			for line in range(start.get_line(), end.get_line() + 1):
				func(line, *args, **kwarg)
			return True
		else:
			return False

	def do_mark_set(self, iter, mark):
		Gtk.TextBuffer.do_mark_set(self, iter, mark)
		if mark.get_name() in ('insert', 'selection_bound'):
			self.update_editmode()

	def do_insert_text(self, iter, string, length):
		'''Signal handler for insert-text signal'''
		#~ print('INSERT', string)

		def end_or_protect_tags(string, length):
			tags = list(filter(_is_tag_tag, self._editmode_tags))
			if tags:
				if iter.ends_tag(tags[0]):
					# End tags if end-of-word char is typed at end of a tag
					# without this you can not insert text behind a tag e.g. at the end of a line
					self._editmode_tags = list(filter(_is_not_tag_tag, self._editmode_tags))
				else:
					# Forbid breaking a tag
					return '', 0
				# TODO this should go into the TextView, not here
				# Now it goes OK only because we only check single char inserts, but would break
				# for multi char inserts from the view - fixing that here breaks insert parsetree
			return string, length

		# Check if we are at a bullet or checkbox line
		# if so insert behind the bullet when you type at start of line
		# FIXME FIXME FIXME - break undo - instead disallow this home position ?
		if not self._insert_tree_in_progress and iter.starts_line() \
		and not string.endswith('\n'):
			bullet = self._get_bullet_at_iter(iter)
			if bullet:
				self._iter_forward_past_bullet(iter, bullet)
				self.place_cursor(iter)

		# Check current formatting
		if string == '\n': # CHARS_END_OF_LINE
			# Break tags that are not allowed to span over multiple lines
			self._editmode_tags = [tag for tag in self._editmode_tags if _is_pre_tag(tag) or _is_not_style_tag(tag)]
			self._editmode_tags = list(filter(_is_not_link_tag, self._editmode_tags))
			self.emit('textstyle-changed', None)
			# TODO make this more robust for multiline inserts

			string, length = end_or_protect_tags(string, length)

		elif string in CHARS_END_OF_WORD:
			# Break links if end-of-word char is typed at end of a link
			# without this you can not insert text behind a link e.g. at the end of a line
			links = list(filter(_is_link_tag, self._editmode_tags))
			if links and iter.ends_tag(links[0]):
				self._editmode_tags = list(filter(_is_not_link_tag, self._editmode_tags))
				# TODO this should go into the TextView, not here
				# Now it goes OK only because we only check single char inserts, but would break
				# for multi char inserts from the view - fixing that here breaks insert parsetree

			string, length = end_or_protect_tags(string, length)

		# Call parent for the actual insert
		Gtk.TextBuffer.do_insert_text(self, iter, string, length)

		# And finally apply current text style
		# Note: looks like parent call modified the position of the TextIter object
		# since it is still valid and now matched the end of the inserted string
		length = len(string)
			# default function argument gives byte length :S
		start = iter.copy()
		start.backward_chars(length)
		self.remove_all_tags(start, iter)
		for tag in self._editmode_tags:
			self.apply_tag(tag, start, iter)

	def insert_child_anchor(self, iter, anchor):
		# Make sure we always apply the correct tags when inserting an object
		if iter.equal(self.get_iter_at_mark(self.get_insert())):
			Gtk.TextBuffer.insert_child_anchor(self, iter, anchor)
		else:
			with self.tmp_cursor(iter):
				Gtk.TextBuffer.insert_child_anchor(self, iter, anchor)

	def do_insert_child_anchor(self, iter, anchor):
		# Like do_insert_pixbuf()
		Gtk.TextBuffer.do_insert_child_anchor(self, iter, anchor)

		start = iter.copy()
		start.backward_char()
		self.remove_all_tags(start, iter)
		for tag in filter(_is_indent_tag, self._editmode_tags):
			self.apply_tag(tag, start, iter)

	def insert_pixbuf(self, iter, pixbuf):
		# Make sure we always apply the correct tags when inserting a pixbuf
		if iter.equal(self.get_iter_at_mark(self.get_insert())):
			Gtk.TextBuffer.insert_pixbuf(self, iter, pixbuf)
		else:
			with self.tmp_cursor(iter):
				Gtk.TextBuffer.insert_pixbuf(self, iter, pixbuf)

	def do_insert_pixbuf(self, iter, pixbuf):
		# Like do_insert_text() but for pixbuf
		# however only apply indenting tags, ignore other
		Gtk.TextBuffer.do_insert_pixbuf(self, iter, pixbuf)

		start = iter.copy()
		start.backward_char()
		self.remove_all_tags(start, iter)
		for tag in filter(_is_indent_tag, self._editmode_tags):
			self.apply_tag(tag, start, iter)

	def do_post_delete_range(self, start, end):
		# Post handler to hook _do_lines_merged and do some logic
		# when deleting bullets
		#
		# Implementation detail:
		# (Interactive) deleting a formatted word with <del>, or <backspace>
		# should drop the formatting, however selecting a formatted word and
		# than typing to replace it, should keep formatting
		# Since we don't know at this point what scenario we are part
		# off, we do NOT touch the editmode. However we do set a flag
		# that edit mode needs to be checked at the end of the user
		# action.
		#
		# Note that 'start' and 'end' refer to the same postion here ...

		if (
			(
				not start.starts_line()
				and list(filter(_is_line_based_tag, start.get_toggled_tags(True)))
			) or (
				not start.ends_line()
				and list(filter(_is_line_based_tag, start.get_toggled_tags(False)))
			)
		):
			self._do_lines_merged(start)

		bullet = self._get_bullet_at_iter(start)
		if bullet is not None:
			if start.starts_line():
				self._check_renumber.append(start.get_line())
			else:
				# Clean up the redundant bullet
				offset = start.get_offset()
				bound = start.copy()
				self._iter_forward_past_bullet(bound, bullet)
				self.delete(start, bound)
				new = self.get_iter_at_offset(offset)

				# NOTE: these assignments should not be needed, but without them
				# there is a crash here on some systems - see issue #766
				start.assign(new)
				end.assign(new)
		elif start.starts_line():
			indent_tags = list(filter(_is_indent_tag, start.get_tags()))
			if indent_tags and indent_tags[0].zim_attrib['_bullet']:
				# had a bullet, but no longer (implies we are start of
				# line - case where we are not start of line is
				# handled by _do_lines_merged by extending the indent tag)
				self.update_indent_tag(start.get_line(), None)

		self._check_edit_mode = True

	def _do_lines_merged(self, iter):
		# Enforce tags like 'h', 'pre' and 'indent' to be consistent over the line
		if iter.starts_line() or iter.ends_line():
			return # TODO Why is this ???

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
		'''Get the bullet type on a specific line, if any

		@param line: the line number
		@returns: the bullet type, if any, or C{None}.
		The bullet type can be any of::
				BULLET
				UNCHECKED_BOX
				CHECKED_BOX
				XCHECKED_BOX
				MIGRATED_BOX
		or a numbered list bullet (test with L{is_numbered_bullet_re})
		'''
		iter = self.get_iter_at_line(line)
		return self._get_bullet_at_iter(iter)

	def get_bullet_at_iter(self, iter):
		'''Return the bullet type in a specific location

		Like L{get_bullet()}

		@param iter: a C{Gtk.TextIter}
		@returns: a bullet type, or C{None}
		'''
		if not iter.starts_line():
			return None
		else:
			return self._get_bullet_at_iter(iter)

	def _get_bullet_at_iter(self, iter):
		pixbuf = iter.get_pixbuf()
		if pixbuf:
			if hasattr(pixbuf, 'zim_type') and pixbuf.zim_type == 'icon' \
			and pixbuf.zim_attrib['stock'] in (
				STOCK_CHECKED_BOX, STOCK_UNCHECKED_BOX, STOCK_XCHECKED_BOX, STOCK_MIGRATED_BOX):
				return bullets[pixbuf.zim_attrib['stock']]
			else:
				return None
		else:
			bound = iter.copy()
			if not self.iter_forward_word_end(bound):
				return None # empty line or whitespace at start of line

			text = iter.get_slice(bound)
			if text.startswith('\u2022'):
				return BULLET
			elif is_numbered_bullet_re.match(text):
				return text
			else:
				return None

	def iter_forward_past_bullet(self, iter):
		'''Move an TextIter past a bullet

		This method is useful because we typically want to insert new
		text on a line with a bullet after the bullet. This method can
		help to find that position.

		@param iter: a C{Gtk.TextIter}. The position of this iter will
		be modified by this method.
		'''
		bullet = self.get_bullet_at_iter(iter)
		if bullet:
			self._iter_forward_past_bullet(iter, bullet)
			return True
		else:
			return False

	def _iter_forward_past_bullet(self, iter, bullet, raw=False):
		if bullet in (BULLET, CHECKED_BOX, UNCHECKED_BOX, XCHECKED_BOX, MIGRATED_BOX):
			# Each of these just means one char
			iter.forward_char()
		else:
			assert is_numbered_bullet_re.match(bullet)
			self.iter_forward_word_end(iter)

		if not raw:
			# Skip whitespace as well
			bound = iter.copy()
			bound.forward_char()
			while iter.get_text(bound) == ' ':
				if iter.forward_char():
					bound.forward_char()
				else:
					break

	def get_parsetree(self, bounds=None, raw=False):
		'''Get a L{ParseTree} representing the buffer contents

		@param bounds: a 2-tuple with two C{Gtk.TextIter} specifying a
		range in the buffer (e.g. current selection). If C{None} the
		whole buffer is returned.

		@param raw: if C{True} you get a tree that is B{not} nicely
		cleaned up. This raw tree should result in the exact same
		contents in the buffer when reloaded. However such a 'raw'
		tree may cause problems when passed to one of the format
		modules. So it is intended only for internal use between the
		buffer and e.g. the L{UndoStackManager}.

		Raw parsetrees have an attribute to flag them as a raw tree, so
		on insert we can make sure they are inserted in the same way.

		When C{raw} is C{False} reloading the same tree may have subtle
		differences.

		@returns: a L{ParseTree} object
		'''
		if bounds is None:
			start, end = self.get_bounds()
			attrib = {}
		else:
			start, end = bounds
			attrib = {'partial': True}

		if raw:
			builder = ElementTreeModule.TreeBuilder()
			attrib['raw'] = True
			builder.start('zim-tree', attrib)
		else:
			builder = OldParseTreeBuilder()
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
						attrib = attrib.copy() # break ref with tree
						del attrib['_bullet']
						bullet = self._get_bullet_at_iter(iter)
						if bullet:
							t = 'li'
							attrib['bullet'] = bullet
							self._iter_forward_past_bullet(iter, bullet, raw=raw)
						elif not raw and not iter.starts_line():
							# Indent not visible if it does not start at begin of line
							t = '_ignore_'
						elif len([t for t in tags[i:] if t.zim_tag == 'pre']):
							# Indent of 'pre' blocks handled in subsequent iteration
							continue_attrib.update(attrib)
							continue
						else:
							t = 'div'
					elif t == 'pre' and not raw and not iter.starts_line():
						# Without indenting 'pre' looks the same as 'code'
						# Prevent turning into a separate paragraph here
						t = 'code'
					elif t == 'pre':
						if attrib:
							attrib.update(continue_attrib)
						else:
							attrib = continue_attrib
						continue_attrib = {}
					elif t == 'link':
						attrib = self.get_link_data(iter)
						if not attrib['href']:
							t = '_ignore_'
					elif t == 'tag':
						attrib = self.get_tag_data(iter)
						if not attrib['name']:
							t = '_ignore_'
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
		set_tags(iter, list(filter(_is_zim_tag, iter.get_tags())))
		while iter.compare(end) == -1:
			pixbuf = iter.get_pixbuf()
			anchor = iter.get_child_anchor()
			if pixbuf:
				if pixbuf.zim_type == 'icon':
					# Reset all tags - and let set_tags parse the bullet
					if open_tags:
						break_tags(open_tags[0][1])
					set_tags(iter, list(filter(_is_indent_tag, iter.get_tags())))
				else:
					pass # reset all tags except indenting
					set_tags(iter, list(filter(_is_indent_tag, iter.get_tags())))

				pixbuf = iter.get_pixbuf() # iter may have moved
				if pixbuf is None:
					continue

				if pixbuf.zim_type == 'icon':
					logger.warn('BUG: Checkbox outside of indent ?')
				elif pixbuf.zim_type == 'image':
					attrib = pixbuf.zim_attrib.copy()
					builder.start('img', attrib)
					builder.end('img')
				else:
					assert False, 'BUG: unknown pixbuf type'

				iter.forward_char()

			# embedded widget
			elif anchor:
				set_tags(iter, list(filter(_is_indent_tag, iter.get_tags())))
				anchor = iter.get_child_anchor() # iter may have moved
				if isinstance(anchor, InsertedObjectAnchor):
					anchor.dump(builder)
					iter.forward_char()
				else:
					continue
			else:
				# Set tags
				copy = iter.copy()

				bullet = self.get_bullet_at_iter(iter) # implies check for start of line
				if bullet:
					break_tags('indent')
					# This is part of the HACK for bullets in
					# set_tags()

				set_tags(iter, list(filter(_is_zim_tag, iter.get_tags())))
				if not iter.equal(copy): # iter moved
					continue

				# Find biggest slice without tags being toggled
				bound = iter.copy()
				toggled = []
				while not toggled:
					if not bound.is_end() and bound.forward_to_tag_toggle(None):
						# For some reason the not is_end check is needed
						# to prevent an odd corner case infinite loop
						toggled = list(filter(_is_zim_tag,
							bound.get_toggled_tags(False)
							+ bound.get_toggled_tags(True)))
					else:
						bound = end.copy() # just to be sure..
						break

				# But limit slice to first pixbuf or any embeddded widget

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

				if [t for t in open_tags if t[1] == 'li'] \
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
					# Else just insert text we got
					builder.data(text)

				iter = bound

		# close any open tags
		set_tags(end, [])

		builder.end('zim-tree')
		tree = ParseTree(builder.close())
		tree.encode_urls()
		#~ print tree.tostring()

		if not raw and tree.hascontent:
			# Reparsing the parsetree in order to find raw wiki codes
			# and get rid of oddities in our generated parsetree.
			#print(">>> Parsetree original:\n", tree.tostring())
			from zim.formats import get_format
			format = get_format("wiki") # FIXME should the format used here depend on the store ?
			dumper = format.Dumper()
			parser = format.Parser()
			text = dumper.dump(tree)
			#print(">>> Wiki text:\n", text)
			tree = parser.parse(text, partial=tree.ispartial)
			#print(">>> Parsetree recreated:\n", tree.tostring())

		return tree

	def select_line(self, line=None):
		'''Selects a line
		@param line: line number; if C{None} current line will be selected
		@returns: C{True} when successful
		'''
		# Differs from get_line_bounds because we exclude the trailing
		# line break while get_line_bounds selects these
		if line is None:
			iter = self.get_iter_at_mark(self.get_insert())
			line = iter.get_line()
		return self.select_lines(line, line)

	def select_lines(self, first, last):
		'''Select multiple lines
		@param first: line number first line
		@param last: line number last line
		@returns: C{True} when successful
		'''
		start = self.get_iter_at_line(first)
		end = self.get_iter_at_line(last)
		if end.ends_line():
			if end.equal(start):
				return False
			else:
				pass
		else:
			end.forward_to_line_end()
		self.select_range(start, end)
		return True

	def select_word(self):
		'''Selects the current word, if any

		@returns: C{True} when succcessful
		'''
		insert = self.get_iter_at_mark(self.get_insert())
		if not insert.inside_word():
			return False

		bound = insert.copy()
		if not insert.starts_word():
			insert.backward_word_start()
		if not bound.ends_word():
			bound.forward_word_end()

		self.select_range(insert, bound)
		return True

	def strip_selection(self):
		'''Shrinks the selection to exclude any whitespace on start and end.
		If only white space was selected this function will not change the selection.
		@returns: C{True} when this function changed the selection.
		'''
		bounds = self.get_selection_bounds()
		if not bounds:
			return False

		text = bounds[0].get_text(bounds[1])
		if not text or text.isspace():
			return False

		start, end = bounds[0].copy(), bounds[1].copy()
		iter = start.copy()
		iter.forward_char()
		text = start.get_text(iter)
		while text and text.isspace():
			start.forward_char()
			iter.forward_char()
			text = start.get_text(iter)

		iter = end.copy()
		iter.backward_char()
		text = iter.get_text(end)
		while text and text.isspace():
			end.backward_char()
			iter.backward_char()
			text = iter.get_text(end)

		if (start.equal(bounds[0]) and end.equal(bounds[1])):
			return False
		else:
			self.select_range(start, end)
			return True

	def select_link(self):
		'''Selects the current link, if any
		@returns: link attributes when succcessful, C{None} otherwise
		'''
		insert = self.get_iter_at_mark(self.get_insert())
		tag = self.get_link_tag(insert)
		if tag is None:
			return None
		start, end = self.get_tag_bounds(insert, tag)
		self.select_range(start, end)
		return self.get_link_data(start)

	def get_has_link_selection(self):
		'''Check whether a link is selected or not
		@returns: link attributes when succcessful, C{None} otherwise
		'''
		bounds = self.get_selection_bounds()
		if not bounds:
			return None

		insert = self.get_iter_at_mark(self.get_insert())
		tag = self.get_link_tag(insert)
		if tag is None:
			return None
		start, end = self.get_tag_bounds(insert, tag)
		if start.equal(bounds[0]) and end.equal(bounds[1]):
			return self.get_link_data(start)
		else:
			return None

	def remove_link(self, start, end):
		'''Removes any links between in a range

		@param start: a C{Gtk.TextIter}
		@param end: a C{Gtk.TextIter}
		'''
		self.smart_remove_tags(_is_link_tag, start, end)
		self.update_editmode()

	def toggle_checkbox(self, line, checkbox_type=None, recursive=False):
		'''Toggles the state of the checkbox at a specific line, if any

		@param line: the line number
		@param checkbox_type: the checkbox type that we want to toggle:
		one of C{CHECKED_BOX}, C{XCHECKED_BOX}, C{MIGRATED_BOX}.
		If C{checkbox_type} is given, it toggles between this type and
		unchecked. Otherwise it rotates through unchecked, checked
		and xchecked.
		As a special case when the C{checkbox_type} ir C{UNCHECKED_BOX}
		the box is always unchecked.
		@param recursive: When C{True} any child items in the list will
		also be upadted accordingly (see L{TextBufferList.set_bullet()}

		@returns: C{True} for success, C{False} if no checkbox was found.
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
		'''Like L{toggle_checkbox()} but applies to current line or
		current selection. Intended for interactive use.

		@param checkbox_type: the checkbox type that we want to toggle
		@param recursive: When C{True} any child items in the list will
		also be upadted accordingly (see L{TextBufferList.set_bullet()}
		'''
		if self.get_has_selection():
			self.foreach_line_in_selection(self.toggle_checkbox, checkbox_type, recursive)
		else:
			line = self.get_insert_iter().get_line()
			return self.toggle_checkbox(line, checkbox_type, recursive)

	def iter_backward_word_start(self, iter):
		'''Like C{Gtk.TextIter.backward_word_start()} but less intelligent.
		This method does not take into account the language or
		punctuation and just skips to either the last whitespace or
		the beginning of line.

		@param iter: a C{Gtk.TextIter}, the position of this iter will
		be modified
		@returns: C{True} when successful
		'''
		if iter.starts_line():
			return False

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

		return iter.compare(orig) != 0

	def iter_forward_word_end(self, iter):
		'''Like C{Gtk.TextIter.forward_word_end()} but less intelligent.
		This method does not take into account the language or
		punctuation and just skips to either the next whitespace or the
		end of the line.

		@param iter: a C{Gtk.TextIter}, the position of this iter will
		be modified
		@returns: C{True} when successful
		'''
		if iter.ends_line():
			return False

		orig = iter.copy()
		while True:
			if iter.ends_line():
				break
			else:
				bound = iter.copy()
				bound.forward_char()
				char = bound.get_slice(iter)
				if char == PIXBUF_CHR or char.isspace():
					break # whitespace or pixbuf after iter
				else:
					iter.forward_char()

		return iter.compare(orig) != 0

	def get_iter_at_line(self, line):
		'''Like C{Gtk.TextBuffer.get_iter_at_line()} but with additional
		safety check
		@param line: an integer line number counting from 0
		@returns: a Gtk.TextIter
		@raises ValueError: when line is not within the buffer
		'''
		# Gtk TextBuffer returns iter of last line for lines past the
		# end of the buffer
		if line < 0:
			raise ValueError('Negative line number: %i' % line)
		else:
			iter = Gtk.TextBuffer.get_iter_at_line(self, line)
			if iter.get_line() != line:
				raise ValueError('Line number beyond the end of the buffer: %i' % line)
			return iter

	def get_line_bounds(self, line):
		'''Get the TextIters at start and end of line

		@param line: the line number
		@returns: a 2-tuple of C{Gtk.TextIter} for start and end of the
		line
		'''
		start = self.get_iter_at_line(line)
		end = start.copy()
		end.forward_line()
		return start, end

	def get_line_is_empty(self, line):
		'''Check for empty lines

		@param line: the line number
		@returns: C{True} if the line only contains whitespace
		'''
		start, end = self.get_line_bounds(line)
		return start.equal(end) or start.get_slice(end).isspace()

	def get_has_selection(self):
		'''Check if there is a selection

		Method available in C{Gtk.TextBuffer} for gtk version >= 2.10
		reproduced here for backward compatibility.

		@returns: C{True} when there is a selection
		'''
		return bool(self.get_selection_bounds())

	def iter_in_selection(self, iter):
		'''Check if a specific TextIter is within the selection

		@param iter: a C{Gtk.TextIter}
		@returns: C{True} if there is a selection and C{iter} is within
		the range of the selection
		'''
		bounds = self.get_selection_bounds()
		return bounds \
			and bounds[0].compare(iter) <= 0 \
			and bounds[1].compare(iter) >= 0
		# not using iter.in_range to be inclusive of bounds

	def unset_selection(self):
		'''Remove any selection in the buffer'''
		iter = self.get_iter_at_mark(self.get_insert())
		self.select_range(iter, iter)

	def copy_clipboard(self, clipboard, format='plain'):
		'''Copy current selection to a clipboard

		@param clipboard: a L{Clipboard} object
		@param format: a format name
		'''
		bounds = self.get_selection_bounds()
		if bounds:
			tree = self.get_parsetree(bounds)
			#~ print(">>>> SET", tree.tostring())
			clipboard.set_parsetree(self.notebook, self.page, tree, format)

	def cut_clipboard(self, clipboard, default_editable):
		'''Cut current selection to a clipboard

		First copies the selection to the clipboard and then deletes
		the selection in the buffer.

		@param clipboard: a L{Clipboard} object
		@param default_editable: default state of the L{TextView}
		'''
		if self.get_has_selection():
			self.copy_clipboard(clipboard)
			self.delete_selection(True, default_editable)

	def paste_clipboard(self, clipboard, iter, default_editable):
		'''Paste data from a clipboard into the buffer

		@param clipboard: a L{Clipboard} object
		@param iter: a C{Gtk.TextIter} for the insert location
		@param default_editable: default state of the L{TextView}
		'''
		if not default_editable:
			return

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
		parsetree = clipboard.get_parsetree(self.notebook, self.page)
		if not parsetree:
			return

		#~ print('!! PASTE', parsetree.tostring())
		with self.user_action:
			if self.get_has_selection():
				start, end = self.get_selection_bounds()
				self.delete(start, end)

			mark = self.get_mark('zim-paste-position')
			if not mark:
				return # prevent crash - see lp:807830

			iter = self.get_iter_at_mark(mark)
			self.delete_mark(mark)

			self.place_cursor(iter)
			parsetree.resolve_images(self.notebook, self.page)
			self.insert_parsetree_at_cursor(parsetree, interactive=True)


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

	@classmethod
	def new_from_line(self, textbuffer, line):
		'''Constructor for a new TextBufferList mapping the list at a
		specific line in the buffer

		@param textbuffer: a L{TextBuffer} object
		@param line: a line number

		This line should be part of a list, the TextBufferList object
		that is returned maps the full list, so it possibly extends
		above and below C{line}.

		@returns: a 2-tuple of a row id and a the new TextBufferList
		object, or C{(None, None)} if C{line} is not part of a list.
		The row id points to C{line} in the list.
		'''
		if textbuffer.get_bullet(line) is None:
			return None, None

		# find start of list
		start = line
		for myline in range(start, -1, -1):
			if textbuffer.get_bullet(myline) is None:
				break # TODO skip lines with whitespace
			else:
				start = myline

		# find end of list
		end = line
		lastline = textbuffer.get_end_iter().get_line()
		for myline in range(end, lastline + 1, 1):
			if textbuffer.get_bullet(myline) is None:
				break # TODO skip lines with whitespace
			else:
				end = myline

		list = TextBufferList(textbuffer, start, end)
		row = list.get_row_at_line(line)
		#~ print('!! LIST %i..%i ROW %i' % (start, end, row))
		#~ print('>>', list)
		return row, list

	def __init__(self, textbuffer, firstline, lastline):
		'''Constructor

		@param textbuffer: a L{TextBuffer} object
		@param firstline: the line number for the first line of the list
		@param lastline: the line number for the last line of the list
		'''
		self.buffer = textbuffer
		self.firstline = firstline
		self.lastline = lastline
		for line in range(firstline, lastline + 1):
			bullet = self.buffer.get_bullet(line)
			indent = self.buffer.get_indent(line)
			if bullet:
				self.append((line, indent, bullet))

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
		'''
		assert bullet in BULLETS
		with self.buffer.user_action:
			self._change_bullet_type(row, bullet)
			if bullet == BULLET:
				pass
			elif bullet == UNCHECKED_BOX:
				self._checkbox_unchecked(row)
			else: # CHECKED_BOX, XCHECKED_BOX, MIGRATED_BOX
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

				return True
		else:
			return False

		self._update_highlight()

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
			with self.buffer.tmp_cursor():
				for startoff, endoff, string in matches:
					start = self.buffer.get_iter_at_offset(startoff)
					end = self.buffer.get_iter_at_offset(endoff)
					if start.get_child_anchor() is not None:
						self._replace_in_widget(start, self.regex, string, True)
					else:
						self.buffer.select_range(start, end) # ensure editmode logic is used
						self.buffer.delete(start, end)

						start = self.buffer.get_iter_at_offset(startoff)
						self.buffer.insert(start, string)

		self._update_highlight()


CURSOR_TEXT = Gdk.Cursor.new_from_name(Gdk.Display.get_default(), 'text')
CURSOR_LINK = Gdk.Cursor.new_from_name(Gdk.Display.get_default(), 'pointer')
CURSOR_WIDGET = Gdk.Cursor.new_from_name(Gdk.Display.get_default(), 'default')


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
		self._object_widgets = WeakSet()
		self.set_left_margin(10)
		self.set_right_margin(5)
		self.set_wrap_mode(Gtk.WrapMode.WORD)
		self.preferences = preferences

		self._object_wrap_width = -1
		self.connect_after('size-allocate', self.__class__.on_size_allocate)
		self.connect_after('motion-notify-event', self.__class__.on_motion_notify_event)

	def set_buffer(self, buffer):
		buffer.connect('insert-objectanchor', self.on_insert_object)
		Gtk.TextView.set_buffer(self, buffer)

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

	def do_paste_clipboard(self):
		# Overriden to force usage of our Textbuffer.paste_clipboard
		# over Gtk.TextBuffer.paste_clipboard
		self.get_buffer().paste_clipboard(Clipboard, None, self.get_editable())
		self.scroll_mark_onscreen(self.get_buffer().get_insert())

	#~ def do_drag_motion(self, context, *a):
		#~ # Method that echos drag data types - only enable for debugging
		#~ print context.targets

	def on_motion_notify_event(self, event):
		# Update the cursor type when the mouse moves
		x, y = event.get_coords()
		x, y = int(x), int(y) # avoid some strange DeprecationWarning
		coords = self.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, x, y)
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
				widgets = anchor.get_widgets()
				assert len(widgets) == 1, 'TODO: support multiple views of same buffer'
				widget = widgets[0]
				if widget.has_cursor():
					widget.grab_cursor(position)
					return None

		return Gtk.TextView.do_move_cursor(self, step_size, count, extend_selection)

	def do_button_press_event(self, event):
		# Handle middle click for pasting and right click for context menu
		# Needed to override these because implementation details of
		# gtktextview.c do not use proper ignals for these actions.
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
						self.click_link() or self.click_checkbox()
					else:
						self.click_link() or self.click_checkbox(CHECKED_BOX)
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
			and not list(filter(_is_pre_tag, iter.get_tags())):
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
			and not list(filter(_is_pre_tag, iter.get_tags())):
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
				editmode = [t.zim_tag
					for t in buffer._editmode_tags
					if hasattr(t, 'zim_tag')
				]
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
			if selection_in_pre_block(start, end):
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

		def selection_in_pre_block(start, end):
			# Checks if there are any tag changes within the selection
			if list(filter(_is_pre_tag, start.get_tags())):
				toggle = start.copy()
				toggle.forward_to_tag_toggle(None)
				return toggle.compare(end) < 0
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
				if selection_in_pre_block(start, end):
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
					if not bullet and not buffer.get_line_is_empty(line):
						buffer.set_bullet(line, newbullet)
					elif bullet == newbullet: # FIXME broken for numbered list
						buffer.set_bullet(line, None)
				if keyval == KEYVAL_POUND:
					buffer.foreach_line_in_selection(toggle_bullet, NUMBER_BULLET)
				else:
					buffer.foreach_line_in_selection(toggle_bullet, BULLET)
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
		x, y = self.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, x, y)
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
				if pixbuf.zim_type == 'icon' and pixbuf.zim_attrib['stock'] in (
					STOCK_CHECKED_BOX, STOCK_UNCHECKED_BOX, STOCK_XCHECKED_BOX, STOCK_MIGRATED_BOX):
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
		handled = True
		#~ print('WORD >>%s<< CHAR >>%s<<' % (word, char))

		if list(filter(_is_not_indent_tag, buffer.iter_get_zim_tags(start))) \
		or list(filter(_is_not_indent_tag, buffer.iter_get_zim_tags(end))):
			# DO not auto-format if any zim tags are applied except for indent
			return

		def apply_tag(match):
			#~ print("TAG >>%s<<" % word)
			start = end.copy()
			if not start.backward_chars(len(match)):
				return False
			if buffer.range_has_tags(_is_not_indent_tag, start, end):
				return False
			tag = buffer._create_tag_tag(match)
			buffer.apply_tag(tag, start, end)
			return True

		def apply_link(match):
			#~ print("LINK >>%s<<" % word)
			start = end.copy()
			if not start.backward_chars(len(match)):
				return False
			if buffer.range_has_tags(_is_not_indent_tag, start, end):
				return False
			tag = buffer._create_link_tag(match, match)
			buffer.apply_tag(tag, start, end)
			return True

		if (char == ' ' or char == '\t') and start.starts_line() \
		and (word in autoformat_bullets or is_numbered_bullet_re.match(word)):
			# format bullet and checkboxes
			line = start.get_line()
			end.forward_char() # also overwrite the space triggering the action
			buffer.delete(start, end)
			bullet = autoformat_bullets.get(word) or word
			buffer.set_bullet(line, bullet)
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
		elif self.preferences['autolink_camelcase'] and camelcase(word):
			apply_link(word)
		elif self.preferences['auto_reformat']:
			handled = False
			linestart = buffer.get_iter_at_line(end.get_line())
			partial_line = linestart.get_slice(end)
			for style, re in list(markup_re.items()):
				if not re.search(partial_line) is None:
					matchstart = linestart.copy()
					matchstart.forward_chars(re.start())
					matchend = linestart.copy()
					matchend.forward_chars(re.end())
					if list(filter(_is_not_indent_tag, buffer.iter_get_zim_tags(matchstart))) \
					or list(filter(_is_not_indent_tag, buffer.iter_get_zim_tags(matchend))):
						continue
					buffer.delete(matchstart, matchend)
					buffer.insert_with_tags_by_name(matchstart, re[2], style)
					handled_here = True
					break
		else:
			handled = False

		if handled:
			self.stop_emission('end-of-word')

	def do_end_of_line(self, end):
		# Default handler, takes care of cutting of formatting on the
		# line end, set indenting and bullet items on the new line etc.
		buffer = self.get_buffer()

		if end.starts_line():
			return # empty line
		start = buffer.get_iter_at_line(end.get_line())
		line = start.get_text(end)
		#~ print('LINE >>%s<<' % line)

		if heading_re.match(line):
			level = len(heading_re[1]) - 1
			heading = heading_re[2]
			mark = buffer.create_mark(None, end)
			buffer.delete(start, end)
			buffer.insert_with_tags_by_name(
				buffer.get_iter_at_mark(mark), heading, 'style-h' + str(level))
			buffer.delete_mark(mark)
		elif is_line(line):
			with buffer.user_action:
				offset = start.get_offset()
				buffer.delete(start, end)
				iter = buffer.get_iter_at_offset(offset)
				buffer.insert_objectanchor(iter, LineSeparatorAnchor())
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
				if bullet in (CHECKED_BOX, XCHECKED_BOX, MIGRATED_BOX):
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
	  - C{data}: either a (raw) L{ParseTree} or a C{Gtk.TextTag}

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

		self.recording_handlers = [] # handlers to be blocked when not recording
		for signal, handler in (
			('undo-save-cursor', self.do_save_cursor),
			('insert-text', self.do_insert_text),
			#~ ('inserted-tree', self.do_insert_tree), # TODO
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

	def clear(self):
		'''Clear the undo stack'''
		self.stack = []
		self.group = UndoActionGroup()
		self.interactive = False
		self.insert_pending = False
		self.undo_count = 0
		self.block_count = 0
		self.block()

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

	#~ def do_inserted_tree(self, buffer, start, end, parsetree):
		#~ if self.undo_count > 0: self._flush_redo_stack()

		#~ start, end = start.get_offset(), end.get_offset()
		#~ self.group.append((self.ACTION_INSERT, start, end, tree))

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
		merging actions we do not immediatly request the parse tree for
		each single character insert. Instead we first group inserts
		based on cursor positions and then request the parse tree for
		the group at once. This method proceses all such delayed
		requests.
		'''
		def _flush_group(group):
			for i in reversed(list(range(len(group)))):
				action, start, end, tree = group[i]
				if action == self.ACTION_INSERT and tree is None:
					bounds = (self.buffer.get_iter_at_offset(start),
								self.buffer.get_iter_at_offset(end))
					tree = self.buffer.get_parsetree(bounds, raw=True)
					#~ print('FLUSH %i to %i\n\t%s' % (start, end, tree.tostring()))
					group[i] = (self.ACTION_INSERT, start, end, tree)
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

		bounds = (start, end)
		tree = self.buffer.get_parsetree(bounds, raw=True)
		start, end = start.get_offset(), end.get_offset()
		#~ print('DELETE RANGE from %i to %i\n\t%s' % (start, end, tree.tostring()))
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

		#~ print('='*80)
		for action, start, end, data in actiongroup:
			iter = self.buffer.get_iter_at_offset(start)
			bound = self.buffer.get_iter_at_offset(end)

			if action == self.ACTION_INSERT:
				#~ print('INSERTING', data.tostring())
				self.buffer.place_cursor(iter)
				self.buffer.insert_parsetree_at_cursor(data)
			elif action == self.ACTION_DELETE:
				#~ print('DELETING', data.tostring())
				self.buffer.place_cursor(iter)
				tree = self.buffer.get_parsetree((iter, bound), raw=True)
				#~ print('REAL', tree.tostring())
				with self.buffer.user_action:
					self.buffer.delete(iter, bound)
					self.buffer._check_renumber = []
						# Flush renumber check - HACK to avoid messing up the stack
				if tree.tostring() != data.tostring():
					logger.warn('Mismatch in undo stack\n%s\n%s\n', tree.tostring(), data.tostring())
			elif action == self.ACTION_APPLY_TAG:
				#~ print('APPLYING', data)
				self.buffer.apply_tag(data, iter, bound)
				self.buffer.place_cursor(bound)
			elif action == self.ACTION_REMOVE_TAG:
				#~ print('REMOVING', data)
				self.buffer.remove_tag(data, iter, bound)
				self.buffer.place_cursor(bound)
			else:
				assert False, 'BUG: unknown action type'

		if not actiongroup.cursor is None:
			iter = self.buffer.get_iter_at_offset(actiongroup.cursor)
			self.buffer.place_cursor(iter)

		self.unblock()


class SavePageHandler(object):
	'''Object for handling page saving.

	This class implements auto-saving on a timer and tries writing in
	a background thread to ot block the user interface.
	'''

	def __init__(self, pageview, notebook, get_page_cb, timeout=15, use_thread=True):
		self.pageview = pageview
		self.notebook = notebook
		self.get_page_cb = get_page_cb
		self.timeout = timeout
		self.use_thread = use_thread
		self._autosave_timer = None
		self._error_event = None

	def wait_for_store_page_async(self):
		# FIXME: duplicate of notebook method
		self.notebook.wait_for_store_page_async()

	def queue_autosave(self, timeout=15):
		'''Queue a single autosave action after a given timeout.
		Will not do anything once an autosave is already queued.
		Autosave will keep running until page is no longer modified and
		then stop.
		@param timeout: timeout in seconds
		'''
		if not self._autosave_timer:
			self._autosave_timer = GObject.timeout_add(
				self.timeout * 1000, # s -> ms
				self.do_try_save_page
			)

	def cancel_autosave(self):
		'''Cancel a pending autosave'''
		if self._autosave_timer:
			GObject.source_remove(self._autosave_timer)
			self._autosave_timer = None

	def _assert_can_save_page(self, page):
		if self.pageview.readonly:
			raise AssertionError('BUG: can not save page when UI is read-only')
		elif page.readonly:
			raise AssertionError('BUG: can not save read-only page')

	def save_page_now(self, dialog_timeout=False):
		'''Save the page in the foregound

		Can result in a L{SavePageErrorDialog} when there is an error
		while saving a page. If that dialog is cancelled by the user,
		the page may not be saved after all.

		@param dialog_timeout: passed on to L{SavePageErrorDialog}
		'''
		self.cancel_autosave()

		self._error_event = None

		with NotebookState(self.notebook):
			page = self.get_page_cb()
			if page:
				try:
					self._assert_can_save_page(page)

					## HACK - otherwise we get a bug when saving a new page immediatly
					# hasattr assertions used to detect when the hack breaks
					assert hasattr(page, '_ui_object')
					if page._ui_object:
						assert hasattr(page._ui_object, '_showing_template')
						page._ui_object._showing_template = False
					##

					logger.debug('Saving page: %s', page)
					#~ assert False, "TEST"
					self.notebook.store_page(page)

				except Exception as error:
					logger.exception('Failed to save page: %s', page.name)
					SavePageErrorDialog(self.pageview, error, page, dialog_timeout).run()

	def try_save_page(self):
		'''Try to save the page

		  * Will not do anything if page is not modified or when an
		    autosave is already in progress.
		  * If last autosave resulted in an error, will run in the
		    foreground, else it tries to write the page in a background
		    thread
		'''
		self.cancel_autosave()
		self.do_try_save_page()

	def do_try_save_page(self, *a):
		page = self.get_page_cb()
		if not (page and page.modified):
			self._autosave_timer = None
			return False # stop timer

		if ongoing_operation(self.notebook):
			logger.debug('Operation in progress, skipping auto-save') # Could be auto-save
			return True # Check back later if on timer


		if not self.use_thread:
			self.save_page_now(dialog_timeout=True)
		elif self._error_event and self._error_event.is_set():
			# Error in previous auto-save, save in foreground to allow error dialog
			logger.debug('Last auto-save resulted in error, re-try in foreground')
			self.save_page_now(dialog_timeout=True)
		else:
			# Save in background async
			# Retrieve tree here and pass on to thread to prevent
			# changing the buffer while extracting it
			parsetree = page.get_parsetree()
			op = self.notebook.store_page_async(page, parsetree)
			self._error_event = op.error_event

		if page.modified:
			return True # if True, timer will keep going
		else:
			self._autosave_timer = None
			return False # stop timer


class SavePageErrorDialog(ErrorDialog):
	'''Error dialog used when we hit an error while trying to save a page.
	Allow to save a copy or to discard changes. Includes a timer which
	delays the action buttons becoming sensitive. Reason for this timer is
	that the dialog may popup from auto-save while the user is typing, and
	we want to prevent an accidental action.
	'''

	def __init__(self, pageview, error, page, timeout=False):
		msg = _('Could not save page: %s') % page.name
			# T: Heading of error dialog
		desc = str(error).strip() \
				+ '\n\n' \
				+ _('''\
To continue you can save a copy of this page or discard
any changes. If you save a copy changes will be also
discarded, but you can restore the copy later.''')
			# T: text in error dialog when saving page failed
		ErrorDialog.__init__(self, pageview, (msg, desc), buttons=Gtk.ButtonsType.NONE)

		self.timeout = timeout

		self.pageview = pageview
		self.page = page
		self.error = error

		self.timer_label = Gtk.Label()
		self.timer_label.set_alignment(0.9, 0.5)
		self.timer_label.set_sensitive(False)
		self.timer_label.show()
		self.vbox.add(self.timer_label)

		cancel_button = Gtk.Button.new_with_mnemonic(_('_Cancel')) # T: Button label
		self.add_action_widget(cancel_button, Gtk.ResponseType.CANCEL)

		self._done = False

		discard_button = Gtk.Button.new_with_mnemonic(_('_Discard Changes'))
			# T: Button in error dialog
		discard_button.connect('clicked', lambda o: self.discard())
		self.add_action_widget(discard_button, Gtk.ResponseType.OK)

		save_button = Gtk.Button.new_with_mnemonic(_('_Save Copy'))
			# T: Button in error dialog
		save_button.connect('clicked', lambda o: self.save_copy())
		self.add_action_widget(save_button, Gtk.ResponseType.OK)

		for button in (cancel_button, discard_button, save_button):
			button.set_sensitive(False)
			button.show()

	def discard(self):
		self.page.set_ui_object(None) # unhook
		self.pageview.clear()
			# issue may be caused in pageview - make sure it unlocks
		self.page._parsetree = None # removed cached tree
		self.page.modified = False
		self.pageview.set_page(self.page)
		self._done = True

	def save_copy(self):
		from zim.gui.uiactions import SaveCopyDialog
		if SaveCopyDialog(self, self.pageview.notebook, self.page).run():
			self.discard()

	def do_response_ok(self):
		return self._done

	def run(self):
		if self.timeout:
			self.timer = 5
			self.timer_label.set_text('%i sec.' % self.timer)
			def timer(self):
				self.timer -= 1
				if self.timer > 0:
					self.timer_label.set_text('%i sec.' % self.timer)
					return True # keep timer going
				else:
					for button in self.action_area.get_children():
						button.set_sensitive(True)
					self.timer_label.set_text('')
					return False # remove timer

			# older gobject version doesn't know about seconds
			id = GObject.timeout_add(1000, timer, self)
			ErrorDialog.run(self)
			GObject.source_remove(id)
		else:
			for button in self.action_area.get_children():
				button.set_sensitive(True)
			ErrorDialog.run(self)


from zim.plugins import ExtensionBase, extendable
from zim.config import ConfigDict
from zim.gui.actionextension import ActionExtensionBase
from zim.gui.widgets import LEFT_PANE, RIGHT_PANE, BOTTOM_PANE, PANE_POSITIONS


class NavigationWrapper(object):
	'''Wrapper to allow late initialization of the "navigation" object'''

	def __init__(self):
		self._real_navigation = None

	def open_page(self, *arg, **kwarg):
		if self._real_navigation:
			return self._real_navigation.open_page(*arg, **kwarg)
		else:
			logger.warn('navigation called before initialisation')


class PageViewExtension(ActionExtensionBase):
	'''Base class for extensions that want to interact with the "page view",
	which is the primary editor view of the application.

	This extension class will collect actions defined with the C{@action},
	C{@toggle_action} or C{@radio_action} decorators and add them to the window.

	This extension class also supports showing side panes that are visible as
	part of the "decoration" of the editor view.

	@ivar pageview: the L{PageView} object
	@ivar navigation: a L{NavigationModel} model
	@ivar uistate: a L{ConfigDict} to store the extensions ui state or

	The "uistate" is the per notebook state of the interface, it is
	intended for stuff like the last folder opened by the user or the
	size of a dialog after resizing. It is stored in the X{state.conf}
	file in the notebook cache folder. It differs from the preferences,
	which are stored globally and dictate the behavior of the application.
	(To access the preference use C{plugin.preferences}.)
	'''

	# HACK: complicated class because we rely on MainWindow for most of the
	# functionality of this extension class. However at initialisation there
	# is no parent window, so we need to delay loading.
	# Plan is to refactor MainWindow and PageView such that these functions
	# end up in the right place.

	def __init__(self, plugin, pageview):
		ExtensionBase.__init__(self, plugin, pageview)
		self.pageview = pageview
		self._on_ui_init_queue = []
		self.connectto(pageview, 'ui-init', self.on_ui_init)

		self._sidepane_widgets = {}
		self.navigation = NavigationWrapper()
		self.uistate = pageview.notebook.state[self.plugin.config_key]
		self._do_on_ui_init(self._init_window)

	def _init_window(self, window):
		if hasattr(window, 'uimanager'): # HACK: PageWindow does not have uimanager
			self._add_actions(window.uimanager)
		self.navigation._real_navigation = window.navigation

	def _do_on_ui_init(self, func, *arg, **kwarg):
		if self.pageview.ui_is_initialized:
			window = self.pageview.get_toplevel()
			assert hasattr(window, 'add_tab'), 'expect mainwindow, got %s' % window
			func(window, *arg, **kwarg)
		else:
			self._on_ui_init_queue.append((func, arg, kwarg))

	def on_ui_init(self, pageview, *a):
		# Execute calls that only work once there is a mainwindow available.
		# Needed because pageview extensions are loaded before the pageview
		# is added to the window.
		window = pageview.get_toplevel()
		assert hasattr(window, 'add_tab'), 'expect mainwindow, got %s' % window
		for func, arg, kwarg in self._on_ui_init_queue:
			func(window, *arg, **kwarg)
		self._on_ui_init_queue = []

	def add_sidepane_widget(self, widget, preferences_key):
		key = widget.__class__.__name__
		position = self.plugin.preferences[preferences_key]
		self._do_on_ui_init(lambda window: window.add_tab(key, widget, position))

		def on_preferences_changed(preferences):
			position = self.plugin.preferences[preferences_key]
			self._do_on_ui_init(lambda window: window.remove(widget))
			self._do_on_ui_init(lambda window: window.add_tab(key, widget, position))

		sid = self.connectto(self.plugin.preferences, 'changed', on_preferences_changed)
		self._sidepane_widgets[widget] = sid
		widget.show_all()

	def remove_sidepane_widget(self, widget):

		def remove(window):
			try:
				window.remove(widget)
			except ValueError:
				pass

		self._do_on_ui_init(remove)

		try:
			sid = self._sidepane_widgets.pop(widget)
			self.plugin.preferences.disconnect(sid)
		except KeyError:
			pass

	def teardown(self):
		for widget in list(self._sidepane_widgets):
			self.remove_sidepane_widget(widget)
			widget.disconnect_all()
		self._on_ui_init_queue = []


from zim.signals import GSignalEmitterMixin

@extendable(PageViewExtension)
class PageView(GSignalEmitterMixin, Gtk.VBox):
	'''Widget to display a single page, consists of a L{TextView} and
	a L{FindBar}. Also adds menu items and in general integrates
	the TextView with the rest of the application.

	@ivar text_style: a L{ConfigSectionsDict} with style properties. Although this
	is a class attribute loading the data from the config file is
	delayed till the first object is constructed

	@ivar page: L{Page} object for the current page displayed in the widget
	@ivar readonly: C{True} when the widget is read-only, see
	L{set_readonly()} for details
	@ivar secondary: hint that the PageView is running in a secondairy
	window (instead of the main window)
	@ivar undostack: the L{UndoStackManager} object for
	@ivar view: the L{TextView} child object
	@ivar find_bar: the L{FindBar} child widget
	@ivar preferences: a L{ConfigDict} with preferences

	@signal: C{modified-changed ()}: emitted when the page is edited
	@signal: C{textstyle-changed (style)}:
	Emitted when textstyle at the cursor changes
	@signal: C{activate-link (link, hints)}: emitted when a link is opened,
	stops emission after the first handler returns C{True}
	@signal: C{ui-init ()}: trigger for extensions to load uimanager stuff,
	do not rely on this signal, may be removed

	@todo: document preferences supported by PageView
	@todo: document extra keybindings implemented in this widget
	@todo: document style properties supported by this widget

	@todo: refactor such that the PageView doesn't need to know whether
	it is in a secondairy window or not
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'modified-changed': (GObject.SignalFlags.RUN_LAST, None, ()),
		'textstyle-changed': (GObject.SignalFlags.RUN_LAST, None, (object,)),
		'page-changed': (GObject.SignalFlags.RUN_LAST, None, (object,)),
		'ui-init': (GObject.SignalFlags.RUN_LAST, None, ()),
	}

	__signals__ = {
		'activate-link': (GObject.SignalFlags.RUN_LAST, bool, (object, object))
	}

	def __init__(self, notebook, navigation, secondary=False):
		'''Constructor
		@param notebook: the L{Notebook} object
		@param navigation: L{NavigationModel} object
		@param secondary: C{True} if this widget is part of a secondary
		widget
		'''
		GObject.GObject.__init__(self)
		GSignalEmitterMixin.__init__(self)

		self._buffer_signals = ()
		self.notebook = notebook
		self.page = None
		self.navigation = navigation
		self.readonly = True
		self._readonly_set = False
		self._readonly_set_error = False
		self.secondary = secondary
		if self.secondary:
			self._readonly_set = True # HACK
		self.undostack = None
		self._current_toggle_action = None
		self._showing_template = False
		self._change_counter = 0
		self.ui_is_initialized = False

		self.preferences = ConfigManager.preferences['PageView']
		self.preferences.define(
			follow_on_enter=Boolean(True),
			read_only_cursor=Boolean(False),
			autolink_camelcase=Boolean(True),
			autolink_files=Boolean(True),
			autoselect=Boolean(True),
			unindent_on_backspace=Boolean(True),
			cycle_checkbox_type=Boolean(True),
			recursive_indentlist=Boolean(True),
			recursive_checklist=Boolean(False),
			auto_reformat=Boolean(False),
			copy_format=Choice('Text', COPY_FORMATS),
			file_templates_folder=String('~/Templates'),
		)

		self.textview = TextView(preferences=self.preferences)
		self.swindow = ScrolledWindow(self.textview)
		self._hack_hbox = Gtk.HBox()
		self._hack_hbox.add(self.swindow)
		self._hack_label = Gtk.Label() # any widget would do I guess
		self._hack_hbox.pack_end(self._hack_label, False, True, 1)
		self.add(self._hack_hbox)

		self.textview.connect_object('link-clicked', PageView.activate_link, self)
		self.textview.connect_object('populate-popup', PageView.do_populate_popup, self)

		## Create search box
		self.find_bar = FindBar(textview=self.textview)
		self.pack_end(self.find_bar, False, True, 0)
		self.find_bar.hide()

		## setup GUI actions
		if self.secondary:
			# HACK - divert actions from uimanager
			self.actiongroup = Gtk.ActionGroup('SecondaryPageView')

		group = get_gtk_actiongroup(self)
		group.add_actions(MENU_ACTIONS, self)

		# setup hooks for new file submenu
		action = self.actiongroup.get_action('insert_new_file_menu')
		action.zim_readonly = False
		action.connect('activate', self._update_new_file_submenu)

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

		self.preferences.connect('changed', self.on_preferences_changed)
		self.on_preferences_changed()

		self.text_style = ConfigManager.get_config_dict('style.conf')
		self.text_style.connect('changed', lambda o: self.on_text_style_changed())
		self.on_text_style_changed()

		def assert_not_modified(page, *a):
			if page == self.page \
			and self.textview.get_buffer().get_modified():
				raise AssertionError('BUG: page changed while buffer changed as well')
				# not using assert here because it could be optimized away

		for s in ('store-page', 'delete-page', 'move-page'):
			self.notebook.connect(s, assert_not_modified)

		# Setup saving
		if_preferences = ConfigManager.preferences['GtkInterface']
		if_preferences.setdefault('autosave_timeout', 15)
		if_preferences.setdefault('autosave_use_thread', True)
		logger.debug('Autosave interval: %r - use threads: %r',
			if_preferences['autosave_timeout'],
			if_preferences['autosave_use_thread']
		)
		self._save_page_handler = SavePageHandler(
			self, notebook,
			self.get_page,
			timeout=if_preferences['autosave_timeout'],
			use_thread=if_preferences['autosave_use_thread']
		)

		def on_focus_out_event(*a):
			self._save_page_handler.try_save_page()
			return False # don't block the event
		self.textview.connect('focus-out-event', on_focus_out_event)

		PluginManager.insertedobjects.connect(
			'changed',
			self.on_insertedobjecttypemap_changed
		)

	def do_ui_init(self):
		self.ui_is_initialized = True

	def grab_focus(self):
		self.textview.grab_focus()

	def on_preferences_changed(self, *a):
		self.textview.set_cursor_visible(
			self.preferences['read_only_cursor'] or not self.readonly)

	def on_text_style_changed(self, *a):
		'''(Re-)intializes properties for TextView, TextBuffer and
		TextTags based on the properties in the style config.
		'''

		# TODO: reload buffer on style changed to make change visible
		#       now it is only visible on next page load

		self.text_style['TextView'].define(
			bullet_icon_size=ConfigDefinitionConstant(
				'GTK_ICON_SIZE_MENU',
				Gtk.IconSize,
				'GTK_ICON_SIZE'
			)
		)

		self.text_style['TextView'].setdefault('indent', TextBuffer.pixels_indent)
		self.text_style['TextView'].setdefault('tabs', None, int)
			# Don't set a default for 'tabs' as not to break pages that
			# were created before this setting was introduced.
		self.text_style['TextView'].setdefault('linespacing', 3)
		self.text_style['TextView'].setdefault('font', None, str)
		self.text_style['TextView'].setdefault('justify', None, str)
		#~ print self.text_style['TextView']

		# Set properties for TextVIew
		if self.text_style['TextView']['tabs']:
			tabarray = Pango.TabArray(1, True) # Initial size, position in pixels
			tabarray.set_tab(0, Pango.TabAlign.LEFT, self.text_style['TextView']['tabs'])
				# We just set the size for one tab, apparently this gets
				# copied automaticlly when a new tab is created by the textbuffer
			self.textview.set_tabs(tabarray)

		if self.text_style['TextView']['linespacing']:
			self.textview.set_pixels_below_lines(self.text_style['TextView']['linespacing'])

		if self.text_style['TextView']['font']:
			font = Pango.FontDescription(self.text_style['TextView']['font'])
			self.textview.modify_font(font)
		else:
			self.textview.modify_font(None)

		if self.text_style['TextView']['justify']:
			try:
				const = self.text_style['TextView']['justify']
				assert hasattr(gtk, const), 'No such constant: Gtk.%s' % const
				self.textview.set_justification(getattr(gtk, const))
			except:
				logger.exception('Exception while setting justification:')

		# Set properties for TextBuffer
		TextBuffer.pixels_indent = self.text_style['TextView']['indent']
		TextBuffer.bullet_icon_size = self.text_style['TextView']['bullet_icon_size']

		# Load TextTags
		testbuffer = Gtk.TextBuffer()
		for key in [k for k in list(self.text_style.keys()) if k.startswith('Tag ')]:
			section = self.text_style[key]
			defs = [(k, TextBuffer.tag_attributes[k])
				for k in section._input if k in TextBuffer.tag_attributes]
			section.define(defs)
			tag = key[4:]

			try:
				if not tag in TextBuffer.tag_styles:
					raise AssertionError('No such tag: %s' % tag)

				attrib = dict(i for i in list(section.items()) if i[1] is not None)
				if 'linespacing' in attrib:
					attrib['pixels-below-lines'] = attrib.pop('linespacing')

				#~ print('TAG', tag, attrib)
				testtag = testbuffer.create_tag('style-' + tag, **attrib)
				if not testtag:
					raise AssertionError('Could not create tag: %s' % tag)
			except:
				logger.exception('Exception while parsing tag: %s:', tag)
			else:
				TextBuffer.tag_styles[tag].update(attrib)

	def _connect_focus_event(self):
		# Connect to parent window here in a HACK to ensure
		# we do not hijack keybindings like ^C and ^V while we are not
		# focus (e.g. paste in find bar) Put it here to ensure
		# mainwindow is initialized.
		def set_actiongroup_sensitive(window, widget):
			#~ print('!! FOCUS SET:', widget)
			sensitive = widget is self.textview
			self._set_menuitems_sensitive(sensitive)

		window = self.get_toplevel()
		if window and window != self:
			window.connect('set-focus', set_actiongroup_sensitive)

	def set_page(self, page, cursor=None):
		'''Set the current page to be displayed in the pageview

		When the page does not yet exist a template is loaded for a
		new page which is obtained from
		L{Notebook.get_template()<zim.notebook.Notebook.get_template>}.

		Exceptions while loading the page are handled gracefully with
		an error dialog and will result in the widget to be read-only
		and insensitive until the next page is loaded.

		@param page: a L{Page} object
		@keyword cursor: optional cursor position (integer)

		When the cursor is set to C{-1} the cursor will be placed at
		the end of the buffer.

		If cursor is C{None} the cursor is set at the start of the page
		for existing pages or to the end of the template when the page
		does not yet exist.
		'''
		# unhook from previous page
		if self.page:
			self.page.set_ui_object(None)
		else:
			# first run - bootstrap HACK
			self._connect_focus_event()

		# for some reason keeping a copy of the previous buffer
		# prevents a number of segfaults ...
		# we do clear the old buffer to save some memory
		if self.undostack:
			self.undostack.block()
			self.undostack = None

		self._prev_buffer = self.textview.get_buffer()
		finderstate = self._prev_buffer.finder.get_state()

		for child in self.textview.get_children():
			if isinstance(child, InsertedObjectWidget):
				self.textview.remove(child)

		for id in self._buffer_signals:
			self._prev_buffer.disconnect(id)
		self._buffer_signals = ()
		start, end = self._prev_buffer.get_bounds()
		self._prev_buffer.clear()

		# now create the new buffer
		self._readonly_set_error = False
		try:
			self.page = page
			buffer = TextBuffer(self.notebook, self.page)
			self._buffer_signals = (
				buffer.connect('end-insert-tree', self._hack_on_inserted_tree),
			)

			self.textview.set_buffer(buffer)
			tree = page.get_parsetree()

			if tree is None:
				# TODO check read-only
				template = True
				tree = self.notebook.get_template(page)
				if cursor is None:
					cursor = -1
			else:
				template = False
				if cursor is None:
					cursor = 0

			self.set_parsetree(tree, template)
			if not self.secondary:
				page.set_ui_object(self) # only after successful set tree in buffer
		except Exception as error:
			# Maybe corrupted parse tree - prevent page to be edited or saved back
			self._readonly_set_error = True
			self._update_readonly()
			self.set_sensitive(False)
			ErrorDialog(self, error).run()
		else:
			# Finish hooking up the new page
			self.set_cursor_pos(cursor)

			self._buffer_signals += (
				buffer.connect('textstyle-changed', lambda o, *a: self.emit('textstyle-changed', *a)),
				buffer.connect('modified-changed', lambda o: self.on_modified_changed(o)),
				buffer.connect_after('mark-set', self.do_mark_set),
			)

			buffer.finder.set_state(*finderstate) # maintain state

			self.undostack = UndoStackManager(buffer)
			self.set_sensitive(True)
			self._update_readonly()

			self.emit('page-changed', self.page)

	def get_page(self):
		'''Get the current page
		@returns: the current L{Page} object
		'''
		return self.page

	def on_modified_changed(self, buffer):
		# one-way traffic, set page modified after modifying the buffer
		# but do not set page.modified False again when buffer goes
		# back to un-modified. Reason is that we use the buffer modified
		# state to track if we already requested the parse tree (see
		# get_parsetree()) while page modified is used to track need
		# for saving and is reset after save was done
		self._showing_template = False
		if buffer.get_modified():
			if self.readonly:
				logger.warn('Buffer edited while read-only - potential bug')
			else:
				# HACK: by setting page.modified to a number rather than a
				# bool we can use this number to check against race conditions
				# in notebook.store_page_async post handler
				self._change_counter = max(1, (self._change_counter + 1) % 1000)
				self.page.modified = self._change_counter
				assert bool(self.page.modified) is True, 'BUG in counter'
				self.emit('modified-changed')

				self._save_page_handler.queue_autosave()

	def save_changes(self, write_if_not_modified=False):
		'''Save contents of the widget back to the page object and
		synchronize it with the notebook.
		@param write_if_not_modified: If C{True} page will be written
		even if there are no changes in the widget.
		'''
		buffer = self.textview.get_buffer()
		if write_if_not_modified or buffer.get_modified():
			self._save_page_handler.save_page_now()
		self._save_page_handler.wait_for_store_page_async()

	def clear(self):
		'''Clear the buffer'''
		# Called e.g. by "discard changes" maybe due to an exception in
		# buffer.get_parse_tree() - so just drop everything...
		buffer = self.textview.get_buffer()
		buffer.clear()
		buffer.set_modified(False)
		self._showing_template = False

	def get_parsetree(self):
		'''Get the L{ParseTree} for the content in the widget

		Note that calling
		L{Page.get_parsetree()<zim.notebook.Page.get_parsetree()>}
		for the current page will call also call this method by proxy.

		@returns: a L{ParseTree} object
		'''
		if self._showing_template:
			return None
		else:
			buffer = self.textview.get_buffer()
			if not hasattr(self, '_parsetree') or buffer.get_modified():
				self._parsetree = buffer.get_parsetree()
				buffer.set_modified(False)
			#~ print self._parsetree.tostring()
			return self._parsetree

	def set_parsetree(self, tree, istemplate=False):
		'''Set the L{ParseTree} for the content in the widget

		Be aware that this will set new content in the current page
		and modify the page.

		Note that calling
		L{Page.set_parsetree()<zim.notebook.Page.set_parsetree()>}
		for the current page will call also call this method by proxy.

		@param tree: a L{ParseTree} object
		@param istemplate: C{True} when the tree is a page template
		instead of the page content
		'''
		buffer = self.textview.get_buffer()
		assert not buffer.get_modified(), 'BUG: changing parsetree while buffer was changed as well'
		tree.resolve_images(self.notebook, self.page)
		buffer.set_parsetree(tree)
		self._parsetree = tree
		self._showing_template = istemplate

	def _hack_on_inserted_tree(self, *a):
		if self.textview._object_widgets:
			# Force resize of the scroll window, forcing a redraw to fix
			# glitch in allocation of embedded obejcts, see isse #642
			# Will add another timeout to rendering the page, increasing the
			# priority breaks the hack though. Which shows the glitch is
			# probably also happening in a drawing or resizing idle event
			#
			# Additional hook is needed for scrolling because re-rendering the
			# objects changes the textview size and thus looses the scrolled
			# position. Here idle didn't work so used a time-out with the
			# potential risk that in some cases the timeout is to fast or to slow.

			self._hack_label.show_all()
			def scroll():
				self.scroll_cursor_on_screen()
				return False

			def hide_hack():
				self._hack_label.hide()
				GLib.timeout_add(100, scroll)
				return False

			GLib.idle_add(hide_hack)
		else:
			self._hack_label.hide()

	def on_insertedobjecttypemap_changed(self, *a):
		self.save_changes()
		buffer = self.textview.get_buffer()
		tree = buffer.get_parsetree()
		self.set_parsetree(tree, self._showing_template)

	def set_readonly(self, readonly):
		'''Set the widget read-only or not

		Sets the read-only state but also update menu items etc. to
		reflect the new state.

		@param readonly: C{True} or C{False} to set the read-only state

		Effective read-only state seen in the C{self.readonly} attribute
		is in fact C{True} (so read-only) when either the widget itself
		OR the current page is read-only. So setting read-only to
		C{False} here may not immediately change C{self.readonly} if
		a read-only page is loaded.
		'''
		self._readonly_set = readonly
		self._update_readonly()

	def _update_readonly(self):
		self.readonly = self._readonly_set \
			or self._readonly_set_error \
			or self.page is None \
			or self.notebook.readonly \
			or self.page.readonly
		self.textview.set_editable(not self.readonly)
		self.textview.set_cursor_visible(
			self.preferences['read_only_cursor'] or not self.readonly)
		self._set_menuitems_sensitive(True) # XXX not sure why this is here

	def _set_menuitems_sensitive(self, sensitive):
		'''Batch update global menu sensitivity while respecting
		sensitivities set due to cursor position, readonly state etc.
		'''
		if sensitive:
			# partly overrule logic in window.toggle_editable()
			for action in self.actiongroup.list_actions():
				action.set_sensitive(
					action.zim_readonly or not self.readonly)

			# update state for menu items for checkboxes and links
			buffer = self.textview.get_buffer()
			iter = buffer.get_insert_iter()
			mark = buffer.get_insert()
			self.do_mark_set(buffer, iter, mark)
		else:
			for action in self.actiongroup.list_actions():
				action.set_sensitive(False)

	def set_cursor_pos(self, pos):
		'''Set the cursor position in the buffer and scroll the TextView
		to show it

		@param pos: the cursor position as an integer offset from the
		start of the buffer

		As a special case when the cursor position is C{-1} the cursor
		is set at the end of the buffer.
		'''
		buffer = self.textview.get_buffer()
		if pos < 0:
			start, end = buffer.get_bounds()
			iter = end
		else:
			iter = buffer.get_iter_at_offset(pos)

		buffer.place_cursor(iter)
		self.scroll_cursor_on_screen()

	def get_cursor_pos(self):
		'''Get the cursor position in the buffer

		@returns: the cursor position as an integer offset from the
		start of the buffer
		'''
		buffer = self.textview.get_buffer()
		iter = buffer.get_iter_at_mark(buffer.get_insert())
		return iter.get_offset()

	def scroll_cursor_on_screen(self):
		buffer = self.textview.get_buffer()
		self.textview.scroll_to_mark(buffer.get_insert(), SCROLL_TO_MARK_MARGIN, False, 0, 0)

	def set_scroll_pos(self, pos):
		pass # FIXME set scroll position

	def get_scroll_pos(self):
		pass # FIXME get scroll position

	def get_selection(self, format=None):
		'''Convenience method to get the text of the current selection.

		@param format: format to use for the formatting of the returned
		text (e.g. 'wiki' or 'html'). If the format is C{None} only the
		text will be returned without any formatting.

		@returns: text selection or C{None}
		'''
		buffer = self.textview.get_buffer()
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
		'''Convenience method to get the word that is under the cursor

		@param format: format to use for the formatting of the returned
		text (e.g. 'wiki' or 'html'). If the format is C{None} only the
		text will be returned without any formatting.

		@returns: current word or C{None}
		'''
		buffer = self.textview.get_buffer()
		buffer.select_word()
		return self.get_selection(format)

	def replace_selection(self, text, autoselect=None):
		assert autoselect in (None, 'word')
		buffer = self.textview.get_buffer()
		if not buffer.get_has_selection():
			if autoselect == 'word':
				buffer.select_word()
			else:
				raise AssertionError

		bounds = buffer.get_selection_bounds()
		if bounds:
			start, end = bounds
			with buffer.user_action:
				buffer.delete(start, end)
				buffer.insert_at_cursor(''.join(text))
		else:
			buffer.insert_at_cursor(''.join(text))

	def do_mark_set(self, buffer, iter, mark):
		# Update menu items relative to cursor position
		if self.readonly or mark.get_name() != 'insert':
			return

		# Set sensitivity of various menu options
		line = iter.get_line()
		bullet = buffer.get_bullet(line)
		if bullet and bullet in CHECKBOXES:
			self.actiongroup.get_action('uncheck_checkbox').set_sensitive(True)
			self.actiongroup.get_action('toggle_checkbox').set_sensitive(True)
			self.actiongroup.get_action('xtoggle_checkbox').set_sensitive(True)
			self.actiongroup.get_action('migrate_checkbox').set_sensitive(True)
		else:
			self.actiongroup.get_action('uncheck_checkbox').set_sensitive(False)
			self.actiongroup.get_action('toggle_checkbox').set_sensitive(False)
			self.actiongroup.get_action('xtoggle_checkbox').set_sensitive(False)
			self.actiongroup.get_action('migrate_checkbox').set_sensitive(False)

		if buffer.get_link_tag(iter):
			self.actiongroup.get_action('remove_link').set_sensitive(True)
			self.actiongroup.get_action('edit_object').set_sensitive(True)
		elif buffer.get_image_data(iter):
			self.actiongroup.get_action('remove_link').set_sensitive(False)
			self.actiongroup.get_action('edit_object').set_sensitive(True)
		else:
			self.actiongroup.get_action('edit_object').set_sensitive(False)
			self.actiongroup.get_action('remove_link').set_sensitive(False)

	def do_textstyle_changed(self, style):
		# Update menu items for current style
		#~ print('>>> SET STYLE', style)

		# set toolbar toggles
		if style:
			style_toggle = 'toggle_format_' + style
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

		#~ print('<<<')

	def activate_link(self, link, new_window=False):
		if not isinstance(link, str):
			link = link['href']

		href = normalize_file_uris(link)
			# can translate file:// -> smb:// so do before link_type()
			# FIXME implement function in notebook to resolve any link
			#       type and take care of this stuff ?
		logger.debug('Activate link: %s', link)

		if link_type(link) == 'interwiki':
			target = interwiki_link(link)
			if target is not None:
				link = target
			else:
				name = link.split('?')[0]
				error = Error(_('No such wiki defined: %s') % name)
					# T: error when unknown interwiki link is clicked
				return ErrorDialog(self, error).run()

		hints = {'new_window': new_window}
		self.emit_return_first('activate-link', link, hints)

	def do_activate_link(self, link, hints):
		try:
			self._do_activate_link(link, hints)
		except:
			zim.errors.exception_handler(
				'Exception during activate-link(%r)' % ((link, hints),))

	def _do_activate_link(self, link, hints):
		type = link_type(link)

		if type == 'page':
			path = self.notebook.pages.resolve_link(
				self.page, HRef.new_from_wiki_link(link)
			)
			self.navigation.open_page(path, new_window=hints.get('new_window', False))
		elif type == 'file':
			path = self.notebook.resolve_file(link, self.page)
			open_file(self, path)
		elif type == 'notebook':
			from zim.main import ZIM_APPLICATION

			if link.startswith('zim+'):
				uri, pagename = link[4:], None
				if '?' in uri:
					uri, pagename = uri.split('?', 1)

				ZIM_APPLICATION.run('--gui', uri, pagename)

			else:
				ZIM_APPLICATION.run('--gui', FilePath(link).uri)

		else:
			if type == 'mailto' and not link.startswith('mailto:'):
				link = 'mailto:' + link  # Enforce proper URI form
			open_url(self, link)

		return True # handled

	def do_populate_popup(self, menu):
		buffer = self.textview.get_buffer()
		if not buffer.get_has_selection():
			iter = self.textview._get_popup_menu_mark()
			if iter is None:
				self._default_do_populate_popup(menu)
			else:
				if iter.get_line_offset() == 1:
					iter.backward_char() # if clicked on right half of image, iter is after the image
				bullet = buffer.get_bullet_at_iter(iter)
				if bullet and bullet in CHECKBOXES:
					self._checkbox_do_populate_popup(menu, buffer, iter)
				else:
					self._default_do_populate_popup(menu)
		else:
			self._default_do_populate_popup(menu)

	def _default_do_populate_popup(self, menu):
		# Add custom tool
		# FIXME need way to (deep)copy widgets in the menu
		#~ toolmenu = uimanager.get_widget('/text_popup')
		#~ tools = [tool for tool in toolmenu.get_children()
					#~ if not isinstance(tool, Gtk.SeparatorMenuItem)]
		#~ print('>>> TOOLS', tools)
		#~ if tools:
			#~ menu.prepend(Gtk.SeparatorMenuItem())
			#~ for tool in tools:
				#~ tool.reparent(menu)

		buffer = self.textview.get_buffer()

		### Copy As option ###
		default = self.preferences['copy_format'].lower()
		copy_as_menu = Gtk.Menu()
		for label in COPY_FORMATS:
			if label.lower() == default:
				continue # Covered by default Copy action

			format = zim.formats.canonical_name(label)
			item = Gtk.MenuItem.new_with_mnemonic(label)
			if buffer.get_has_selection():
				item.connect('activate',
					lambda o, f: self.textview.do_copy_clipboard(format=f),
					format)
			else:
				item.set_sensitive(False)
			copy_as_menu.append(item)

		item = Gtk.MenuItem.new_with_mnemonic(_('Copy _As...')) # T: menu item for context menu of editor
		item.set_submenu(copy_as_menu)
		item.show_all()
		menu.insert(item, 2) # position after Copy in the standard menu - may not be robust...
			# FIXME get code from test to seek stock item

		### Move text to new page ###
		item = Gtk.MenuItem.new_with_mnemonic(_('Move Selected Text...'))
			# T: Context menu item for pageview to move selected text to new/other page
		item.show_all() # FIXME should not be needed here
		menu.insert(item, 7) # position after Copy in the standard menu - may not be robust...
			# FIXME get code from test to seek stock item

		if buffer.get_has_selection():
			item.connect('activate',
				lambda o: MoveTextDialog(self, self.notebook, self.page, buffer, self.navigation).run())
		else:
			item.set_sensitive(False)
		###


		iter = self.textview._get_popup_menu_mark()
			# This iter can be either cursor position or pointer
			# position, depending on how the menu was called
		if iter is None:
			return

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
			else:
				return # No link or image

		if file:
			file = self.notebook.resolve_file(file, self.page)


		menu.prepend(Gtk.SeparatorMenuItem())

		# remove link
		if link:
			item = Gtk.MenuItem.new_with_mnemonic(_('_Remove Link'))
			item.connect('activate', lambda o: self.remove_link(iter=iter))
			item.set_sensitive(not self.readonly)
			menu.prepend(item)

		# edit
		if type == 'image':
			item = Gtk.MenuItem.new_with_mnemonic(_('_Edit Properties')) # T: menu item in context menu for image
		else:
			item = Gtk.MenuItem.new_with_mnemonic(_('_Edit Link')) # T: menu item in context menu
		item.connect('activate', lambda o: self.edit_object(iter=iter))
		item.set_sensitive(not self.readonly)
		menu.prepend(item)

		# copy
		def set_pagelink(o, path):
			Clipboard.set_pagelink(self.notebook, path)
			SelectionClipboard.set_pagelink(self.notebook, path)

		def set_interwikilink(o, data):
			href, url = data
			Clipboard.set_interwikilink(href, url)
			SelectionClipboard.set_interwikilink(href, url)

		def set_uri(o, uri):
			Clipboard.set_uri(uri)
			SelectionClipboard.set_uri(uri)

		if type == 'page':
			item = Gtk.MenuItem.new_with_mnemonic(_('Copy _Link')) # T: context menu item
			path = self.notebook.pages.resolve_link(
				self.page, HRef.new_from_wiki_link(link['href'])
			)
			item.connect('activate', set_pagelink, path)
		elif type == 'interwiki':
			item = Gtk.MenuItem.new_with_mnemonic(_('Copy _Link')) # T: context menu item
			url = interwiki_link(link['href'])
			item.connect('activate', set_interwikilink, (link['href'], url))
		elif type == 'mailto':
			item = Gtk.MenuItem.new_with_mnemonic(_('Copy Email Address')) # T: context menu item
			item.connect('activate', set_uri, file or link['href'])
		else:
			item = Gtk.MenuItem.new_with_mnemonic(_('Copy _Link')) # T: context menu item
			item.connect('activate', set_uri, file or link['href'])
		menu.prepend(item)

		menu.prepend(Gtk.SeparatorMenuItem())

		# open with & open folder
		if type in ('file', 'image') and file:
			item = Gtk.MenuItem.new_with_mnemonic(_('Open Folder'))
				# T: menu item to open containing folder of files
			menu.prepend(item)
			dir = file.dir
			if dir.exists():
				item.connect('activate', lambda o: open_file(self, dir))
			else:
				item.set_sensitive(False)

			item = Gtk.MenuItem.new_with_mnemonic(_('Open With...'))
				# T: menu item for sub menu with applications
			menu.prepend(item)
			if file.exists():
				submenu = OpenWithMenu(self, file)
				item.set_submenu(submenu)
			else:
				item.set_sensitive(False)
		elif type not in ('page', 'notebook', 'interwiki', 'file', 'image'): # urls etc.
			# FIXME: for interwiki inspect final link and base
			# open with menu based on that url type
			item = Gtk.MenuItem.new_with_mnemonic(_('Open With...'))
			menu.prepend(item)
			submenu = OpenWithMenu(self, link['href'])
			if submenu.get_children():
				item.set_submenu(submenu)
			else:
				item.set_sensitive(False)

		# open in new window
		if type == 'page':
			item = Gtk.MenuItem.new_with_mnemonic(_('Open in New _Window'))
				# T: menu item to open a link
			item.connect(
				'activate', lambda o: self.activate_link(link, new_window=True))
			menu.prepend(item)

		# open
		if type == 'image':
			link = {'href': file.uri}

		item = Gtk.MenuItem.new_with_mnemonic(_('_Open'))
			# T: menu item to open a link or file
		if file and not file.exists():
			item.set_sensitive(False)
		else:
			item.connect_object(
				'activate', PageView.activate_link, self, link)
		menu.prepend(item)

		menu.show_all()

	def _checkbox_do_populate_popup(self, menu, buffer, iter):
		line = iter.get_line()

		menu.prepend(Gtk.SeparatorMenuItem())

		for bullet, label in (
			(MIGRATED_BOX, _('Check Checkbox \'>\'')), # T: popup menu menuitem
			(XCHECKED_BOX, _('Check Checkbox \'X\'')), # T: popup menu menuitem
			(CHECKED_BOX, _('Check Checkbox \'V\'')), # T: popup menu menuitem
			(UNCHECKED_BOX, _('Un-check Checkbox')), # T: popup menu menuitem
		):
			item = Gtk.ImageMenuItem(bullet_types[bullet])
			item.set_label(label)
			item.connect('activate', callback(buffer.set_bullet, line, bullet))
			menu.prepend(item)

		menu.show_all()

	@action(_('_Save'), '<Primary>S', menuhints='edit') # T: Menu item
	def save_page(self):
		'''Menu action to save the current page.

		Can result in a L{SavePageErrorDialog} when there is an error
		while saving a page. If that dialog is cancelled by the user,
		the page may not be saved after all.
		'''
		self.save_changes(write_if_not_modified=True) # XXX

	@action(_('_Undo'), '<Primary>Z', menuhints='edit') # T: Menu item
	def undo(self):
		'''Menu action to undo a single step'''
		self.undostack.undo()
		self.scroll_cursor_on_screen()

	@action(_('_Redo'), '<Primary><shift>Z', alt_accelerator='<Primary>Y', menuhints='edit') # T: Menu item
	def redo(self):
		'''Menu action to redo a single step'''
		self.undostack.redo()
		self.scroll_cursor_on_screen()

	@action(_('Cu_t'), '<Primary>X', menuhints='edit') # T: Menu item
	def cut(self):
		'''Menu action for cut to clipboard'''
		self.textview.emit('cut-clipboard')

	@action(_('_Copy'), '<Primary>C', menuhints='edit') # T: Menu item
	def copy(self):
		'''Menu action for copy to clipboard'''
		self.textview.emit('copy-clipboard')

	@action(_('_Paste'), '<Primary>V', menuhints='edit') # T: Menu item
	def paste(self):
		'''Menu action for paste from clipboard'''
		self.textview.emit('paste-clipboard')

	@action(_('_Delete'), menuhints='edit') # T: Menu item
	def delete(self):
		'''Menu action for delete'''
		self.textview.emit('delete-from-cursor', Gtk.DeleteType.CHARS, 1)

	@action(_('Un-check Checkbox'), verb_icon=STOCK_UNCHECKED_BOX, menuhints='edit') # T: Menu item
	def uncheck_checkbox(self):
		buffer = self.textview.get_buffer()
		recurs = self.preferences['recursive_checklist']
		buffer.toggle_checkbox_for_cursor_or_selection(UNCHECKED_BOX, recurs)

	@action(_('Toggle Checkbox \'V\''), 'F12', verb_icon=STOCK_CHECKED_BOX, menuhints='edit') # T: Menu item
	def toggle_checkbox(self):
		'''Menu action to toggle checkbox at the cursor or in current
		selected text
		'''
		buffer = self.textview.get_buffer()
		recurs = self.preferences['recursive_checklist']
		buffer.toggle_checkbox_for_cursor_or_selection(CHECKED_BOX, recurs)

	@action(_('Toggle Checkbox \'X\''), '<shift>F12', verb_icon=STOCK_XCHECKED_BOX, menuhints='edit') # T: Menu item
	def xtoggle_checkbox(self):
		'''Menu action to toggle checkbox at the cursor or in current
		selected text
		'''
		buffer = self.textview.get_buffer()
		recurs = self.preferences['recursive_checklist']
		buffer.toggle_checkbox_for_cursor_or_selection(XCHECKED_BOX, recurs)

	@action(_('Toggle Checkbox \'>\''), verb_icon=STOCK_MIGRATED_BOX, menuhints='edit') # T: Menu item
	def migrate_checkbox(self):
		'''Menu action to toggle checkbox at the cursor or in current
		selected text
		'''
		buffer = self.textview.get_buffer()
		recurs = self.preferences['recursive_checklist']
		buffer.toggle_checkbox_for_cursor_or_selection(MIGRATED_BOX, recurs)

	@action(_('_Edit Link or Object...'), '<Primary>E', menuhints='edit') # T: Menu item
	def edit_object(self, iter=None):
		'''Menu action to trigger proper edit dialog for the current
		object at the cursor

		Can show e.g. L{InsertLinkDialog} for a link, C{EditImageDialog}
		for the a image, or a plugin dialog for e.g. an equation.

		@param iter: C{TextIter} for an alternative cursor position
		'''
		buffer = self.textview.get_buffer()
		if iter:
			buffer.place_cursor(iter)

		iter = buffer.get_iter_at_mark(buffer.get_insert())
		if buffer.get_link_tag(iter):
			return InsertLinkDialog(self, self).run()

		image = buffer.get_image_data(iter)
		anchor = buffer.get_objectanchor(iter)
		if not (image or (anchor and isinstance(anchor, PluginInsertedObjectAnchor))):
			iter.backward_char() # maybe we clicked right side of an image
			image = buffer.get_image_data(iter)
			anchor = buffer.get_objectanchor(iter)

		if image:
			EditImageDialog(self, buffer, self.notebook, self.page).run()
		elif anchor and isinstance(anchor, PluginInsertedObjectAnchor):
			widget = anchor.get_widgets()[0]
			try:
				widget.edit_object()
			except NotImplementedError:
				return False
			else:
				return True
		else:
			return False

	@action(_('_Remove Link'), menuhints='edit') # T: Menu item
	def remove_link(self, iter=None):
		'''Menu action to remove link object at the current cursor position

		@param iter: C{TextIter} for an alternative cursor position
		'''
		buffer = self.textview.get_buffer()

		if not buffer.get_has_selection() \
		or (iter and not buffer.iter_in_selection(iter)):
			if iter:
				buffer.place_cursor(iter)
			buffer.select_link()

		bounds = buffer.get_selection_bounds()
		if bounds:
			buffer.remove_link(*bounds)

	@action(_('_Date and Time...'), accelerator='<Primary>D', menuhints='insert') # T: Menu item
	def insert_date(self):
		'''Menu action to insert a date, shows the L{InsertDateDialog}'''
		InsertDateDialog(self, self.textview.get_buffer(), self.notebook, self.page).run()

	def insert_object(self, attrib, data):
		buffer = self.textview.get_buffer()
		with buffer.user_action:
			buffer.insert_object_at_cursor(attrib, data)

	def insert_object_model(self, otype, model):
		buffer = self.textview.get_buffer()
		with buffer.user_action:
			buffer.insert_object_model_at_cursor(otype, model)

	@action(_('Horizontal _Line'), menuhints='insert') # T: Menu item for Insert menu
	def insert_line(self):
		'''
                This function is called from menu action.
                Insert a line at the cursor position.
		'''
		buffer = self.textview.get_buffer()
		with buffer.user_action:
			buffer.insert_objectanchor_at_cursor(LineSeparatorAnchor())
			# Add newline after line separator widget.
			buffer.insert_at_cursor('\n')

	@action(_('_Image...'), menuhints='insert') # T: Menu item
	def show_insert_image(self, file=None):
		'''Menu action to insert an image, shows the L{InsertImageDialog}
		@param file: optional file to suggest in the dialog
		'''
		InsertImageDialog(self, self.textview.get_buffer(), self.notebook, self.page, file).run()

	def insert_image(self, file):
		'''Insert a image
		@param file: the image file to insert. If C{file} does not exist or
		isn't an image, a "broken image" icon will be shown
		'''
		file = adapt_from_newfs(file)
		assert isinstance(file, File)
		src = self.notebook.relative_filepath(file, self.page) or file.uri
		self.textview.get_buffer().insert_image_at_cursor(file, src)

	@action(_('Bulle_t List'), menuhints='insert') # T: Menu item
	def insert_bullet_list(self):
		'''Menu action insert a bullet item at the cursor'''
		self._start_bullet(BULLET)

	@action(_('_Numbered List'), menuhints='insert') # T: Menu item
	def insert_numbered_list(self):
		'''Menu action insert a numbered list item at the cursor'''
		self._start_bullet(NUMBER_BULLET)

	@action(_('Checkbo_x List'), menuhints='insert') # T: Menu item
	def insert_checkbox_list(self):
		'''Menu action insert an open checkbox at the cursor'''
		self._start_bullet(UNCHECKED_BOX)

	def _start_bullet(self, bullet_type):
		buffer = self.textview.get_buffer()
		line = buffer.get_insert_iter().get_line()

		with buffer.user_action:
			iter = buffer.get_iter_at_line(line)
			buffer.insert(iter, '\n')
			buffer.set_bullet(line, bullet_type)
			iter = buffer.get_iter_at_line(line)
			iter.forward_to_line_end()
			buffer.place_cursor(iter)

	@action(_('Bulle_t List'), menuhints='edit') # T: Menu item,
	def apply_format_bullet_list(self):
		'''Menu action to format selection as bullet list'''
		self._apply_bullet(BULLET)

	@action(_('_Numbered List'), menuhints='edit') # T: Menu item,
	def apply_format_numbered_list(self):
		'''Menu action to format selection as numbered list'''
		self._apply_bullet(NUMBER_BULLET)

	@action(_('Checkbo_x List'), menuhints='edit') # T: Menu item,
	def apply_format_checkbox_list(self):
		'''Menu action to format selection as checkbox list'''
		self._apply_bullet(UNCHECKED_BOX)

	def _apply_bullet(self, bullet_type):
		buffer = self.textview.get_buffer()
		buffer.foreach_line_in_selection(buffer.set_bullet, bullet_type)

	@action(_('Text From _File...'), menuhints='insert') # T: Menu item
	def insert_text_from_file(self):
		'''Menu action to show a L{InsertTextFromFileDialog}'''
		InsertTextFromFileDialog(self, self.textview.get_buffer(), self.notebook, self.page).run()

	def insert_links(self, links):
		'''Non-interactive method to insert one or more links

		Inserts the links separated by newlines. Intended e.g. for
		drag-and-drop or copy-paste actions of e.g. files from a
		file browser.

		@param links: list of links, either as string, L{Path} objects,
		or L{File} objects
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
			links[i] = self.notebook.relative_filepath(file, self.page) or file.uri

		if len(links) == 1:
			sep = ' '
		else:
			sep = '\n'

		buffer = self.textview.get_buffer()
		with buffer.user_action:
			if buffer.get_has_selection():
				start, end = buffer.get_selection_bounds()
				buffer.delete(start, end)
			for link in links:
				buffer.insert_link_at_cursor(link, link)
				buffer.insert_at_cursor(sep)

	@action(_('_Link...'), '<Primary>L', verb_icon='zim-link', menuhints='insert') # T: Menu item
	def insert_link(self):
		'''Menu item to show the L{InsertLinkDialog}'''
		InsertLinkDialog(self, self).run()

	def _update_new_file_submenu(self, action):
		dir = self.preferences['file_templates_folder']
		if isinstance(dir, str):
			dir = Dir(dir)

		items = []
		if dir.exists():
			def handler(menuitem, file):
				self.insert_new_file(file)

			for name in dir.list(): # FIXME could use list objects here
				file = dir.file(name)
				if file.exists(): # it is a file
					name = file.basename
					if '.' in name:
						name, x = name.rsplit('.', 1)
					name = name.replace('_', ' ')
					item = Gtk.MenuItem.new_with_mnemonic(name)
						# TODO mimetype icon would be nice to have
					item.connect('activate', handler, file)
					item.zim_new_file_action = True
					items.append(item)

		if not items:
			item = Gtk.MenuItem.new_with_mnemonic(_('No templates installed'))
				# T: message when no file templates are found in ~/Templates
			item.set_sensitive(False)
			item.zim_new_file_action = True
			items.append(item)


		for widget in action.get_proxies():
			if hasattr(widget, 'get_submenu'):
				menu = widget.get_submenu()
				if not menu:
					continue

				# clear old items
				for item in menu.get_children():
					if hasattr(item, 'zim_new_file_action'):
						menu.remove(item)

				# add new ones
				populate_popup_add_separator(menu, prepend=True)
				for item in reversed(items):
					menu.prepend(item)

				# and finish up
				menu.show_all()

	def insert_new_file(self, template, basename=None):
		dir = self.notebook.get_attachments_dir(self.page)

		if not basename:
			basename = NewFileDialog(self, template.basename).run()
			if basename is None:
				return # cancelled

		file = dir.new_file(basename)
		template.copyto(file)

		# Same logic as in AttachFileDialog
		# TODO - incorporate in the insert_links function ?
		if file.isimage():
			ok = self.insert_image(file)
			if not ok: # image type not supported?
				logger.info('Could not insert image: %s', file)
				self.insert_links([file])
		else:
			self.insert_links([file])

		#~ open_file(self, file) # FIXME should this be optional ?

	@action(_('File _Templates...')) # T: Menu item in "Insert > New File Attachment" submenu
	def open_file_templates_folder(self):
		'''Menu action to open the templates folder'''
		dir = self.preferences['file_templates_folder']
		if isinstance(dir, str):
			dir = Dir(dir)

		if dir.exists():
			open_file(self, dir)
		else:
			path = dir.user_path or dir.path
			question = (
				_('Create folder?'),
					# T: Heading in a question dialog for creating a folder
				_('The folder\n%s\ndoes not yet exist.\nDo you want to create it now?')
					% path
			)
					# T: Text in a question dialog for creating a folder, %s is the folder path
			create = QuestionDialog(self, question).run()
			if create:
				dir.touch()
				open_file(self, dir)

	@action(_('_Clear Formatting'), accelerator='<Primary>9', menuhints='edit') # T: Menu item
	def clear_formatting(self):
		'''Menu item to remove formatting from current (auto-)selection'''
		buffer = self.textview.get_buffer()
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
		if name.startswith('apply_format_'):
			style = name[13:]
		elif name.startswith('toggle_format_'):
			style = name[14:]
		else:
			assert False, "BUG: don't known this action"
		self.toggle_format(style)
		self._current_toggle_action = None

	def toggle_format(self, format):
		'''Toggle the format for the current (auto-)selection or new
		insertions at the current cursor position

		When the cursor is in the middle of a word it can be selected
		automatically to format it. But we only autoselect words that
		were not formatted - otherwise the behavior is not consistent
		when trying to break a formatted region by toggling off the
		formatting. For headings and other line based formats
		auto-selects the whole line.

		This is the handler for all the format menu- and toolbar-items.

		@param format: the format style name (e.g. "h1", "strong" etc.)
		'''
		buffer = self.textview.get_buffer()
		selected = False
		mark = buffer.create_mark(None, buffer.get_insert_iter())

		if format != buffer.get_textstyle():
			ishead = format in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6')
			selected = self.autoselect(selectline=ishead)

		buffer.toggle_textstyle(format)

		if selected:
			# If we keep the selection we can not continue typing
			# so remove the selection and restore the cursor.
			buffer.unset_selection()
			buffer.place_cursor(buffer.get_iter_at_mark(mark))
		buffer.delete_mark(mark)

	def autoselect(self, selectline=False):
		'''Auto select either a word or a line.

		Does not do anything if a selection is present already or when
		the preference for auto-select is set to False.

		@param selectline: if C{True} auto-select a whole line,
		only auto-select a single word otherwise
		@returns: C{True} when this function changed the selection.
		'''
		if not self.preferences['autoselect']:
			return False

		buffer = self.textview.get_buffer()
		if buffer.get_has_selection():
			if selectline:
				start, end = buffer.get_selection_bounds()
				return buffer.select_lines(start.get_line(), end.get_line())
			else:
				return buffer.strip_selection()
		elif selectline:
			return buffer.select_line()
		else:
			return buffer.select_word()

	def find(self, string, flags=0):
		'''Find some string in the text, scroll there and select it

		@param string: the text to find
		@param flags: options for find behavior, see L{TextFinder.find()}
		'''
		self.hide_find() # remove previous highlighting etc.
		buffer = self.textview.get_buffer()
		buffer.finder.find(string, flags)
		self.textview.scroll_to_mark(buffer.get_insert(), SCROLL_TO_MARK_MARGIN, False, 0, 0)

	@action(_('_Find...'), '<Primary>F', alt_accelerator='<Primary>F3') # T: Menu item
	def show_find(self, string=None, flags=0, highlight=False):
		'''Show the L{FindBar} widget

		@param string: the text to find
		@param flags: options for find behavior, see L{TextFinder.find()}
		@param highlight: if C{True} highlight the results
		'''
		self.find_bar.show()
		if string:
			self.find_bar.find(string, flags, highlight)
			self.textview.grab_focus()
		else:
			self.find_bar.set_from_buffer()
			self.find_bar.grab_focus()

	def hide_find(self):
		'''Hide the L{FindBar} widget'''
		self.find_bar.hide()
		self.textview.grab_focus()

	@action(_('Find Ne_xt'), accelerator='<Primary>G', alt_accelerator='F3') # T: Menu item
	def find_next(self):
		'''Menu action to skip to next match'''
		self.find_bar.show()
		self.find_bar.find_next()

	@action(_('Find Pre_vious'), accelerator='<Primary><shift>G', alt_accelerator='<shift>F3') # T: Menu item
	def find_previous(self):
		'''Menu action to go back to previous match'''
		self.find_bar.show()
		self.find_bar.find_previous()

	@action(_('_Replace...'), '<Primary>H', menuhints='edit') # T: Menu item
	def show_find_and_replace(self):
		'''Menu action to show the L{FindAndReplaceDialog}'''
		dialog = FindAndReplaceDialog.unique(self, self, self.textview)
		dialog.set_from_buffer()
		dialog.present()

	@action(_('Word Count...')) # T: Menu item
	def show_word_count(self):
		'''Menu action to show the L{WordCountDialog}'''
		WordCountDialog(self).run()

	@action(_('_Zoom In'), '<Primary>plus', alt_accelerator='<Primary>equal') # T: Menu item
	def zoom_in(self):
		'''Menu action to increase the font size'''
		self._zoom_increase_decrease_font_size(+1)

	@action(_('Zoom _Out'), '<Primary>minus') # T: Menu item
	def zoom_out(self):
		'''Menu action to decrease the font size'''
		self._zoom_increase_decrease_font_size(-1)

	def _zoom_increase_decrease_font_size(self, plus_or_minus):
		style = self.text_style
		if self.text_style['TextView']['font']:
			font = Pango.FontDescription(self.text_style['TextView']['font'])
		else:
			logger.debug('Switching to custom font implicitly because of zoom action')
			style = self.textview.get_style_context()
			font = style.get_property(Gtk.STYLE_PROPERTY_FONT, Gtk.StateFlags.NORMAL)

		font_size = font.get_size()
		if font_size <= 1 * 1024 and plus_or_minus < 0:
			return
		else:
			font_size_new = font_size + plus_or_minus * 1024
			font.set_size(font_size_new)
		try:
			self.text_style['TextView']['font'] = font.to_string()
		except UnicodeDecodeError:
			logger.exception('FIXME')
		self.textview.modify_font(font)

		self.text_style.write()

	@action(_('_Normal Size'), '<Primary>0') # T: Menu item to reset zoom
	def zoom_reset(self):
		'''Menu action to reset the font size'''
		if not self.text_style['TextView']['font']:
			return

		widget = TextView({}) # Get new widget
		style = widget.get_style_context()
		default_font = style.get_property(Gtk.STYLE_PROPERTY_FONT, Gtk.StateFlags.NORMAL)

		font = Pango.FontDescription(self.text_style['TextView']['font'])
		font.set_size(default_font.get_size())

		if font.equal(default_font):
			self.text_style['TextView']['font'] = None
			self.textview.modify_font(None)
		else:
			self.text_style['TextView']['font'] = font.to_string()
			self.textview.modify_font(font)

		self.text_style.write()


class InsertedObjectAnchor(Gtk.TextChildAnchor):

	def create_widget(self):
		raise NotImplementedError

	def dump(self, builder):
		raise NotImplementedError


class LineSeparatorAnchor(InsertedObjectAnchor):

	def create_widget(self):
		return LineSeparator()

	def dump(self, builder):
		builder.start(LINE)
		builder.data('-'*20) # FIXME: get rid of text here
		builder.end(LINE)


class TableAnchor(InsertedObjectAnchor):
	# HACK - table support is native in formats, but widget is still in plugin
	#        so we need to "glue" the table tokens to the plugin widget

	def __init__(self, objecttype, objectmodel):
		GObject.GObject.__init__(self)
		self.objecttype = objecttype
		self.objectmodel = objectmodel

	def create_widget(self):
		return self.objecttype.create_widget(self.objectmodel)

	def dump(self, builder):
		self.objecttype.dump(builder, self.objectmodel)


class PluginInsertedObjectAnchor(InsertedObjectAnchor):

	def __init__(self, objecttype, objectmodel):
		GObject.GObject.__init__(self)
		self.objecttype = objecttype
		self.objectmodel = objectmodel

	def create_widget(self):
		return self.objecttype.create_widget(self.objectmodel)

	def dump(self, builder):
		attrib, data = self.objecttype.data_from_model(self.objectmodel)
		builder.start(OBJECT, dict(attrib)) # dict() because ElementTree doesn't like ConfigDict
		if data is not None:
			builder.data(data)
		builder.end(OBJECT)


class InsertDateDialog(Dialog):
	'''Dialog to insert a date-time in the page'''

	FORMAT_COL = 0 # format string
	DATE_COL = 1 # strfime rendering of the format

	def __init__(self, parent, buffer, notebook, page):
		Dialog.__init__(
			self,
			parent,
			_('Insert Date and Time'), # T: Dialog title
			button=_('_Insert') # T: Button label
		)
		self.buffer = buffer
		self.notebook = notebook
		self.page = page
		self.date = datetime.now()

		self.uistate.setdefault('lastusedformat', '')
		self.uistate.setdefault('linkdate', False)
		self.uistate.setdefault('calendar_expanded', False)

		## Add format list box
		label = Gtk.Label()
		label.set_markup('<b>' + _("Format") + '</b>') # T: label in "insert date" dialog
		label.set_alignment(0.0, 0.5)
		self.vbox.pack_start(label, False, False, 0)

		model = Gtk.ListStore(str, str) # FORMAT_COL, DATE_COL
		self.view = BrowserTreeView(model)
		self.vbox.pack_start(ScrolledWindow(self.view), True, True, 0)

		cell_renderer = Gtk.CellRendererText()
		column = Gtk.TreeViewColumn('_date_', cell_renderer, text=1)
		self.view.append_column(column)
		self.view.set_headers_visible(False)
		self.view.connect('row-activated',
			lambda *a: self.response(Gtk.ResponseType.OK))

		## Add Calendar widget
		from zim.plugins.journal import Calendar # FIXME put this in zim.gui.widgets

		self.calendar_expander = Gtk.Expander.new_with_mnemonic('<b>' + _("_Calendar") + '</b>')
			# T: expander label in "insert date" dialog
		self.calendar_expander.set_use_markup(True)
		self.calendar_expander.set_expanded(self.uistate['calendar_expanded'])
		self.calendar = Calendar()
		self.calendar.set_display_options(
			Gtk.CalendarDisplayOptions.SHOW_HEADING |
			Gtk.CalendarDisplayOptions.SHOW_DAY_NAMES |
			Gtk.CalendarDisplayOptions.SHOW_WEEK_NUMBERS)
		self.calendar.connect('day-selected', lambda c: self.set_date(c.get_date()))
		self.calendar_expander.add(self.calendar)
		self.vbox.pack_start(self.calendar_expander, False, True, 0)

		## Add Link checkbox and Edit button
		self.linkbutton = Gtk.CheckButton.new_with_mnemonic(_('_Link to date'))
			# T: check box in InsertDate dialog
		self.linkbutton.set_active(self.uistate['linkdate'])
		self.vbox.pack_start(self.linkbutton, False, True, 0)

		button = Gtk.Button.new_with_mnemonic(_('_Edit')) # T: Button label
		button.connect('clicked', self.on_edit)
		self.action_area.add(button)
		self.action_area.reorder_child(button, 1)

		## Setup data
		self.load_file()
		self.set_date(self.date)

	def load_file(self):
		lastused = None
		model = self.view.get_model()
		model.clear()
		file = ConfigManager.get_config_file('dates.list')
		for line in file.readlines():
			line = line.strip()
			if not line or line.startswith('#'):
				continue
			try:
				format = line
				iter = model.append((format, format))
				if format == self.uistate['lastusedformat']:
					lastused = iter
			except:
				logger.exception('Could not parse date: %s', line)

		if len(model) == 0:
			# file not found ?
			model.append(("%c", "%c"))

		if not lastused is None:
			path = model.get_path(lastused)
			self.view.get_selection().select_path(path)

	def set_date(self, date):
		self.date = date

		def update_date(model, path, iter):
			format = model[iter][self.FORMAT_COL]
			try:
				string = datetime.strftime(format, date)
			except ValueError:
				string = 'INVALID: ' + format
			model[iter][self.DATE_COL] = string

		model = self.view.get_model()
		model.foreach(update_date)

		link = date.strftime('%Y-%m-%d') # YYYY-MM-DD
		self.link = self.notebook.suggest_link(self.page, link)
		self.linkbutton.set_sensitive(not self.link is None)

	#def run(self):
		#self.view.grab_focus()
		#Dialog.run(self)

	def save_uistate(self):
		model, iter = self.view.get_selection().get_selected()
		if iter:
			format = model[iter][self.FORMAT_COL]
			self.uistate['lastusedformat'] = format
		self.uistate['linkdate'] = self.linkbutton.get_active()
		self.uistate['calendar_expanded'] = self.calendar_expander.get_expanded()

	def on_edit(self, button):
		file = ConfigManager.get_config_file('dates.list') # XXX
		if edit_config_file(self, file):
			self.load_file()

	def do_response_ok(self):
		model, iter = self.view.get_selection().get_selected()
		if iter:
			text = model[iter][self.DATE_COL]
		else:
			text = model[0][self.DATE_COL]

		if self.link and self.linkbutton.get_active():
			self.buffer.insert_link_at_cursor(text, self.link.name)
		else:
			self.buffer.insert_at_cursor(text)

		return True


class InsertImageDialog(FileDialog):
	'''Dialog to insert an image in the page'''

	def __init__(self, parent, buffer, notebook, path, file=None):
		FileDialog.__init__(
			self, parent, _('Insert Image'), Gtk.FileChooserAction.OPEN)
			# T: Dialog title

		self.buffer = buffer
		self.notebook = notebook
		self.path = path

		self.uistate.setdefault('attach_inserted_images', False)
		self.uistate.setdefault('last_image_folder', None, check=str)

		self.add_shortcut(notebook, path)
		self.add_filter_images()

		checkbox = Gtk.CheckButton.new_with_mnemonic(_('Attach image first'))
			# T: checkbox in the "Insert Image" dialog
		checkbox.set_active(self.uistate['attach_inserted_images'])
		self.filechooser.set_extra_widget(checkbox)

		if file:
			self.set_file(file)
		else:
			self.load_last_folder()

	def do_response_ok(self):
		file = self.get_file()
		if file is None:
			return False

		if not GdkPixbuf.Pixbuf.get_file_info(file.path):
			ErrorDialog(self, _('File type not supported: %s' % file.get_mimetype())).run()
				# T: Error message when trying to insert a not supported file as image
			return False

		self.save_last_folder()

		# Similar code in AttachFileDialog
		checkbox = self.filechooser.get_extra_widget()
		self.uistate['attach_inserted_images'] = checkbox.get_active()
		if self.uistate['attach_inserted_images']:
			folder = self.notebook.get_attachments_dir(self.path)
			if not file.ischild(folder):
				file = attach_file(self, self.notebook, self.path, file)
				if file is None:
					return False # Cancelled overwrite dialog

		src = self.notebook.relative_filepath(file, self.path) or file.uri
		self.buffer.insert_image_at_cursor(file, src)
		return True


class AttachFileDialog(FileDialog):

	def __init__(self, parent, notebook, path, pageview=None):
		assert path, 'Need a page here'
		FileDialog.__init__(self, parent, _('Attach File'), multiple=True) # T: Dialog title
		self.notebook = notebook
		self.path = path
		self.pageview = pageview

		self.add_shortcut(notebook, path)
		self.load_last_folder()

		dir = notebook.get_attachments_dir(path)
		if dir is None:
			ErrorDialog(self, _('Page "%s" does not have a folder for attachments') % self.path)
				# T: Error dialog - %s is the full page name
			raise Exception('Page "%s" does not have a folder for attachments' % self.path)

		self.uistate.setdefault('insert_attached_images', True)
		checkbox = Gtk.CheckButton.new_with_mnemonic(_('Insert images as link'))
			# T: checkbox in the "Attach File" dialog
		checkbox.set_active(not self.uistate['insert_attached_images'])
		self.filechooser.set_extra_widget(checkbox)

	def do_response_ok(self):
		files = self.get_files()
		if not files:
			return False

		self.save_last_folder()

		# Similar code in zim.gui.pageview.InsertImageDialog
		checkbox = self.filechooser.get_extra_widget()
		self.uistate['insert_attached_images'] = not checkbox.get_active()


class EditImageDialog(Dialog):
	'''Dialog to edit properties of an embedded image'''

	def __init__(self, parent, buffer, notebook, path):
		Dialog.__init__(self, parent, _('Edit Image')) # T: Dialog title
		self.buffer = buffer
		self.notebook = notebook
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
		href = image_data.get('href', '')
		self.add_form([
			('file', 'image', _('Location')), # T: Input in 'edit image' dialog
			('href', 'link', _('Link to'), path), # T: Input in 'edit image' dialog
			('width', 'int', _('Width'), (0, 1)), # T: Input in 'edit image' dialog
			('height', 'int', _('Height'), (0, 1)) # T: Input in 'edit image' dialog
		],
			{'file': src, 'href': href}
			# range for width and height are set in set_ranges()
		)
		self.form.widgets['file'].set_use_relative_paths(notebook, path)
			# Show relative paths

		reset_button = Gtk.Button.new_with_mnemonic(_('_Reset Size'))
			# T: Button in 'edit image' dialog
		hbox = Gtk.HBox()
		hbox.pack_end(reset_button, False, True, 0)
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
			info, w, h = GdkPixbuf.Pixbuf.get_file_info(file.path)
			if w <= 0 or h <= 0:
				raise AssertionError
		except:
			logger.warn('Could not get size for image: %s', file.path)
			width.set_sensitive(False)
			height.set_sensitive(False)
		else:
			width.set_sensitive(True)
			height.set_sensitive(True)
			self._block = True
			width.set_range(0, 4 * w)
			width.set_value(w)
			height.set_range(0, 4 * w)
			height.set_value(h)
			self._block = False
			self._ratio = float(w) / h

	def do_width_changed(self):
		if self._block:
			return
		self._image_data.pop('height', None)
		self._image_data['width'] = int(self.form['width'])
		h = int(float(self._image_data['width']) / self._ratio)
		self._block = True
		self.form['height'] = h
		self._block = False

	def do_height_changed(self):
		if self._block:
			return
		self._image_data.pop('width', None)
		self._image_data['height'] = int(self.form['height'])
		w = int(self._ratio * float(self._image_data['height']))
		self._block = True
		self.form['width'] = w
		self._block = False

	def do_response_ok(self):
		file = self.form['file']
		attrib = self._image_data
		attrib['src'] = self.notebook.relative_filepath(file, self.path) or file.uri

		href = self.form['href']
		if href:
			type = link_type(href)
			if type == 'file':
				# Try making the path relative
				linkfile = self.form.widgets['href'].get_file()
				href = self.notebook.relative_filepath(linkfile, self.path) or linkfile.uri
			attrib['href'] = href

		iter = self.buffer.get_iter_at_offset(self._iter)
		bound = iter.copy()
		bound.forward_char()
		with self.buffer.user_action:
			self.buffer.delete(iter, bound)
			self.buffer.insert_image_at_cursor(file, **attrib)
		return True


class InsertTextFromFileDialog(FileDialog):
	'''Dialog to insert text from an external file into the page'''

	def __init__(self, parent, buffer, notebook, page):
		FileDialog.__init__(
			self, parent, _('Insert Text From File'), Gtk.FileChooserAction.OPEN)
			# T: Dialog title
		self.load_last_folder()
		self.add_shortcut(notebook, page)
		self.buffer = buffer

	def do_response_ok(self):
		file = self.get_file()
		if file is None:
			return False
		parser = get_format('plain').Parser()
		tree = parser.parse(file.readlines())
		self.buffer.insert_parsetree_at_cursor(tree)
		self.save_last_folder()
		return True


class InsertLinkDialog(Dialog):
	'''Dialog to insert a new link in the page or edit properties of
	an existing link
	'''

	def __init__(self, parent, pageview):
		self.pageview = pageview
		href, text = self._get_link_from_buffer()

		if href:
			title = _('Edit Link') # T: Dialog title
		else:
			title = _('Insert Link') # T: Dialog title

		Dialog.__init__(self, parent, title, button=_('_Link'))  # T: Dialog button

		self.add_form(
			[
				('href', 'link', _('Link to'), pageview.page), # T: Input in 'insert link' dialog
				('text', 'string', _('Text')) # T: Input in 'insert link' dialog
			], {
				'href': href,
				'text': text,
			},
			notebook=pageview.notebook
		)

		# Hook text entry to copy text from link when apropriate
		self.form.widgets['href'].connect('changed', self.on_href_changed)
		self.form.widgets['text'].connect('changed', self.on_text_changed)
		if self._selected_text or (text and text != href):
			self._copy_text = False
		else:
			self._copy_text = True

	def _get_link_from_buffer(self):
		# Get link and text from the text buffer
		href, text = '', ''

		buffer = self.pageview.textview.get_buffer()
		if buffer.get_has_selection():
			buffer.strip_selection()
			link = buffer.get_has_link_selection()
		else:
			link = buffer.select_link()
			if not link:
				self.pageview.autoselect()

		if buffer.get_has_selection():
			start, end = buffer.get_selection_bounds()
			text = start.get_text(end)
			self._selection_bounds = (start.get_offset(), end.get_offset())
				# Interaction in the dialog causes buffer to loose selection
				# maybe due to clipboard focus !??
				# Anyway, need to remember bounds ourselves.
			if link:
				href = link['href']
				self._selected_text = False
			else:
				href = text
				self._selected_text = True
		else:
			self._selection_bounds = None
			self._selected_text = False

		return href, text

	def on_href_changed(self, o):
		# Check if we can also update text
		if not self._copy_text:
			return

		self._copy_text = False # block on_text_changed()
		self.form['text'] = self.form['href']
		self._copy_text = True

	def on_text_changed(self, o):
		# Check if we should stop updating text
		if not self._copy_text:
			return

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
			notebook = self.pageview.notebook
			href = notebook.relative_filepath(file, page) or file.uri

		text = self.form['text'] or href

		buffer = self.pageview.textview.get_buffer()
		with buffer.user_action:
			if self._selection_bounds:
				start, end = list(map(
					buffer.get_iter_at_offset, self._selection_bounds))
				buffer.delete(start, end)
			buffer.insert_link_at_cursor(text, href)

		return True


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
		self.textview.grab_focus()

	def find_previous(self):
		buffer = self.textview.get_buffer()
		buffer.finder.find_previous()
		self.textview.scroll_to_mark(buffer.get_insert(), SCROLL_TO_MARK_MARGIN, False, 0, 0)
		self.textview.grab_focus()


class FindBar(FindWidget, Gtk.HBox):
	'''Bar to be shown below the TextView for find functions'''

	# TODO use smaller buttons ?

	def __init__(self, textview):
		GObject.GObject.__init__(self)
		self.set_spacing(5)
		FindWidget.__init__(self, textview)

		self.pack_start(Gtk.Label(_('Find') + ': '), False, True, 0)
			# T: label for input in find bar on bottom of page
		self.pack_start(self.find_entry, False, True, 0)
		self.pack_start(self.previous_button, False, True, 0)
		self.pack_start(self.next_button, False, True, 0)
		self.pack_start(self.case_option_checkbox, False, True, 0)
		self.pack_start(self.highlight_checkbox, False, True, 0)
		# TODO allow box to shrink further by putting buttons in menu

		close_button = IconButton(Gtk.STOCK_CLOSE, relief=False, size=Gtk.IconSize.MENU)
		close_button.connect_object('clicked', self.__class__.hide, self)
		self.pack_end(close_button, False, True, 0)

	def grab_focus(self):
		self.find_entry.grab_focus()

	def show(self):
		self.on_highlight_toggled()
		self.set_no_show_all(False)
		self.show_all()

	def hide(self):
		Gtk.HBox.hide(self)
		self.set_no_show_all(True)
		buffer = self.textview.get_buffer()
		buffer.finder.set_highlight(False)
		self.textview.grab_focus()

	def on_find_entry_activate(self):
		self.on_find_entry_changed()
		self.textview.grab_focus()

	def do_key_press_event(self, event):
		keyval = strip_boolean_result(event.get_keyval())
		if keyval == KEYVAL_ESC:
			self.hide()
			return True
		else:
			return Gtk.HBox.do_key_press_event(self, event)


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


class WordCountDialog(Dialog):
	'''Dialog showing line, word, and character counts'''

	def __init__(self, pageview):
		Dialog.__init__(self, pageview,
			_('Word Count'), buttons=Gtk.ButtonsType.CLOSE) # T: Dialog title
		self.set_resizable(False)

		def count(buffer, bounds):
			start, end = bounds
			lines = end.get_line() - start.get_line() + 1
			chars = end.get_offset() - start.get_offset()

			strings = start.get_text(end).strip().split()
			non_space_chars = sum(len(s) for s in strings)

			words = 0
			iter = start.copy()
			while iter.compare(end) < 0:
				if iter.forward_word_end():
					words += 1
				elif iter.compare(end) == 0:
					# When end is end of buffer forward_end_word returns False
					words += 1
					break
				else:
					break

			return lines, words, chars, non_space_chars

		buffer = pageview.textview.get_buffer()
		buffercount = count(buffer, buffer.get_bounds())
		insert = buffer.get_iter_at_mark(buffer.get_insert())
		start = buffer.get_iter_at_line(insert.get_line())
		end = start.copy()
		end.forward_line()
		paracount = count(buffer, (start, end))
		if buffer.get_has_selection():
			selectioncount = count(buffer, buffer.get_selection_bounds())
		else:
			selectioncount = (0, 0, 0, 0)

		table = Gtk.Table(3, 4)
		table.set_row_spacings(5)
		table.set_col_spacings(12)
		self.vbox.add(table)

		plabel = Gtk.Label(label=_('Page')) # T: label in word count dialog
		alabel = Gtk.Label(label=_('Paragraph')) # T: label in word count dialog
		slabel = Gtk.Label(label=_('Selection')) # T: label in word count dialog
		wlabel = Gtk.Label(label='<b>' + _('Words') + '</b>:') # T: label in word count dialog
		llabel = Gtk.Label(label='<b>' + _('Lines') + '</b>:') # T: label in word count dialog
		clabel = Gtk.Label(label='<b>' + _('Characters') + '</b>:') # T: label in word count dialog
		dlabel = Gtk.Label(label='<b>' + _('Characters excluding spaces') + '</b>:') # T: label in word count dialog

		for label in (wlabel, llabel, clabel, dlabel):
			label.set_use_markup(True)
			label.set_alignment(0.0, 0.5)

		# Heading
		table.attach(plabel, 1, 2, 0, 1)
		table.attach(alabel, 2, 3, 0, 1)
		table.attach(slabel, 3, 4, 0, 1)

		# Lines
		table.attach(llabel, 0, 1, 1, 2)
		table.attach(Gtk.Label(label=str(buffercount[0])), 1, 2, 1, 2)
		table.attach(Gtk.Label(label=str(paracount[0])), 2, 3, 1, 2)
		table.attach(Gtk.Label(label=str(selectioncount[0])), 3, 4, 1, 2)

		# Words
		table.attach(wlabel, 0, 1, 2, 3)
		table.attach(Gtk.Label(label=str(buffercount[1])), 1, 2, 2, 3)
		table.attach(Gtk.Label(label=str(paracount[1])), 2, 3, 2, 3)
		table.attach(Gtk.Label(label=str(selectioncount[1])), 3, 4, 2, 3)

		# Characters
		table.attach(clabel, 0, 1, 3, 4)
		table.attach(Gtk.Label(label=str(buffercount[2])), 1, 2, 3, 4)
		table.attach(Gtk.Label(label=str(paracount[2])), 2, 3, 3, 4)
		table.attach(Gtk.Label(label=str(selectioncount[2])), 3, 4, 3, 4)

		# Characters excluding spaces
		table.attach(dlabel, 0, 1, 4, 5)
		table.attach(Gtk.Label(label=str(buffercount[3])), 1, 2, 4, 5)
		table.attach(Gtk.Label(label=str(paracount[3])), 2, 3, 4, 5)
		table.attach(Gtk.Label(label=str(selectioncount[3])), 3, 4, 4, 5)


class MoveTextDialog(Dialog):

	def __init__(self, pageview, notebook, page, buffer, navigation):
		assert buffer.get_has_selection(), 'No Selection present'
		Dialog.__init__(
			self,
			pageview,
			_('Move Text to Other Page'), # T: Dialog title
			button=_('_Move')  # T: Button label
		)
		self.pageview = pageview
		self.notebook = notebook
		self.page = page
		self.buffer = buffer
		self.navigation = navigation
		self.text = self.pageview.get_selection(format='wiki')
		assert self.text # just to be sure
		start, end = buffer.get_selection_bounds()
		self.bounds = (start.get_offset(), end.get_offset())
			# Save selection bounds - can get lost later :S

		self.uistate.setdefault('link', True)
		self.uistate.setdefault('open_page', False)
		self.add_form([
			('page', 'page', _('Move text to'), page), # T: Input in 'move text' dialog
			('link', 'bool', _('Leave link to new page')), # T: Input in 'move text' dialog
			('open_page', 'bool', _('Open new page')), # T: Input in 'move text' dialog

		], self.uistate)

	def do_response_ok(self):
		newpage = self.form['page']
		if not newpage:
			return False

		try:
			newpage = self.notebook.get_page(newpage)
		except PageNotFoundError:
			return False

		# Copy text
		if newpage.exists():
			newpage.parse('wiki', self.text, append=True) # FIXME: probably should use parsetree here instead
			self.notebook.store_page(newpage)
		else:
			template = self.notebook.get_template(newpage)
			newpage.set_parsetree(template)
			newpage.parse('wiki', self.text) # FIXME: probably should use parsetree here instead
			self.notebook.store_page(newpage)

		# Delete text (after copy was successfulll..)
		bounds = list(map(self.buffer.get_iter_at_offset, self.bounds))
		self.buffer.delete(*bounds)

		# Insert Link
		self.uistate['link'] = self.form['link']
		if self.form['link']:
			href = self.form.widgets['page'].get_text() # TODO add method to Path "get_link" which gives rel path formatted correctly
			self.buffer.insert_link_at_cursor(href, href)

		# Show page
		self.uistate['open_page'] = self.form['open_page']
		if self.form['open_page']:
			self.navigation.open_page(newpage)

		return True


class NewFileDialog(Dialog):

	def __init__(self, parent, basename):
		Dialog.__init__(self, parent, _('New File')) # T: Dialog title
		self.add_form((
			('basename', 'string', _('Name')), # T: input for new file name
		), {
			'basename': basename
		})

	def show_all(self):
		Dialog.show_all(self)

		# Select only first part of name
		# TODO - make this a widget type in widgets.py
		text = self.form.widgets['basename'].get_text()
		if '.' in text:
			name, ext = text.split('.', 1)
			self.form.widgets['basename'].select_region(0, len(name))

	def do_response_ok(self):
		self.result = self.form['basename']
		return True
