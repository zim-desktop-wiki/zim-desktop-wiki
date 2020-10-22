# -*- coding: utf-8 -*-

# Copyright 2020 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from zim.gui.pageview import PageView, PageViewExtension, PageViewExtensionBase
from zim.plugins import extendable


class NotebookViewExtension(PageViewExtensionBase):
	'''Base class for extensions of the L{NotebookView},
	see L{PageViewExtensionBase} for API documentation.
	'''
	pass


@extendable(NotebookViewExtension, PageViewExtension, register_after_init=False)
class NotebookView(PageView):
	'''Sub-class of the L{PageView} class that is used when the view is
	navigatable. Plugins can choose to extend this class if they don't want
	to load extensions for a fixed page view.
	'''
	pass
