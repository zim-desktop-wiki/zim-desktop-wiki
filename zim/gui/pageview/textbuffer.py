# Copyright 2008-2024 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from gi.repository import GObject
from gi.repository import GLib
from gi.repository import GdkPixbuf
from gi.repository import Pango
from gi.repository import Gtk

import re
import logging

from zim.signals import SignalHandler
from zim.config import Float, Boolean, Integer, String, ConfigDefinitionConstant
from zim.formats import get_dumper, heading_to_anchor, increase_list_iter, \
	ParseTree, BackwardParseTreeBuilderWithCleanup
from zim.newfs import LocalFile
from zim.config import String, Float, Integer, Boolean, \
	ConfigDefinitionConstant
from zim.parse.links import link_type
from zim.plugins import PluginManager
from zim.gui.base.images import image_file_load_pixels
from zim.gui.clipboard import textbuffer_register_serialize_formats
from zim.gui.insertedobjects import \
	UnknownInsertedObject, UnknownInsertedImageObject

from .constants import *
from .objectanchors import *
from .lists import TextBufferList
from .find import TextBufferFindMixin, FIND_HIGHLIGHT_TAG, FIND_MATCH_TAG


logger = logging.getLogger('zim.gui.pageview.textbuffer')


is_numbered_bullet_re = re.compile(r'^(\d+|\w|#)\.$')
	#: This regular expression is used to test whether a bullet belongs to a numbered list or not


# Base categories - these are not mutually exclusive
_is_zim_tag = lambda tag: hasattr(tag, 'zim_tag')

_line_based_tags = (BLOCK, LISTITEM, HEADING, VERBATIM_BLOCK)
_is_line_based_tag = lambda tag: hasattr(tag, 'zim_tag') and tag.zim_tag in _line_based_tags
_is_not_line_based_tag = lambda tag: hasattr(tag, 'zim_tag') and tag.zim_tag not in _line_based_tags
	# Line based tags are mutually exclusive and should cover the newline at the
	# end of the last line

_format_tags = ('h', 'pre', 'emphasis', 'strong', 'mark', 'strike', 'sub', 'sup', 'code')
_inline_format_tags = ('emphasis', 'strong', 'mark', 'strike', 'sub', 'sup', 'code')
_is_format_tag = lambda tag: hasattr(tag, 'zim_tag') and tag.zim_tag in _format_tags
_is_not_format_tag = lambda tag: hasattr(tag, 'zim_tag') and tag.zim_tag not in _format_tags
	# Format tags are tags that apply a formatting (like bold & italic), and do not
	# have additional semantics (like links and tags)
_is_inline_format_tag = lambda tag: hasattr(tag, 'zim_tag') and tag.zim_tag in _inline_format_tags
_is_not_inline_format_tag = lambda tag: hasattr(tag, 'zim_tag') and tag.zim_tag not in _inline_format_tags
	# Inline format tags are format tags that are not line based

_is_inline_nesting_tag = lambda tag: hasattr(tag, 'zim_tag') and tag.zim_tag in TextBuffer._nesting_style_tags or tag.zim_tag == LINK
_is_non_nesting_tag = lambda tag: hasattr(tag, 'zim_tag') and tag.zim_tag in ('pre', 'code', 'tag')
	# Nesting tags can have other formatting styles nested inside them
	# So they are specifically not mutually exclusive
	# Non-nesting tags are exclusive and also do not allow other tags to be combined

# Tests for specific tags
_is_indent_tag = lambda tag: hasattr(tag, 'zim_tag') and tag.zim_tag in (BLOCK, LISTITEM)
_is_not_indent_tag = lambda tag: hasattr(tag, 'zim_tag') and tag.zim_tag not in (BLOCK, LISTITEM)
_is_listitem_tag = lambda tag: hasattr(tag, 'zim_tag') and tag.zim_tag == LISTITEM 
_is_heading_tag = lambda tag: hasattr(tag, 'zim_tag') and tag.zim_tag == HEADING
_is_not_heading_tag = lambda tag: hasattr(tag, 'zim_tag') and tag.zim_tag != HEADING
_is_pre_tag = lambda tag: hasattr(tag, 'zim_tag') and tag.zim_tag == VERBATIM_BLOCK
_is_pre_or_code_tag = lambda tag: hasattr(tag, 'zim_tag') and tag.zim_tag in (VERBATIM, VERBATIM_BLOCK)
_is_link_tag = lambda tag: hasattr(tag, 'zim_tag') and tag.zim_tag == LINK
_is_not_link_tag = lambda tag: hasattr(tag, 'zim_tag') and tag.zim_tag != LINK
_is_tag_tag = lambda tag: hasattr(tag, 'zim_tag') and tag.zim_tag == TAG
_is_not_tag_tag = lambda tag: hasattr(tag, 'zim_tag') and tag.zim_tag != TAG
_is_link_tag_without_href = lambda tag: _is_link_tag(tag) and not tag.zim_attrib['href']


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


class TextBuffer(TextBufferFindMixin, Gtk.TextBuffer):
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
	additional attribute C{zim_tag} which gives the format type
	for this tag. All TextTags without this attribute are not ours.
	All TextTags that have a C{zim_tag} attribute also have an
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
	Again the ones that are handled by us have the extra C{zim_type} and
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

	@signal: C{begin-insert-tree (interactive)}:
	Emitted at the begin of a complex insert, c{interactive} is boolean flag
	@signal: C{end-insert-tree ()}:
	Emitted at the end of a complex insert
	@signal: C{textstyle-changed (style)}:
	Emitted when textstyle at the cursor changes, gets the list of text styles or None.
	@signal: C{link-clicked ()}:
	Emitted when a link is clicked; for example within a table cell
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
		'begin-insert-tree': (GObject.SignalFlags.RUN_LAST, None, (bool,)),
		'end-insert-tree': (GObject.SignalFlags.RUN_LAST, None, ()),
		'textstyle-changed': (GObject.SignalFlags.RUN_LAST, None, (object,)),
		'undo-save-cursor': (GObject.SignalFlags.RUN_LAST, None, (object,)),
		'insert-objectanchor': (GObject.SignalFlags.RUN_LAST, None, (object,)),
		'link-clicked': (GObject.SignalFlags.RUN_LAST, None, (object,)),
	}

	# style attributes
	pixels_indent = 30 #: pixels indent for a single indent level
	bullet_icon_size = Gtk.IconSize.MENU #: constant for icon size of checkboxes etc.

	#: text styles supported by the editor
	tag_styles = {
		HEADING_1: {'weight': Pango.Weight.BOLD, 'scale': 1.15**4},
		HEADING_2: {'weight': Pango.Weight.BOLD, 'scale': 1.15**3},
		HEADING_3: {'weight': Pango.Weight.BOLD, 'scale': 1.15**2},
		HEADING_4: {'weight': Pango.Weight.ULTRABOLD, 'scale': 1.15},
		HEADING_5: {'weight': Pango.Weight.BOLD, 'scale': 1.15, 'style': Pango.Style.ITALIC},
		HEADING_6: {'weight': Pango.Weight.BOLD, 'scale': 1.15},
		EMPHASIS:  {'style': Pango.Style.ITALIC},
		STRONG:    {'weight': Pango.Weight.BOLD},
		MARK:      {'background': 'yellow'},
		STRIKE:    {'strikethrough': True, 'foreground': 'grey'},
		VERBATIM:  {'family': 'monospace'},
		VERBATIM_BLOCK: {'family': 'monospace', 'wrap-mode': Gtk.WrapMode.NONE},
		SUBSCRIPT:       {'rise': -3500, 'scale': 0.7},
		SUPERSCRIPT:       {'rise': 7500, 'scale': 0.7},
		LINK:      {'foreground': 'blue'},
		PAGE_LINK: {'foreground': 'blue'},
		TAG:       {'foreground': '#ce5c00'},
		INDENT_BLOCK_STYLE: {},
		BULLET_LIST_STYLE: {},
		NUMBERED_LIST_STYLE: {},
		UNCHECKED_BOX: {},
		CHECKED_BOX: {},
		XCHECKED_BOX: {},
		MIGRATED_BOX: {},
		TRANSMIGRATED_BOX: {},
		FIND_HIGHLIGHT_TAG: {'background': 'magenta', 'foreground': 'white'},
		FIND_MATCH_TAG: {'background': '#38d878', 'foreground': 'white'}
	}

	#: tags that can be mapped to named TextTags
	_static_style_tags = \
		HEADING_1_to_6 + (
		EMPHASIS, STRONG, MARK, STRIKE, SUBSCRIPT, SUPERSCRIPT,
		VERBATIM_BLOCK, VERBATIM
	)   # The order here determines order of nesting, and order of formatting
		# Indent-tags will be inserted before headings
		# Link-tags and tag-tags will be inserted before "pre" and "code"
		# search for "set_priority()" and "get_priority()" to see impact
	_static_tag_before_links = SUPERSCRIPT # link will be inserted with this prio +1
	_static_tag_after_tags = VERBATIM_BLOCK # link will be inserted with this prio

	#: tags that can nest in any order
	_nesting_style_tags = (
		'emphasis', 'strong', 'mark', 'strike', 'sub', 'sup',
	)

	tag_attributes = {
		'weight': ConfigDefinitionConstant(None, Pango.Weight, 'PANGO_WEIGHT'),
		'scale': Float(None),
		'style': ConfigDefinitionConstant(None, Pango.Style, 'PANGO_STYLE'),
		'background': String(None),
		'paragraph-background': String(None),
		'foreground': String(None),
		'strikethrough': Boolean(None),
		'font': String(None),
		'family': String(None),
		'wrap-mode': ConfigDefinitionConstant(None, Gtk.WrapMode, 'GTK_WRAP'),
		'indent': Integer(None),
		'underline': ConfigDefinitionConstant(None, Pango.Underline, 'PANGO_UNDERLINE'),
		'linespacing': Integer(None),
		'wrapped-lines-linespacing': Integer(None),
		'rise': Integer(None),
	} #: Valid properties for a style in tag_styles

	def __init__(self, notebook, page, parsetree=None):
		'''Constructor

		@param notebook: a L{Notebook} object
		@param page: a L{Page} object
		@param parsetree: optional L{ParseTree} object, if given this will
		initialize the buffer content *before* initializing the undostack
		'''
		GObject.GObject.__init__(self)
		TextBufferFindMixin.__init__(self)
		self.notebook = notebook
		self.page = page
		self._insert_tree_in_progress = False
		self._deleted_editmode_mark = None
		self._deleted_line_end = False
		self._check_renumber = []
		self._renumbering = False
		self.user_action = UserActionContext(self)
		self.showing_template = False

		for name in self._static_style_tags:
			tag = self.create_tag('style-' + name, **self.tag_styles[name])
			if name in HEADING_1_to_6:
				# This is needed to get proper output in get_parse_tree
				tag.zim_tag = HEADING
				tag.zim_attrib = {'level': int(name[1])}
			else:
				tag.zim_tag = name
				tag.zim_attrib = None

		self._editmode_tags = []

		textbuffer_register_serialize_formats(self, notebook, page)

		self.connect('delete-range', self.do_pre_delete_range)
		self.connect_after('delete-range', self.do_post_delete_range)

		if parsetree is not None:
			# Do this *before* initializing the undostack
			self.set_parsetree(parsetree)
			self.set_modified(False)

		from .undostack import UndoStackManager # prevent circular import
		self.undostack = UndoStackManager(self)

	#~ def do_begin_user_action(self):
		#~ print('>>>> USER ACTION')
		#~ pass

	@property
	def hascontent(self):
		if self.showing_template:
			return False
		else:
			start, end = self.get_bounds()
			return not start.equal(end)

	def do_end_user_action(self):
		#print('<<<< USER ACTION')
		if self._deleted_editmode_mark is not None:
			self.delete_mark(self._deleted_editmode_mark)
			self._deleted_editmode_mark = None

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
		self.delete(*self.get_bounds())
		if self._deleted_editmode_mark is not None:
			self.delete_mark(self._deleted_editmode_mark)
			self._deleted_editmode_mark = None
		self._editmode_tags = []

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

	def set_parsetree(self, tree, showing_template=False):
		'''Load a new L{ParseTree} in the buffer

		This method replaces any content in the buffer with the new
		parser tree.

		@param tree: a L{ParseTree} object
		@param showing_template: if C{True} the C{tree} represents a template
		and not actual page content (yet)
		'''
		with self.user_action:
			self.clear()
			self.insert_parsetree_at_cursor(tree)

		self.showing_template = showing_template # Set after modifying!

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

	def append_parsetree(self, tree, interactive=False):
		'''Append a L{ParseTree} to the buffer

		Like L{insert_parsetree()} but inserts at the end of the current buffer.
		'''
		self.insert_parsetree(self.get_end_iter(), tree, interactive)

	def insert_parsetree_at_cursor(self, tree, interactive=False):
		'''Insert a L{ParseTree} in the buffer

		Like L{insert_parsetree()} but inserts at the current cursor
		position.

		@param tree: a L{ParseTree} object
		@param interactive: Boolean which determines how current state
		in the buffer is handled.
		'''
		#print('INSERT AT CURSOR', tree.tostring())

		# Check tree
		root = tree._etree.getroot() # HACK - switch to new interface !
		assert root.tag == 'zim-tree'

		# Check if we are at a bullet or checkbox line
		iter = self.get_iter_at_mark(self.get_insert())
		if iter.starts_line() and not tree.get_ends_with_newline():
			bullet = self._get_bullet_at_iter(iter)
			if bullet:
				self._iter_forward_past_bullet(iter, bullet)
				self.place_cursor(iter)

		# Prepare
		startoffset = iter.get_offset()
		indent_offset = 0
		if interactive:
			if iter.starts_line() and any(_is_indent_tag(t) for t in self._editmode_tags):
				# Special case - risk of being overwritten in tree insert
				# TODO: need to think through how to map the whole tree to indent
				#       or at least the elements that allow it and break at first
				#       element that does not allow it
				indent_offset = self.get_indent(iter.get_line())
		else:
			self._editmode_tags = []
		tree.decode_urls()

		if self._deleted_editmode_mark is not None:
			self.delete_mark(self._deleted_editmode_mark)
			self._deleted_editmode_mark = None

		# Actual insert
		modified = self.get_modified()
		try:
			self.emit('begin-insert-tree', interactive)
			if root.text:
				self.insert_at_cursor(root.text)
			self._insert_element_children(root, indent_offset=indent_offset)

			# Fix partial tree inserts
			startiter = self.get_iter_at_offset(startoffset)
			if not startiter.starts_line():
				self._do_lines_merged(startiter)

			enditer = self.get_iter_at_mark(self.get_insert())
			if not enditer.starts_line():
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

	def do_begin_insert_tree(self, interactive):
		self._insert_tree_in_progress = True

	def do_end_insert_tree(self):
		self._insert_tree_in_progress = False
		self.emit('textstyle-changed', self.get_format_tags_by_name())

	# emitting textstyle-changed is skipped while loading the tree

	def _insert_element_children(self, node, list_level=-1, list_type=None, list_start='0', textstyles=[], indent_offset=0):
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
				return  # Nothing more to do

			iter = self.get_insert_iter()
			if not iter.starts_line():
				# Check existing indent - may have bullet type while we have not
				tags = list(filter(_is_indent_tag, self.iter_get_zim_tags(iter)))
				if len(tags) > 1:
					logger.warning('BUG: overlapping indent tags')
				if tags and int(tags[0].zim_attrib['indent']) == level:
					self._editmode_tags.append(tags[0])
					return  # Re-use tag

			tag = self._get_indent_tag(level, bullet)
				# We don't set the LTR / RTL direction here
				# instead we update all indent tags after the full
				# insert is done.
			self._editmode_tags.append(tag)

		def force_line_start():
			# Inserts a newline if we are not at the beginning of a line
			# makes pasting a tree halfway in a line more sane
			iter = self.get_iter_at_mark(self.get_insert())
			if not iter.starts_line():
				self.insert_at_cursor('\n')

		for element in iter(node):
			with self.user_action: # For test case only ...
				if element.tag in ('p', 'div'):
					# No force line start here on purpose
					if 'indent' in element.attrib:
						set_indent(int(element.attrib['indent']) + indent_offset)
					elif indent_offset:
						set_indent(indent_offset)
					else:
						set_indent(None)

					if element.text:
						self.insert_at_cursor(element.text)

					self._insert_element_children(element, list_level=list_level, textstyles=textstyles)  # recurs

					set_indent(None)
				elif element.tag in ('ul', 'ol'):
					start = element.attrib.get('start')
					if 'indent' in element.attrib:
						level = int(element.attrib['indent']) + indent_offset
					else:
						level = list_level + 1
					self._insert_element_children(element, list_level=level, list_type=element.tag, list_start=start,
												textstyles=textstyles)  # recurs
					set_indent(None)
				elif element.tag == 'li':
					force_line_start()

					if 'indent' in element.attrib:
						list_level = int(element.attrib['indent'])
					elif list_level < 0:
						list_level = 0 # We skipped the <ul> ?

					if list_type == 'ol':
						bullet = list_iter + '.'
						list_iter = increase_list_iter(list_iter)
					elif 'bullet' in element.attrib and element.attrib['bullet'] != '*':
						bullet = element.attrib['bullet']
					else:
						bullet = BULLET # default to '*'

					set_indent(list_level, bullet)
					self._insert_bullet_at_cursor(bullet)
					self.insert_at_cursor(' ')

					if element.text:
						self.insert_at_cursor(element.text)

					self._insert_element_children(element, list_level=list_level, textstyles=textstyles)  # recurs
					set_indent(None)

				elif element.tag == 'link':
					self._set_textstyles(textstyles)  # reset Needed for interactive insert tree after paste
					tag = self._create_link_tag('', **element.attrib)
					self._editmode_tags = list(filter(_is_not_link_tag, self._editmode_tags)) + [tag]
					linkstartpos = self.get_insert_iter().get_offset()
					if element.text:
						self.insert_at_cursor(element.text)
					self._insert_element_children(element, list_level=list_level,
												textstyles=textstyles)  # recurs
					linkstart = self.get_iter_at_offset(linkstartpos)
					text = linkstart.get_text(self.get_insert_iter())
					if element.attrib['href'] and text != element.attrib['href']:
						# same logic in _create_link_tag, but need to check text after all child elements inserted
						tag.zim_attrib['href'] = element.attrib['href']
					else:
						tag.zim_attrib['href'] = None
					self._editmode_tags.pop()
				elif element.tag == 'tag':
					self._set_textstyles(textstyles)  # reset Needed for interactive insert tree after paste
					self.insert_tag_at_cursor(element.text, **element.attrib)
				elif element.tag == 'anchor':
					self._set_textstyles(textstyles)
					self.insert_anchor_at_cursor(element.attrib['name'])
				elif element.tag == 'img':
					self.insert_image_at_cursor(None, **element.attrib)
				elif element.tag == 'pre':
					if 'indent' in element.attrib:
						set_indent(int(element.attrib['indent']))
					self._set_textstyles([element.tag])
					if element.text:
						self.insert_at_cursor(element.text)
					self._set_textstyles(None)
					set_indent(None)
				elif element.tag == 'table':
					force_line_start()
					if 'indent' in element.attrib:
						set_indent(int(element.attrib['indent']))
					self._insert_table_element_at_cursor(element)
					set_indent(None)
				elif element.tag == 'line':
					anchor = LineSeparatorAnchor()
					self.insert_objectanchor_at_cursor(anchor)
					self.insert_at_cursor('\n')
				elif element.tag == 'object':
					if 'indent' in element.attrib:
						force_line_start()
						set_indent(int(element.attrib['indent']))
						self.insert_object_at_cursor(element.attrib, element.text)
						set_indent(None)
					else:
						self.insert_object_at_cursor(element.attrib, element.text)
				else:
					# Text styles
					if element.tag == 'h':
						force_line_start()
						tag = 'h' + str(element.attrib['level'])
						self._set_textstyles([tag])
						if element.text:
							self.insert_at_cursor(element.text)
						self._insert_element_children(element, list_level=list_level,
													textstyles=[tag])  # recurs
					elif element.tag in self._static_style_tags:
						self._set_textstyles(textstyles + [element.tag])
						if element.text:
							self.insert_at_cursor(element.text)
						self._insert_element_children(element, list_level=list_level,
													textstyles=textstyles + [element.tag])  # recurs
					elif element.tag == '_ignore_':
						if element.text:
							self.insert_at_cursor(element.text)
						self._insert_element_children(element, list_level=list_level, textstyles=textstyles)  # recurs
					else:
						logger.debug("Unknown tag : %s, %s, %s", element.tag,
									element.attrib, element.text)
						assert False, 'Unknown tag: %s' % element.tag

					self._set_textstyles(textstyles)

				if element.tail:
					self.insert_at_cursor(element.tail)

	def _set_textstyles(self, names):
		# TODO: fully factor out this method
		self._editmode_tags = list(filter(_is_not_format_tag, self._editmode_tags))  # remove all text styles first

		if names:
			for name in names:
				tag = self.get_tag_table().lookup('style-' + name)
				if _is_heading_tag(tag):
					self._editmode_tags = \
						list(filter(_is_not_indent_tag, self._editmode_tags))
				self._editmode_tags.append(tag)

	#region Links

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
		if self._deleted_editmode_mark is not None:
			self.delete_mark(self._deleted_editmode_mark)
			self._deleted_editmode_mark = None

		tag = self._create_link_tag(text, href, **attrib)
		self._editmode_tags = list(filter(_is_not_link_tag, self._editmode_tags)) + [tag]
		self.insert_at_cursor(text)
		self._editmode_tags = self._editmode_tags[:-1]

	def _create_link_tag(self, text, href, **attrib):
		'''Creates an anonymouse TextTag for a link'''
		# These are created after __init__, so higher priority for Formatting
		# properties than any of the _static_style_tags
		if hasattr(href, 'uri'):
			href = href.uri
		assert isinstance(href, str) or href is None
		link_style = PAGE_LINK if (link_type(href or '') == 'page') else LINK
		tag = self.create_tag(None, **self.tag_styles[link_style])
		tag.zim_tag = LINK
		tag.zim_attrib = attrib
		if href == text or not href or href.isspace():
			tag.zim_attrib['href'] = None
		else:
			tag.zim_attrib['href'] = href

		prio_tag = self.get_tag_table().lookup('style-' + self._static_tag_before_links)
		tag.set_priority(prio_tag.get_priority()+1)

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
		for tag in sorted(iter.get_tags(), key=lambda i: i.get_priority()):
			if hasattr(tag, 'zim_tag') and tag.zim_tag == LINK:
				return tag
		else:
			return None

	def get_link_text(self, iter):
		tag = self.get_link_tag(iter)
		return self.get_tag_text(iter, tag) if tag else None

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
				link['href'] = start.get_text(end).strip()
					# assume starting or trailing whitespace is an editing artefact
			return link
		else:
			return None

	#endregion

	#region TextTags

	def get_tag(self, iter, type):
		'''Get the C{Gtk.TextTag} for a zim type at a specific position, if any

		@param iter: a C{Gtk.TextIter}
		@param type: the zim type to look for ('style', 'link', 'tag', 'indent', 'anchor')
		@returns: a C{Gtk.TextTag} if there is a tag at C{iter},
		C{None} otherwise
		'''
		for tag in iter.get_tags():
			if hasattr(tag, 'zim_tag') and tag.zim_tag == type:
				return tag
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

	def get_tag_text(self, iter, tag):
		start, end = self.get_tag_bounds(iter, tag)
		return start.get_text(end)

	#endregion

	#region Tags

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
		if self._deleted_editmode_mark is not None:
			self.delete_mark(self._deleted_editmode_mark)
			self._deleted_editmode_mark = None

		tag = self._create_tag_tag(text, **attrib)
		self._editmode_tags = \
			[t for t in self._editmode_tags if not _is_non_nesting_tag(t)] + [tag]
		self.insert_at_cursor(text)
		self._editmode_tags = self._editmode_tags[:-1]

	def _create_tag_tag(self, text, **attrib):
		'''Creates an anonymous TextTag for a tag'''
		# These are created after __init__, so higher priority for Formatting
		# properties than any of the _static_style_tags
		tag = self.create_tag(None, **self.tag_styles['tag'])
		tag.zim_tag = TAG
		tag.zim_attrib = attrib
		tag.zim_attrib['name'] = None

		prio_tag = self.get_tag_table().lookup('style-' + self._static_tag_after_tags)
		tag.set_priority(prio_tag.get_priority())

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
			if hasattr(tag, 'zim_tag') and tag.zim_tag == TAG:
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

	#endregion

	#region Anchors

	def insert_anchor(self, iter, name, **attrib):
		'''Insert a "link anchor" with id C{name} at C{iter}'''
		widget = Gtk.HBox() # Need *some* widget here...
		pixbuf = widget.render_icon('zim-pilcrow', self.bullet_icon_size)
		pixbuf.zim_type = ANCHOR
		pixbuf.zim_attrib = attrib
		pixbuf.zim_attrib['name'] = name
		self.insert_pixbuf(iter, pixbuf)

	def insert_anchor_at_cursor(self, name):
		'''Insert a "link anchor" with id C{name}'''
		iter = self.get_iter_at_mark(self.get_insert())
		self.insert_anchor(iter, name)

	def get_anchor_data(self, iter):
		pixbuf = iter.get_pixbuf()
		if pixbuf and hasattr(pixbuf, 'zim_type') and pixbuf.zim_type == ANCHOR:
			return pixbuf.zim_attrib.copy()
		else:
			return None

	def get_anchor_or_object_id(self, iter):
		# anchor or image
		pixbuf = iter.get_pixbuf()
		if pixbuf and hasattr(pixbuf, 'zim_type') and pixbuf.zim_type == ANCHOR:
			return pixbuf.zim_attrib.get('name', None)
		elif pixbuf and hasattr(pixbuf, 'zim_type') and pixbuf.zim_type == IMAGE:
			return pixbuf.zim_attrib.get('id', None)

		# object?
		anchor = iter.get_child_anchor()
		if anchor and isinstance(anchor, PluginInsertedObjectAnchor):
			object_type = anchor.objecttype
			object_model = anchor.objectmodel
			attrib, _ = object_type.data_from_model(object_model)
			return attrib.get('id', None)

	def iter_anchors_for_range(self, start, end):
		iter = start.copy()
		match = iter.forward_search(PIXBUF_CHR, 0, limit=end)
		while match:
			iter, mend = match
			name = self.get_anchor_or_object_id(iter)
			if name:
				yield (iter.copy(), name)
			match = mend.forward_search(PIXBUF_CHR, 0, limit=end)

	def get_anchor_for_location(self, iter):
		'''Returns an anchor name that refers to C{iter} or the same line
		Uses C{iter} to return id of explicit anchor on the same line closest
		to C{iter}. If no explicit anchor is found and C{iter} is within a heading
		line, the implicit anchor for the heading is returned.
		@param iter: the location to refer to
		@returns: an anchor name if any anchor object or heading is found, else C{None}
		'''
		return self.get_anchor_or_object_id(iter) \
			or self._get_close_anchor_or_object_id(iter) \
				or self._get_implict_anchor_if_heading(iter)

	def _get_close_anchor_or_object_id(self, iter):
		line_start = iter.copy() if iter.starts_line() else self.get_iter_at_line(iter.get_line())
		line_end = line_start.copy()
		line_end.forward_line()
		line_offset = iter.get_line_offset()
		anchors = [
			(abs(myiter.get_line_offset() - line_offset), name)
				for myiter, name in self.iter_anchors_for_range(line_start, line_end)
		]
		if anchors:
			anchors.sort()
			return anchors[0][1]
		else:
			return None

	def _get_implict_anchor_if_heading(self, iter):
		i, text = self.get_heading(iter.get_line())
		return heading_to_anchor(text) if text else None

	def get_heading(self, line: int) -> (int, str):
		'''Returns the heading level and text or C{(None, None)}'''
		line_start = self.get_iter_at_line(line)
		heading_tags = list(filter(_is_heading_tag, line_start.get_tags()))
		if not heading_tags:
			return None, None

		level = int(heading_tags[0].zim_attrib['level'])

		line_end = line_start.copy()
		line_end.forward_line()
		text = line_start.get_text(line_end).strip()
		return level, text

	#endregion

	#region Images

	def insert_image(self, iter, file, src, **attrib):
		'''Insert an image in the buffer

		@param iter: a C{Gtk.TextIter} for the insert position
		@param file: a L{File} object or a absolute file path or URI,
		if C{None} the file will be resolved based on C{src} relative to the
		notebook and page
		@param src: the file path the show to the user

		If the image is e.g. specified in the page source as a relative
		link, C{file} should give the absolute path the link resolves
		to, while C{src} gives the relative path.

		@param attrib: any other image properties
		'''
		try:
			if file is None:
				file = self.notebook.resolve_file(src, self.page)
			elif isinstance(file, str):
				file = LocalFile(file)

			pixbuf = image_file_load_pixels(file, int(attrib.get('width', -1)), int(attrib.get('height', -1)))
		except:
			#~ logger.exception('Could not load image: %s', file)
			logger.warning('No such image: %s', file)
			widget = Gtk.HBox() # Need *some* widget here...
			pixbuf = widget.render_icon(Gtk.STOCK_MISSING_IMAGE, Gtk.IconSize.DIALOG)
			pixbuf = pixbuf.copy() # need unique instance to set zim_attrib

		pixbuf.zim_type = IMAGE
		pixbuf.zim_attrib = attrib
		pixbuf.zim_attrib['src'] = src
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
		if pixbuf and hasattr(pixbuf, 'zim_type') and pixbuf.zim_type == IMAGE:
			return pixbuf.zim_attrib.copy()
		else:
			return None

	#endregion

	#region Objects

	def insert_object_at_cursor(self, attrib, data):
		'''Inserts a custom object in the page
		@param attrib: dict with object attributes
		@param data: string data of object
		'''
		objecttype, model = self._get_objecttype_and_model_for_object(attrib, data)
		self.insert_object_model_at_cursor(objecttype, model)

	def _get_objecttype_and_model_for_object(self, attrib, data):
		try:
			objecttype = PluginManager.insertedobjects[attrib['type']]
		except KeyError:
			if attrib['type'].startswith('image+'):
				# Fallback for backward compatibility of image generators < zim 0.70
				objecttype = UnknownInsertedImageObject()
			else:
				objecttype = UnknownInsertedObject()

		model = objecttype.model_from_data(self.notebook, self.page, attrib, data)
		return objecttype, model

	def insert_object_model_at_cursor(self, objecttype, model):
		if objecttype.is_inline:
			self._insert_object_model_at_cursor(objecttype, model)
		else:
			if not self.get_insert_iter().starts_line():
				self.insert_at_cursor('\n')
			self._insert_object_model_at_cursor(objecttype, model)
			self.insert_at_cursor('\n')

	def _insert_object_model_at_cursor(self, objecttype, model):
		from zim.plugins.tableeditor import TableViewObjectType # XXX

		model.connect('changed', lambda o: self.set_modified(True))

		if isinstance(objecttype, TableViewObjectType):
			anchor = TableAnchor(objecttype, model)
		else:
			anchor = PluginInsertedObjectAnchor(objecttype, model)

		self.insert_objectanchor_at_cursor(anchor)

	def _insert_table_element_at_cursor(self, element):
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
			self.insert_at_cursor('\n')

	def insert_objectanchor_at_cursor(self, anchor):
		iter = self.get_insert_iter()
		self.insert_objectanchor(iter, anchor)

	def insert_objectanchor(self, iter, anchor):
		self.insert_child_anchor(iter, anchor)
		self.emit('insert-objectanchor', anchor)

	def get_objectanchor_at_cursor(self):
		iter = self.get_insert_iter()
		return self.get_objectanchor(iter)

	def get_objectanchor(self, iter):
		anchor = iter.get_child_anchor()
		if anchor and isinstance(anchor, InsertedObjectAnchor):
			return anchor
		else:
			return None

	def list_objectanchors(self):
		start, end = self.get_bounds()
		match = start.forward_search(PIXBUF_CHR, 0)
		while match:
			start, end = match
			anchor = start.get_child_anchor()
			if anchor and isinstance(anchor, InsertedObjectAnchor):
				yield start, anchor
			match = end.forward_search(PIXBUF_CHR, 0)

	#endregion

	#region Bullets

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
			TRANSMIGRATED_BOX
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
		with self.user_action:
			with self.tmp_cursor(gravity=GRAVITY_RIGHT):
				iter = self.get_iter_at_line(line)
				bound = iter.copy()
				self.iter_forward_past_bullet(bound)
				with self.do_pre_delete_range.blocked():
					with self.do_post_delete_range.blocked():
						self.delete(iter, bound)

				if not bullet is None:
					iter = self.get_iter_at_line(line)
					self.place_cursor(iter) # update editmode

					insert = self.get_insert_iter()
					assert insert.starts_line(), 'BUG: bullet not at line start'

					# Turning into list item removes heading
					end = insert.copy()
					end.forward_line()
					self.smart_remove_tags(_is_heading_tag, insert, end)

					# TODO: convert 'pre' to 'code' ?

					# Temporary clear non indent tags during insert
					orig_editmode_tags = self._editmode_tags
					self._editmode_tags = list(filter(_is_indent_tag, self._editmode_tags))

					# Actual bullet insert
					self._insert_bullet_at_cursor(bullet)
					self.insert_at_cursor(' ')
					self._editmode_tags = orig_editmode_tags

			self._set_indent(line, indent, bullet)

	def _insert_bullet_at_cursor(self, bullet):
		'''Low level insert bullet

		External interface should use `set_bullet(line, bullet)` 
		instead of calling this method directly.
		'''
		insert = self.get_insert_iter()
		assert insert.starts_line(), 'BUG: bullet not at line start'

		assert bullet in BULLETS or is_numbered_bullet_re.match(bullet), 'Bullet: >>%s<<' % bullet
		if self._deleted_editmode_mark is not None:
			self.delete_mark(self._deleted_editmode_mark)
			self._deleted_editmode_mark = None

		if bullet == BULLET:
			self.insert_at_cursor('\u2022')
		elif bullet in BULLET_TYPES:
			# Insert icon
			stock = BULLET_TYPES[bullet]
			widget = Gtk.HBox() # Need *some* widget here...
			pixbuf = widget.render_icon(stock, self.bullet_icon_size)
			if pixbuf is None:
				logger.warning('Could not find icon: %s', stock)
				pixbuf = widget.render_icon(Gtk.STOCK_MISSING_IMAGE, self.bullet_icon_size)
			pixbuf.zim_type = ICON
			pixbuf.zim_attrib = {'stock': stock}
			self.insert_pixbuf(self.get_insert_iter(), pixbuf)
		else:
			# Numbered
			self.insert_at_cursor(bullet)

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

	#endregion

	def get_format_tags_by_name(self):
		'''Get the names of the formatting styles that will be applied
		to newly inserted text

		This may change as soon as the cursor position changes,
		so only relevant for current cursor position.
		'''
		tags = list(filter(_is_format_tag, self._editmode_tags))
		return [tag.get_property('name')[6:] for tag in tags]  # len('style-') == 6

	def get_editmode(self):
		return self._editmode_tags[:] # copy to prevent modification

	def set_editmode(self, tags):
		if self._deleted_editmode_mark is not None:
			self.delete_mark(self._deleted_editmode_mark)
			self._deleted_editmode_mark = None

		if not tags == self._editmode_tags:
			#print('> %r' % [(t.zim_tag, t.get_property('name')) for t in tags])
			self._editmode_tags = tags
			self.emit('textstyle-changed', self.get_format_tags_by_name())

	def filter_editmode(self, tag_filter):
		self.set_editmode(list(filter(tag_filter, self._editmode_tags)))

	def update_editmode(self):
		'''Updates the text style and indenting applied to newly indented
		text based on the current cursor position

		This method is triggered automatically when the cursor is moved,
		but there are some cases where you may need to call it manually
		to force a consistent state.
		'''
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
			#print('> %r' % [(t.zim_tag, t.get_property('name')) for t in tags])
			self._editmode_tags = tags
			self.emit('textstyle-changed', self.get_format_tags_by_name())

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

		This method is for example used by L{update_editmode()} to
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
		tags = [t for t in filter(_is_zim_tag, iter.get_tags()) if not t in start_tags]
		end_tags = list(filter(_is_zim_tag, iter.get_toggled_tags(False)))
		# So now we have 3 separate sets with tags ending here,
		# starting here and being continuous here. Result will be
		# continuous tags and ending tags but logic for line based
		# tags can mix in tags starting here and filter out
		# tags ending here.

		if iter.starts_line():
			# Special case because line based tags include the newline that
			# ends the line, but should not automatically continue
			tags += list(filter(_is_line_based_tag, start_tags))
			tags += list(filter(_is_not_line_based_tag, end_tags))
		else:
			# By default only take tags from the left
			tags += end_tags

		tags.sort(key=lambda tag: tag.get_priority())
		return tags

	def _iter_get_zim_tags_incl_line_based(self, iter):
		# Simplified case for "range" methods where line based tags are included
		start_tags = list(filter(_is_zim_tag, iter.get_toggled_tags(True)))
		tags = [t for t in filter(_is_zim_tag, iter.get_tags()) if not t in start_tags]
		end_tags = list(filter(_is_zim_tag, iter.get_toggled_tags(False)))
		tags += end_tags
		tags.sort(key=lambda tag: tag.get_priority())
		return tags

	def toggle_format_tag_by_name_interactive(self, name, autoselect=True):
		'''Toggle the format for the current (auto-)selection or new
		insertions at the current cursor position

		When the cursor is at the begin or in the middle of a word and there is
		no selection, the word is selected automatically to toggle the format.
		For headings and other line based formats auto-selects the whole line.

		This is the handler for all the format actions.

		@param name: the format style name (e.g. "h1", "strong" etc.)
		@param autoselect: if C{True} use auto-selection for inline formatting
		'''
		selected = False
		bounds = self.get_selection_bounds()
		start, end = bounds if bounds else (None, None)
		mark = self.create_mark(None, self.get_insert_iter())

		if name in HEADING_1_to_6:
			selected = self.select_lines_for_selection()
		elif name == 'code' and bounds and start.starts_line() and end.starts_line():
			# Change 'code' to 'pre'
			# In case line is selected up to end of line or selection stops
			# halfway a line, it should remain  "code" and not become a "pre" block
			name = 'pre'
		elif self.get_has_selection():
			self.strip_selection()
		elif autoselect:
			# First check formatting is consistent left and right of the cursor, if not 
			# this should be an edit-mode toggle, not a selection toggle
			iter = self.get_insert_iter()
			name_left = name in [t.zim_tag for t in self.iter_get_zim_tags(iter)]
			name_right = name in [t.zim_tag for t in filter(_is_zim_tag, iter.get_tags())]
			if name_left is name_right:
				selected = self.select_word()
		else:
			pass

		self.toggle_format_tag_by_name(name)

		if selected:
			# If we keep the selection we can not continue typing
			# so remove the selection and restore the cursor.
			self.unset_selection()
			self.place_cursor(self.get_iter_at_mark(mark))
		self.delete_mark(mark)

	def toggle_format_tag_by_name(self, name):
		'''Toggle the current textstyle

		If there is a selection toggle the text style of the selection,
		otherwise toggle the text style for newly inserted text.

		This method is mainly to change the behavior for
		interactive editing. E.g. it is called indirectly when the
		user clicks one of the formatting buttons in the EditBar.

		For selections we remove the format if the whole range has the
		format already. If some part of the range does not have the
		format we apply the format to the whole tange. This makes the
		behavior of the format buttons consistent if a single tag
		applies to any range.

		@param name: the format style name
		'''
		try:
			tag = self.get_tag_table().lookup('style-' + name)
		except:
			raise ValueError('Invalid tag name: %s' % name)

		if not self.get_has_selection():
			tags = self.get_editmode()
			if any(filter(_is_pre_tag, tags)) and name != 'pre':
				pass # do not allow styles within verbatim block
			elif tag in tags:
				tags.remove(tag)
				self.set_editmode(tags)
			else:
				tags.append(tag)
				self.set_editmode(tags)
		else:
			with self.user_action:
				start, end = self.get_selection_bounds()
				had_tag = self.whole_range_has_tag(tag, start, end)
				pre_tag = self.get_tag_table().lookup('style-pre')

				if tag.zim_tag == HEADING:
					assert start.starts_line() and (end.starts_line() or end.is_end()), 'Selection must be whole line'
					self.smart_remove_tags(_is_line_based_tag, start, end)
				elif tag.zim_tag == VERBATIM:
					self.smart_remove_tags(_is_non_nesting_tag, start, end)
				elif tag.zim_tag == VERBATIM_BLOCK:
					assert start.starts_line() and (end.starts_line() or end.is_end()), 'Selection must be whole line'
					if not had_tag:
						start, end = self._fix_pre_selection(start, end)
					self.smart_remove_tags(_is_zim_tag, start, end)
				elif self.range_has_tag(pre_tag, start, end):
					return # do not allow formatting withing verbatim block

				if had_tag:
					self.remove_tag(tag, start, end)
				else:
					self.apply_tag(tag, start, end)
				self.set_modified(True)

			self.update_editmode()

	def _fix_pre_selection(self, start, end):
		# This method converts indent back into TAB before a region is
		# formatted as "pre"
		start_mark = self.create_mark(None, start, True)
		end_mark = self.create_mark(None, end, True)

		lines = range(*sorted([start.get_line(), end.get_line()]))
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
		# test right gravity for start iter, but left gravity for end iter
		if tag in start.get_tags() and tag in self._iter_get_zim_tags_incl_line_based(end):
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
		if tag in start.get_tags() or tag in self._iter_get_zim_tags_incl_line_based(end):
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
			or any(filter(func, self._iter_get_zim_tags_incl_line_based(end))):
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

	def get_iter_in_verbatim(self, iter):
		return any(filter(_is_pre_or_code_tag, iter.get_tags()))

	def get_iter_in_verbatim_block(self, iter):
		return any(filter(_is_pre_tag, iter.get_tags()))

	def get_range_in_verbatim_block(self, start, end):
		t = list(filter(_is_pre_tag, start.get_tags()))
		if t:
			return self.range_has_tag(t[0], start, end)
		else:
			return False

	def get_range_has_non_nesting_formatting(self, start, end):
		return self.range_has_tags(_is_non_nesting_tag, start, end)

	def get_line_is_heading(self, line):
		start = self.get_iter_at_line(line)
		return any(filter(_is_heading_tag, start.get_tags()))

	def get_anchor_object_at_iter(self, iter, klass=None):
		anchor = iter.get_child_anchor()
		if anchor and (klass is None or isinstance(anchor, klass)):
			return anchor
		else:
			return None

	def smart_remove_tags(self, func, start, end):
		'''This method removes tags over a range based on a function

		see L{range_has_tags()} for a details on such a test function.

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

	def clear_formatting_interactive(self, autoselect=True):
		'''Remove formatting for selection and edit-mode
		@param autoselect: if C{True} apply auto-selection
		'''
		mark = self.create_mark(None, self.get_insert_iter())
		pre_tag = self.get_tag_table().lookup('style-pre')

		had_selection = self.get_has_selection()
		if had_selection:
			start, end = self.get_selection_bounds()
			in_pre_block = self.range_has_tag(pre_tag, start, end)
		else:
			iter = self.get_insert_iter()
			in_pre_block = pre_tag in self.iter_get_zim_tags(iter)

		if in_pre_block:
			self.select_lines_for_selection()
		elif had_selection:
			self.strip_selection()
		elif autoselect:
			self.select_word()

		if self.get_has_selection():
			start, end = self.get_selection_bounds() # can be modified
			if start.starts_line() and end.starts_line():
				self.smart_remove_tags(_is_format_tag, start, end)
			else:
				# Exclude line-based format tags
				self.smart_remove_tags(_is_inline_format_tag, start, end)

			if not had_selection:
				self.unset_selection()
				self.place_cursor(self.get_iter_at_mark(mark))

			self.update_editmode()
		else:
			self.filter_editmode(_is_not_inline_format_tag)

		self.delete_mark(mark)

	def clear_heading_format_interactive(self):
		'''Remove heading formatting for current line or selection'''
		mark = self.create_mark(None, self.get_insert_iter())
		selected = self.select_lines_for_selection()
		if self.get_has_selection():
			start, end = self.get_selection_bounds()
			self.smart_remove_tags(_is_heading_tag, start, end)
			if selected:
				self.unset_selection()
				self.place_cursor(self.get_iter_at_mark(mark))

		self.delete_mark(mark)
		self.filter_editmode(tag_filter=_is_not_heading_tag)

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
				logger.warning('BUG: overlapping indent tags')
			return int(tags[0].zim_attrib['indent'])
		else:
			return 0

	def _get_indent_tag(self, level, bullet=None, dir='LTR'):
		if dir is None:
			dir = 'LTR'  # Assume western default direction - FIXME need system default

		if bullet:
			if bullet == BULLET:
				stylename = BULLET_LIST_STYLE
			elif bullet in CHECKBOXES or bullet in (BULLET_LIST_STYLE, NUMBERED_LIST_STYLE):
				stylename = bullet
			elif is_numbered_bullet_re.match(bullet):
				stylename = NUMBERED_LIST_STYLE
			else:
				raise AssertionError('BUG: Unknown bullet type')
			name = 'indent-%s-%i-%s' % (dir, level, stylename)
		else:
			name = 'indent-%s-%i' % (dir, level)

		tag = self.get_tag_table().lookup(name)
		if tag is None:
			if bullet:
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

				tag.zim_tag = LISTITEM
				tag.zim_attrib = {'indent': level, 'style': stylename}
			else:
				margin = 12 + self.pixels_indent * level
				# Note: I would think the + 12 is not needed here, but
				# the effect in the view is different than expected,
				# putting text all the way to the left against the
				# window border
				if dir == 'LTR':
					tag = self.create_tag(name,
						left_margin=margin,
						**self.tag_styles[INDENT_BLOCK_STYLE])
				else: # RTL
					tag = self.create_tag(name,
						right_margin=margin,
						**self.tag_styles[INDENT_BLOCK_STYLE])

				tag.zim_tag = BLOCK
				tag.zim_attrib = {'indent': level}

			# Set the prioriy below any _static_style_tags
			tag.set_priority(0)

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

	def _set_indent(self, line, level, bullet=None, dir=None):
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

	def foreach_line_in_selection(self, func, *args, skip_empty_lines=False, **kwarg):
		'''Convenience function to call a function for each line that
		is currently selected

		@param func: function which will be called as::

			func(line, *args, **kwargs)

		where C{line} is the line number
		@param skip_empty_lines: if C{True}, C{func} won't be called
		for empty lines
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
			if skip_empty_lines:
				all_lines_are_empty = True
				for line in range(start.get_line(), end.get_line() + 1):
					if not self.get_line_is_empty(line):
						all_lines_are_empty = False
						func(line, *args, **kwarg)
				if all_lines_are_empty:
					# the user wanted to do something to these empty lines, so we do
					self.foreach_line_in_selection(func, *args, skip_empty_lines=False, **kwarg)
			else:
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
		#print("INSERT %r %d" % (string, length))

		if self._deleted_editmode_mark is not None:
			# Use mark if we are the same postion, clear it anyway
			markiter = self.get_iter_at_mark(self._deleted_editmode_mark)
			if iter.equal(markiter):
				self._editmode_tags = self._deleted_editmode_mark.editmode_tags
			self.delete_mark(self._deleted_editmode_mark)
			self._deleted_editmode_mark = None

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
		# FIXME this should go in move cursor code of the view
		if not self._insert_tree_in_progress and iter.starts_line() \
		and not string.endswith('\n'):
			bullet = self._get_bullet_at_iter(iter)
			if bullet:
				self._iter_forward_past_bullet(iter, bullet)
				self.place_cursor(iter)

		# Check current formatting
		if not self._insert_tree_in_progress and string == '\n': # CHARS_END_OF_LINE
			# Break tags that are not allowed to span over multiple lines
			# Do not break heading tags here, they are handled seperately after the insert
			# TODO: make this more robust for multiline inserts
			self._editmode_tags = list(filter(_is_line_based_tag, self._editmode_tags))
			self.emit('textstyle-changed', None)

			string, length = end_or_protect_tags(string, length)

		elif not self._insert_tree_in_progress and string in CHARS_END_OF_WORD:
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

		# Special handling for ending headings on insert newline - CHARS_END_OF_LINE
		if not self._insert_tree_in_progress and string == '\n' \
			and any(_is_heading_tag(t) for t in self._editmode_tags) and iter.ends_line():
				# Implies we inserted a newline at the end of a heading
				# Remove the format tag over the previous line end of the heading
				end = iter.copy()
				end.forward_line()
				if not end.equal(iter):
					self.smart_remove_tags(_is_heading_tag, iter, end)
				self._editmode_tags = list(filter(_is_not_heading_tag, self._editmode_tags))
		elif not self._insert_tree_in_progress and string == '\n' \
			and any(_is_line_based_tag(t) for t in self._editmode_tags):
				# Check whether we inserted empty line in fron of line based block
				# ('h', 'div' or 'pre') and if so remove formatting on empty line
				# effectively moving block down.
				start = iter.copy()
				start.backward_char()
				if start.starts_line():
					# empty line, so did not break in the middle of the line
					self.smart_remove_tags(_is_line_based_tag, start, iter)

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
		if hasattr(pixbuf, 'zim_type') and pixbuf.zim_type == ANCHOR:
			for tag in self._editmode_tags:
				self.apply_tag(tag, start, iter)
		else:
			for tag in filter(_is_indent_tag, self._editmode_tags):
				self.apply_tag(tag, start, iter)

	@SignalHandler
	def do_pre_delete_range(self, o, start, end):
		# (Interactive) deleting a formatted word with <del>, or <backspace>
		# should drop the formatting, however selecting a formatted word and
		# than typing to replace it, should keep formatting
		# Therefore we set a mark to remember the formatting and clear it
		# at the end of a user action, or with the next insert at a different
		# location
		if self._deleted_editmode_mark:
			self.delete_mark(self._deleted_editmode_mark)
		self._deleted_editmode_mark = self.create_mark(None, end, left_gravity=True)
		self._deleted_editmode_mark.editmode_tags = self.iter_get_zim_tags(end)

		# Also need to know whether range spanned multiple lines or not
		self._deleted_line_end = start.get_line() != end.get_line()

	@SignalHandler
	def do_post_delete_range(self, o, start, end):
		# Post handler to hook _do_lines_merged and do some logic
		# when deleting bullets
		# Note that 'start' and 'end' refer to the same postion here ...
		was_list = any(_is_listitem_tag(t) for t in start.get_tags())
			# get_tags() uses right side gravity, so omits list item ending here

		# Do merging of tags regardless of whether we deleted a line end or not
		# worst case some clean up of run-aways tags is done
		if not start.starts_line() and (
			any(filter(_is_line_based_tag, start.get_toggled_tags(True)))
			or
			any(filter(_is_line_based_tag, start.get_toggled_tags(False)))
		):
			self._do_lines_merged(start)

		# For cleaning up bullets do check more, else we can delete sequences
		# that look like a bullet but aren't - see issue #1328
		bullet = self._get_bullet_at_iter(start) # Does not check start of line !
		if self._deleted_line_end and bullet is not None:
			if start.starts_line():
				self._check_renumber.append(start.get_line())
			elif was_list:
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
			else:
				pass
		elif start.starts_line():
			if any(_is_listitem_tag(t) for t in start.get_tags()):
				# had a bullet, but no longer (implies we are start of
				# line - case where we are not start of line is
				# handled by _do_lines_merged by extending the indent tag)
				line = start.get_line()
				level = self.get_indent(line)
				self._set_indent(line, level) # Update the indent tag

		self.update_editmode()

	def _do_lines_merged(self, iter):
		# Enforce tags like 'h', 'pre', 'div' and 'li' to be consistent over the line
		# and including the line end
		# Merge links that have same href target
		if iter.starts_line():
			return # special position where line based tags can be toggled

		end = iter.copy()
		end.forward_line()

		self.smart_remove_tags(_is_line_based_tag, iter, end)

		for tag in self.iter_get_zim_tags(iter):
			if _is_line_based_tag(tag):
				if tag.zim_tag == VERBATIM_BLOCK:
					self.smart_remove_tags(_is_zim_tag, iter, end)
				self.apply_tag(tag, iter, end)
			elif _is_link_tag(tag):
				for rh_tag in filter(_is_link_tag, iter.get_tags()):
					if rh_tag is not tag and rh_tag.zim_attrib['href'] == tag.zim_attrib['href']:
						bound = iter.copy()
						bound.forward_to_tag_toggle(rh_tag)
						self.remove_tag(rh_tag, iter, bound)
						self.apply_tag(tag, iter, bound)

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
				TRANSMIGRATED_BOX
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
			if getattr(pixbuf, 'zim_type', None) == ICON:

				return BULLETS_FROM_STOCK.get(pixbuf.zim_attrib['stock'])
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

	def _iter_forward_past_bullet(self, iter, bullet):
		if bullet in BULLETS:
			# Each of these just means one char
			iter.forward_char()
		else:
			assert is_numbered_bullet_re.match(bullet)
			self.iter_forward_word_end(iter)

		# Skip whitespace as well
		bound = iter.copy()
		bound.forward_char()
		while iter.get_text(bound) == ' ':
			if iter.forward_char():
				bound.forward_char()
			else:
				break

	def get_parsetree(self, bounds=None):
		'''Get a L{ParseTree} representing the buffer contents

		NOTE: the C{ParseTree} is a cleaned up representation of the buffer,
		reloading it may have subtle differences in the internal representation.
		If it is important to get an exact representation use the low-level
		functions from L{zim.gui.pageview.serialize} instead.

		@param bounds: a 2-tuple with two C{Gtk.TextIter} specifying a
		range in the buffer (e.g. current selection). If C{None} the
		whole buffer is returned.

		@returns: a L{ParseTree} object
		'''
		if self.showing_template:
			return None

		attrib = {}
		start, end = bounds or self.get_bounds()
		builder = BackwardParseTreeBuilderWithCleanup()
		builder.start('zim-tree', attrib)

		open_tags = []
		def set_tags(iter, tags):
			# This function changes the parse tree based on the TextTags in
			# effect for the next section of text.
			# It does so be keeping the stack of open tags and compare it
			# with the new set of tags in order to decide which of the
			# tags can be closed and which new ones need to be opened.

			tags.sort(key=lambda tag: tag.get_priority())
			if any(_is_tag_tag(t) for t in tags):
				# Although not highest prio, no other tag can nest below a tag-tag
				while not _is_tag_tag(tags[-1]):
					tags.pop()

			if any(_is_inline_nesting_tag(t) for t in tags):
				tags = self._sort_nesting_style_tags(iter, end, tags, [t[0] for t in open_tags])

			# For tags that can only appear once, if somehow an overlap
			# occured, choose the one with the highest prio
			for i in range(len(tags)-2, -1, -1):
				if tags[i].zim_tag in (LINK, TAG) \
					and tags[i+1].zim_tag == tags[i].zim_tag:
						tags.pop(i)
				elif tags[i+1].zim_tag in (HEADING, BLOCK, LISTITEM) \
					and tags[i].zim_tag in (HEADING, BLOCK, LISTITEM):
						tags.pop(i)
				elif tags[i+1].zim_tag == VERBATIM_BLOCK \
					and _is_format_tag(tags[i]):
						tags.pop(i)

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
					if t in (BLOCK, LISTITEM):
						attrib = attrib.copy() # break ref with tree
						if t == LISTITEM:
							del attrib['style']
						bullet = self._get_bullet_at_iter(iter)
						if bullet:
							t = 'li'
							attrib['bullet'] = bullet
							self._iter_forward_past_bullet(iter, bullet)
						elif not iter.starts_line():
							# Indent not visible if it does not start at begin of line
							t = '_ignore_'
						elif len([t for t in tags[i:] if t.zim_tag == VERBATIM_BLOCK]):
							# Indent of 'pre' blocks handled in subsequent iteration
							continue_attrib.update(attrib)
							continue
						else:
							t = 'div'
					elif t == 'pre' and not iter.starts_line():
						# Without indenting 'pre' looks the same as 'code'
						# Prevent turning into a separate paragraph here
						t = 'code'
					elif t in BLOCK_LEVEL and not iter.starts_line():
						# Not perfect, but prevent illegal sequence towards dumper
						t = '_ignore_'
					elif t == 'pre':
						if attrib:
							attrib.update(continue_attrib)
						else:
							attrib = continue_attrib
						continue_attrib = {}
					elif t == 'link':
						attrib = self.get_link_data(iter)
					elif t == 'tag':
						attrib = self.get_tag_data(iter)
						if not attrib['name']:
							t = '_ignore_'
					builder.start(t, attrib or {})
					open_tags.append((tag, t))
					if t == 'li':
						break
						# HACK - ignore any other tags because we moved
						# the cursor - needs also a break_tags before
						# which is special cased below
						# TODO: cleaner solution for this issue -
						# maybe easier when tags for list and indent
						# are separated ?

		def break_tags(*types):
			# Forces breaking the stack of open tags on the level of 'tag'
			# The next set_tags() will re-open any tags that are still open
			i = 0
			for i in range(len(open_tags)):
				if open_tags[i][1] in types:
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
				if pixbuf.zim_type == ICON:
					# Reset all tags - and let set_tags parse the bullet
					if open_tags:
						break_tags(open_tags[0][1])
					set_tags(iter, list(filter(_is_indent_tag, iter.get_tags())))
				elif pixbuf.zim_type == ANCHOR:
					pass # allow as object nested in e.g. header tag
				else:
					# reset all tags except indenting
					set_tags(iter, list(filter(_is_indent_tag, iter.get_tags())))

				pixbuf = iter.get_pixbuf() # iter may have moved
				if pixbuf is None:
					continue

				if pixbuf.zim_type == ICON:
					logger.warning('BUG: Checkbox outside of indent ?')
				elif pixbuf.zim_type == IMAGE:
					attrib = pixbuf.zim_attrib.copy()
					builder.start(IMAGE, attrib or {})
					builder.end(IMAGE)
				elif pixbuf.zim_type == ANCHOR:
					attrib = pixbuf.zim_attrib.copy()
					builder.start(ANCHOR, attrib)
					builder.end(ANCHOR)
				else:
					assert False, 'BUG: unknown pixbuf type'

				iter.forward_char()

			# embedded widget
			elif anchor:
				set_tags(iter, list(filter(_is_indent_tag, iter.get_tags())))
				anchor = iter.get_child_anchor() # iter may have moved
				if isinstance(anchor, InsertedObjectAnchor):
					if anchor.is_inline:
						anchor.dump(builder)
						iter.forward_char()
					else:
						if not iter.starts_line():
							builder.data('\n')
						anchor.dump(builder)
						iter.forward_char()
						if iter.ends_line():
							iter.forward_char() # skip over line-end
				else:
					continue
			else:
				# Set tags
				copy = iter.copy()

				bullet = self.get_bullet_at_iter(iter) # implies check for start of line
				if bullet:
					break_tags(BLOCK, LISTITEM)
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

				break_at = None
				if bound.get_line() != iter.get_line():
					if any(t[1] in (HEADING, LISTITEM) for t in open_tags):
						# And limit bullets and headings to a single line
						break_at = LISTITEM if LISTITEM in [t[1] for t in open_tags] else HEADING
					elif any(t[1] not in BLOCK_LEVEL for t in open_tags):
						# Prevent formatting tags to run multiple lines
						for t in open_tags:
							if t[1] not in BLOCK_LEVEL:
								break_at = t[1]
								break

				if break_at:
					orig = bound
					bound = iter.copy()
					bound.forward_line()
					assert bound.compare(orig) < 1
					text = iter.get_slice(bound)
					if break_at in (HEADING, LISTITEM): # XXX - exception because it is blocklevel and include "\n"
						builder.data(text)
						break_tags(break_at)
					else:
						text = text.rstrip('\n')
						builder.data(text)
						break_tags(break_at)
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

		if tree.hascontent:
			# Reparsing the parsetree in order to find wiki codes
			# and get rid of oddities in our generated parsetree.
			#print(">>> Parsetree original:\n", tree.tostring())
			from zim.formats import get_format
			format = get_format("wiki") # FIXME should the format used here depend on the store ?
			dumper = format.Dumper()
			parser = format.Parser()
			text = dumper.dump(tree)
			#print(">>> Wiki text:\n", ''.join(text))
			tree = parser.parse(text)
			#print(">>> Parsetree recreated:\n", tree.tostring())

		return tree

	def _sort_nesting_style_tags(self, iter, end, tags, open_tags):
		new_block, new_nesting, new_leaf = self._split_nesting_style_tags(tags)
		open_block, open_nesting, open_leaf = self._split_nesting_style_tags(open_tags)
		sorted_new_nesting = []

		# First prioritize open tags - these are sorted already
		if new_block == open_block:
			for tag in open_nesting:
				if tag in new_nesting:
					i = new_nesting.index(tag)
					sorted_new_nesting.append(new_nesting.pop(i))
				else:
					break

		# Then sort by length untill closing all tags that open at the same time
		def tag_close_pos(tag):
			my_iter = iter.copy()
			my_iter.forward_to_tag_toggle(tag)
			if my_iter.compare(end) > 0:
				return end.get_offset()
			else:
				return my_iter.get_offset()

		new_nesting.sort(key=tag_close_pos, reverse=True)
		sorted_new_nesting += new_nesting

		return new_block + sorted_new_nesting + new_leaf

	def _split_nesting_style_tags(self, tags):
		block, nesting = [], []
		while tags and not _is_inline_nesting_tag(tags[0]):
			block.append(tags.pop(0))
		while tags and _is_inline_nesting_tag(tags[0]):
			nesting.append(tags.pop(0))
		return block, nesting, tags

	def select_line(self, line=None):
		'''Selects a line
		@param line: line number; if C{None} current line will be selected
		@returns: C{True} when successful
		'''
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
		end.forward_line()
		if end.equal(start):
			return False
		self.select_range(start, end)
		return True

	def select_lines_for_selection(self):
		'''Select current line or extent the selection to cover full lines
		@returns: C{True} if selection changed
		'''
		bounds = self.get_selection_bounds()
		if bounds:
			start, end = bounds
			if start.starts_line() and end.starts_line():
				return False
			else:
				return self.select_lines(start.get_line(), end.get_line())
		else:
			return self.select_line()

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

	def find_implicit_anchor(self, name):
		"""Search the current page for a heading who's derived (implicit) anchor name is
		matching the provided parameter.
		@param name: the name of the anchor
		@returns: a C{Gtk.TextIter} pointing to the start of the heading or C{None}.
		"""
		iter = self.get_start_iter()
		while True:
			tags = list(filter(_is_heading_tag, iter.get_tags()))
			if tags:
				tag = tags[0]
				end = iter.copy()
				end.forward_to_tag_toggle(tag)
				text = iter.get_text(end)
				if heading_to_anchor(text) == name:
					return iter
			if not iter.forward_line():
				break
		return None

	def find_anchor(self, name):
		"""Searches the current page for an anchor with the requested name.

		Explicit anchors are being searched with precedence over implicit
		anchors derived from heading elements.

		@param name: the name of the anchor to look for
		@returns: a C{Gtk.TextIter} pointing to the start of the heading or C{None}.
		"""
		# look for explicit anchors tags including image or object tags
		start, end = self.get_bounds()
		for iter, myname in self.iter_anchors_for_range(start, end):
			if myname == name:
				return iter

		# look for an implicit heading anchor
		return self.find_implicit_anchor(name)

	def toggle_checkbox(self, line, checkbox_type=None, recursive=False):
		'''Toggles the state of the checkbox at a specific line, if any

		@param line: the line number
		@param checkbox_type: the checkbox type that we want to toggle:
		one of C{CHECKED_BOX}, C{XCHECKED_BOX}, C{MIGRATED_BOX},
		C{TRANSMIGRATED_BOX}.
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

	def paste_clipboard(self, clipboard, iter, default_editable, text_format=None):
		'''Paste data from a clipboard into the buffer

		@param clipboard: a L{Clipboard} object
		@param iter: a C{Gtk.TextIter} for the insert location
		@param default_editable: default state of the L{TextView}
		'''
		if not default_editable:
			return

		if iter is None:
			iter = self.get_iter_at_mark(self.get_insert())
			tags = list(filter(_is_pre_or_code_tag, self._editmode_tags))
			if tags:
				text_format = 'verbatim-' + tags[0].zim_tag
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
		if text_format is None:
			tags = list(filter(_is_pre_or_code_tag, self.iter_get_zim_tags(iter)))
			if tags:
				text_format = 'verbatim-' + tags[0].zim_tag
			else:
				text_format = 'wiki' # TODO: should depend on page format
		parsetree = clipboard.get_parsetree(self.notebook, self.page, text_format)
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
			self.insert_parsetree_at_cursor(parsetree, interactive=True)

