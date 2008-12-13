# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import gtk

def button(stock, label):
	'''Create a button with a stock icon, but different label'''
	icon = gtk.image_new_from_stock(stock, gtk.ICON_SIZE_BUTTON)
	label = gtk.Label(label)
	label.set_use_underline(True)
	hbox = gtk.HBox()
	hbox.add(icon)
	hbox.add(label)
	button = gtk.Button()
	button.add(hbox)
	button.set_alignment(0.5, 0.5)
	return button


def icon_button(stock, small_size=False):
	'''Creates a button with only an icon and no label'''
	icon = gtk.image_new_from_stock(stock, gtk.ICON_SIZE_BUTTON)
	button = gtk.Button()
	button.add(icon)
	button.set_alignment(0.5, 0.5)
	return button


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
			#if not self.get_selection().path_is_selected(path):
			self.row_activated(path, column)

		return gtk.TreeView.do_button_release_event(self, event)
