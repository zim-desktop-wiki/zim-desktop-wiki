# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

'''Utilities to work with the clipboard for copy-pasting

Some functions defined here are also re-used for drag-and-drop
functionality, which works similar to the clipboard, but has a less
straight forward API.
'''

# TODO support converting HTML to parsetree - need html Parser
# TODO support for pasting image as parsetree - attach + tree ?
# TODO unit test for copy - paste parsetree & page link

import gtk
import logging

from zim.parsing import url_encode, url_decode
from zim.formats import get_format, ParseTree, TreeBuilder
from zim.exporter import StaticLinker


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

URI_TARGET_ID = 7
URI_TARGETS = tuple(gtk.target_list_add_uri_targets(info=URI_TARGET_ID))
	# According to docs we should provide list as arg to this function,
	# but seems docs are not correct
URI_TARGET_NAMES = tuple([target[0] for target in URI_TARGETS])

HTML_TARGET_ID = 8
HTML_TARGET_NAMES = ('text/html', 'HTML Format')
	# "HTML Format" is from MS Word
HTML_TARGETS = tuple([(name, 0, HTML_TARGET_ID) for name in HTML_TARGET_NAMES])

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


def pack_urilist(uris):
	return ''.join(["%s\n" % url_encode(uri) for uri in uris])


def unpack_urilist(data):
	return map(url_decode, data.strip().split('\n'))


def parsetree_from_selectiondata(selectiondata):
	'''Function to get a parsetree based on the selectiondata contents
	if at all possible. Used by both copy-paste and drag-and-drop
	methods.
	'''
	targetname = str(selectiondata.target)
	if targetname == PARSETREE_TARGET_NAME:
		return ParseTree().fromstring(selectiondata.data)
	elif targetname in (INTERNAL_PAGELIST_TARGET_NAME, PAGELIST_TARGET_NAME) \
	or targetname in URI_TARGET_NAMES:
		# \n seperated list of urls / pagelinks / ..
		links = unpack_urilist(selectiondata.data)
		print 'LINKS: ', links
		builder = TreeBuilder()
		builder.start('zim-tree')
		for i in range(len(links)):
			if i > 0:
				builder.data(' ')
			builder.start('link', {'href': links[i]})
			builder.data(links[i])
			builder.end('link')
		builder.end('zim-tree')
		return ParseTree(builder.close())
	elif targetname in TEXT_TARGET_NAMES:
		# plain text parser should highlight urls etc.
		text = selectiondata.get_text()
		return get_format('plain').Parser().parse(text.decode('utf-8'))
	else:
		return None


HTML_HEAD = '''\
<meta http-equiv="Content-Type" content="text/html;charset=utf-8">
<meta name="Description" content="Copy-Paste Buffer">
<meta name="Generator" content="Zim">
'''.strip()

def wrap_html(html, target):
	'''Fucntion to wrap html with appropriate headers based on target type'''
	html = html.encode('utf-8')
	if target == 'HTML Format':
		return Win32HtmlFormat.encode(html, head=HTML_HEAD)
	else:
		return '''\
<html>
<head>
%s
</head>
<body>
%s
</body>
</html>
''' % (HTML_HEAD, html)


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
		targets.extend(HTML_TARGETS)
		targets.extend(TEXT_TARGETS)
		self.set_with_data(
			targets,
			Clipboard._get_parsetree_data, Clipboard._clear_data,
			(notebook, page, parsetree)
		) or logger.warn('Failed to set data on clipboard')

	def _get_parsetree_data(self, selectiondata, id, data):
		logger.debug("Cliboard data request of type '%s', we have a parsetree", selectiondata.target)
		notebook, page, parsetree = data
		if id == PARSETREE_TARGET_ID:
			xml = parsetree.tostring().encode('utf-8')
			selectiondata.set(PARSETREE_TARGET_NAME, 8, xml)
		elif id == HTML_TARGET_ID:
			# FIXME - HACK - dump and parse as wiki first to work
			# around glitches in pageview parsetree dumper
			# main visibility when copy pasting bullet lists
			# Same hack in print to browser plugin
			dumper = get_format('wiki').Dumper()
			text = ''.join( dumper.dump(parsetree) ).encode('utf-8')
			parser = get_format('wiki').Parser()
			parsetree = parser.parse(text)
			#--
			dumper = get_format('html').Dumper(
				linker=StaticLinker('html', notebook, page) )
			html = ''.join( dumper.dump(parsetree) )
			html = wrap_html(html, target=selectiondata.target)
			#~ print 'PASTING: >>>%s<<<' % html
			selectiondata.set(selectiondata.target, 8, html)
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

		if targets is None:
			return

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
		targets = [INTERNAL_PAGELIST_TARGET, PAGELIST_TARGET]
		targets.extend(gtk.target_list_add_text_targets(info=TEXT_TARGET_ID))
		self.set_with_data(
			targets,
			Clipboard._get_pagelink_data, Clipboard._clear_data,
			(notebook.name, page.name)
		) or logger.warn('Failed to set data on clipboard')

	def _get_pagelink_data(self, selectiondata, id, data):
		logger.debug("Cliboard data request of type '%s', we have pagelink", selectiondata.target)
		notebookname, pagename = data
		if id == INTERNAL_PAGELIST_TARGET_ID:
			text = pack_urilist((pagename,))
			selectiondata.set(INTERNAL_PAGELIST_TARGET_NAME, 8, text)
		elif id == PAGELIST_TARGET_ID:
			text = "%s?%s\n" % (url_encode(notebookname), url_encode(pagename))
			selectiondata.set(PAGELIST_TARGET_NAME, 8, text)
		elif id == TEXT_TARGET_ID:
			text = "%s?%s\n" % (url_encode(notebookname), url_encode(pagename))
			selectiondata.set_text(text)
		else:
			assert False, 'Unknown target id %i' % id

	def _clear_data(self, data):
		# Callback to clear our cliboard data - pass because we keep no state
		pass

	def debug_dump_contents(self):
		'''Interactively dumps clipboard contents to stdout - used for debug sessions'''
		import sys
		targets = self.wait_for_targets()
		print "="*80
		print "Enter a number to see a specific target, or <Enter> to exit"
		print "Available targets:"
		for i in range(len(targets)):
			print i, targets[i]
		line = sys.stdin.readline().strip()
		while line:
			target = targets[int(line)]
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
			line = sys.stdin.readline().strip()


class Win32HtmlFormat:
	'''This class adds support for Windows "HTML Format" clipboard content type

	Code is based on example code from
		http://code.activestate.com/recipes/474121/

	written by Phillip Piper (jppx1[at]bigfoot.com)

	Also see specification at:
		http://msdn.microsoft.com/library/default.asp?url=/library/en-us/winui/winui/windowsuserinterface/dataexchange/clipboard/htmlclipboardformat.asp
	'''

	MARKER_BLOCK_OUTPUT = \
		"Version:1.0\r\n" \
		"StartHTML:%09d\r\n" \
		"EndHTML:%09d\r\n" \
		"StartFragment:%09d\r\n" \
		"EndFragment:%09d\r\n" \
		"StartSelection:%09d\r\n" \
		"EndSelection:%09d\r\n" \
		"SourceURL:%s\r\n"

	#~ MARKER_BLOCK_EX = \
		#~ "Version:(\S+)\s+" \
		#~ "StartHTML:(\d+)\s+" \
		#~ "EndHTML:(\d+)\s+" \
		#~ "StartFragment:(\d+)\s+" \
		#~ "EndFragment:(\d+)\s+" \
		#~ "StartSelection:(\d+)\s+" \
		#~ "EndSelection:(\d+)\s+" \
		#~ "SourceURL:(\S+)"
	#~ MARKER_BLOCK_EX_RE = re.compile(MARKER_BLOCK_EX)

	#~ MARKER_BLOCK = \
		#~ "Version:(\S+)\s+" \
		#~ "StartHTML:(\d+)\s+" \
		#~ "EndHTML:(\d+)\s+" \
		#~ "StartFragment:(\d+)\s+" \
		#~ "EndFragment:(\d+)\s+" \
		   #~ "SourceURL:(\S+)"
	#~ MARKER_BLOCK_RE = re.compile(MARKER_BLOCK)

	DEFAULT_HTML_BODY = \
		"<!DOCTYPE HTML PUBLIC \"-//W3C//DTD HTML 4.0 Transitional//EN\">" \
		"<HTML><HEAD>%s</HEAD><BODY><!--StartFragment-->%s<!--EndFragment--></BODY></HTML>"

	@classmethod
	def encode(klass, fragment, selection=None, head=None, source=None):
		if selection is None:
			selection = fragment
		if source is None:
			source = "zim://copy-pase-buffer"
		if head is None:
			head = ''

		html = klass.DEFAULT_HTML_BODY % (head, fragment)
		fragmentStart = html.index(fragment)
		fragmentEnd = fragmentStart + len(fragment)
		selectionStart = html.index(selection)
		selectionEnd = selectionStart + len(selection)

		# How long is the prefix going to be?
		dummyPrefix = klass.MARKER_BLOCK_OUTPUT % (0, 0, 0, 0, 0, 0, source)
		lenPrefix = len(dummyPrefix)

		prefix = klass.MARKER_BLOCK_OUTPUT % (
			lenPrefix, len(html)+lenPrefix,
			fragmentStart+lenPrefix, fragmentEnd+lenPrefix,
			selectionStart+lenPrefix, selectionEnd+lenPrefix,
			source
		)
		return prefix + html

	#~ @classmethod
	#~ def decode(self, data):
		#~ """
		#~ Decode the given string to figure out the details of the HTML that's on the string
		#~ """
		#~ # Try the extended format first (which has an explicit selection)
		#~ matches = self.MARKER_BLOCK_EX_RE.match(src)
		#~ if matches:
			#~ self.prefix = matches.group(0)
			#~ self.htmlClipboardVersion = matches.group(1)
			#~ self.html = src[int(matches.group(2)):int(matches.group(3))]
			#~ self.fragment = src[int(matches.group(4)):int(matches.group(5))]
			#~ self.selection = src[int(matches.group(6)):int(matches.group(7))]
			#~ self.source = matches.group(8)
		#~ else:
			#~ # Failing that, try the version without a selection
			#~ matches = self.MARKER_BLOCK_RE.match(src)
			#~ if matches:
				#~ self.prefix = matches.group(0)
				#~ self.htmlClipboardVersion = matches.group(1)
				#~ self.html = src[int(matches.group(2)):int(matches.group(3))]
				#~ self.fragment = src[int(matches.group(4)):int(matches.group(5))]
				#~ self.source = matches.group(6)
				#~ self.selection = self.fragment
