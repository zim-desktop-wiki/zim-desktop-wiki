# Copyright 2008-2023 Jaap Karssenberg <jaap.karssenberg@gmail.com>


from gi.repository import Gdk


from zim.formats import \
	BULLET, CHECKED_BOX, UNCHECKED_BOX, XCHECKED_BOX, TRANSMIGRATED_BOX, \
	MIGRATED_BOX, LINE, OBJECT, HEADING, LISTITEM, BLOCK_LEVEL, FORMATTEDTEXT, \
	LINK, TAG, ANCHOR, EMPHASIS, STRONG, MARK, STRIKE, SUBSCRIPT, SUPERSCRIPT, IMAGE, \
	VERBATIM, VERBATIM_BLOCK, \
	BULLETLIST, NUMBEREDLIST, BLOCK

# Special character that acts as placeholder for images and objects
PIXBUF_CHR = '\uFFFC'

# Special character that acts as placeholder for images and objects
PIXBUF_CHR = '\uFFFC'


# Tag names used internally but not part of tokenlist for formats
HEADING_1, HEADING_2, HEADING_3, HEADING_4, HEADING_5, HEADING_6 = 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'
HEADING_1_to_6 = (HEADING_1, HEADING_2, HEADING_3, HEADING_4, HEADING_5, HEADING_6)
PAGE_LINK = 'page-link'


# Pixbuf types used internally
ICON = 'icon'


## Bullets and checkboxes

STOCK_CHECKED_BOX = 'zim-checked-box'
STOCK_UNCHECKED_BOX = 'zim-unchecked-box'
STOCK_XCHECKED_BOX = 'zim-xchecked-box'
STOCK_MIGRATED_BOX = 'zim-migrated-box'
STOCK_TRANSMIGRATED_BOX = 'zim-transmigrated-box'

BULLET_TYPES = {
	CHECKED_BOX: STOCK_CHECKED_BOX,
	UNCHECKED_BOX: STOCK_UNCHECKED_BOX,
	XCHECKED_BOX: STOCK_XCHECKED_BOX,
	MIGRATED_BOX: STOCK_MIGRATED_BOX,
	TRANSMIGRATED_BOX: STOCK_TRANSMIGRATED_BOX,
}

BULLETS_FROM_STOCK = {}
for _b in BULLET_TYPES:
	BULLETS_FROM_STOCK[BULLET_TYPES[_b]] = _b

AUTOFORMAT_BULLETS = {
	'*': BULLET,
	'[]': UNCHECKED_BOX,
	'[ ]': UNCHECKED_BOX,
	'[*]': CHECKED_BOX,
	'[x]': XCHECKED_BOX,
	'[>]': MIGRATED_BOX,
	'[<]': TRANSMIGRATED_BOX,
	'()': UNCHECKED_BOX,
	'( )': UNCHECKED_BOX,
	'(*)': CHECKED_BOX,
	'(x)': XCHECKED_BOX,
	'(>)': MIGRATED_BOX,
	'(<)': TRANSMIGRATED_BOX,
}

BULLETS = (BULLET, UNCHECKED_BOX, CHECKED_BOX, XCHECKED_BOX, MIGRATED_BOX, TRANSMIGRATED_BOX)
CHECKBOXES = (UNCHECKED_BOX, CHECKED_BOX, XCHECKED_BOX, MIGRATED_BOX, TRANSMIGRATED_BOX)

NUMBER_BULLET = '#.' # Special case for autonumbering

# Styles
INDENT_BLOCK_STYLE = 'indent'
BULLET_LIST_STYLE = 'bullet-list'
NUMBERED_LIST_STYLE = 'numbered-list'


## Keybindings

# Check the (undocumented) list of constants in Gtk.keysyms to see all names
KEYVALS_HOME = list(map(Gdk.keyval_from_name, ('Home', 'KP_Home')))
KEYVALS_ENTER = list(map(Gdk.keyval_from_name, ('Return', 'KP_Enter', 'ISO_Enter')))
KEYVALS_BACKSPACE = list(map(Gdk.keyval_from_name, ('BackSpace',)))
KEYVALS_TAB = list(map(Gdk.keyval_from_name, ('Tab', 'KP_Tab')))
KEYVALS_LEFT_TAB = list(map(Gdk.keyval_from_name, ('ISO_Left_Tab',)))

# ~ CHARS_END_OF_WORD = (' ', ')', '>', '.', '!', '?')
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

# Minimal distance from mark to window border after scroll_to_mark()
SCROLL_TO_MARK_MARGIN = 0.2
