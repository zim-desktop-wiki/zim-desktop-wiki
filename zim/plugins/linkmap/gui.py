# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import gtk

from zim._lib import xdot

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
	# name, stock id, label, accelerator, tooltip
	('show_linkmap', None, 'Show Link Map', None, 'Show Link Map'),
)


class GtkLinkMap():

	def __init__(self, ui):
		self.ui = ui
		self.ui.add_actions(ui_actions, self)
		self.ui.add_ui(ui_xml, self)

	def show_linkmap(self):
		linkmap = LinkMap(self.ui.notebook)
		dialog = LinkMapDialog(linkmap)
		dialog.show_all()


class LinkMapDialog(gtk.Dialog):
	'''FIXME'''

	def __init__(self, linkmap):
		gtk.Dialog.__init__(self)
		self.set_default_size(400, 400)
		self.linkmap = linkmap
		self.xdotview = xdot.DotWidget()
		self.xdotview.set_dotcode(linkmap.get_dotcode())
		self.vbox.add(self.xdotview)
