# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''This module contains a number of custom gtk widgets
that are used in the zim gui modules.
'''

import gobject
import gtk


# Check the (undocumented) list of constants in gtk.keysyms to see all names
KEYVAL_LEFT = gtk.gdk.keyval_from_name('Left')
KEYVAL_RIGHT = gtk.gdk.keyval_from_name('Right')
KEYVALS_ASTERISK = (
	gtk.gdk.unicode_to_keyval(ord('*')), gtk.gdk.keyval_from_name('KP_Multiply'))
KEYVALS_SLASH = (
	gtk.gdk.unicode_to_keyval(ord('\\')),
	gtk.gdk.unicode_to_keyval(ord('/')), gtk.gdk.keyval_from_name('KP_Divide'))



class Button(gtk.Button):
	'''This class overloads the constructor of the default gtk.Button
	class. The purpose is to change the behavior in such a way that stock
	icon and label can be specified independently. If only stock or only
	label is given, it falls back to the default behavior of gtk.Button .
	'''

	def __init__(self, label=None, stock=None, use_underline=True):
		if label is None or stock is None:
			gtk.Button.__init__(self, label=label, stock=stock)
		else:
			gtk.Button.__init__(self, label=label)
			icon = gtk.image_new_from_stock(stock, gtk.ICON_SIZE_BUTTON)
			self.set_image(icon)
		self.set_use_underline(use_underline)


class IconButton(gtk.Button):
	'''Button with a stock icon, but no label.'''

	def __init__(self, stock, relief=True):
		gtk.Button.__init__(self)
		icon = gtk.image_new_from_stock(stock, gtk.ICON_SIZE_BUTTON)
		self.add(icon)
		self.set_alignment(0.5, 0.5)
		if not relief:
			self.set_relief(gtk.RELIEF_NONE)


class BrowserTreeView(gtk.TreeView):
	'''TreeView subclass intended for lists that are in "browser" mode.
	Default behavior will be single click navigation for these lists.

	Extra keybindings that are added here:
		<Left>   Collapse sub-items
		<Right>  Expand sub-items
		\        Collapse whole tree
		*        Expand whole tree
	'''

	# TODO some global option to restore to double click navigation ?

	def __init__(self, *arg):
		gtk.TreeView.__init__(self, *arg)
		self.get_selection().set_mode(gtk.SELECTION_BROWSE)

	def do_key_press_event(self, event):
		'''Handler for key-press-event, adds extra key bindings'''
		# Keybindings for the treeview:
		#  * expand all
		#  / or \ collapse all
		#  Right expand sub items
		#  Left collapse sub items
		handled = True
		#~ print 'KEY %s (%i)' % (gtk.gdk.keyval_name(event.keyval), event.keyval)

		if event.keyval in KEYVALS_ASTERISK:
			self.expand_all()
		elif event.keyval in KEYVALS_SLASH:
			self.collapse_all()
		elif event.keyval == KEYVAL_LEFT:
			model, iter = self.get_selection().get_selected()
			if not iter is None:
				path = model.get_path(iter)
				self.collapse_row(path)
		elif event.keyval == KEYVAL_RIGHT:
			model, iter = self.get_selection().get_selected()
			if not iter is None:
				path = model.get_path(iter)
				self.expand_row(path, 0)
		else:
			handled = False

		if handled:
			return True
		else:
			return gtk.TreeView.do_key_press_event(self, event)

	def do_button_release_event(self, event):
		'''Handler for button-release-event, implements single click navigation'''
		if event.button == 1:
			x, y = map(int, event.get_coords())
				# map to int to surpress deprecation warning :S
			path, column, x, y = self.get_path_at_pos(x, y)
			if self.get_selection().path_is_selected(path):
				self.row_activated(path, column)
				# This action is conditional on the path being selected
				# because otherwise we can not toggle the folding state
				# of a path without activating it. The assumption being
				# that the path gets selected on button press and then
				# gets activated on button release. Clicking the
				# expander in front of a path should not select the path.
				# This logic is based on particulars of the C implementation
				# and might not be future proof.
		elif event.button == 3:
			print 'TODO: context menu for page'

		return gtk.TreeView.do_button_release_event(self, event)


# Need to register classes defining / overriding gobject signals
gobject.type_register(BrowserTreeView)


class MenuButton(gtk.HBox):
	'''A button which pops up a menu when clicked. It behaves different from
	a combobox because it is not a selector and the label on the button is
	not a selected item from the menu. Main example of this widget type is the
	button with backlinks in the statusbar of the main window.

	This module is based loosely on gedit-status-combo-box.c from the gedit
	sources.
	'''

	# Set up a style for the statusbar variant to decrease spacing of the button
	gtk.rc_parse_string('''\
style "zim-statusbar-menubutton-style"
{
	GtkWidget::focus-padding = 0
	GtkWidget::focus-line-width = 0
	xthickness = 0
	ythickness = 0
}
widget "*.zim-statusbar-menubutton" style "zim-statusbar-menubutton-style"
''')

	def __init__(self, label, menu, status_bar_style=False):
		gtk.HBox.__init__(self)
		if isinstance(label, basestring):
			self.label = gtk.Label()
			self.label.set_markup_with_mnemonic(label)
		else:
			assert isinstance(label, gtk.Widget)
			self.label = label
		self.menu = menu
		self.button = gtk.ToggleButton()
		if status_bar_style:
			self.button.set_name('zim-statusbar-menubutton')
			self.button.set_relief(gtk.RELIEF_NONE)
		self.button.add(self.label)
		# We need to wrap stuff in an eventbox in order to get the gdk.Window
		# which we need to get coordinates when positioning the menu
		self.eventbox = gtk.EventBox()
		self.eventbox.add(self.button)
		self.add(self.eventbox)

		self.button.connect_object(
			'button-press-event', self.__class__.popup_menu, self)
		self._clicked_signal = self.button.connect_object(
			'clicked', self.__class__.popup_menu, self)

		# TODO reduce size of toggle-button - see gedit-status-combo for example
		# TODO looks like other statusbar items resize on toggle button

	def popup_menu(self, event=None):
		'''This method actually pops up the menu.
		Sub-calsses can overload and wrap it to populate the menu
		dynamically.
		'''
		if not self.get_property('sensitive'):
			return

		if event: # we came from button-press-event or similar
			button = event.button
			time = event.time
			if self.button.get_active():
				return
		else:
			button = 0
			time = gtk.get_current_event_time()

		self.button.handler_block(self._clicked_signal)
		self.button.set_active(True)
		self.button.handler_unblock(self._clicked_signal)
		self.menu.connect('deactivate', self._deactivate_menu)
		self.menu.show_all()
		self.menu.popup(None, None, self._position_menu, button, time)

	def _position_menu(self, menu):
		x, y = self.eventbox.window.get_origin()
		w, h = menu.get_toplevel().size_request()
		y -= h # make the menu pop above the button
		return x, y, False

	def _deactivate_menu(self, menu):
		self.button.handler_block(self._clicked_signal)
		self.button.set_active(False)
		self.button.handler_unblock(self._clicked_signal)

# Need to register classes defining / overriding gobject signals
gobject.type_register(MenuButton)
