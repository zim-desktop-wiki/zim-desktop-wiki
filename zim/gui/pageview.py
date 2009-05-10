# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import logging
import gobject
import gtk
import pango

from zim.notebook import Path
from zim.parsing import link_type
from zim.config import config_file

logger = logging.getLogger('zim.gui.pageview')


STOCK_CHECKED_BOX = 'zim-checked-box'
STOCK_UNCHECKED_BOX = 'zim-unchecked-box'
STOCK_XCHECKED_BOX = 'zim-xchecked-box'

bullet_types = {
	'checked-box': STOCK_CHECKED_BOX,
	'unchecked-box': STOCK_UNCHECKED_BOX,
	'xchecked-box': STOCK_XCHECKED_BOX,
}

ui_actions = (
	# name, stock id, label, accelerator, tooltip
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
		'textstyle-changed': (gobject.SIGNAL_RUN_LAST, None, (object,)),
		'indent-changed': (gobject.SIGNAL_RUN_LAST, None, (int,)),
	}

	# text tags supported by the editor and default stylesheet
	tag_styles = {
		'h1':       {'weight': pango.WEIGHT_BOLD, 'scale': 1.15**4},
		'h2':       {'weight': pango.WEIGHT_BOLD, 'scale': 1.15**3},
		'h3':       {'weight': pango.WEIGHT_BOLD, 'scale': 1.15**2},
		'h4':       {'weight': pango.WEIGHT_ULTRABOLD, 'scale': 1.15},
		'h5':       {'weight': pango.WEIGHT_BOLD, 'scale': 1.15, 'style': 'italic'},
		'h6':       {'weight': pango.WEIGHT_BOLD, 'scale': 1.15},
		'emphasis': {'style': 'italic'},
		'strong':   {'weight': pango.WEIGHT_BOLD},
		'mark':     {'background': 'yellow'},
		'strike':   {'strikethrough': 'true', 'foreground': 'grey'},
		'code':     {'family': 'monospace'},
		'pre':      {'family': 'monospace', 'wrap-mode': 'none'},
		'link':     {'foreground': 'blue'},
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
			tag.zim_style = k

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
				self.set_indent(list_level)
				if 'bullet' in element.attrib:
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
				self.insert_link_at_cursor(element.attrib, element.text)
			elif element.tag == 'img':
				self.insert_image_at_cursor(element.attrib, element.text)
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
		self._editmode_tags = self._editmode_tags + (tag,)
		self.insert_at_cursor(text)
		self._editmode_tags = self._editmode_tags[:-1]

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
		# TODO support width / height arguemnts from_file_at_size()
		# TODO parse image file locations elsewhere
		# TODO support tooltip text
		file = attrib['src-file']
		try:
			pixbuf = gtk.gdk.pixbuf_new_from_file(file.path)
		except:
			logger.warn('No such image: %s', file)
			widget = gtk.HBox() # FIXME need *some* widget here...
			pixbuf = widget.render_icon(gtk.STOCK_MISSING_IMAGE, gtk.ICON_SIZE_DIALOG)
		self.insert_pixbuf(iter, pixbuf)

	def insert_image_at_cursor(self, attrib, text):
		iter = self.get_iter_at_mark(self.get_insert())
		self.insert_image(iter, attrib, text)

	def insert_icon(self, iter, stock):
		widget = gtk.HBox() # FIXME need *some* widget here...
		pixbuf = widget.render_icon(stock, gtk.ICON_SIZE_MENU)
		if pixbuf is None:
			logger.warn('Could not find icon: %s', stock)
			pixbuf = widget.render_icon(gtk.STOCK_MISSING_IMAGE, gtk.ICON_SIZE_MENU)

		mark = self.create_mark('zim-tmp', iter, True)
		self.insert_pixbuf(iter, pixbuf)

		if not self.textstyle_tag is None:
			start = self.get_iter_at_mark(mark)
			end = start.copy()
			end.forward_char()
			self.remove_all_tags(start, end)
			self.apply_tag(self.textstyle_tag, start, end)

		self.delete_mark(mark)

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
		tags = self.get_tags(iter)
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

	def get_tags(self, iter):
		'''Like gtk.TextIter.get_tags() but only returns our own tags and
		assumes tags have "left gravity".
		'''
		tags = filter(
			lambda tag: hasattr(tag, 'zim_type') and not iter.begins_tag(tag),
			iter.get_tags() )
		tags.extend( filter(
			lambda tag: hasattr(tag, 'zim_type'),
			iter.get_toggled_tags(False) ))
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
		# test right gravity for start itere, but left gravity for end iter
		if tag in start.get_tags() \
		or tag in self.get_tags(end):
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
		pass

	def set_indent(self, level):
		'''Sets the current indent level. This style will be applied
		to text inserted at the cursor. Using 'set_indent(None)' is
		equivalent to 'set_indent(0)'.
		'''
		self._editmode_tags = filter(
			lambda tag: not tag.get_property('name').startswith('indent-'),
			self._editmode_tags)

		if level and level > 0:
			# TODO make number of pixels in indent configable (call this tabstop)
			name = 'indent-%i' % level
			tag = self.get_tag_table().lookup(name)
			if tag is None:
				margin = 10 + 30 * level-1 # offset from left side for all lines
				indent = -10 # offset for first line (bullet)
				tag = self.create_tag(name, left_margin=margin, indent=indent)
				tag.zim_type = 'indent'
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
		start = end.copy()
		start.backward_chars(len(string))
			# do not trust the given length, it does not understand unicode
		self.remove_all_tags(start, end)
		for tag in self._editmode_tags:
			self.apply_tag(tag, start, end)

	def get_parsetree(self, bounds=None):
		'''FIXME'''
		if bounds is None:
			start, end = self.get_bounds()
		else:
			start, end = bounds

	def get_has_selection(self):
		'''Returns boolean whether there is a selection or not.

		Method available in gtk.TextBuffer for gtk version >= 2.10
		reproduced here for backward compatibility.
		'''
		return bool(self.get_selection_bounds())

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
		gtk.TextView.__init__(self, TextBuffer())
		self.cursor = 'text'
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

		self.load_styles()

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

	def set_page(self, page):
		tree = page.get_parsetree()
		buffer = TextBuffer()
		if not tree is None:
			tree.resolve_images(self.ui.notebook, page)
				# TODO same for links ?
			buffer.set_parsetree(tree)
		else:
			print 'TODO get template'
		self.view.set_buffer(buffer)
		buffer.connect('textstyle-changed', self.do_textstyle_changed)
		buffer.place_cursor(buffer.get_iter_at_offset(0)) # FIXME

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
		logger.debug('Link clinked: %s: %s' % (type, link['href']))

		if type == 'page':
			path = self.ui.notebook.resolve_path(
				link['href'], Path(self.ui.page.namespace))
			self.ui.open_page(path)
		elif type == 'file':
			path = self.ui.notebook.resolve_file(
				link['href'], self.ui.page)
			print 'TODO: open_file(path)'
			#~ self.ui.open_file(path)
		else:
			print 'TODO: open_url(url)'

	def clear_formatting(self):
		buffer = self.view.get_buffer()

		# if self.ui.preferences['autoselect'] \
		#		and not buffer.get_has_selection() \
		#		and not buffer.textstyle == format:
		# 	buffer.select(TextBuffer.SELECT_WORD)

		if buffer.get_has_selection():
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

		# if self.ui.preferences['autoselect'] \
		#		and not buffer.get_has_selection() \
		#		and not buffer.textstyle == format:
		# 	buffer.select(TextBuffer.SELECT_WORD)

		buffer.toggle_textstyle(format)
