# -*- coding: utf8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import gtk
import logging

logger = logging.getLogger('zim.gui.clipboard')

# Targets have format (name, flags, id), flags need be 0 instead of None

PAGELIST_TARGET_ID = 1
PAGELIST_TARGET = ('text/x-zim-page-list', 0, PAGELIST_TARGET_ID)

TEXT_TARGET_ID = 9
TEXT_TARGET_LIST = (
	('UTF8_STRING', 0, TEXT_TARGET_ID),
	('TEXT', 0, TEXT_TARGET_ID),
	('COMPOUND_TEXT', 0, TEXT_TARGET_ID),
	('text/plain', 0, TEXT_TARGET_ID),
)


class Clipboard(gtk.Clipboard):

	def set_pagelink(self, page):
		'''Copy a pagename to the clipboard. The pagename can be pasted by the
		user either as a link within zim or as text outside zim.
		'''
		store = page.store
		notebook = store.notebook
		# TODO uri encode step to escape other '?' characters
		uri = '%s?%s' % (notebook.name, page.name)

		targets = [PAGELIST_TARGET]
		targets.extend(TEXT_TARGET_LIST)
		self.set_with_data(
			targets,
			Clipboard._get_uri_data, Clipboard._clear_data,
			(uri,)
		) or logger.warn('Failed to set data on clipboard')

	def _get_uri_data(self, selectiondata, id, uris):
		logger.debug("Cliboard data request of type '%s'", selectiondata.target)
		if id == PAGELIST_TARGET_ID:
			selectiondata.set_uris(uris)
		elif id == TEXT_TARGET_ID:
			selectiondata.set_text('\n'.join(uris))
		else:
			assert False, 'Unknown target id %i' % id

	def _clear_data(self, data):
		pass
