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


KEYVAL_HOME = gtk.gdk.keyval_from_name('Home')
KEYVAL_ENTER = gtk.gdk.keyval_from_name('Return')
KEYVAL_BACKSPACE = gtk.gdk.keyval_from_name('BackSpace')
KEYVAL_TAB = gtk.gdk.keyval_from_name('Tab')
KEYVALS_END_OF_WORD = map(
	gtk.gdk.unicode_to_keyval, map(ord, (' ', ')', '>', '.', '!', '?')))
KEYVAL_ASTERISK = gtk.gdk.unicode_to_keyval(ord('*'))
KEYVAL_GT = gtk.gdk.unicode_to_keyval(ord('>'))


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
		'begin-insert-tree': (gobject.SIGNAL_RUN_LAST, None, ()),
		'end-insert-tree': (gobject.SIGNAL_RUN_LAST, None, ()),
		'inserted-tree': (gobject.SIGNAL_RUN_LAST, None, (object, object, object)),
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
		self._insert_tree_in_progress = False

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
		self.emit('begin-insert-tree')
		startoffset = self.get_iter_at_mark(self.get_insert()).get_offset()
		self._insert_element_children(tree.getroot())
		startiter = self.get_iter_at_offset(startoffset)
		enditer = self.get_iter_at_mark(self.get_insert())
		self.emit('end-insert-tree')
		self.emit('inserted-tree', startiter, enditer, tree)

	def do_begin_insert_tree(self):
		self._insert_tree_in_progress = True

	def do_end_insert_tree(self):
		self._insert_tree_in_progress = False

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
				file = element.attrib['_src_file']
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
		# TODO emit signals if not self._insert_tree_in_progress
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
		# TODO emit signals if not self._insert_tree_in_progress
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
			tag = self._get_indent_tag(level)
			self._editmode_tags = self._editmode_tags + (tag,)
		else:
			level = 0

		self.emit('indent-changed', level)

	def apply_indent(self, level, start, end):
		def remove_indent(tag, buffer):
			if _is_indent_tag(tag):
				buffer.remove_tag(tag, start, end)
		self.get_tag_table().foreach(remove_indent, self)

		if level and level > 0:
			tag = self._get_indent_tag(level)
			self.apply_tag(tag, start, end)
		self.set_textstyle_from_cursor() # also updates indent tag

	def _get_indent_tag(self, level):
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
		return tag

	def increment_indent(self, iter):
		print "INCREMENT INDENT"
		start = self.get_iter_at_line(iter.get_line())
		end = start.copy()
		end.forward_line()
		level = self.get_indent(start)
		self.apply_indent(level+1, start, end)

	def decrement_indent(self, iter):
		print "DECREMENT INDENT"
		start = self.get_iter_at_line(iter.get_line())
		end = start.copy()
		end.forward_line()
		level = self.get_indent(start)
		self.apply_indent(level-1, start, end)

	def foreach_line_in_selection(self, func, userdata=None):
		bounds = self.get_selection_bounds()
		if bounds:
			start, end = bounds
			self.foreach_line(start, end, func, userdata)
			return True
		else:
			return False

	def foreach_line(self, start, end, func, userdata=None):
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
							self._iter_forward_past_bullet(iter, bullet)
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

	def toggle_checkbox(self, iter, checkbox_type=CHECKED_BOX):
		bullet = self.get_bullet_at_iter(iter)
		if bullet in (UNCHECKED_BOX, CHECKED_BOX, XCHECKED_BOX):
			if bullet == checkbox_type:
				icon = bullet_types[UNCHECKED_BOX]
			else:
				icon = bullet_types[checkbox_type]
		else:
			return False

		self.begin_user_action()
		bound = iter.copy()
		bound.forward_char()
		self.delete(iter, bound)
		self.insert_icon(iter, icon)
		self.end_user_action()
		return True

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
CURSOR_WIDGET = gtk.gdk.Cursor(gtk.gdk.LEFT_PTR)


class TextView(gtk.TextView):
	'''FIXME'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		# New signals
		'link-clicked': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'link-enter': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'link-leave': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'end-of-word': (gobject.SIGNAL_RUN_LAST, None, ()),
		'end-of-line': (gobject.SIGNAL_RUN_LAST, None, ()),

		# Override clipboard interaction
		#~ 'copy-clipboard': 'override',
		#~ 'cut-clipboard': 'override',
		#~ 'paste-clipboard': 'override',

		# And some events we want to connect to
		'motion-notify-event': 'override',
		'visibility-notify-event': 'override',
		'button-release-event': 'override',
		'key-press-event': 'override',
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
				self.click_link(iter) or self.get_buffer().toggle_checkbox(iter)
			elif event.button == 3:
				self.get_buffer().toggle_checkbox(iter, XCHECKED_BOX)
		return cont # continue emit ?

	def do_key_press_event(self, event):
		# Returns boolean whether we handled the event or it should continue to emit
		# Key bindings in standard input mode:
		#   Tab at start of line indents line
		#   Shift-Tab and optionally Backspace at start of line unindent line
		#   Space, Tab and some other characters trigger word autoformatting
		#   Enter triggers line autoformatting
		#   Home toggles between real home and start of first word
		# See below fro read-only mode and selection mode
		handled = True
		buffer = self.get_buffer()
		print 'KEY %s (%i)' % (gtk.gdk.keyval_name(event.keyval), event.keyval)
		#~ if readonly TODO
			#~ handled = self._do_key_press_event_readonly(event)
		#~ elif
		if buffer.get_has_selection():
			handled = self._do_key_press_event_selection(event)
		elif event.state & gtk.gdk.SHIFT_MASK and event.keyval in (KEYVAL_TAB, KEYVAL_BACKSPACE):
			#~ if setting and event.keyval == KEYVAL_BACKSPACE:
				#~ handled = False
			#~ else:
			iter = buffer.get_iter_at_mark(buffer.get_insert())
			realhome, ourhome = self.get_home_positions(iter)
			if iter.compare(ourhome) == 1: # iter beyond home position
				handled = False
			else:
				iter = buffer.get_iter_at_line(iter.get_line())
				buffer.decrement_indent(iter)
		elif event.keyval == KEYVAL_TAB:
			iter = buffer.get_iter_at_mark(buffer.get_insert())
			realhome, ourhome = self.get_home_positions(iter)
			if iter.compare(ourhome) == 1: # iter beyond home position
				self.emit('end-of-word')
				handled = False
			else:
				iter = buffer.get_iter_at_mark(buffer.get_insert())
				iter = buffer.get_iter_at_line(iter.get_line())
				buffer.increment_indent(iter)
		elif event.keyval in KEYVALS_END_OF_WORD:
			self.emit('end-of-word')
			handled = False
		elif event.keyval == KEYVAL_ENTER:
			buffer = self.get_buffer()
			iter = buffer.get_iter_at_mark(buffer.get_insert())
			link = buffer.get_link_data(iter)
			if link:
				# if setting follow link on enter FIXME
				self.click_link(iter)
			else:
				self.emit('end-of-line')
				handled = False
		elif event.keyval == KEYVAL_HOME and not event.state & gtk.gdk.CONTROL_MASK:
			insert = buffer.get_iter_at_mark(buffer.get_insert())
			realhome, ourhome = self.get_home_positions(insert)
			if insert.equal(ourhome): iter = realhome
			else: iter = ourhome
			if event.state & gtk.gdk.SHIFT_MASK:
				buffer.move_mark_by_name('insert', iter)
			else:
				buffer.place_cursor(iter)
		else:
			handled = False

		if handled:
			return True
		else:
			return gtk.TextView.do_key_press_event(self, event)

	def _do_key_press_event_readonly(self, event):
		# Key bindings in read-only mode:
		#   / open searchs box
		#   Space scrolls one page
		#   Shift-Space scrolls one page up
		return False
		# TODO key bindings for read-only
		#~ handled = True
		#~ if key == '/':
			#~ self.begin_find()
		#~ elif key == ' ':
			#~ if shift_mask: i = -1
		#~ else: i = 1
			#~ self.emit('move-cursor', gtk.MOVEMENT_PAGES, i, False)
		#~ else:
			#~ handled = False
		#~ return handled

	def _do_key_press_event_selection(self, event):
		# Key bindings when there is an active selections:
		#   Tab indents whole selection
		#   Shift-Tab and optionally Backspace unindent whole selection
		#   * Turns whole selection in bullet list
		#   > Quotes whole selection with '>'
		handled = True
		buffer = self.get_buffer()
		if event.state & gtk.gdk.SHIFT_MASK and event.keyval in (KEYVAL_TAB, KEYVAL_BACKSPACE):
			#~ if setting and event.keyval == KEYVAL_BACKSPACE:
				#~ handled = False
			#~ else:
			buffer.foreach_line_in_selection(buffer.decrement_indent)
		elif event.keyval == KEYVAL_TAB:
			buffer.foreach_line_in_selection(buffer.increment_indent)
		elif event.keyval == KEYVAL_ASTERISK:
			buffer.foreach_line_in_selection(lambda i: buffer.insert(i, u'\u2022 '))
		elif event.keyval == KEYVAL_GT:
			buffer.foreach_line_in_selection(lambda i: buffer.insert(i, '> '))
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

	def do_end_of_word(self):
		print 'End Of Word'

	def do_end_of_line(self):
		print 'End Of Line'

# Need to register classes defining gobject signals
gobject.type_register(TextView)


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

	# Actions can be grouped on the stack by putting them inside lists. These lists
	# will be undone / redone recursively as single actions. When recording a group
	# will start and stop with the begin-user-action and end-user-action signals.
	# By definition these signals will not be emitted if a group is open already, so
	# groups will not be nested inside each other. However folding* the stack can result
	# in nested groups, so these should be handled transparently.

	# *) Folding: if the user presses undo a few times and starts typing we "fold" the
	#    actions that are on the redo stack into the undo stack. So this content is not
	#    dropped. Pressing undo again will first undo the typing, then undo (or redo) the
	#    previous undo actions and then proceed undoing the rest of the stack.
	#	FIXME: nice ascii diagram of how folding of the undo stack works...

	# Each interactive action (e.g. every single key stroke) is wrapped in a set of
	# begin-user-action and end-user-action signals. We use these signals to group actions.
	# This implies that any sequence on non-interactive actions will also end up in a
	# single group. An interactively created group consisting of a single character insert
	# or single character delete is a candidate for merging*.

	# *) Merging: grouping various small actions into a meaningful action automatically.
	#    In this case we merge single character inserts into words so undo is a bit faster
	#    then just undoing one character at the time.

	def __init__(self, textbuffer):
		self.buffer = textbuffer
		self.stack = [] # stack of actions & action groups
		self.group = [] # current group of actions
		self.can_merge = False # can we merge interactive key strokes to head of stack ?
		self.undo_count = 0 # number of undo steps that were done
		self.block_count = 0 # number of times block() was called

		self.recording_handlers = [] # handlers to be blocked when not recording
		for signal, handler in (
			('insert-text', self.do_insert_text),
			('inserted-tree', self.do_insert_tree),
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
				self.buffer.connect(signal, self.do_change_tag, data=action) )

		self.buffer.connect_object('begin-insert-tree',
			self.__class__.block, self)
		self.buffer.connect_object('end-insert-tree',
			self.__class__.unblock, self)

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
				self.buffer.block_handler(id)
		self.block_count += 1

	def unblock(self):
		# blocking / unblocking does not affect the state - just "pause"
		if self.block_count > 1:
			self.block_count -= 1
		else:
			for id in self.recording_handlers:
				self.buffer.unblock_handler(id)
			self.block_count = 0

	def begin_user_action(self):
		'''Start a group of actions that will be undone / redone as a single action'''
		if self.group:
			self._flush_insert()
			self.stack.append(self.group)
			self.group = []
			self.can_merge = False # content was entered non-interactive, so can't merge

			while len(self.stack) > MAX_UNDO:
				self.stack.pop(0)
		elif self.undo_count > 0:
			self._flush_redo_stack()
		else:
			pass

	def end_user_action(self):
		'''End a group of actions that will be undone / redone as a single action'''
		if self.group:
			self._flush_insert()
			merged = False
			if len(self.group) == 1 \
				and self.group[0][0] in (self.ACTION_INSERT, self.ACTION_DELETE) \
				and self.group[0][1] - self.group[0][2] == 1:
				can_merge = self.group[0][0] # ACTION_INSERT or ACTION_DELETE
				if can_merge == self.can_merge:
					self.stack[-1].extend(self.group) # TODO more intelligent merging ?
			else:
				can_merge = False

			if not merged:
				self.stack.append(self.group)
			self.group = []
			self.can_merge = can_merge

			while len(self.stack) > MAX_UNDO:
				self.stack.pop(0)
		else:
			pass

	def do_inserted_tree(self, buffer, start, end, parsetree):
		if self.undo_count > 0: self._flush_redo_stack()

		start, end = start.get_offset(), end.get_offset()
		self.group.append((self.ACTION_INSERT, start, end, tree))

	def do_insert_text(self, buffer, end, text, length):
		# Do not use length argument, it seems not to understand unicode
		if self.undo_count > 0: self._flush_redo_stack()

		start = end.copy()
		start.backward_chars(lenght)
		start, end = start.get_offset(), end.get_offset()
		self.group.append((self.ACTION_INSERT, start, end, None))

	def _flush_insert(self):
		# For insert actually getting the tree is delayed when possible
		for i in range(len(self.group)):
			if self.group[i][0] == self.ACTION_INSERT and self.group[i][3] is None:
				start = self.buffer.get_iter(self.group[i][1])
				end = self.buffer.get_iter(self.group[i][2])
				tree = self.buffer.get_parsetree(start, end)
				self.group[i] = (self.ACTION_INSERT, self.group[i][1], self.group[i][2], tree)

	def do_delete_range(self, buffer, start, end):
		if self.undo_count > 0: self._flush_redo_stack()
		elif self.group: self._flush_insert()

		tree = self.buffer.get_parsetree(start, end)
		start, end = start.get_offset(), end.get_offset()
		self.group.append((self.ACTION_DELETE, start, end, tree))

	def do_change_tag(self, buffer, tag, start, end, action):
		assert action in (self.ACTION_APPLY_TAG, self.ACTION_REMOVE_TAG)
		if not hasattr(tag, 'zim_type'):
			return

		if self.undo_count > 0: self._flush_redo_stack()

		start, end = start.get_offset(), end.get_offset()
		if self.group and self.group[-1][0] == self.ACTION_INSERT \
			and self.group[-1][1:] == (start, end, None):
			pass # for text that is not yet flushed tags will be in the tree
		else:
			if self.group: self._flush_insert()
			self.group.append((action, start, end, tag))

	def undo(self):
		'''Undo one user action'''
		assert not self.group, 'BUG: interactive action not ended before undo() was called'
		l = len(self.stack)
		if self.undo_count == l:
			return False
		else:
			self.undo_count += 1
			i = l - self.undo_count
			self._do_action(self._reverse_action(self.stack[i]))
			return True

	def _flush_redo_stack(self):
		# fold stack so no data is lost, each undo step can now be undone
		assert not self.group, 'BUG: interactive action not ended before starting new action'
		i = len(self.stack) - self.undo_count
		fold = self._reverse_action(self.stack[i:])
		self.stack = self.stack[:i]
		self.stack.extend(fold)
		self.undo_count = 0

	def redo(self):
		'''Redo one user action'''
		assert not self.group, 'BUG: interactive action not ended before redo() was called'
		if self.undo_count == 0:
			return False
		else:
			i = len(self.stack) - self.undo_count
			self.undo_count += 1
			self._do_action(self.stack[i])
			return True

	def _reverse_action(self, action):
		if isinstance(action, list): # group
			action = map(self._reverse_action, reversed(action)) # recurs
		else:
			# constants are defined such that negating them reverses the action
			action = (-action[0],) + action[1:]
		return action

	def _do_action(self, action):
		self.block()

		if isinstance(action, list): # group
			for a in action:
				self._do_action(a) # recurs
		else:
			act, start, end, data = action
			start = self.buffer.get_iter_at_offset(start)
			end = self.buffer.get_iter_at_offset(end)

			if act == self.ACTION_INSERT:
				self.buffer.insert_tree(start, tree)
			elif act == self.ACTION_DELETE:
				self.buffer.delete(start, end)
				# TODO - assert that deleted content matches what is on the stack ?
			elif act == self.ACTION_APPLY_TAG:
				self.buffer.apply_tag(data, start, end)
			elif act == self.ACTION_REMOVE_TAG:
				self.buffer.remove_tag(data, start, end)
			else:
				assert False, 'BUG: unknown action type'

		self.unblock()


class PageView(gtk.VBox):
	'''FIXME'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'modified-changed': (gobject.SIGNAL_RUN_LAST, None, ()),
	}


	def __init__(self, ui):
		self.ui = ui
		gtk.VBox.__init__(self)
		self.page = None
		self.undostack = None
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

		self.load_styles()

		self.ui.connect('open-notebook', self.on_open_notebook)

	def grab_focus(self):
		self.view.grab_focus()

	def load_styles(self):
		'''Load and parse the style config file'''
		style = config_file('style.conf')
		testbuffer = gtk.TextBuffer()
		for tag in [k[4:] for k in style.keys() if k.startswith('Tag ')]:
			try:
				assert tag in TextBuffer.tag_styles, 'No such tag: %s' % tag
				attrib = style['Tag '+tag].copy()
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

		for s in ('page-updated', 'page-deleted', 'page-moved'):
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
		self._prev_buffer.delete(*self._prev_buffer.get_bounds())

		# now create the new buffer
		self.page = page
		buffer = TextBuffer()
		self.view.set_buffer(buffer)
		tree = page.get_parsetree()
		page.set_ui_object(self)

		cursorpos = 0
		if tree is None:
			# TODO check read-only
			template = self.ui.notebook.get_template(page)
			tree = template.process_to_parsetree(self.ui.notebook, page)
			cursorpos = -1
		self.set_parsetree(tree)
		if cursorpos != -1:
			buffer.place_cursor(buffer.get_iter_at_offset(cursorpos))
		# TODO else check template for cursor pos ??

		buffer.connect('textstyle-changed', self.do_textstyle_changed)
		buffer.connect('modified-changed',
			lambda o: self.on_modified_changed(o))

		#~ self.undostack = UndoStackManager(buffer)

	def get_page(self): return self.page

	def on_modified_changed(self, buffer):
		# one-way traffic, set page modified after modifying the buffer
		# but not the other way
		if buffer.get_modified() and not self.page.modified:
			self.page.modified = True
			self.emit('modified-changed')

	def get_parsetree(self):
		buffer = self.view.get_buffer()
		if buffer.get_modified():
			self._parsetree = buffer.get_parsetree()
			buffer.set_modified(False)
		return self._parsetree

	def set_parsetree(self, tree):
		buffer = self.view.get_buffer()
		assert not buffer.get_modified(), 'BUG: changing parsetree while buffer was changed as well'
		tree.resolve_images(self.ui.notebook, self.page)
			# TODO same for links ?
		buffer.set_parsetree(tree)
		self._parsetree = tree

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
				link['href'], self.page.get_parent())
			self.ui.open_page(path)
		elif type == 'file':
			path = self.ui.notebook.resolve_file(
				link['href'], self.page)
			self.ui.open_file(path)
		else:
			self.ui.open_url(link['href'])

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

	def edit_object(self):
		buffer = self.view.get_buffer()
		insert = buffer.get_iter_at_mark(buffer.get_insert())
		alt = insert.copy()
		alt.backward_char()
		if buffer.get_image_data(insert) or buffer.get_image_data(alt):
			EditImageDialog(self.ui, buffer, self.page).run()
		elif buffer.get_link_tag(insert):
			EditLinkDialog(self.ui, buffer, self.page).run()
		else:
			return False

	def insert_image(self, file=None, interactive=True):
		if interactive:
			InsertImageDialog(self.ui, self.view.get_buffer(), self.page, file).run()
		else:
			assert isinstance(file, File)
			src = self.ui.notebook.relative_filepath(file, self.page) or file.uri
			print 'SRC', src
			self.view.get_buffer().insert_image_at_cursor(file, src)

	def insert_text_from_file(self):
		InsertTextFromFileDialog(self.ui, self.view.get_buffer(), self.page).run()

	def insert_external_link(self):
		InsertExternalLinkDialog(self.ui, self.view.get_buffer(), self.page).run()

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
		buffer.begin_user_action()
		if buffer.get_has_selection():
			start, end = buffer.get_selection_bounds()
			self.buffer.delete(start, end)
		for link in links:
			buffer.insert_link_at_cursor(link, link)
			buffer.insert_at_cursor(sep)
		buffer.end_user_action()

	def insert_link(self):
		InsertLinkDialog(self.ui, self.view.get_buffer(), self.page).run()

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
		#~ elif not self.ui.preferences['autoselect']:
			#~ return False
		else:
			return buffer.select_word()

# Need to register classes defining gobject signals
gobject.type_register(PageView)


class InsertImageDialog(FileDialog):

	def __init__(self, ui, buffer, path, file=None):
		FileDialog.__init__(
			self, ui, 'Insert Image', gtk.FILE_CHOOSER_ACTION_OPEN)
		self.buffer = buffer
		self.path = path
		self.add_filter_images()
		if file:
			self.set_file(file)
		# TODO custom 'insert' button ?

	def do_response_ok(self):
		file = self.get_file()
		if file is None: return False
		src = self.ui.notebook.relative_filepath(file, self.path) or file.uri
		self.buffer.insert_image_at_cursor(file, src)
		return True


class EditImageDialog(Dialog):

	def __init__(self, ui, buffer, path):
		Dialog.__init__(self, ui, 'Edit Image')
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

	def __init__(self, ui, buffer, path):
		Dialog.__init__(self, ui, 'Insert Link')
		self.buffer = buffer
		self.path = path

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
		#~ elif self.ui.preferences['autoselect']:
		else:
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
			href = self.ui.notebook.relative_filepath(file, self.path) or file.uri

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

	def __init__(self, ui, buffer, path):
		Dialog.__init__(self, ui, 'Insert External Link')
		self.buffer = buffer
		self.path = path

		href, text = self._get_link()
		self.add_fields([
			('href', 'file', 'Link to', href),
			('text', 'string', 'Text', text)
		])
		# TODO custom "link" button


class EditLinkDialog(InsertLinkDialog):

	def __init__(self, ui, buffer, path):
		Dialog.__init__(self, ui, 'Edit Link')
		self.buffer = buffer
		self.path = path

		href, text = self._get_link()
		type = link_type(href)
		if type == 'file': input = 'file'
		else: input = 'page'
		self.add_fields([
			('href', input, 'Link to', href),
			('text', 'string', 'Text', text)
		])
		# TODO custom "link" button
