# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

'''Utilities to work with the clipboard for copy-pasting

Some functions defined here are also re-used for drag-and-drop
functionality, which works similar to the clipboard, but has a less
straight forward API.
'''

# TODO support pasting parsetree as HTML
# TODO support for pasting image as parsetree - attach + tree ?
# TODO check how we tie into drag & drop (e.g. image from firefox ..)
# TODO unit test for copy - paste parsetree & page link

import gtk
import logging

from zim.formats import get_format, ParseTree, TreeBuilder
from zim.parsing import url_encode, url_decode


logger = logging.getLogger('zim.gui.clipboard')


# Targets have format (name, flags, id), flags need be 0 to allow
# paste to other widgets and to other aplication instances
PARSETREE_TARGET_ID = 1
PARSETREE_TARGET_NAME = 'text/x-zim-parsetree'
PARSETREE_TARGET = (PARSETREE_TARGET_NAME, 0, PARSETREE_TARGET_ID)

INTERNAL_PAGELIST_TARGET_ID = 2
INTERNAL_PAGELIST_TARGET_NAME = 'text/x-zim-page-list-internal'
INTERNAL_PAGELIST_TARGET = \
	(INTERNAL_PAGELIST_TARGET_NAME, gtk.TARGET_SAME_APP, INTERNAL_PAGELIST_TARGET_ID)

PAGELIST_TARGET_ID = 3
PAGELIST_TARGET_NAME = 'text/x-zim-page-list'
PAGELIST_TARGET = (PAGELIST_TARGET_NAME, 0, PAGELIST_TARGET_ID)

URI_TARGET_ID = 8
URI_TARGETS = tuple(gtk.target_list_add_uri_targets(info=URI_TARGET_ID))
	# According to docs we should provide list as arg to this function,
	# but seems docs are not correct
URI_TARGET_NAMES = tuple([target[0] for target in URI_TARGETS])

TEXT_TARGET_ID = 9
TEXT_TARGETS = tuple(gtk.target_list_add_text_targets(info=TEXT_TARGET_ID))
	# According to docs we should provide list as arg to this function,
	# but seems docs are not correct
TEXT_TARGET_NAMES = tuple([target[0] for target in TEXT_TARGETS])

# All targets that we can convert to a parsetree, in order of choice
PARSETREE_ACCEPT_TARGETS = (
	PARSETREE_TARGET,
	INTERNAL_PAGELIST_TARGET, PAGELIST_TARGET,
) + URI_TARGETS + TEXT_TARGETS
PARSETREE_ACCEPT_TARGET_NAMES = tuple([target[0] for target in PARSETREE_ACCEPT_TARGETS])
#~ print 'ACCEPT', PARSETREE_ACCEPT_TARGET_NAMES


def parsetree_from_selectiondata(selectiondata):
	'''Function to get a parsetree based on the selectiondata contents
	if at all possible. Used by both copy-paste and drag-and-drop
	methods.
	'''
	targetname = str(selectiondata.type)
	if targetname == PARSETREE_TARGET_NAME:
		return ParseTree().fromstring(selectiondata.data)
	elif targetname in (INTERNAL_PAGELIST_TARGET_NAME, PAGELIST_TARGET_NAME) \
	or targetname in URI_TARGET_NAMES:
		# \n seperated list of urls / pagelinks / ..
		text = selectiondata.data
		links = map(url_decode, text.strip().split('\n'))
		print 'LINKS: ', links
		builder = TreeBuilder()
		builder.start('zim-tree')
		for link in links:
			builder.start('link', {'href': link})
			builder.data(link)
			builder.end('link')
			builder.data(' ')
		builder.end('zim-tree')
		return ParseTree(builder.close())
	elif targetname in TEXT_TARGET_NAMES:
		# plain text parser should highlight urls etc.
		text = selectiondata.get_text()
		return get_format('plain').Parser().parse(text.decode('utf-8'))
	else:
		return None


class Clipboard(gtk.Clipboard):
	'''This class extends the default gtk.Clipboard class with conversion
	methods and convenience methods for zim specific data types. It's main
	use is to get any paste data into a format that can be pasted into the
	zim pageview widget.
	'''

	def set_parsetree(self, notebook, page, parsetree):
		'''Copy a parsetree to the clipboard. The parsetree can be pasted by
		the user either as formatted text within zim or as plain text outside
		zim. The tree can be the full tree for 'page', but also a selection.
		'''
		targets = [PARSETREE_TARGET]
		targets.extend(gtk.target_list_add_text_targets(info=TEXT_TARGET_ID))
		self.set_with_data(
			targets,
			Clipboard._get_parsetree_data, Clipboard._clear_data,
			parsetree
		) or logger.warn('Failed to set data on clipboard')

	def _get_parsetree_data(self, selectiondata, id, parsetree):
		logger.debug("Cliboard data request of type '%s', we have a parsetree", selectiondata.target)
		if id == PARSETREE_TARGET_ID:
			xml = parsetree.tostring().encode('utf-8')
			selectiondata.set(PARSETREE_TARGET_NAME, 8, xml)
		elif id == TEXT_TARGET_ID:
			dumper = get_format('wiki').Dumper()
			text = ''.join( dumper.dump(parsetree) ).encode('utf-8')
			selectiondata.set_text(text)
		else:
			assert False, 'Unknown target id %i' % id

	def request_parsetree(self, callback):
		'''Request a parsetree from the clipboard if possible. Because pasting
		is asynchronous a callback needs to be provided to accept the parsetree.
		This callback just gets the parsetree as single argument.
		'''
		targets = self.wait_for_targets()
		logger.debug('Targets available for paste: %s, we want parsetree', targets)
		for name in PARSETREE_ACCEPT_TARGET_NAMES:
			if name in targets:
				break
		else:
			name = None

		def request_parsetree_data(self, selectiondata, data):
			tree = parsetree_from_selectiondata(selectiondata)
			callback(tree)

		if name:
			logger.debug('Requesting data for %s', name)
			self.request_contents(name, request_parsetree_data)
		else:
			logger.warn('Could not paste - no compatible data types on clipboard')

	def set_pagelink(self, notebook, page):
		'''Copy a pagename to the clipboard. The pagename can be pasted by the
		user either as a link within zim or as text outside zim.
		'''
		# TODO escape other '?' characters
		uri = '%s?%s' % (url_encode(notebook.name), url_encode(page.name))

		targets = [INTERNAL_PAGELIST_TARGET, PAGELIST_TARGET]
		targets.extend(gtk.target_list_add_text_targets(info=TEXT_TARGET_ID))
		self.set_with_data(
			targets,
			Clipboard._get_uri_data, Clipboard._clear_data,
			(uri,)
		) or logger.warn('Failed to set data on clipboard')

	def _get_uri_data(self, selectiondata, id, uris):
		# Callback to get uri data we set on the clipboard
		logger.debug("Cliboard data request of type '%s', we have uris", selectiondata.target)
		text = ''.join(["%s\n" % uri for uri in uris]).encode('utf-8')
		if id == INTERNAL_PAGELIST_TARGET_ID:
			# remove notebook name from links - pasting internally
			text = ''.join([l.split('?', 1)[1] for l in text.splitlines(True)])
			selectiondata.set(INTERNAL_PAGELIST_TARGET_NAME, 8, text)
		elif id == PAGELIST_TARGET_ID:
			selectiondata.set(PAGELIST_TARGET_NAME, 8, text)
		elif id == TEXT_TARGET_ID:
			selectiondata.set_text(text)
		else:
			assert False, 'Unknown target id %i' % id

	def _clear_data(self, data):
		# Callback to clear our cliboard data - pass because we keep no state
		pass

	def debug_dump_contents(self):
		'''Dumps clipboard contents to stdout - used for debug sessions'''
		targets = self.wait_for_targets()
		for target in targets:
			print '>>>>', target
			selection = self.wait_for_contents(target)
			if selection:
				text = selection.get_text()
				if not text is None:
					print '== Text:', text
				else:
					print '== Data:', selection.data
			else:
				print '== No contents'
			print '<<<<'
