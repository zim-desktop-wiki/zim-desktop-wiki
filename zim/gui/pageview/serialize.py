# Copyright 2008-2024 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains functions to serialize L{TextBuffer} content

NOTE: This type of serialization should only be used for representation
of C{TextBuffer} contents in classes directly related to the C{TextBuffer}
and for testing purposes. All other parsing should us C{ParseTree} instead.
'''

import re
import logging

logger = logging.getLogger('zim.gui.pageview')


from zim.plugins import PluginManager
from zim.formats import IMAGE, OBJECT, ANCHOR, LINK, TAG, HEADING, LINE, TABLE
from zim.parse.tokenlist import TEXT, END, collect_until_end_token
from zim.parse.xml import simple_token_to_xml_dumper, simple_xml_to_token_parser

from .constants import PIXBUF_CHR, BULLETS_FROM_STOCK, ICON, BLOCK, LISTITEM
from .objectanchors import InsertedObjectAnchor, LineSeparatorAnchor
from .textbuffer import _is_inline_nesting_tag

__all__ = ('textbuffer_internal_insert_at_cursor', 'textbuffer_internal_serialize_range', 'TextBufferInternalContents')

_INTERNAL_ROOT = 'zim-textbuffer'
_INTERNAL_OBJECT_LIKE_TAGS = (IMAGE, ANCHOR, ICON, LINE) # These are not text ranges, but pixbuf / object anchor


from zim.parse.tokenlist import TokenBuilder
class MyBuilder(TokenBuilder):

	def data(self, data):
		self.text(data)


def _object_to_tag(objectanchor):
	# TODO - update object interface to do this without builder
	builder = MyBuilder()
	objectanchor.dump(builder)
	tokens = builder._tokens
	if tokens[0][0] == LINE:
		return [(LINE, None)]
	elif tokens[0][0] == TABLE:
		return tokens
	else:
		assert tokens[0][0] == OBJECT
		if len(tokens) > 3:
			data = ''.join(t[1] for t in tokens[1:-1])
			tokens = [tokens[0], (TEXT, data), tokens[-1]]
		return tokens


class TextBufferInternalContents():
	'''Container object for "raw" textbuffer content serialization

	The key difference between the content in this object and the content in
	a L{ParseTree} object is that this object is intended to exaxtly reproduce
	the L{TextBuffer} contents even if it contains semantic errors. This is 
	relevant specifically for undo/redo actions that should reproduce the 
	exact state of the buffer. The 	L{ParseTree} applies various filters and
	cleans up errors where possible and therefore is a much more stable and 
	clean interface to the document contents.

	NOTE: This type of serialization should only be used for representation
	of C{TextBuffer} contents in classes directly related to the C{TextBuffer}
	and for testing purposes. All other parsing should us C{ParseTree} instead.
	
	**The content of this class is not considered stable for outside APIs.**
	'''

	__slots__ = ('_data',)

	def __init__(self, data):
		self._data = data

	def __eq__(self, data):
		return self.__class__ == data.__class__ and self._data == data._data

	def __repr__(self):
		return '<%s %r>' % (self.__class__.__name__, self._data)

	def __str__(self):
		return self.to_xml()

	@classmethod
	def new_from_xml(cls, xml):
		'''Convert xml-like to object instance
		
		NOTE: Inteded for test cases only, do not use in the application - 
		not robust / un-save for external or mal-formed context
		'''
		data = []
		token_iter = simple_xml_to_token_parser(xml)
		for t in token_iter:
			if t[0] in (TEXT, END):
				data.append(t)
			else:
				data.append(t)
				if t[0] in _INTERNAL_OBJECT_LIKE_TAGS:
					# skip end tag
					end = next(token_iter)
					assert end == (END, t[0]), 'Expected %s got %s' % ((END, t[0]), end)

		if data[0][0] == _INTERNAL_ROOT:
			data = data[1:-1]
		return cls(data)

	def to_xml(self):
		'''Convert obejct contents to xml-like
		
		NOTE: Inteded for test cases only, do not use in the application - 
		not robust / un-save for external or mal-formed context
		'''	
		xml = simple_token_to_xml_dumper(
			self._data,
			tags_without_end_tag=_INTERNAL_OBJECT_LIKE_TAGS
		)
		return '<%s>%s</%s>' % (_INTERNAL_ROOT, xml, _INTERNAL_ROOT)



_is_zim_tag = lambda tag: hasattr(tag, 'zim_tag')


def textbuffer_internal_serialize_range(textbuffer, start, end):
	'''Function that returns a C{TextBufferInternalContents} object
	
	Basic serialization is in terms of TextTags, PixBufs and TextChildAnchors
	These are represented as tokens where TextTags have a start and an end token
	and text, pixbufs and anchors are represented as single tokens

	This method does not enforce zim's semantic rules becaues it is used for 
	direct representation of the buffer, including errors.

	The only logic it applies is the hierarchic nesting of TextTags to allow 
	a stable xml-like representation.
	'''
	textbuffer_data = []
	texttags_stack = [] # list of (texttag, zimtag)

	iter = start.copy()
	while iter.compare(end) == -1:
		open_tags = list(filter(_is_zim_tag, iter.get_tags()))
		if iter.equal(start):
			textbuffer_data.extend(
				_init_texttags_stack(texttags_stack, iter, open_tags) )
		else:
			textbuffer_data.extend(
				_update_texttags_stack(texttags_stack, iter, open_tags) )

		pixbuf = iter.get_pixbuf()
		anchor = iter.get_child_anchor()
		if pixbuf:
			assert hasattr(pixbuf, 'zim_type')
			textbuffer_data.append((pixbuf.zim_type, pixbuf.zim_attrib.copy()))
			iter.forward_char()
		elif anchor:
			assert isinstance(anchor, InsertedObjectAnchor)
			textbuffer_data.extend(_object_to_tag(anchor))
			iter.forward_char()
		else:
			# Find biggest slice without tags being toggled
			bound = iter.copy()
			toggled = []
			while not toggled:
				if not bound.is_end() and bound.forward_to_tag_toggle(None):
					# For some reason the not is_end check is needed to prevent an odd corner case infinite loop
					toggled = list(filter(_is_zim_tag, bound.get_toggled_tags(False) + bound.get_toggled_tags(True)))
						# breaks if toggle was indeed zim tag, else continue loop
				else:
					bound = end.copy() # just to be sure..
					break

			if bound.compare(end) == 1:
				bound = end.copy()

			# But limit slice to first pixbuf or embeddded widget
			text = iter.get_slice(bound)
			if PIXBUF_CHR in text[1:]:
				# Position 0 is a special case - we see this char, 
				# but get_pixbuf already returned None, so it must be taken literal
				i = 1 + text[1:].index(PIXBUF_CHR)
				bound = iter.copy()
				bound.forward_chars(i)
				text = text[:i]

			textbuffer_data.append((TEXT, text))
			iter = bound

	# close any open tags
	if texttags_stack:
		textbuffer_data.extend([(END, t[1]) for t in reversed(texttags_stack)])
	
	return TextBufferInternalContents(textbuffer_data)


def _init_texttags_stack(texttags_stack, iter, texttags):
	# Like _update_texttags_stack but for initalizing the stack
	# at the starting iter. This is subtly different from update because
	# sorting of inline tags also needs to look backward.
	# While updating this backward information is preserved on the stack
	tokens = []

	texttags.sort(key=lambda t: t.get_priority())
	if any(_is_inline_nesting_tag(t) for t in texttags):
		texttags = _sort_nesting_style_tags_for_init(iter, texttags)

	# Open tags
	for texttag in texttags:
		tag = texttag.zim_tag
		attrib = texttag.zim_attrib.copy() if texttag.zim_attrib else None
		tokens.append((tag, attrib))
		texttags_stack.append((texttag, tag))

	return tokens


def _update_texttags_stack(texttags_stack, iter, texttags):
	# This is a helper function that compares TextTags at a given iter with the 
	# stack of open tags. It updates the stack and returns open/close tokens
	# that reflect the change.
	#
	# It takes care of sorting stability of that tags which implies semantic
	# logic for how zim uses these tags.
	tokens = []

	texttags.sort(key=lambda t: t.get_priority())
	if any(_is_inline_nesting_tag(t) for t in texttags):
		texttags = _sort_nesting_style_tags_for_update(iter, texttags, [t[0] for t in texttags_stack])

	# Compare tags with stack
	i = 0
	while i < len(texttags) and i < len(texttags_stack) \
		and texttags[i] == texttags_stack[i][0]:
			i += 1

	# Close tags
	while len(texttags_stack) > i:
		tokens.append((END, texttags_stack[-1][1]))
		texttags_stack.pop()

	# Open tags
	for texttag in texttags[i:]:
		tag = texttag.zim_tag
		attrib = texttag.zim_attrib.copy() if texttag.zim_attrib else None
		tokens.append((tag, attrib))
		texttags_stack.append((texttag, tag))

	return tokens


def _sort_nesting_style_tags_for_init(iter, new_texttags):
	new_block, new_nesting, new_leaf = _split_nesting_style_tags(new_texttags)

	def tag_start_close_pos(tag):
		if iter.starts_tag(tag):
			start = iter.get_offset()
		else:
			my_iter = iter.copy()
			my_iter.backward_to_tag_toggle(tag)
			start = my_iter.get_offset()

		my_iter = iter.copy()
		my_iter.forward_to_tag_toggle(tag)
		end = my_iter.get_offset()
		return (start, end)

	new_nesting.sort(key=tag_start_close_pos, reverse=True)

	return new_block + new_nesting + new_leaf


def _sort_nesting_style_tags_for_update(iter, new_texttags, open_texttags):
	# This helper function figures out the sorting of style tags that have the same priority.
	# Tags that start earlier obviously go first. Of all tags opening at the same time, those 
	# which run longest get opened first - this way we optimize for longest stretch without breaks.
	new_block, new_nesting, new_leaf = _split_nesting_style_tags(new_texttags)
	open_block, open_nesting, open_leaf = _split_nesting_style_tags(open_texttags)
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
		return my_iter.get_offset()

	new_nesting.sort(key=tag_close_pos, reverse=True)
	sorted_new_nesting += new_nesting

	return new_block + sorted_new_nesting + new_leaf


def _split_nesting_style_tags(texttags):
	# Helper function to split a set of texttags in block level, nesting and leaf tags
	# This applies semantic knowledge on the tag interpretation
	block, nesting = [], []
	while texttags and not _is_inline_nesting_tag(texttags[0]):
		block.append(texttags.pop(0))
	while texttags and _is_inline_nesting_tag(texttags[0]):
		nesting.append(texttags.pop(0))
	return block, nesting, texttags


def textbuffer_internal_insert_at_cursor(textbuffer, data):
	'''Function that inserts L{TextBufferInternalContents} into a L{TextBuffer}'''
	interactive = False
	textbuffer.emit('begin-insert-tree', interactive)

	textbuffer._editmode_tags = [] # low level insert method, no carry over of open tags
	texttag_stack = []
	
	token_iter = iter(data._data)
	for t in token_iter:
		if t[0] == TEXT:
			textbuffer.insert_at_cursor(t[1])
		
		# Pixbuf types
		elif t[0] == IMAGE:
			textbuffer.insert_image_at_cursor(None, **t[1]) # TODO - should we use _file to store actual file object in attrib
		elif t[0] == ANCHOR:
			textbuffer.insert_anchor_at_cursor(**t[1])
		elif t[0] == ICON:
			bullet = BULLETS_FROM_STOCK[t[1]['stock']] # TODO low level function that takes stock
			textbuffer._insert_bullet_at_cursor(bullet)

		# InsertedObject
		elif t[0] == LINE:
			anchor = LineSeparatorAnchor()
			textbuffer.insert_objectanchor_at_cursor(anchor)
		elif t[0] == OBJECT:
			attrib = t[1].copy()
			data = ''
			for t in token_iter:
				if t[0] == TEXT:
					data += t[1]
				else:
					assert t == (END, OBJECT), 'Expected end of object, got: %r' % t
					break
			objecttype, model = textbuffer._get_objecttype_and_model_for_object(attrib, data or None)
			textbuffer._insert_object_model_at_cursor(objecttype, model)
		elif t[0] == TABLE:
			try:
				objecttype = PluginManager.insertedobjects['table']
			except KeyError:
				# HACK - if table plugin is not loaded - show table as plain text
				from zim.formats import ParseTree
				tree = ParseTree.new_from_tokens(tokens)
				lines = tree.dump('wiki')
				objecttype, model = textbuffer._get_objecttype_and_model_for_object({'type': 'table'}, ''.join(lines))
				textbuffer._insert_object_model_at_cursor(objecttype, model)
			else:
				tokens = collect_until_end_token(token_iter, TABLE)
				tokens.insert(0, t)
				model = objecttype.model_from_tokens(tokens)
				textbuffer._insert_object_model_at_cursor(objecttype, model)

		# TextTag types
		elif t[0] == END:
			assert texttag_stack and t[1] == texttag_stack[-1][0], 'Inconsistend closing tag: %r' % (t, )
			x, texttag = texttag_stack.pop()
			textbuffer._editmode_tags = [tt for tt in textbuffer._editmode_tags if tt is not texttag]
			if texttag.zim_tag == LINK:
				_postprocess_insert_link_tag(textbuffer.get_insert_iter(), texttag)
		else:
			if t[0] == LINK:
				texttag = _get_link_texttag(textbuffer.get_insert_iter())
				if texttag and texttag.zim_attrib == t[1]:
					pass # Continue open link tag
				else:
					texttag = textbuffer._create_link_tag('', **t[1])
			elif t[0] == TAG:
				texttag = textbuffer._create_tag_tag(None)
			elif t[0] == HEADING:
				texttag = textbuffer.get_tag_table().lookup('style-h' + str(t[1]['level']))
			elif t[0] == BLOCK:
				texttag = textbuffer._get_indent_tag(t[1]['indent'])
				# TODO: note from original insert function: We don't set the LTR / RTL direction here
				# instead we update all indent tags after the full
				# insert is done.
			elif t[0] == LISTITEM:
				texttag = textbuffer._get_indent_tag(t[1]['indent'], t[1]['style'])
				# TODO: note from original insert function: We don't set the LTR / RTL direction here
				# instead we update all indent tags after the full
				# insert is done.
			else:
				texttag = textbuffer.get_tag_table().lookup('style-' + t[0])

			if not texttag:
				raise AssertionError('Unknown internal data element: %r' % (t,))			
			texttag_stack.append((t[0], texttag))
			textbuffer._editmode_tags.append(texttag)

	if texttag_stack:
		logger.warn('Tags not closed on insert: %r' % texttag_stack)

	textbuffer.update_editmode() # Ensure we leave buffer ready for interactive editing
	textbuffer.emit('end-insert-tree')


def _get_link_texttag(startiter):
	# Like Textbuffer.get_link_tag() but with right gravity instead of left gravity
	texttags = list(startiter.get_tags()) + list(startiter.get_toggled_tags(False))
	for texttag in sorted(texttags, key=lambda i: i.get_priority()):
			if hasattr(texttag, 'zim_tag') and texttag.zim_tag == 'link':
				return texttag
	else:
		return None	


def _postprocess_insert_link_tag(enditer, texttag):
	# If the "href" attribute matches the text of the link it should
	# be set to `None` to flag that the href is "dynamic" and should 
	# change with the text. Otherwise the href is fixed regardless of 
	# text editing.
	
	# TODO: this logic is copy of logic in _create_link_tag -- refactor for re-use
	href = texttag.zim_attrib['href']
	if not href or href.isspace():
		texttag.zim_attrib['href'] = None
	else:
		startiter = enditer.copy()
		startiter.backward_to_tag_toggle(texttag)
		text = startiter.get_slice(enditer)
		if href == text:
			texttag.zim_attrib['href'] = None
