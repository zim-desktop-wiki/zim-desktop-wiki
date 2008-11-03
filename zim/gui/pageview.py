# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

# TODO: figure out how to connect signals for self
#       connecting do_insert_text in create_tags() seems wrong

import gtk
import pango


class TextView(gtk.TextView):
	'''FIXME'''


class TextBuffer(gtk.TextBuffer):
	'''FIXME'''

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
		'a':      {'foreground': 'blue'},
	}

	def create_tags(self):
		'''FIXME'''
		for k, v in self.tag_styles.items():
			self.create_tag(k, **v)
		self.connect_after('insert-text', self.do_insert_text)

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
		# Remember cursor position and restore afterwards
		mark = self.create_mark(
			'zim-insert-parsetree-orig-insert',
			self.get_iter_at_mark(self.get_insert()), True)
		self.place_cursor(iter)
		self.insert_parsetree_at_cursor(tree)
		self.place_cursor(self.get_iter_at_mark(mark))
		self.delete_mark(mark)

	def insert_parsetree_at_cursor(self, tree):
		'''FIXME'''
		self._insert_element_children(tree.getroot())

	def _insert_element_children(self, node):
		for element in node.getchildren():
			# set mode
			if element.tag == 'p':
				self._insert_element_children(element) # recurs
			elif element.tag == 'h':
				tag = 'h'+str(element.attrib['level'])
				self.set_textstyle(tag)
			elif element.tag == 'a':
				pass
			elif element.tag == 'img':
				#~ self.insert_image(element.attrib)
				continue # do not insert text
			elif element.tag in self.tag_styles:
				self.set_textstyle(element.tag)
			else:
				assert False, 'Unknown tag: %s' % element.tag

			if element.text:
				self.insert_at_cursor(element.text)
			self.set_textstyle(None)
			if element.tail:
				self.insert_at_cursor(element.tail)

	def set_textstyle(self, style):
		'''FIXME'''
		self.textstyle = style
		if not style is None:
			self.textstyle_tag = self.get_tag_table().lookup(style)
			assert self.textstyle_tag
		else:
			self.textstyle_tag = None
		# TODO: emit signal edit-mode-changed

	def do_insert_text(self, buffer, end, string, length):
		'''Signal handler for insert-text signal'''
		# Apply current text style
		if not self.textstyle_tag is None:
			start = end.copy()
			start.backward_chars(len(string))
			self.remove_all_tags(start, end)
			self.apply_tag(self.textstyle_tag, start, end)
		# TODO: record undo step


if __name__ == '__main__':
	import sys
	import zim.formats.wiki as format
	from zim.fs import *

	file = File(sys.argv[1])
	parser = format.Parser({})
	tree = parser.parse(file)

	buffer = TextBuffer()
	buffer.create_tags()
	buffer.set_parsetree(tree)

	view = TextView()
	view.set_buffer(buffer)

	scrolled = gtk.ScrolledWindow()
	scrolled.add(view)

	window = gtk.Window()
	window.set_default_size(500, 500)
	window.connect('delete-event', gtk.main_quit)
	window.add(scrolled)

	window.show_all()
	gtk.main()
