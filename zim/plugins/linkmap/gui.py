# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import gtk

from zim._lib import xdot

from zim.notebook import Path
from zim.gui.widgets import ui_environment, Dialog, IconButton

from zim.plugins.linkmap import LinkMap

ui_xml = '''
<ui>
	<menubar name='menubar'>
		<menu action='view_menu'>
			<placeholder name='plugin_items'>
				<menuitem action='show_linkmap'/>
			</placeholder>
		</menu>
	</menubar>
</ui>
'''

ui_actions = (
	# name, stock id, label, accelerator, tooltip, readonly
	('show_linkmap', 'zim-linkmap', _('Show Link Map'), None, _('Show Link Map'), True), # T: Menu item
)


class GtkLinkMap():

	def __init__(self, ui):
		self.ui = ui
		self.ui.add_actions(ui_actions, self)
		self.ui.add_ui(ui_xml, self)

	def show_linkmap(self):
		linkmap = LinkMap(self.ui.notebook, self.ui.page)
		dialog = LinkMapDialog(self.ui, linkmap)
		dialog.show_all()


class LinkMapDialog(Dialog):

	def __init__(self, ui, linkmap):
		if ui_environment['platform'] == 'maemo':
			defaultsize = (800, 480)
			# The dialog hides the main window, so use all available screen anyway
			# setting defaultsize doesn't work because maemo makes the dialog
			# window as small as possible to fit the window's internal widgets
		else:
			defaultsize = (400, 400)
		Dialog.__init__(self, ui, 'LinkMap',
			defaultwindowsize=defaultsize, buttons=gtk.BUTTONS_CLOSE)
		self.linkmap = linkmap

		hbox = gtk.HBox(spacing=5)
		self.vbox.add(hbox)

		self.xdotview = xdot.DotWidget()
		self.xdotview.set_filter('fdp')
		self.xdotview.set_dotcode(linkmap.get_dotcode())
		self.xdotview.connect('clicked', self.on_node_clicked)
		hbox.add(self.xdotview)

		vbox = gtk.VBox()
		hbox.pack_start(vbox, False)
		for stock, method in (
			(gtk.STOCK_ZOOM_IN,  self.xdotview.on_zoom_in ),
			(gtk.STOCK_ZOOM_OUT, self.xdotview.on_zoom_out),
			(gtk.STOCK_ZOOM_FIT, self.xdotview.on_zoom_fit),
			(gtk.STOCK_ZOOM_100, self.xdotview.on_zoom_100),
		):
			button = IconButton(stock)
			button.connect('clicked', method)
			vbox.pack_start(button, False)

	def on_node_clicked(self, widget, name, event):
		self.ui.open_page(Path(name))
