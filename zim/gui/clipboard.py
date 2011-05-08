# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Utilities to work with the clipboard for copy-pasting

Some functions defined here are also re-used for drag-and-drop
functionality, which works similar to the clipboard, but has a less
straight forward API.
'''

# TODO support converting HTML to parsetree - need html Parser

import gtk
import logging

from zim.fs import File
from zim.parsing import is_url_re, url_encode, URL_ENCODE_READABLE
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

IMAGE_TARGET_ID = 6
IMAGE_TARGETS = tuple(gtk.target_list_add_image_targets(info=IMAGE_TARGET_ID))
	# According to docs we should provide list as arg to this function,
	# but seems docs are not correct
IMAGE_TARGET_NAMES = tuple([target[0] for target in IMAGE_TARGETS])

# Add image format names as well, seen these being used by MS Office
for format in gtk.gdk.pixbuf_get_formats():
	if format['mime_types'][0] in IMAGE_TARGET_NAMES:
		for n in (format['name'], format['name'].upper()):
			IMAGE_TARGET_NAMES += (n,)
			IMAGE_TARGETS += ((n, 0, IMAGE_TARGET_ID),)

#~ print IMAGE_TARGETS
#~ print IMAGE_TARGET_NAMES

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
) + IMAGE_TARGETS + URI_TARGETS + TEXT_TARGETS
PARSETREE_ACCEPT_TARGET_NAMES = tuple([target[0] for target in PARSETREE_ACCEPT_TARGETS])
#~ print 'ACCEPT', PARSETREE_ACCEPT_TARGET_NAMES


# Mimetype text/uri-list is used for drag n drop of URLs
# it is plain text encoded list of urls, seperated by \r\n
# Since not all apps foolow the standard exactly, do allow for
# just \n separated lists.
#
# Zim page links are also encoded in this format, but no url encoding
# is applied and no scheme is used. The target mimetype can be used to
# distinguish between proper uri lists and lists of page names.

def pack_urilist(links):
	text = ''
	for link in links:
		link = link.encode('utf-8')
		if is_url_re.match(link):
			link = url_encode(link, mode=URL_ENCODE_READABLE) # just to be sure
		text += '%s\r\n' % link
	return text


def unpack_urilist(text):
	# FIXME be tolerant here for file://path/to/file uris here
	lines = text.splitlines() # takes care of \r\n
	return [line.decode('utf-8') for line in lines]


def _file_link_tree(links, notebook, page):
		#~ print 'LINKS: ', links
		builder = TreeBuilder()
		builder.start('zim-tree')
		for i in range(len(links)):
			if i > 0:
				builder.data(' ')

			isimage = False
			if links[i].startswith('file:/'):
				try:
					isimage = File(links[i]).isimage()
				except:
					pass

			if isimage:
				file = File(links[i])
				src = notebook.relative_filepath(file, page) or file.path
				builder.start('img', {'src': src})
				builder.end('img')
			elif links[i].startswith('@'):
				builder.start('tag', {'name': links[i][1:]})
				builder.data(links[i])
				builder.end('tag')
			else:
				builder.start('link', {'href': links[i]})
				builder.data(links[i])
				builder.end('link')
		builder.end('zim-tree')
		tree = ParseTree(builder.close())
		tree.resolve_images(notebook, page)
		tree.decode_urls()
		return tree


def _get_image_info(targetname):
	# Target name for images is supposed to be mimetype, we check
	# in available pixbuf writers for this type and return the
	# format name and file extension
	for format in gtk.gdk.pixbuf_get_formats():
		if targetname == format['name'] \
		or targetname == format['name'].upper() \
		or targetname in format['mime_types']:
			if format['is_writable']:
				return format['name'], format['extensions'][0]
			else:
				return None, None
	else:
		return None, None


def parsetree_from_selectiondata(selectiondata, notebook, page=None):
	'''Function to get a parsetree based on the selectiondata contents
	if at all possible. Used by both copy-paste and drag-and-drop
	methods.

	The 'notebook' and optional 'page' arguments are used to format
	links relative to the page which is the target for the pasting or
	drop operation.

	For image data, the parameters notebook and page are used
	to save the image to the correct attachment folder and return a
	parsetree with the correct image link.
	'''
	targetname = str(selectiondata.target)
	if targetname == PARSETREE_TARGET_NAME:
		return ParseTree().fromstring(selectiondata.data)
	elif targetname in (INTERNAL_PAGELIST_TARGET_NAME, PAGELIST_TARGET_NAME) \
	or targetname in URI_TARGET_NAMES:
		links = unpack_urilist(selectiondata.data)
		return _file_link_tree(links, notebook, page)
	elif targetname in TEXT_TARGET_NAMES:
		# plain text parser should highlight urls etc.
		# FIXME some apps drop text/uri-list as a text/plain mimetype
		# try to catch this situation by a check here
		text = selectiondata.get_text()
		return get_format('plain').Parser().parse(text.decode('utf-8'))
	elif targetname in IMAGE_TARGET_NAMES:
		# save image
		pixbuf = selectiondata.get_pixbuf()
		if not pixbuf:
			return None

		dir = notebook.get_attachments_dir(page)
		if not dir.exists():
			logger.debug("Creating attachment dir: %s", dir)
			dir.touch()

		format, extension = _get_image_info(targetname)
		if format is None:
			format, extension = 'png', 'png' # default to png format

		file = dir.new_file('pasted_image.%s' % extension)
		logger.debug("Saving image from clipboard to %s", file)
		pixbuf.save(file.path, format)

		links = [file.uri]
		return _file_link_tree(links, notebook, page)
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

	def set_parsetree(self, notebook, page, parsetree, format='plain'):
		'''Copy a parsetree to the clipboard. The parsetree can be pasted by
		the user either as formatted text within zim or as plain text outside
		zim. The tree can be the full tree for 'page', but also a selection.

		@param notebook: the L{Notebook} object
		@param page: the L{Page} object - used to resolve links etc.
		@param parsetree: the actual L{ParseTree} to be set on the clipboard
		@keyword format: the format to use for pasting text, 'wiki' or 'plain'
		'''
		targets = [PARSETREE_TARGET]
		targets.extend(HTML_TARGETS)
		targets.extend(TEXT_TARGETS)
		self.set_with_data(
			targets,
			Clipboard._get_parsetree_data, Clipboard._clear_data,
			(notebook, page, parsetree, format)
		) or logger.warn('Failed to set data on clipboard')

	def _get_parsetree_data(self, selectiondata, id, data):
		logger.debug("Cliboard data request of type '%s', we have a parsetree", selectiondata.target)
		notebook, page, parsetree, format = data
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
			dumper = get_format(format).Dumper()
			text = ''.join( dumper.dump(parsetree) ).encode('utf-8')
			selectiondata.set_text(text)
		else:
			assert False, 'Unknown target id %i' % id

	def request_parsetree(self, callback, notebook, page=None, block=False):
		'''Request a parsetree from the clipboard if possible. Because pasting
		is asynchronous a callback needs to be provided to accept the parsetree.
		This callback just gets the parsetree as single argument.

		For image data, the parameters notebook and page are used
		to save the image to the correct attachment folder and return a
		parsetree with the correct image link.

		If 'block' is True the operation is blocking. This is only intended
		for testing and should not be used for real functionality.
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
			tree = parsetree_from_selectiondata(selectiondata, notebook, page)
			callback(tree)

		if name:
			logger.debug('Requesting data for %s', name)
			if block:
				selectiondata = self.wait_for_contents(name)
				return parsetree_from_selectiondata(selectiondata, notebook, page)
			else:
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
			link = "%s?%s" % (notebookname, pagename)
			text = pack_urilist((link,))
			selectiondata.set(PAGELIST_TARGET_NAME, 8, text)
		elif id == TEXT_TARGET_ID:
			selectiondata.set_text(pagename)
		else:
			assert False, 'Unknown target id %i' % id

	def _clear_data(self, data):
		# Callback to clear our cliboard data - pass because we keep no state
		pass


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
