# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''


import gobject
import gtk
import pango


class TextView(gtk.TextView):
	'''FIXME'''


class TextBuffer(gtk.TextBuffer):
	'''Zim subclass of gtk.TextBuffer.

	This class manages the contents of a TextView widget. It can load a zim
	parsetree and after editing return a new parsetree. It manages images,
	links, bullet lists etc.

	TODO: manage undo stack
	TODO: manage rich copy-paste
	'''

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'insert-text': 'override',
		'textstyle-changed': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
	}

	# text tags supported by the editor and default stylesheet
	tag_styles = {
		'h1':     {'weight': pango.WEIGHT_BOLD, 'scale': 1.15**4},
		'h2':     {'weight': pango.WEIGHT_BOLD, 'scale': 1.15**3},
		'h3':     {'weight': pango.WEIGHT_BOLD, 'scale': 1.15**2},
		'h4':     {'weight': pango.WEIGHT_ULTRABOLD, 'scale': 1.15},
		'h5':     {'weight': pango.WEIGHT_BOLD, 'scale': 1.15, 'style': 'italic'},
		'h6':     {'weight': pango.WEIGHT_BOLD, 'scale': 1.15},
		'em':     {'style': 'italic'},
		'strong': {'weight': pango.WEIGHT_BOLD},
		'mark':   {'background': 'yellow'},
		'strike': {'strikethrough': 'true', 'foreground': 'grey'},
		'code':   {'family': 'monospace'},
		'pre':    {'family': 'monospace', 'wrap-mode': 'none'},
		'link':   {'foreground': 'blue'},
	}

	def __init__(self):
		'''FIXME'''
		gtk.TextBuffer.__init__(self)
		for k, v in self.tag_styles.items():
			self.create_tag(k, **v)

	def clear(self):
		'''FIXME'''
		self.set_textstyle(None)
		self.delete(*self.get_bounds())
		# TODO: also throw away undo stack

	def set_parsetree(self, tree):
		'''FIXME'''
		# TODO: this insert should not be recorded by undo stack
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

	def _insert_element_children(self, node):
		# FIXME: should block textstyle-changed here for performance
		for element in node.getchildren():
			if element.tag in ('p', 'link', 'img'):
				# Blocks and object
				if element.tag == 'p':
					if element.text:
						self.insert_at_cursor(element.text)
					self._insert_element_children(element) # recurs
				elif element.tag == 'link':
					self.insert_link_at_cursor(element.attrib, element.text)
				elif element.tag == 'img':
					self.insert_image_at_cursor(element.attrib, element.text)

				if element.tail:
					self.insert_at_cursor(element.tail)
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

	def insert_link(self, iter, attrib, text):
		'''FIXME'''
		self._place_cursor(iter)
		self.insert_link_at_cursor(attrib, text)
		self._restore_cursor()

	def insert_link_at_cursor(self, attrib, text):
		'''FIXME'''
		# TODO generate anonymous tags for links
		self.set_textstyle('link')
		self.insert_at_cursor(text)
		self.set_textstyle(None)

	def insert_image(self, iter, attrib, text):
		'''FIXME'''
		self._place_cursor(iter)
		self.insert_image_at_cursor(attrib, text)
		self._restore_cursor()

	def insert_image_at_cursor(self, attrib, text):
		'''FIXME'''
		# TODO support for images

	def set_textstyle(self, style):
		'''FIXME'''
		self.textstyle = style
		if not style is None:
			self.textstyle_tag = self.get_tag_table().lookup(style)
			assert self.textstyle_tag
		else:
			self.textstyle_tag = None
		self.emit('textstyle-changed')

	def do_insert_text(self, end, string, length):
		'''Signal handler for insert-text signal'''
		# First call parent for the actual insert
		gtk.TextBuffer.do_insert_text(self, end, string, length)

		# Apply current text style
		if not self.textstyle_tag is None:
			start = end.copy()
			start.backward_chars(len(string))
			self.remove_all_tags(start, end)
			self.apply_tag(self.textstyle_tag, start, end)

		# TODO: record undo step


# Need to register classes defining gobject signals
gobject.type_register(TextBuffer)
gobject.type_register(TextView)


class PageView(gtk.VBox):
	'''FIXME'''

	def __init__(self):
		gtk.VBox.__init__(self)
		self.view = TextView()
		swindow = gtk.ScrolledWindow()
		swindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
		swindow.add(self.view)
		self.add(swindow)

	def set_page(self, page):
		tree = page.get_parsetree()
		buffer = TextBuffer()
		buffer.set_parsetree(tree)
		self.view.set_buffer(buffer)
