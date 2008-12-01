# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import gtk

from zim._lib import xdot

class LinkMapDialog(gtk.Dialog):
	'''FIXME'''

	def __init__(self, linkmap):
		gtk.Dialog.__init__(self)
		self.set_default_size(400, 400)
		self.linkmap = linkmap
		self.xdotview = xdot.DotWidget()
		self.xdotview.set_dotcode(linkmap.get_dotcode())
		self.vbox.add(self.xdotview)
