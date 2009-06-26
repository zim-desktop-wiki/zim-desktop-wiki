# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import logging

import gobject
import gtk
import pango

from zim.fs import *
from zim.notebook import Path
from zim.parsing import link_type
from zim.config import config_file
from zim.formats import get_format, ParseTree, TreeBuilder, \
	BULLET, CHECKED_BOX, UNCHECKED_BOX, XCHECKED_BOX
from zim.gui import Dialog, FileDialog


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

ui_actions = (
	# name, stock id, label, accelerator, tooltip
	('undo', 'gtk-undo', '_Undo', '<ctrl>Z', 'Undo'),
	('redo', 'gtk-redo', '_Redo', '<ctrl><shift>Z', 'Redo'),
	('cut', 'gtk-cut', 'Cu_t', '<ctrl>X', 'Cut'),
	('copy', 'gtk-copy', '_Copy', '<ctrl>C', 'Copy'),
	('paste', 'gtk-paste', '_Paste', '<ctrl>V', 'Paste'),
	('delete', 'gtk-delete', '_Delete', '', 'Delete'),
	('toggle_checkbox', STOCK_CHECKED_BOX, 'Toggle Checkbox \'V\'', 'F12', ''),
	('xtoggle_checkbox', STOCK_XCHECKED_BOX, 'Toggle Checkbox \'X\'', '<shift>F12', ''),
	('edit_object', 'gtk-properties', '_Edit Link or Object...', '<ctrl>E', ''),
	('insert_image', None, '_Image...', '', 'Insert Image'),
	('insert_text_from_file', None, 'Text From _File...', '', 'Insert Text From File'),
	('insert_external_link', 'gtk-connect', 'E_xternal Link...', '', 'Insert External Link'),
	('insert_link', 'gtk-connect', '_Link...', '<ctrl>L', 'Insert Link'),
	('clear_formatting', None, '_Clear Formatting', '<ctrl>0', ''),
)

ui_format_actions = (
	# name, stock id, label, accelerator, tooltip
	('apply_format_h1', None, 'Heading _1', '<ctrl>1', 'Heading 1'),
	('apply_format_h2', None, 'Heading _2', '<ctrl>2', 'Heading 2'),
	('apply_format_h3', None, 'Heading _3', '<ctrl>3', 'Heading 3'),
	('apply_format_h4', None, 'Heading _4', '<ctrl>4', 'Heading 4'),
	('apply_format_h5', None, 'Heading _5', '<ctrl>5', 'Heading 5'),
	('apply_format_strong', 'gtk-bold', '_Strong', '<ctrl>B', 'Strong'),
	('apply_format_emphasis', 'gtk-italic', '_Emphasis', '<ctrl>I', 'Emphasis'),
	('apply_format_mark', 'gtk-underline', '_Mark', '<ctrl>U', 'Mark'),
	('apply_format_strike', 'gtk-strikethrough', '_Strike', '<ctrl>K', 'Strike'),
	('apply_format_code', None, '_Verbatim', '<ctrl>T', 'Verbatim'),
)

ui_format_toggle_actions = (
	# name, stock id, label, accelerator, tooltip, None, initial state
	('toggle_format_strong', 'gtk-bold', '_Strong', '', 'Strong', None, False),
	('toggle_format_emphasis', 'gtk-italic', '_Emphasis', '', 'Emphasis', None, False),
	('toggle_format_mark', 'gtk-underline', '_Mark', '', 'Mark', None, False),
	('toggle_format_strike', 'gtk-strikethrough', '_Strike', '', 'Strike', None, False),
)

ui_preferences = (
	# key, type, category, label, default
	('follow_on_enter', 'bool', 'Interface', 'Use the <Enter> key to follow links\n(If disabled you can still use <Alt><Enter>)', True),
	('read_only_cursor', 'bool', 'Interface', 'Show the cursor also for pages that can not be edited', False),
	('autolink_camelcase', 'bool', 'Editing', 'Automatically turn CamelCasewords into links', True),
	('autolink_files', 'bool', 'Editing', 'Automatically turn file paths into links', True),
	('autoselect', 'bool', 'Editing', 'Automatically select the current word when you apply formatting', True),
	('unindent_on_backspace', 'bool', 'Editing', 'Unindent on <BackSpace>\n(If disabled you can still use <Shift><Tab>)', True),
	('recursive_checklist', 'bool', 'Editing', 'Checking a checkbox also change any sub-items', False),
)

_is_zim_tag = lambda tag: hasattr(tag, 'zim_type')
_is_indent_tag = lambda tag: _is_zim_tag(tag) and tag.zim_type == 'indent'
_is_not_indent_tag = lambda tag: _is_zim_tag(tag) and tag.zim_type != 'indent'

PIXBUF_CHR = u'\uFFFC'


class TextBuffer(gtk.TextBuffer):
	'''Zim subclass of gtk.TextBuffer.

	This class manages the contents of a TextView widget. It can load a zim
	parsetree and after editing return a new parsetree. It manages images,
	links, bullet lists etc.

	The styles supported are given in the dict 'tag_styles'. These map to
	like named TextTags. For links anonymous TextTags are used. Not all tags
	are styles though, e.g. gtkspell uses it's own tags and tags may also
	be used to highlight search results etc.

	TODO: manage undo stack - group by memorizing offsets and get/set trees
	TODO: manage rich copy-paste based on zim formats
		  use serialization API if gtk >= 2.10 ?
	'''

	# We rely on the priority of gtk TextTags to sort links before styles,
	# and styles before indenting. Since styles are initialized on init,
	# while indenting tags are created when needed, indenting tags always
	# have the higher priority. By explicitly lowering the priority of new
	# link tags to zero we keep those tags on the lower endof the scale.


	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'insert-text': 'override',
		'textstyle-changed': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'indent-changed': (gobject.SIGNAL_RUN_LAST, None, (int,)),
	}

	# text tags supported by the editor and default stylesheet
	tag_styles = {
		'h1':	   {'weight': pango.WEIGHT_BOLD, 'scale': 1.15**4},
		'h2':	   {'weight': pango.WEIGHT_BOLD, 'scale': 1.15**3},
		'h3':	   {'weight': pango.WEIGHT_BOLD, 'scale': 1.15**2},
		'h4':	   {'weight': pango.WEIGHT_ULTRABOLD, 'scale': 1.15},
		'h5':	   {'weight': pango.WEIGHT_BOLD, 'scale': 1.15, 'style': 'italic'},
		'h6':	   {'weight': pango.WEIGHT_BOLD, 'scale': 1.15},
		'emphasis': {'style': 'italic'},
		'strong':   {'weight': pango.WEIGHT_BOLD},
		'mark':	 {'background': 'yellow'},
		'strike':   {'strikethrough': 'true', 'foreground': 'grey'},
		'code':	 {'family': 'monospace'},
		'pre':	  {'family': 'monospace', 'wrap-mode': 'none'},
		'link':	 {'foreground': 'blue'},
	}

	# possible attributes for styles in tag_styles
	tag_attributes = set( (
		'weight', 'scale', 'style', 'background', 'foreground', 'strikethrough',
		'family', 'wrap-mode', 'indent', 'underline'
	) )

	def __init__(self):
		'''FIXME'''
		gtk.TextBuffer.__init__(self)

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

		#~ self.connect('begin-user-action', lambda o: logger.info('action'))

	def clear(self):
		'''FIXME'''
		self.set_textstyle(None)
		self.set_indent(None)
		self.delete(*self.get_bounds())
		# TODO: also throw away undo stack

	def set_parsetree(self, tree):
		'''FIXME'''
		self.clear()
		self.insert_parsetree_at_cursor(tree)
		self.set_modified(False)

	def insert_parsetree(self, iter, tree):
		'''FIXME'''
		self._place_cursor(iter)
		self.insert_parsetree_at_cursor(tree)
		self._restore_cursor()

	def _place_cursor(self, iter=None):
		self.create_mark('zim-textbuffer-orig-insert',
			self.get_iter_at_mark(self.get_insert()), True)
		self.place_cursor(iter)

	def _restore_cursor(self):
		mark = self.get_mark('zim-textbuffer-orig-insert')
		self.place_cursor(self.get_iter_at_mark(mark))
		self.delete_mark(mark)

	def insert_parsetree_at_cursor(self, tree):
		'''FIXME'''
		self._insert_element_children(tree.getroot())

	def _insert_element_children(self, node, list_level=-1):
		# FIXME: should block textstyle-changed here for performance
		# FIXME should load list_level from cursor position
		for element in node.getchildren():
			if element.tag == 'p':
				if element.text:
					self.insert_at_cursor(element.text)

				self._insert_element_children(element, list_level=list_level) # recurs
			elif element.tag == 'ul':
				if element.text:
					self.insert_at_cursor(element.text)

				self._insert_element_children(element, list_level=list_level+1) # recurs
			elif element.tag == 'li':
				self.set_indent(list_level+1)
				if 'bullet' in element.attrib and element.attrib['bullet'] != '*':
					bullet = element.attrib['bullet']
					if bullet in bullet_types:
						stock = bullet_types[bullet]
					else:
						logger.warn('Unkown bullet type: %s', bullet)
						stock = gtk.STOCK_MISSING_IMAGE
					self.insert_icon_at_cursor(stock)
					self.insert_at_cursor(' ')
				else:
					self.insert_at_cursor(u'\u2022 ')

				if element.tail:
					element.tail += '\n'
				else:
					element.tail = '\n'

				if element.text:
					self.insert_at_cursor(element.text)

				self._insert_element_children(element, list_level=list_level) # recurs
				self.set_indent(None)
			elif element.tag == 'link':
				self.insert_link_at_cursor(element.text, **element.attrib)
			elif element.tag == 'img':
				file = element.attrib['src-file']
				self.insert_image_at_cursor(file, alt=element.text, **element.attrib)
			else:
				# Text styles
				if element.tag == 'h':
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
		'''FIXME'''
		self._place_cursor(iter)
		self.insert_link_at_cursor(text, href, **attrib)
		self._restore_cursor()

	def insert_link_at_cursor(self, text, href, **attrib):
		'''FIXME'''
		# TODO generate anonymous tags for links
		tag = self.create_tag(None, **self.tag_styles['link'])
		tag.set_priority(0) # force links to be below styles
		tag.zim_type = 'link'
		tag.zim_tag = 'link'
		tag.zim_attrib = attrib
		tag.zim_attrib['href'] = href
		self._editmode_tags = self._editmode_tags + (tag,)
		self.insert_at_cursor(text)
		self._editmode_tags = self._editmode_tags[:-1]

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
				print 'TODO get tag text and use as href'
			return link
		else:
			return None

	def set_link_data(self, iter, attrib):
		'''Set the link properties for a link at iter. Will throw an exception
		if there is no link at iter.
		'''
		tag = self.get_link_tag(iter)
		if tag is None:
			raise Exception, 'No link at iter'
		else:
			# TODO check if href needs to be set to None again
			tag.zim_attrib = attrib

	def insert_pixbuf(self, iter, pixbuf):
		# Make sure we always apply the correct tags when inserting a pixbuf
		if iter.equal(self.get_iter_at_mark(self.get_insert())):
			gtk.TextBuffer.insert_pixbuf(self, iter, pixbuf)
		else:
			mode = self._editmode_tags
			self._editmode_tags = tuple(self.get_zim_tags(iter))
			gtk.TextBuffer.insert_pixbuf(self, iter, pixbuf)
			self._editmode_tags = mode

	def insert_image(self, iter, file, src, **attrib):
		# TODO support tooltip text
		try:
			if 'width' in attrib or 'height' in attrib:
				w = int(attrib.get('width', -1))
				h = int(attrib.get('height', -1))
				pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(file.path, w, h)
			else:
				pixbuf = gtk.gdk.pixbuf_new_from_file(file.path)
		except:
			logger.warn('No such image: %s', file)
			widget = gtk.HBox() # Need *some* widget here...
			pixbuf = widget.render_icon(gtk.STOCK_MISSING_IMAGE, gtk.ICON_SIZE_DIALOG)
		pixbuf.zim_type = 'image'
		pixbuf.zim_attrib = attrib
		pixbuf.zim_attrib['src'] = src
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

	def set_textstyle(self, name):
		'''Sets the current text style. This style will be applied
		to text inserted at the cursor. Use 'set_textstyle(None)' to
		reset to normal text.
		'''
		self._editmode_tags = filter(
			lambda tag: not tag.get_property('name').startswith('style-'),
			self._editmode_tags)

		if not name is None:
			tag = self.get_tag_table().lookup('style-'+name)
			self._editmode_tags = self._editmode_tags + (tag,)

		self.emit('textstyle-changed', name)

	def set_textstyle_from_cursor(self):
		iter = self.get_iter_at_mark(self.get_insert())
		self.set_textstyle_from_iter(iter)

	def set_textstyle_from_iter(self, iter):
		'''Updates the textstyle from a text position.
		Triggered automatically when moving the cursor.
		'''
		tags = self.get_zim_tags(iter)
		if not tags == self._editmode_tags:
			#~ print '>', [(t.zim_type, t.get_property('name')) for t in tags]
			self._editmode_tags = tuple(tags)
			for tag in tags:
				if tag.zim_type == 'style':
					name = tag.get_property('name')[6:]
					self.emit('textstyle-changed', name)
					break
			else:
				self.emit('textstyle-changed', None)

	def get_zim_tags(self, iter):
		'''Like gtk.TextIter.get_tags() but only returns our own tags and
		assumes tags have "left gravity". An exception are indent tags, which
		gravitate both ways.
		'''
		start_tags = set(filter(_is_not_indent_tag, iter.get_toggled_tags(True)))
		tags = filter(
			lambda tag: _is_zim_tag(tag) and not tag in start_tags,
			iter.get_tags() )
		tags.extend( filter(_is_zim_tag, iter.get_toggled_tags(False)) )
		tags.sort(key=lambda tag: tag.get_priority())
		return tags

	def do_textstyle_changed(self, name):
		self.textstyle = name

	def toggle_textstyle(self, name):
		'''If there is a selection toggle the text style of the selection,
		otherwise toggle the text style of the cursor.
		'''
		if not self.get_has_selection():
			if self.textstyle == name:
				self.set_textstyle(None)
			else:
				self.set_textstyle(name)
		else:
			start, end = self.get_selection_bounds()
			tag = self.get_tag_table().lookup('style-'+name)
			had_tag = self.range_has_tag(start, end, tag)
			self.remove_textstyle_tags(start, end)
			if not had_tag:
				self.apply_tag(tag, start, end)

			self.set_textstyle_from_cursor()

	def range_has_tag(self, start, end, tag):
		'''Check if a certain tag appears anywhere in a certain range'''
		# test right gravity for start iter, but left gravity for end iter
		if tag in start.get_tags() \
		or tag in self.get_zim_tags(end):
			return True
		else:
			iter = start.copy()
			if iter.forward_to_tag_toggle(tag):
				return iter.compare(end) < 0
			else:
				return False

	def remove_textstyle_tags(self, start, end):
		'''Removes all textstyle tags from a range'''
		for name in self.tag_styles.keys():
			if not name == 'link':
				self.remove_tag_by_name('style-'+name, start, end)

		self.set_textstyle_from_cursor()

	def get_indent(self, iter=None):
		'''Returns the indent level at iter, or at cursor if 'iter' is None.'''
		if iter is None:
			iter = self.get_iter_at_mark(self.get_insert())
		tags = filter(_is_indent_tag, self.get_zim_tags(iter))
		if tags:
			return tags[0].zim_attrib['indent']
		else:
			return 0

	def set_indent(self, level):
		'''Sets the current indent level. This style will be applied
		to text inserted at the cursor. Using 'set_indent(None)' is
		equivalent to 'set_indent(0)'.
		'''
		self._editmode_tags = filter(_is_not_indent_tag, self._editmode_tags)

		if level and level > 0:
			# TODO make number of pixels in indent configable (call this tabstop)
			name = 'indent-%i' % level
			tag = self.get_tag_table().lookup(name)
			if tag is None:
				margin = 10 + 30 * (level-1) # offset from left side for all lines
				indent = -10 # offset for first line (bullet)
				tag = self.create_tag(name, left_margin=margin, indent=indent)
				tag.zim_type = 'indent'
				tag.zim_tag = 'indent'
				tag.zim_attrib = {'indent': level-1}
			self._editmode_tags = self._editmode_tags + (tag,)
		else:
			level = 0

		self.emit('indent-changed', level)

	def apply_indent(self, level):
		pass

	def do_mark_set(self, iter, mark):
		if mark.get_name() == 'insert':
			self.set_textstyle_from_iter(iter)
		gtk.TextBuffer.do_mark_set(self, iter, mark)

	def do_insert_text(self, end, string, length):
		'''Signal handler for insert-text signal'''
		# First call parent for the actual insert
		gtk.TextBuffer.do_insert_text(self, end, string, length)

		# Apply current text style
		length = len(unicode(string))
			# default function argument gives byte length :S
		start = end.copy()
		start.backward_chars(length)
		self.remove_all_tags(start, end)
		for tag in self._editmode_tags:
			self.apply_tag(tag, start, end)

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

	def _iter_forward_past_bullet(self, iter):
		iter.forward_char()
		bound = iter.copy()
		bound.forward_char()
		if iter.get_text(bound) == ' ':
			iter.forward_char()

	def get_parsetree(self, bounds=None):
		if bounds is None:
			start, end = self.get_bounds()
		else:
			start, end = bounds

		builder = TreeBuilder()
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

			if tags:
				for tag in tags[i:]:
					t, attrib = tag.zim_tag, tag.zim_attrib
					if t == 'indent':
						bullet = self.get_bullet_at_iter(iter)
						if bullet:
							t = 'li'
							attrib = attrib.copy() # break ref with tree
							attrib['bullet'] = bullet
							self._iter_forward_past_bullet(iter)
						else:
							t = 'p'
					builder.start(t, attrib)
					open_tags.append((tag, t))

		# And now the actual loop going through the buffer
		iter = start.copy()
		while iter.compare(end) == -1:
			pixbuf = iter.get_pixbuf()
			if pixbuf:
				# reset all tags except indenting
				set_tags(iter, filter(_is_indent_tag, iter.get_tags()))
				pixbuf = iter.get_pixbuf() # iter may have moved
				if pixbuf is None:
					continue

				if pixbuf.zim_type == 'icon':
					pass # TODO checkboxes etc.
				elif pixbuf.zim_type == 'image':
					attrib = pixbuf.zim_attrib
					text = attrib['alt']
					del attrib['alt']
					builder.start('img', attrib)
					builder.data(text)
					builder.end('img')
				else:
					assert False, 'BUG: unknown pixbuf type'

				iter.forward_char()
			# TODO elif embedded widget
			else:
				# Set tags
				set_tags(iter, filter(_is_zim_tag, iter.get_tags()))

				# Find biggest slice without tags being toggled
				bound = iter.copy()
				toggled = []
				while not toggled:
					if bound.forward_to_tag_toggle(None):
						toggled = filter(_is_zim_tag,
							bound.get_toggled_tags(False)
							+ bound.get_toggled_tags(True) )
					else:
						break

				# But limit slice to first pixbuf
				# TODO: also limit slice to any embeddded widget
				text = iter.get_slice(bound)
				if PIXBUF_CHR in text:
					i = text.index(PIXBUF_CHR)
					bound = iter.copy()
					bound.forward_chars(i)
					text = text[:i]

				# And limit to end
				if bound.compare(end) == 1:
					bound = end
					text = iter.get_slice(end)

				# And insert text
				builder.data(text)
				iter = bound

		# close any open tags
		set_tags(end, [])

		builder.end('zim-tree')
		return ParseTree(builder.close())

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

		self.select_range(insert, bound)
		return link

	def get_has_selection(self):
		'''Returns boolean whether there is a selection or not.

		Method available in gtk.TextBuffer for gtk version >= 2.10
		reproduced here for backward compatibility.
		'''
		return bool(self.get_selection_bounds())

# Need to register classes defining gobject signals
gobject.type_register(TextBuffer)


CURSOR_TEXT = gtk.gdk.Cursor(gtk.gdk.XTERM)
CURSOR_LINK = gtk.gdk.Cursor(gtk.gdk.HAND2)
CURSOR_TOGGLE = gtk.gdk.Cursor(gtk.gdk.LEFT_PTR)


class TextView(gtk.TextView):
	'''FIXME'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		# New signals
		'link-clicked': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'link-enter': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'link-leave': (gobject.SIGNAL_RUN_LAST, None, (object,)),

		# Override clipboard interaction
		#~ 'copy-clipboard': 'override',
		#~ 'cut-clipboard': 'override',
		#~ 'paste-clipboard': 'override',

		# And some events we want to connect to
		'motion-notify-event': 'override',
		'visibility-notify-event': 'override',
		'button-release-event': 'override',
		#~ 'key-press-event': 'override',

	}

	def __init__(self):
		'''FIXME'''
		gtk.TextView.__init__(self, TextBuffer())
		self.cursor = CURSOR_TEXT
		self.cursor_link = None
		self.gtkspell = None
		self.set_left_margin(10)
		self.set_right_margin(5)
		self.set_wrap_mode(gtk.WRAP_WORD)

	def set_buffer(self, buffer):
		if not self.gtkspell is None:
			# Hardcoded hook because usign signals here
			# seems to introduce lag
			self.gtkspell.detach()
			self.gtkspell = None
		gtk.TextView.set_buffer(self, buffer)

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

	def do_button_release_event(self, event):
		'''FIXME'''
		cont = gtk.TextView.do_button_release_event(self, event)
		selection = self.get_buffer().get_selection_bounds()
		if not selection:
			iter = self.get_iter_at_pointer()
			if event.button == 1:
				self.click_link(iter) or self.toggle_checkbox(iter)
			elif event.button == 3:
				self.toggle_checkbox(iter, XCHECKED_BOX)
		return cont # continue emit ?

	#~ def do_key_press_event(self, event):
		#~ '''FIXME'''
		#~ cont = gtk.TextView.do_key_press_event(self, event)
		#~ print 'key press'
		#~ return cont # continue emit ?

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
				cursor = CURSOR_TOGGLE
			else:
				cursor = CURSOR_TEXT

		if cursor != self.cursor:
			window = self.get_window(gtk.TEXT_WINDOW_TEXT)
			window.set_cursor(cursor)

		# Check if we need to emit any events for hovering
		# TODO: do we need similar events for images ?
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

	def toggle_checkbox(self, iter, checkbox_type=CHECKED_BOX):
		buffer = self.get_buffer()
		bullet = buffer.get_bullet_at_iter(iter)
		if bullet in (UNCHECKED_BOX, CHECKED_BOX, XCHECKED_BOX):
			if bullet == checkbox_type:
				icon = bullet_types[UNCHECKED_BOX]
			else:
				icon = bullet_types[checkbox_type]
		else:
			return False

		buffer.begin_user_action()
		bound = iter.copy()
		bound.forward_char()
		buffer.delete(iter, bound)
		buffer.insert_icon(iter, icon)
		buffer.end_user_action()
		return True


# Need to register classes defining gobject signals
gobject.type_register(TextView)


class PageView(gtk.VBox):
	'''FIXME'''

	def __init__(self, ui):
		self.ui = ui
		gtk.VBox.__init__(self)
		self.view = TextView()
		swindow = gtk.ScrolledWindow()
		swindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
		swindow.set_shadow_type(gtk.SHADOW_IN)
		swindow.add(self.view)
		self.add(swindow)

		self.view.connect_object('link-clicked', PageView.do_link_clicked, self)
		self.view.connect_object('link-enter', PageView.do_link_enter, self)
		self.view.connect_object('link-leave', PageView.do_link_leave, self)

		self.ui.add_actions(ui_actions, self)

		# format actions need some custom hooks
		actiongroup = self.ui.init_actiongroup(self)
		actiongroup.add_actions(ui_format_actions)
		actiongroup.add_toggle_actions(ui_format_toggle_actions)
		for name in [a[0] for a in ui_format_actions]:
			action = actiongroup.get_action(name)
			action.connect('activate', self.do_toggle_format_action)
		for name in [a[0] for a in ui_format_toggle_actions]:
			action = actiongroup.get_action(name)
			action.connect('activate', self.do_toggle_format_action)

		self.preferences = self.ui.preferences['PageView']
		self.ui.register_preferences('PageView', ui_preferences)

		PageView.style = config_file('style.conf')
		self.ui.connect('preferences-changed', lambda o: self.reload_style())
		self.reload_style()

	def grab_focus(self):
		self.view.grab_focus()

	def reload_style(self):
		'''(Re-)loads style definition from the config. While running this
		config is found as the class attribute 'style'.
		'''
		# FIXME use Textview/tabstop
		try:
			font = pango.FontDescription(self.style['TextView']['font'])
		except KeyError:
			self.view.modify_font(None)
		else:
			self.view.modify_font(font)

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

	def set_page(self, page):
		# for some reason keeping a copy of the previus buffer
		# prevents a number of segfaults ...
		# we do clear the old buffer to save some memory
		self._prev_buffer = self.view.get_buffer()
		self._prev_buffer.delete(*self._prev_buffer.get_bounds())

		# now create the new buffer
		buffer = TextBuffer()
		self.view.set_buffer(buffer)
		tree = page.get_parsetree()
		cursorpos = 0
		if tree is None:
			# TODO check read-only
			template = self.ui.notebook.get_template(page)
			tree = template.process_to_parsetree(self.ui.notebook, page)
			cursorpos = -1
		tree.resolve_images(self.ui.notebook, page)
			# TODO same for links ?
		buffer.set_parsetree(tree)
		if cursorpos != -1:
			buffer.place_cursor(buffer.get_iter_at_offset(cursorpos))
		# TODO else check template for cursor pos ??
		buffer.connect('textstyle-changed', self.do_textstyle_changed)

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
		# TODO use link object if available
		type = link_type(link['href'])
		logger.debug('Link clicked: %s: %s' % (type, link['href']))

		if type == 'page':
			path = self.ui.notebook.resolve_path(
				link['href'], Path(self.ui.page.namespace))
			self.ui.open_page(path)
		elif type == 'file':
			path = self.ui.notebook.resolve_file(
				link['href'], self.ui.page)
			self.ui.open_file(path)
		else:
			self.ui.open_url(link['href'])

	def undo(self):
		pass

	def redo(self):
		pass

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
		iter = buffer.get_iter_at_mark(buffer.get_insert())
		if not iter.starts_line():
			iter = buffer.get_iter_at_line(iter.get_line())
		self.view.toggle_checkbox(iter, checkbox)

	def edit_object(self):
		buffer = self.view.get_buffer()
		insert = buffer.get_iter_at_mark(buffer.get_insert())
		alt = insert.copy()
		alt.backward_char()
		if buffer.get_image_data(insert) or buffer.get_image_data(alt):
			EditImageDialog(self.ui, buffer).run()
		elif buffer.get_link_tag(insert):
			EditLinkDialog(self.ui, buffer).run()
		else:
			return False

	def insert_image(self, file=None, interactive=True):
		if interactive:
			InsertImageDialog(self.ui, self.view.get_buffer(), file).run()
		else:
			assert isinstance(file, File)
			src = self.ui.notebook.relative_filepath(file, self.ui.page) or file.uri
			print 'SRC', src
			self.view.get_buffer().insert_image_at_cursor(file, src)

	def insert_text_from_file(self):
		InsertTextFromFileDialog(self.ui, self.view.get_buffer()).run()

	def insert_external_link(self):
		InsertExternalLinkDialog(self.ui, self.view.get_buffer()).run()

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
			links[i] = self.ui.notebook.relative_filepath(file, self.ui.page) or file.uri

		if len(links) == 1: sep = ' '
		else: sep = '\n'

		buffer = self.view.get_buffer()
		buffer.begin_user_action()
		if buffer.get_has_selection():
			start, end = buffer.get_selection_bounds()
			self.buffer.delete(start, end)
		for link in links:
			buffer.insert_link_at_cursor(link, link)
			buffer.insert_at_cursor(sep)
		buffer.end_user_action()

	def insert_link(self):
		InsertLinkDialog(self.ui, self.view.get_buffer()).run()

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
		logger.debug('Action: %s (format toggle action)', name)
		if name.startswith('apply_format_'): style = name[13:]
		elif name.startswith('toggle_format_'): style = name[14:]
		else: assert False, "BUG: don't known this action"
		self.toggle_format(style)

	def toggle_format(self, format):
		buffer = self.view.get_buffer()
		if not buffer.textstyle == format:
			self.autoselect()
		buffer.toggle_textstyle(format)

	def autoselect(self):
		buffer = self.view.get_buffer()
		if buffer.get_has_selection():
			return True
		elif self.preferences['autoselect']:
			return buffer.select_word()
		else:
			return False


class InsertImageDialog(FileDialog):

	def __init__(self, ui, buffer, file=None):
		FileDialog.__init__(
			self, ui, 'Insert Image', gtk.FILE_CHOOSER_ACTION_OPEN)
		self.buffer = buffer
		self.add_filter_images()
		if file:
			self.set_file(file)
		# TODO custom 'insert' button ?

	def do_response_ok(self):
		file = self.get_file()
		if file is None: return False
		src = self.ui.notebook.relative_filepath(file, self.ui.page) or file.uri
		self.buffer.insert_image_at_cursor(file, src)
		return True


class EditImageDialog(Dialog):

	def __init__(self, ui, buffer):
		Dialog.__init__(self, ui, 'Edit Image')
		self.buffer = buffer

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
			('file', 'image', 'Location', src),
			('width', 'int', 'Width', (0, 0, 0)),
			('height', 'int', 'Height', (0, 0, 0))
		])

		reset_button = gtk.Button('_Reset Size')
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
		file = self.ui.notebook.resolve_file(filename, self.ui.page)
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
		file = self.ui.notebook.resolve_file(filename, self.ui.page)
		attrib = self._image_data
		attrib['src'] = self.ui.notebook.relative_filepath(file, self.ui.page) or file.uri

		iter = self.buffer.get_iter_at_offset(self._iter)
		bound = iter.copy()
		bound.forward_char()
		self.buffer.begin_user_action()
		self.buffer.delete(iter, bound)
		self.buffer.insert_image_at_cursor(file, **attrib)
		self.buffer.end_user_action()
		return True


class InsertTextFromFileDialog(FileDialog):

	def __init__(self, ui, buffer):
		FileDialog.__init__(
			self, ui, 'Insert Text From File', gtk.FILE_CHOOSER_ACTION_OPEN)
		self.buffer = buffer
		# TODO custom 'insert' button ?

	def do_response_ok(self):
		file = self.get_file()
		if file is None: return False
		parser = get_format('plain').Parser()
		tree = parser.parse(file.readlines())
		self.buffer.insert_parsetree_at_cursor(tree)
		return True


class InsertLinkDialog(Dialog):

	def __init__(self, ui, buffer):
		Dialog.__init__(self, ui, 'Insert Link')
		self.buffer = buffer
		href, text = self._get_link()
		self.add_fields([
			('href', 'page', 'Link to', href),
			('text', 'string', 'Text', text)
		])
		# TODO custom "link" button

	def _get_link(self):
		link = self.buffer.select_link()
		href = ''
		text = ''
		if link:
			href = link['href']
		elif self.ui.preferences['PageView']['autoselect']:
			self.buffer.select_word()

		if self.buffer.get_has_selection():
			start, end = self.buffer.get_selection_bounds()
			text = self.buffer.get_text(start, end)
			self._selection_bounds = (start.get_offset(), end.get_offset())
				# Interaction in the dialog causes buffer to loose selection
				# maybe due to clipboard focus !??
				# Anyway, need to remember bounds ourselves.
		else:
			self._selection_bounds = None

		return href, text

	def do_response_ok(self):
		href = self.get_field('href')
		if not href:
			return False

		type = link_type(href)
		if type == 'file':
			file = File(href)
			href = self.ui.notebook.relative_filepath(file, self.ui.page) or file.uri

		text = self.get_field('text') or href

		self.buffer.begin_user_action()
		if self._selection_bounds:
			start, end = map(
				self.buffer.get_iter_at_offset, self._selection_bounds)
			self.buffer.delete(start, end)
		self.buffer.insert_link_at_cursor(text, href)
		if not self._selection_bounds:
			self.buffer.insert_at_cursor(' ')
		self.buffer.end_user_action()

		return True


class InsertExternalLinkDialog(InsertLinkDialog):

	def __init__(self, ui, buffer):
		Dialog.__init__(self, ui, 'Insert External Link')
		self.buffer = buffer
		href, text = self._get_link()
		self.add_fields([
			('href', 'file', 'Link to', href),
			('text', 'string', 'Text', text)
		])
		# TODO custom "link" button


class EditLinkDialog(InsertLinkDialog):

	def __init__(self, ui, buffer):
		Dialog.__init__(self, ui, 'Edit Link')
		self.buffer = buffer
		href, text = self._get_link()
		type = link_type(href)
		if type == 'file': input = 'file'
		else: input = 'page'
		self.add_fields([
			('href', input, 'Link to', href),
			('text', 'string', 'Text', text)
		])
		# TODO custom "link" button
