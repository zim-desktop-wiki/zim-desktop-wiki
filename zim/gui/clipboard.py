# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Utilities to work with the clipboard for copy-pasting

Some functions defined here are also re-used for drag-and-drop
functionality, which works similar to the clipboard, but has a less
straight forward API.
'''

import gtk
import logging

from zim.fs import File, Dir, FS
from zim.notebook import Path
from zim.parsing import is_url_re, url_encode, link_type, URL_ENCODE_READABLE
from zim.formats import get_format, ParseTree, ParseTreeBuilder, \
	FORMATTEDTEXT, IMAGE, LINK
from zim.export.linker import StaticExportLinker


logger = logging.getLogger('zim.gui.clipboard')


# Targets have format (name, flags, id), flags need be 0 to allow
# paste to other widgets and to other application instances
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
# it is plain text encoded list of urls, separated by \r\n
# Since not all apps follow the standard exactly, do allow for
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
	text = text.strip('\x00') # Found trailing NULL character on windows
	lines = text.splitlines() # takes care of \r\n
	return [ line.decode('utf-8')
		for line in lines if line and not line.isspace() ]
		# Just to be sure we also skip empty or whitespace lines


def parsetree_from_selectiondata(selectiondata, notebook=None, path=None):
	'''Function to get a parsetree based on the selectiondata contents
	if at all possible. Used by both copy-paste and drag-and-drop
	methods.

	The 'notebook' and optional 'path' arguments are used to format
	links relative to the page which is the target for the pasting or
	drop operation.

	For image data, the parameters notebook and page are used
	to save the image to the correct attachment folder and return a
	parsetree with the correct image link.

	@param selectiondata: a C{gtk.SelectionData} object
	@param notebook: a L{Notebook} object
	@param path: a L{Path} object

	@returns: a L{ParseTree} or C{None}
	'''
	# TODO: check relative linking for all parsetrees !!!

	targetname = str(selectiondata.target)
	if targetname == PARSETREE_TARGET_NAME:
		return ParseTree().fromstring(selectiondata.data)
	elif targetname in (INTERNAL_PAGELIST_TARGET_NAME, PAGELIST_TARGET_NAME) \
	or targetname in URI_TARGET_NAMES:
		links = unpack_urilist(selectiondata.data)
		return _link_tree(links, notebook, path)
	elif targetname in TEXT_TARGET_NAMES:
		# plain text parser should highlight urls etc.
		# FIXME some apps drop text/uri-list as a text/plain mimetype
		# try to catch this situation by a check here
		text = selectiondata.get_text()
		if text:
			return get_format('plain').Parser().parse(text.decode('utf-8'), partial=True)
		else:
			return None
	elif targetname in IMAGE_TARGET_NAMES:
		# save image
		pixbuf = selectiondata.get_pixbuf()
		if not pixbuf:
			return None

		dir = notebook.get_attachments_dir(path)
		if not dir.exists():
			logger.debug("Creating attachment dir: %s", dir)
			dir.touch()

		format, extension = _get_image_info(targetname)
		if format is None or format == 'bmp':
			# default to png format
			# special casing bmp since many window apps use it internally
			# but is quite large to store, so compress by using png
			format, extension = 'png', 'png'

		file = dir.new_file('pasted_image.%s' % extension)
		logger.debug("Saving image from clipboard to %s", file)
		pixbuf.save(file.path, format)
		FS.emit('path-created', file) # notify version control

		links = [file.uri]
		return _link_tree(links, notebook, path)
	else:
		return None


def _link_tree(links, notebook, path):
	# Convert a list of links (of any type) into a parsetree
	#~ print 'LINKS: ', links
	#~ print 'NOTEBOOK and PATH:', notebook, path
	builder = ParseTreeBuilder()
	builder.start(FORMATTEDTEXT)
	for i in range(len(links)):
		if i > 0:
			builder.text(' ')

		link = links[i]
		type = link_type(link)
		isimage = False
		if type == 'file':
			try:
				file = File(link)
				isimage = file.isimage()
			except:
				pass

		logger.debug('Pasting link: %s (type: %s, isimage: %s)', link, type, isimage)

		if isimage:
			src = notebook.relative_filepath(file, path) or file.uri
			builder.append(IMAGE, {'src': src})
		elif link.startswith('@'):
			# FIXME - is this ever used ??
			builder.append(TAG, {'name': links[i][1:]}, links[i])
		else:
			if type == 'page':
				href = Path(notebook.cleanup_pathname(link)) # Assume links are always absolute
				link = notebook.relative_link(path, href) or link
			elif type == 'file':
				file = File(link) # Assume links are always URIs
				link = notebook.relative_filepath(file, path) or file.uri

			builder.append(LINK, {'href': link}, link)

	builder.end(FORMATTEDTEXT)
	tree = builder.get_parsetree()
	tree.resolve_images(notebook, path)
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


class ClipboardItem(object):
	'''Item that can be set on the clipboard'''

	def set(self, clipboard, clear_func):
		'''Put this item on the clipboard
		@param clipboard: a C{gtk.Clipboard} objet
		@param clear_func: function to be passed to the clipboard as
		callback on clearing the data
		@implementation: must be implemented by sub-classes
		'''
		raise NotImplementedError


class TextItem(ClipboardItem):
	'''Text item for the clipboard'''

	def __init__(self, text):
		self.text = text

	def set(self, clipboard, clear_func):
		clipboard.set_text(self.text)


class UriItem(ClipboardItem):
	'''Uri item for the clipboard'''

	targets = URI_TARGETS + TEXT_TARGETS

	def __init__(self, obj):
		if isinstance(obj, basestring):
			self.uri = obj
			self.obj = None
		else:
			assert hasattr(obj, 'uri')
			self.obj = obj
			self.uri = obj.uri

	def set(self, clipboard, clear_func):
		clipboard.set_with_data(self.targets, self._get, clear_func)

	def _get(self, clipboard, selectiondata, id, *a):
		if id == URI_TARGET_ID:
			selectiondata.set_uris((self.uri,))
		else:
			if isinstance(self.obj, (File, Dir)):
				selectiondata.set_text(self.obj.user_path)
			else:
				selectiondata.set_text(self.uri)


class InterWikiLinkItem(UriItem):
	'''Like L{UriItem} but with special case for zim parsetree'''

	targets = (PARSETREE_TARGET,) + UriItem.targets

	def __init__(self, href, url):
		UriItem.__init__(self, url)
		self.interwiki_href = href

	def _get(self, clipboard, selectiondata, id, *a):
		logger.debug("Clipboard requests data as '%s', we have an interwiki link", selectiondata.target)
		if id == PARSETREE_TARGET_ID:
			tree = _link_tree((self.interwiki_href,), None, None)
			xml = tree.tostring().encode('utf-8')
			selectiondata.set(PARSETREE_TARGET_NAME, 8, xml)
		else:
			UriItem._get(self, clipboard, selectiondata, id, *a)


class ParseTreeItem(ClipboardItem):
	'''Clipboard wrapper for a L{ParseTree}.'''

	targets = (PARSETREE_TARGET,) + HTML_TARGETS + TEXT_TARGETS

	def __init__(self, notebook, path, parsetree, format):
		self.notebook = notebook # FIXME - should not need to keep this reference - resolve parsetree immediatly
		self.path = path
		self.parsetree = parsetree
		self.format = format

	def set(self, clipboard, clear_func):
		clipboard.set_with_data(self.targets, self._get, clear_func, self) \
			or logger.warn('Failed to set data on clipboard')

	def _get(self, clipboard, selectiondata, id, *a):
		'''Callback to get the data in a specific format
		@param clipboard: a C{gtk.Clipboard} objet
		@param selectiondata: a C{gtk.SelectionData} object to set the data on
		@param id: target id for the requested data format
		@param a: any additional arguments are discarded
		'''
		logger.debug("Clipboard requests data as '%s', we have a parsetree", selectiondata.target)
		if id == PARSETREE_TARGET_ID:
			# TODO make links absolute (?)
			xml = self.parsetree.tostring().encode('utf-8')
			selectiondata.set(PARSETREE_TARGET_NAME, 8, xml)
		elif id == HTML_TARGET_ID:
			dumper = get_format('html').Dumper(
				linker=StaticExportLinker(self.notebook, source=self.path) )
			html = ''.join( dumper.dump(self.parsetree) )
			html = wrap_html(html, target=selectiondata.target)
			#~ print 'PASTING: >>>%s<<<' % html
			selectiondata.set(selectiondata.target, 8, html)
		elif id == TEXT_TARGET_ID:
			logger.debug("Clipboard requested text, we provide '%s'" % self.format)
			#~ print ">>>>", self.format, parsetree.tostring()

			if self.format in ('wiki', 'plain'):
				dumper = get_format(self.format).Dumper()
			else:
				dumper = get_format(self.format).Dumper(
					linker=StaticExportLinker(self.notebook, source=self.path) )

			text = ''.join( dumper.dump(self.parsetree) ).encode('utf-8')
			selectiondata.set_text(text)
		else:
			assert False, 'Unknown target id %i' % id


class PageLinkItem(ClipboardItem):
	'''Clipboard wrapper for a L{ParseTree}.'''

	targets = (INTERNAL_PAGELIST_TARGET, PAGELIST_TARGET) + TEXT_TARGETS

	def __init__(self, notebook, path):
		self.notebookname = notebook.name
		self.path = path

	def set(self, clipboard, clear_func):
		clipboard.set_with_data(self.targets, self._get, clear_func, self) \
			or logger.warn('Failed to set data on clipboard')

	def _get(self, clipboard, selectiondata, id, *a):
		'''Callback to get the data in a specific format
		@param clipboard: a C{gtk.Clipboard} objet
		@param selectiondata: a C{gtk.SelectionData} object to set the data on
		@param id: target id for the requested data format
		@param a: any additional arguments are discarded
		'''
		logger.debug("Clipboard requests data as '%s', we have a pagelink", selectiondata.target)
		if id == INTERNAL_PAGELIST_TARGET_ID:
			text = pack_urilist((self.path.name,))
			selectiondata.set(INTERNAL_PAGELIST_TARGET_NAME, 8, text)
		elif id == PAGELIST_TARGET_ID:
			link = "%s?%s" % (self.notebookname, self.path.name)
			text = pack_urilist((link,))
			selectiondata.set(PAGELIST_TARGET_NAME, 8, text)
		elif id == TEXT_TARGET_ID:
			selectiondata.set_text(self.path.name)
		else:
			assert False, 'Unknown target id %i' % id


class ClipboardManager(object):
	'''Interface to the clipboard for copy and paste.
	Replacement for gtk.Clipboard(), to be used everywhere in the
	zim gui modules.
	'''

	def __init__(self, atom):
		'''Constructor
		@param atom: clipboard name, can be either "CLIPBOARD" or "PRIMARY",
		see C{gtk.Clipboard} for details.
		'''
		assert atom in ('CLIPBOARD', 'PRIMARY')
		self.clipboard = gtk.Clipboard(selection=atom)
		self.store = None
		self._i_am_owner = False

	def clear(self):
		'''Clear clipboard if we set it'''
		if self._i_am_owner:
			self.clipboard.clear()

	def set(self, item):
		'''Set an item on the clipboard
		@param item: a L{ClipboardItem}
		'''
		item.set(self.clipboard, self._clear)
		self._i_am_owner = True
		if self.store:
			pass

	def _clear(self, o, item):
		self._i_am_owner = False
		if self.store:
			pass

	def set_text(self, text):
		'''Set text to the clipboard
		@param text: text to set on the clipboard
		@note: DO NOT USE THIS METHOD if you can use L{set_parsetree()}
		instead
		'''
		item = TextItem(text)
		self.set(item)

	def get_text(self):
		'''Get text from the clipboard.
		@returns: (unicode) text or C{None}
		@note: DO NOT USE THIS METHOD if you can use L{get_parsetree()}
		instead
		'''
		text = self.clipboard.wait_for_text()
		if isinstance(text, basestring):
			text = text.decode('utf-8')
		return text

	def set_parsetree(self, notebook, path, parsetree, format='plain'):
		'''Copy a parsetree to the clipboard. The parsetree can be pasted by
		the user either as formatted text within zim or as plain text outside
		zim. The tree can be the full tree for 'page', but also a selection.

		@param notebook: the L{Notebook} object
		@param path: the L{Path} object - used to resolve links etc.
		@param parsetree: the actual L{ParseTree} to be set on the clipboard
		@keyword format: the format to use for pasting text, e.g. 'wiki' or 'plain'
		'''
		item = ParseTreeItem(notebook, path, parsetree, format)
		self.set(item)

	def get_parsetree(self, notebook=None, path=None):
		'''Get a parsetree from the clipboard.

		Can handle various data types and convert them to L{ParseTree}
		objects. So they can be pasted directly in a text buffer.

		The 'notebook' and optional 'path' arguments are used to format
		links relative to the page which is the target for the pasting or
		drop operation. Otherwise absolute links will be used.

		@param notebook: a L{Notebook} object
		@param path: a L{Path} object

		@returns: a L{ParseTree} or C{None}
		'''
		targets = self.clipboard.wait_for_targets()
		logger.debug('Targets available for paste: %s, we want parsetree', targets)

		if targets is None:
			return None

		targets = [n for n in PARSETREE_ACCEPT_TARGET_NAMES if n in targets]
			# Filter and sort by PARSETREE_ACCEPT_TARGET_NAMES

		if targets:
			name = targets[0]
			logger.debug('Requesting data for %s', name)
			selectiondata = self.clipboard.wait_for_contents(name)
			if selectiondata:
				return parsetree_from_selectiondata(selectiondata, notebook, path)
			else:
				logger.warn('Did not get requested data from clipboard')
				return None
		else:
			logger.warn('Could not paste - no compatible data types on clipboard')
			return None

	def set_pagelink(self, notebook, path):
		'''Copy a pagename to the clipboard. The pagename can be pasted by the
		user either as a link within zim or as text outside zim.
		@param notebook: a L{Notebook} object
		@param path: a L{Path} object
		'''
		item = PageLinkItem(notebook, path)
		self.set(item)

	def set_interwikilink(self, href, url):
		'''Copy an interwiki link to the clipboard
		@param href: the link as shown in zim, e.g. "wp?foobar"
		@param url: the expanded url for this interwiki link, e.g.
		"http://en.wikipedia.org/wiki/foobar"
		'''
		item = InterWikiLinkItem(href, url)
		self.set(item)

	def set_uri(self, uri):
		'''Copy an uri to the clipboard
		@param uri: an uri as string, or an object with an attribute C{uri}
		'''
		item = UriItem(uri)
		self.set(item)

Clipboard = ClipboardManager("CLIPBOARD") #: Singleton object for the default clipboard
SelectionClipboard = ClipboardManager("PRIMARY") #: Singleton object for the selection clipboard (unix)




########### Code to deal with HTML formatting on windows ############

HTML_HEAD = '''\
<meta http-equiv="Content-Type" content="text/html;charset=utf-8">
<meta name="Description" content="Copy-Paste Buffer">
<meta name="Generator" content="Zim">'''

def wrap_html(html, target):
	'''Function to wrap html with appropriate headers based on target type'''
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


class Win32HtmlFormat:
	'''This class adds support for Windows "HTML Format" clipboard content type

	Code is based on example code from
	U{http://code.activestate.com/recipes/474121/}

	written by Phillip Piper (jppx1[at]bigfoot.com)

	Also see specification at:
	U{http://msdn.microsoft.com/library/default.asp?url=/library/en-us/winui/winui/windowsuserinterface/dataexchange/clipboard/htmlclipboardformat.asp}
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
