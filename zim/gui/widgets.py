# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''This module contains a number of custom gtk widgets
that are used in the zim gui modules.
'''

import gobject
import gtk


class Button(gtk.Button):
	'''This class overloads the constructor of the default gtk.Button
	class. The purpose is to change the behavior in such a way that stock
	icon and label can be specified independently. If only stock or only
	label is given, it falls back to the default behavior of gtk.Button .
	'''

	def __init__(self, label=None, stock=None, use_underline=True):
		if label is None or label is None:
			gtk.Button.__init__(self, label=label, stock=stock)
		else:
			gtk.Button.__init__(self)
			icon = gtk.image_new_from_stock(stock, gtk.ICON_SIZE_BUTTON)
			label = gtk.Label(label)
			label.set_use_underline(use_underline)
			hbox = gtk.HBox(spacing=2)
			hbox.add(icon)
			hbox.add(label)
			self.add(hbox)
			self.set_alignment(0.5, 0.5)


class IconButton(gtk.Button):
	'''Button with a stock icon, but no label.'''

	def __init__(self, stock):
		gtk.Button.__init__(self)
		icon = gtk.image_new_from_stock(stock, gtk.ICON_SIZE_BUTTON)
		self.add(icon)
		self.set_alignment(0.5, 0.5)


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
		if event.keyval == gtk.keysyms.Left:
			model, iter = self.get_selection().get_selected()
			if not iter is None:
				path = model.get_path(iter)
				self.collapse_row(path)
			return True
		elif event.keyval == gtk.keysyms.Right:
			model, iter = self.get_selection().get_selected()
			if not iter is None:
				path = model.get_path(iter)
				self.expand_row(path, 0)
			return True

		try:
			key = chr(event.keyval)
		except ValueError:
			return False

		if key == '\\':
			self.collapse_all()
			return True
		elif key == '*':
			self.expand_all()
			return True
		else:
			return False

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
