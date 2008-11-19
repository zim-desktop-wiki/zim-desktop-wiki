# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''


import gobject
import gtk
import pango

from zim import Component


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

	# define signals we want to use - (closure type, return type and arg types)
	__gsignals__ = {
		'insert-text': 'override',
		'textstyle-changed': (gobject.SIGNAL_RUN_LAST, None, ()),
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
			tag = self.create_tag('style-'+k, **v)
			tag.zim_type = 'style'
			tag.zim_style = k

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
		tag = self.create_tag(None, **self.tag_styles['link'])
		tag.zim_type = 'link'
		tag.zim_attrib = attrib
		self.set_textstyle('link', tag=tag)
		self.insert_at_cursor(text)
		self.set_textstyle(None)

	def get_link_data(self, iter):
		'''Returns the dict with link properties for a link at iter.
		Fails silently and returns None when there is no link at iter.
		'''
		for tag in iter.get_tags():
			try:
				if tag.zim_type == 'link':
					break
			except AttributeError:
				pass
		else:
			tag = None

		if tag:
			link = tag.zim_attrib.copy()
			if link['href'] is None:
				print 'TODO get tag text and use as href'
			return link
		else:
			return False

	def set_link_data(self, iter, attrib):
		'''Set the link properties for a link at iter. Will throw an exception
		if there is no link at iter.
		'''
		for tag in iter.get_tags():
			try:
				if tag.zim_type == 'link':
					# TODO check if href needs to be set to None again
					tag.zim_attrib = attrib
					break
			except AttributeError:
				pass
		else:
			raise Exception, 'No link at iter'

	def insert_image(self, iter, attrib, text):
		'''FIXME'''
		self._place_cursor(iter)
		self.insert_image_at_cursor(attrib, text)
		self._restore_cursor()

	def insert_image_at_cursor(self, attrib, text):
		'''FIXME'''
		# TODO support for images

	def set_textstyle(self, style, tag=None):
		'''Sets the current text style. This style will be applied
		to text inserted at the cursor. Use 'set_textstyle(None)' to
		reset to normal text.

		If tag is given it shoul dbe a TextTag object to be used.
		This is used for styles that use anonymous tags, e.g. links.
		'''
		self.textstyle = style
		if not style is None:
			if tag is None:
				tagname = 'style-'+style
				tag = self.get_tag_table().lookup(tagname)
			assert isinstance(tag, gtk.TextTag)
			self.textstyle_tag = tag
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

		# TODO: record undo steps

	def get_parsetree(self, bounds=None):
		'''FIXME'''
		if bounds is None:
			start, end = self.get_bounds()
		else:
			start, end = bounds

# Need to register classes defining gobject signals
gobject.type_register(TextBuffer)


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

	cursors = {
		'text':  gtk.gdk.Cursor(gtk.gdk.XTERM),
		'link':  gtk.gdk.Cursor(gtk.gdk.HAND2),
		'arrow': gtk.gdk.Cursor(gtk.gdk.LEFT_PTR),
	}

	def __init__(self):
		'''FIXME'''
		gtk.TextView.__init__(self)
		self.cursor = 'text'
		self.set_left_margin(10)
		self.set_right_margin(5)
		self.set_wrap_mode(gtk.WRAP_WORD)

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
				self.click_link(iter)
			elif event.button == 3:
				pass # TODO alternative click on checkbox
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

		if not link:
			pass # TODO check for pixbufs that are clickable

		if link: cursor = 'link'
		else:    cursor = 'text'

		if cursor != self.cursor:
			window = self.get_window(gtk.TEXT_WINDOW_TEXT)
			window.set_cursor(self.cursors[cursor])

		# Check if we need to emit any events for hovering
		# TODO: do we need similar events for images ?
		if self.cursor == 'link': # was over link before
			if cursor == 'link':
				pass
				#~ print 'TODO: check we are still over same link'
			else:
				self.emit('link-leave', link)
		elif cursor == 'link': # was not over link, but is now
			self.emit('link-enter', link)

		self.cursor = cursor

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

# Need to register classes defining gobject signals
gobject.type_register(TextView)


class PageView(gtk.VBox, Component):
	'''FIXME'''

	def __init__(self, app):
		self.app = app
		gtk.VBox.__init__(self)
		self.view = TextView()
		swindow = gtk.ScrolledWindow()
		swindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
		swindow.set_shadow_type(gtk.SHADOW_IN)
		swindow.add(self.view)
		self.add(swindow)

		self.view.connect_object('link-clicked', PageView.do_link_clicked, self)
		self.view.connect_object('link-clicked', PageView.do_link_enter, self)
		self.view.connect_object('link-clicked', PageView.do_link_leave, self)

	def set_page(self, page):
		tree = page.get_parsetree()
		buffer = TextBuffer()
		buffer.set_parsetree(tree)
		self.view.set_buffer(buffer)

	def do_link_enter(self, link):
		pass # TODO set statusbar

	def do_link_leave(self, link):
		pass # TODO set statusbar

	def do_link_clicked(self, link):
		self.app.open_link(link)
