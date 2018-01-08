# -*- coding: utf-8 -*-

# Copyright 2008-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import logging

logger = logging.getLogger('zim.gui')


import gtk
import webbrowser

if gtk.gtk_version >= (2, 10) \
and gtk.pygtk_version >= (2, 10):
	gtk.link_button_set_uri_hook(lambda o, url: webbrowser.open(url))


from zim.config import data_dirs

# Load custom application icons as stock
def load_zim_stock_icons():
	'''Function to load zim custom stock icons for Gtk. Will load all
	icons found in the "pixmaps" folder with a stock name prefixed
	with "zim-", so "data/pixmaps/link.png" becomes the "zim-link"
	stock icon. Called directly when this module is loaded.
	'''
	factory = gtk.IconFactory()
	factory.add_default()
	for dir in data_dirs(('pixmaps')):
		for file in dir.list('*.png'):
			# not all installs have svg support, so only check png for now..
			name = 'zim-' + file[:-4] # e.g. checked-box.png -> zim-checked-box
			icon_theme = gtk.icon_theme_get_default()
			try:
			    pixbuf = icon_theme.load_icon(name, 24, 0)
			except:
			    pixbuf = gtk.gdk.pixbuf_new_from_file(str(dir + file))

			try:
			    set = gtk.IconSet(pixbuf)
			    factory.add(name, set)
			except Exception:
				logger.exception('Got exception while loading application icons')


load_zim_stock_icons()
