
# Copyright 2009-2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Utilities to work with the clipboard for copy-pasting

Some functions defined here are also re-used for drag-and-drop
functionality, which works similar to the clipboard, but has a less
straight forward API.
'''

from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GdkPixbuf

import logging

from zim.fs import File, Dir, FS
from zim.newfs import LocalFolder
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
	(INTERNAL_PAGELIST_TARGET_NAME, Gtk.TargetFlags.SAME_APP, INTERNAL_PAGELIST_TARGET_ID)

PAGELIST_TARGET_ID = 3
PAGELIST_TARGET_NAME = 'text/x-zim-page-list'
PAGELIST_TARGET = (PAGELIST_TARGET_NAME, 0, PAGELIST_TARGET_ID)

IMAGE_TARGET_ID = 6
IMAGE_TARGETS = tuple(
	(name, 0, IMAGE_TARGET_ID) for name in [
		'image/png', 'image/x-wmf', 'application/x-navi-animation',
		'image/bmp', 'image/x-bmp', 'image/x-MS-bmp', 'image/gif',
		'image/x-icns', 'image/x-icon', 'image/x-ico', 'image/x-win-bitmap',
		'image/vnd.microsoft.icon', 'application/ico', 'image/ico',
		'image/icon', 'text/ico', 'image/jpeg', 'image/x-portable-anymap',
		'image/x-portable-bitmap', 'image/x-portable-graymap',
		'image/x-portable-pixmap', 'image/x-quicktime', 'image/qtif',
		'image/svg+xml', 'image/svg', 'image/svg-xml',
		'image/vnd.adobe.svg+xml', 'text/xml-svg', 'image/svg+xml-compressed',
		'image/x-tga', 'image/tiff', 'image/x-xbitmap', 'image/x-xpixmap'
	] # TODO - check any win32 specific types to be added
)
#IMAGE_TARGETS = tuple(Gtk.target_list_add_image_targets(info=IMAGE_TARGET_ID))
IMAGE_TARGET_NAMES = tuple([target[0] for target in IMAGE_TARGETS])

# Add image format names as well, seen these being used by MS Office
for format in GdkPixbuf.Pixbuf.get_formats():
	if format.get_mime_types()[0] in IMAGE_TARGET_NAMES:
		name = format.get_name()
		for n in (name, name.upper()):
			IMAGE_TARGET_NAMES += (n,)
			IMAGE_TARGETS += ((n, 0, IMAGE_TARGET_ID),)

#~ print IMAGE_TARGETS
#~ print IMAGE_TARGET_NAMES

URI_TARGET_ID = 7
URI_TARGETS = (('text/uri-list', 0, URI_TARGET_ID),)
#URI_TARGETS = tuple(Gtk.target_list_add_uri_targets(info=URI_TARGET_ID))
	# According to docs we should provide list as arg to this function,
	# but seems docs are not correct
URI_TARGET_NAMES = tuple([target[0] for target in URI_TARGETS])

HTML_TARGET_ID = 8
HTML_TARGET_NAMES = ('text/html', 'HTML Format')
	# "HTML Format" is from MS Word
HTML_TARGETS = tuple([(name, 0, HTML_TARGET_ID) for name in HTML_TARGET_NAMES])

TEXT_TARGET_ID = 9
TEXT_TARGETS = tuple(
	(name, 0, TEXT_TARGET_ID) for name in [
		'UTF8_STRING', 'COMPOUND_TEXT', 'TEXT', 'STRING',
		'text/plain;charset=utf-8', 'text/plain'
	]
)
#TEXT_TARGETS = tuple(Gtk.target_list_add_text_targets(info=TEXT_TARGET_ID))
	# According to docs we should provide list as arg to this function,
	# but seems docs are not correct
TEXT_TARGET_NAMES = tuple([target[0] for target in TEXT_TARGETS])

# All targets that we can convert to a parsetree, in order of choice
PARSETREE_ACCEPT_TARGETS = (
        PARSETREE_TARGET,
        INTERNAL_PAGELIST_TARGET, PAGELIST_TARGET,
) + IMAGE_TARGETS + URI_TARGETS + TEXT_TARGETS
PARSETREE_ACCEPT_TARGET_NAMES = tuple([target[0] for target in PARSETREE_ACCEPT_TARGETS])
#~ print('ACCEPT', PARSETREE_ACCEPT_TARGET_NAMES)



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
		if is_url_re.match(link):
			link = url_encode(link, mode=URL_ENCODE_READABLE) # just to be sure
		text += '%s\r\n' % link
	return text.encode()


def unpack_urilist(text):
	# FIXME be tolerant here for file://path/to/file uris here
	text = text.strip(b'\x00').decode() # Found trailing NULL character on windows
	lines = text.splitlines() # takes care of \r\n
	return [line for line in lines if line and not line.isspace()]
		# Just to be sure we also skip empty or whitespace lines

# TODO: Probably the serialize formats can replace custom copy/paste
# handlers in TextView and TextBuffer as well


def textbuffer_register_serialize_formats(buffer, notebook, page):
	buffer.register_serialize_format('text/x-zim-parsetree', serialize_parse_tree)
	buffer.register_deserialize_format('text/x-zim-parsetree', deserialize_parse_tree, (notebook, page))
	for name in (INTERNAL_PAGELIST_TARGET_NAME, PAGELIST_TARGET_NAME) + URI_TARGET_NAMES:
		buffer.register_deserialize_format(name, deserialize_urilist, (notebook, page))
	for name in IMAGE_TARGET_NAMES: # FIXME, should we limit the list ?
		buffer.register_deserialize_format(name, deserialize_image, (name, notebook, page))

def serialize_parse_tree(register_buf, content_buf, start, end, user_data):
	tree = content_buf.get_parsetree((start, end))
	xml = tree.tostring()
	return xml

def deserialize_parse_tree(register_buf, content_buf, iter, data, length, create_tags, user_data):
	notebook, path = user_data
	tree = ParseTree().fromstring(data)
	tree.resolve_images(notebook, path)
	content_buf.insert_parsetree(iter, tree, interactive=True)
	return True

def deserialize_urilist(register_buf, content_buf, iter, data, length, create_tags, user_data):
	notebook, path = user_data
	links = unpack_urilist(data)
	tree = _link_tree(links, notebook, path)
	content_buf.insert_parsetree(iter, tree, interactive=True)
	return True

def deserialize_image(register_buf, content_buf, iter, data, length, create_tags, user_data):
	# Implementation note: we follow gtk_selection_get_pixbuf() in usage of
	# Gtk.PixbufLoader to capture clipboard data in a pixbuf object.
	# We could skip this, but it allows for on-the-fly conversion of the data
	# type.
	mimetype, notebook, path = user_data

	# capture image
	loader = GdkPixbuf.PixbufLoader()
	loader.write(data)
	loader.close()
	pixbuf = loader.get_pixbuf()

	# save it as an attachment
	dir = notebook.get_attachments_dir(path)
	if not dir.exists():
		logger.debug("Creating attachment dir: %s", dir)
		dir.touch()

	format, extension = _get_image_info(mimetype)
	if format is None or format == 'bmp':
		# default to png format
		# special casing bmp since many window apps use it internally
		# but is quite large to store, so compress by using png
		format, extension = 'png', 'png'

	file = dir.new_file('pasted_image.%s' % extension)
	logger.debug("Saving image from clipboard to %s", file)
	pixbuf.savev(file.path, format, [], [])
	FS.emit('path-created', file) # notify version control

	# and insert it in the page
	links = [file.uri]
	tree = _link_tree(links, notebook, path)
	content_buf.insert_parsetree(iter, tree, interactive=True)
	return True


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

	@param selectiondata: a C{Gtk.SelectionData} object
	@param notebook: a L{Notebook} object
	@param path: a L{Path} object

	@returns: a L{ParseTree} or C{None}
	'''
	# TODO: check relative linking for all parsetrees !!!

	targetname = selectiondata.get_target().name()
	if targetname == PARSETREE_TARGET_NAME:
		return ParseTree().fromstring(selectiondata.get_data())
	elif targetname in (INTERNAL_PAGELIST_TARGET_NAME, PAGELIST_TARGET_NAME) \
	or targetname in URI_TARGET_NAMES:
		links = selectiondata.get_uris()
		return _link_tree(links, notebook, path)
	elif targetname in TEXT_TARGET_NAMES:
		# plain text parser should highlight urls etc.
		# FIXME some apps drop text/uri-list as a text/plain mimetype
		# try to catch this situation by a check here
		text = selectiondata.get_text()
		if text:
			return get_format('plain').Parser().parse(text, partial=True)
		else:
			return None
	elif targetname in IMAGE_TARGET_NAMES:
		# save image
		pixbuf = selectiondata.get_pixbuf()
		if not pixbuf:
			return None

		dir = notebook.get_attachments_dir(path)
		assert isinstance(dir, LocalFolder) or hasattr(dir, '_folder') and isinstance(dir._folder, LocalFolder)
			# XXX: assert we have local path  - HACK to deal with FilesAttachmentFolder
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
		pixbuf.savev(file.path, format, [], [])
		FS.emit('path-created', file) # notify version control

		links = [file.uri]
		return _link_tree(links, notebook, path)
	else:
		return None


def _link_tree(links, notebook, path):
	# Convert a list of links (of any type) into a parsetree
	#~ print('LINKS: ', links)
	#~ print('NOTEBOOK and PATH:', notebook, path)
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
				target = Path(Path.makeValidPageName(link)) # Assume links are always absolute
				href = notebook.pages.create_link(path, target)
				link = href.to_wiki_link()
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
	for format in GdkPixbuf.Pixbuf.get_formats():
		name = format.get_name()
		mimetypes = format.get_mime_types()
		if targetname in (name, name.upper()) or targetname in mimetypes:
			if format.is_writable():
				return name, format.get_extensions()[0]
			else:
				return None, None
	else:
		return None, None


class MockSelectionData(object):
	'''Adapter to allow usage of C{ClipboardData} as input for
	C{parsetree_from_selectiondata()}
	'''

	def __init__(self, target, clipboard_data):
		self.target = target
		self.data = clipboard_data

	def get_target(self):
		target_name = self.target[0]
		return Gdk.Atom.intern(target_name, False)

	def get_data(self):
		target_id = self.target[-1]
		return self.data.get_data_as(target_id)

	def get_text(self):
		return self.data.get_data_as(TEXT_TARGET_ID)

	def get_uris(self):
		if self.target in URI_TARGETS:
			return self.data.get_data_as(URI_TARGET_ID)
		else:
			return unpack_urilist(self.get_data())

	def get_pixbuf(self):
		raise NotImplementedError


class ClipboardData(object):
	'''Wrapper for data that can be set on the clipboard and pasted
	multiple formats
	'''

	targets = ()

	def get_data_as(self, targetid):
		'''Return data in the requested target format
		@param targetid: the target id
		@implementation: must be implemented by sub-classes
		'''
		raise NotImplementedError


class UriData(ClipboardData):

	targets = URI_TARGETS + TEXT_TARGETS

	def __init__(self, *obj):
		uris = []
		text = []
		for o in obj:
			if isinstance(o, (File, Dir)):
				uris.append(o.uri)
				text.append(o.user_path)
			else:
				uri = o if isinstance(o, str) else o.uri
				uris.append(uri)
				text.append(uri)
		self.uris = tuple(uris)
		self.text = ' '.join(text)

	def get_data_as(self, targetid):
		if targetid == URI_TARGET_ID:
			return self.uris
		else:
			return self.text


class InterWikiLinkData(UriData):

	targets = (PARSETREE_TARGET,) + UriData.targets

	def __init__(self, href, url):
		UriData.__init__(self, url)
		self.interwiki_href = href

	def get_data_as(self, targetid):
		if targetid == PARSETREE_TARGET_ID:
			parsetree = _link_tree((self.interwiki_href,), None, None)
			return parsetree.tostring()
		else:
			return UriData.get_data_as(self, targetid)


class ParseTreeData(ClipboardData):

	targets = (PARSETREE_TARGET,) + HTML_TARGETS + TEXT_TARGETS

	def __init__(self, notebook, path, parsetree, format):
		self.notebook = notebook # FIXME - should not need to keep this reference - resolve parsetree immediatly
		self.path = path
		self.parsetree = parsetree
		self.format = format

	def get_data_as(self, targetid):
		if targetid == PARSETREE_TARGET_ID:
			# TODO make links absolute (?)
			return self.parsetree.tostring()
		elif targetid == HTML_TARGET_ID:
			dumper = get_format('html').Dumper(
				linker=StaticExportLinker(self.notebook, source=self.path))
			html = ''.join(dumper.dump(self.parsetree))
			return wrap_html(html, target=selectiondata.get_target().name())
		elif targetid == TEXT_TARGET_ID:
			if self.format in ('wiki', 'plain'):
				dumper = get_format(self.format).Dumper()
			else:
				dumper = get_format(self.format).Dumper(
					linker=StaticExportLinker(self.notebook, source=self.path))

			return ''.join(dumper.dump(self.parsetree))
		else:
			raise ValueError('Unknown target id %i' % targetid)


class PageLinkData(ClipboardData):

	targets = (INTERNAL_PAGELIST_TARGET, PAGELIST_TARGET) + TEXT_TARGETS

	def __init__(self, notebook, path):
		self.notebookname = notebook.name
		self.path = path

	def get_data_as(self, targetid):
		if targetid == INTERNAL_PAGELIST_TARGET_ID:
			return pack_urilist((self.path.name,))
		elif targetid == PAGELIST_TARGET_ID:
			link = "%s?%s" % (self.notebookname, self.path.name)
			return pack_urilist((link,))
		elif targetid == TEXT_TARGET_ID:
			return self.path.name
		else:
			raise ValueError('Unknown target id %i' % targetid)


class ClipboardManager(object):
	'''Wrapper for C{Gtk.Clipboard}, supporting specific data formats'''

	def __init__(self, name):
		'''Constructor
		@param name: clipboard name, can be either "CLIPBOARD" or "PRIMARY",
		see C{Gtk.Clipboard} for details.
		'''
		assert name in ('CLIPBOARD', 'PRIMARY')
		atom = Gdk.SELECTION_CLIPBOARD if name == 'CLIPBOARD' else Gdk.SELECTION_PRIMARY
		self.clipboard = Gtk.Clipboard.get(atom)
		self.data = None

	def clear(self):
		if self.data is not None:
			self.clipboard.clear()
		self.data = None

	def set_clipboard_data(self, clipboard_data):
		'''Set an item on the clipboard
		@param clipboard_data: a L{ClipboardData} object
		'''
		self.data = clipboard_data
		#self.clipboard.set_with_data(self.data.targets, self._get, self._clear) \
		#	or logger.warn('Failed to set data on clipboard')

		### set_with_data() workaround
		assert TEXT_TARGETS[0] in self.data.targets
		text = self.data.get_data_as(TEXT_TARGET_ID)
		self.clipboard.set_text(text, -1)
		self.data._workaround_text = text
		###

	def _get(self, clipboard, selectiondata, targetid):
		logger.debug(
			"Clipboard requests data as '%s', we have %r",
			selectiondata.get_target().name(),
			self.data
		)
		data = self.data.get_data_as(targetid)
		if targetid == TEXT_TARGET_ID:
			selectiondata.set_text(data, -1)
		elif targetid == URI_TARGET_ID:
			selectiondata.set_uris(data)
		else:
			selectiondata.set(PARSETREE_TARGET_NAME, 8, data)

	def _clear(self):
		self.data = None

	def set_text(self, text):
		'''Set text to the clipboard
		@param text: text to set on the clipboard
		@note: DO NOT USE THIS METHOD if you can use L{set_parsetree()}
		instead
		'''
		self.clipboard.set_text(text, -1)

	def get_text(self):
		'''Get text from the clipboard.
		@returns: (unicode) text or C{None}
		@note: DO NOT USE THIS METHOD if you can use L{get_parsetree()}
		instead
		'''
		return self.clipboard.wait_for_text()

	def set_parsetree(self, notebook, path, parsetree, format='plain'):
		'''Copy a parsetree to the clipboard. The parsetree can be pasted by
		the user either as formatted text within zim or as plain text outside
		zim. The tree can be the full tree for 'page', but also a selection.

		@param notebook: the L{Notebook} object
		@param path: the L{Path} object - used to resolve links etc.
		@param parsetree: the actual L{ParseTree} to be set on the clipboard
		@keyword format: the format to use for pasting text, e.g. 'wiki' or 'plain'
		'''
		self.set_clipboard_data(
			ParseTreeData(notebook, path, parsetree, format) )

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
		(has_data, atoms) = self.clipboard.wait_for_targets()
		logger.debug('Targets available for paste: %s, we want parsetree', atoms)

		if not has_data:
			return None

		### set_with_data() workaround
		if atoms and self.data and hasattr(self.data, '_workaround_text') \
			and any(a.name() in TEXT_TARGET_NAMES for a in atoms):
				text = self.clipboard.wait_for_text()
				if text == self.data._workaround_text:
					targets = sorted(
						filter(lambda t: t in PARSETREE_ACCEPT_TARGETS, self.data.targets),
						key=lambda t: PARSETREE_ACCEPT_TARGETS.index(t)
					)
					assert len(targets) > 0
					logger.debug('Requesting data for %s -- using set_with_data() workaround', targets[0])
					selectiondata = MockSelectionData(targets[0], self.data)
					return parsetree_from_selectiondata(selectiondata, notebook, path)
		###

		atoms = sorted(
					filter(lambda a: a and a.name() in PARSETREE_ACCEPT_TARGET_NAMES, atoms),
					key=lambda a: PARSETREE_ACCEPT_TARGET_NAMES.index(a.name())
				)
				# NOTE: "atoms" can contain None values, see issue #774
		if atoms:
			atom = atoms[0]  # TODO why choose 1st index?
			logger.debug('Requesting data for %s', atom)
			selectiondata = self.clipboard.wait_for_contents(atom)
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
		self.set_clipboard_data(PageLinkData(notebook, path))

	def set_interwikilink(self, href, url):
		'''Copy an interwiki link to the clipboard
		@param href: the link as shown in zim, e.g. "wp?foobar"
		@param url: the expanded url for this interwiki link, e.g.
		"http://en.wikipedia.org/wiki/foobar"
		'''
		self.set_clipboard_data(InterWikiLinkData(href, url))

	def set_uri(self, *uris):
		'''Copy an uri to the clipboard
		@param uri: an uri as string, or an object with an attribute C{uri}
		'''
		self.set_clipboard_data(UriData(*uris))


Clipboard = ClipboardManager("CLIPBOARD") #: Singleton object for the default clipboard


SelectionClipboard = ClipboardManager("PRIMARY") #: Singleton object for the selection clipboard (unix)




########### Code to deal with HTML formatting on windows ############

HTML_HEAD = '''\
<meta http-equiv="Content-Type" content="text/html;charset=utf-8">
<meta name="Description" content="Copy-Paste Buffer">
<meta name="Generator" content="Zim">'''

def wrap_html(html, target):
	'''Function to wrap html with appropriate headers based on target type'''
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
			lenPrefix, len(html) + lenPrefix,
			fragmentStart + lenPrefix, fragmentEnd + lenPrefix,
			selectionStart + lenPrefix, selectionEnd + lenPrefix,
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
