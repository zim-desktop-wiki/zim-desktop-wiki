# Copyright 2026 Joshes <mail@template7.de>
# License: GPL v2+
#
# Zim plugin to find and clean up orphaned attachment files.
# Scans all pages for image/file references, then lists attachment
# files that are no longer referenced by any page.

import logging
import mimetypes
import os

from gi.repository import Gio, Gtk, GLib, GdkPixbuf

from zim.plugins import PluginClass
from zim.actions import action
from zim.gui.pageview import PageViewExtension
from zim.gui.widgets import Dialog, ErrorDialog
from zim.newfs import LocalFile
from zim.newfs.helpers import TrashHelper, TrashNotSupportedError, format_file_size
from zim.parse.links import link_type


logger = logging.getLogger('zim.plugins.attachmentcleaner')


# Companion source file extensions for imagegenerator plugins
_COMPANION_EXTENSIONS = {
	'image+equation': '.tex',
	'image+diagram': '.dot',
	'image+gnuplot': '.gnuplot',
	'image+ditaa': '.ditaa',
	'image+mermaid': '.mermaid',
	'image+score': '.ly',
	'image+sequencediagram': '.msc',
}


class AttachmentCleanerPlugin(PluginClass):

	plugin_info = {
		'name': _('Attachment Cleaner'),  # T: plugin name
		'description': _('''\
Find and remove orphaned attachment files.

Scans all pages in the notebook for image and file references,
then lists attachment files that are no longer referenced by
any page. Selected orphans can be moved to the system trash.
'''),  # T: plugin description
		'author': 'Joshes',
		'help': 'Plugins:Attachment Cleaner',
	}


class AttachmentCleanerExtension(PageViewExtension):

	@action(_('Clean Up _Attachments...'), menuhints='tools')  # T: menu item
	def show_attachment_cleaner(self):
		notebook = self.pageview.notebook
		AttachmentCleanerDialog(self.pageview, notebook).run()


class OrphanScanner:
	"""Scans a notebook for orphaned attachment files."""

	def __init__(self, notebook):
		self.notebook = notebook

	def collect_refs_for_page(self, tree, attach_dir, referenced):
		"""Extract all file references from a page's parse tree.

		Resolves each reference to an absolute path and adds it to
		the referenced set.
		"""
		# IMAGE elements
		for elt in tree._etree.iter('img'):
			src = elt.attrib.get('src', '')
			if src:
				self._add_resolved(src, attach_dir, referenced)

		# OBJECT elements (imagegenerator plugins)
		for elt in tree._etree.iter('object'):
			src = elt.attrib.get('src', '')
			obj_type = elt.attrib.get('type', '')
			if src and src != '_new_' and obj_type.startswith('image+'):
				self._add_resolved(src, attach_dir, referenced)
				# Also mark the companion source file (.tex, .dot, ...)
				ext = _COMPANION_EXTENSIONS.get(obj_type)
				if ext and '.' in src:
					companion = src.rsplit('.', 1)[0] + ext
					self._add_resolved(companion, attach_dir, referenced)

		# LINK elements pointing to files
		for elt in tree._etree.iter('link'):
			href = elt.attrib.get('href', '')
			if href and link_type(href) == 'file':
				self._add_resolved(href, attach_dir, referenced)

	def _add_resolved(self, path, attach_dir, referenced):
		try:
			abs_path = attach_dir.get_abspath(path)
			path_str = abs_path.path if hasattr(abs_path, 'path') else str(abs_path)
			referenced.add(os.path.realpath(path_str))
		except Exception:
			logger.debug('Could not resolve attachment path: %s', path)


class AttachmentCleanerDialog(Dialog):

	COL_SELECTED = 0
	COL_ICON = 1
	COL_FILENAME = 2
	COL_PAGE = 3
	COL_SIZE_STR = 4
	COL_SIZE_BYTES = 5
	COL_FILE_PATH = 6

	def __init__(self, pageview, notebook):
		Dialog.__init__(self, pageview, _('Clean Up Attachments'),
			buttons=None, defaultwindowsize=(650, 480))
		self.notebook = notebook
		self._scan_active = False

		self._build_ui()
		self._start_scan()

	def _build_ui(self):
		# Info label
		info = Gtk.Label(
			label=_('Attachment files that are not referenced by any page in the notebook.')
		)
		info.set_xalign(0.0)
		info.set_line_wrap(True)
		self.vbox.pack_start(info, False, True, 6)

		# Progress bar (visible during scan)
		self._progress_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
		self._progress_label = Gtk.Label(label=_('Scanning notebook...'))
		self._progress_label.set_xalign(0.0)
		self._progress_bar = Gtk.ProgressBar()
		self._progress_box.pack_start(self._progress_label, False, True, 0)
		self._progress_box.pack_start(self._progress_bar, False, True, 0)
		self.vbox.pack_start(self._progress_box, False, True, 6)

		# TreeView
		self._store = Gtk.ListStore(
			bool,               # COL_SELECTED
			GdkPixbuf.Pixbuf,   # COL_ICON
			str,                # COL_FILENAME
			str,                # COL_PAGE
			str,                # COL_SIZE_STR
			int,                # COL_SIZE_BYTES
			str,                # COL_FILE_PATH (absolute)
		)

		self._treeview = Gtk.TreeView(model=self._store)
		self._treeview.set_rules_hint(True)

		# Column: checkbox
		toggle = Gtk.CellRendererToggle()
		toggle.connect('toggled', self._on_toggle)
		col = Gtk.TreeViewColumn('', toggle, active=self.COL_SELECTED)
		self._treeview.append_column(col)

		# Column: icon + filename
		col = Gtk.TreeViewColumn(_('File'))
		icon_renderer = Gtk.CellRendererPixbuf()
		text_renderer = Gtk.CellRendererText()
		col.pack_start(icon_renderer, False)
		col.pack_start(text_renderer, True)
		col.add_attribute(icon_renderer, 'pixbuf', self.COL_ICON)
		col.add_attribute(text_renderer, 'text', self.COL_FILENAME)
		col.set_expand(True)
		col.set_resizable(True)
		col.set_sort_column_id(self.COL_FILENAME)
		self._treeview.append_column(col)

		# Column: page
		renderer = Gtk.CellRendererText()
		col = Gtk.TreeViewColumn(_('Page'), renderer, text=self.COL_PAGE)
		col.set_resizable(True)
		col.set_min_width(120)
		col.set_sort_column_id(self.COL_PAGE)
		self._treeview.append_column(col)

		# Column: size
		renderer = Gtk.CellRendererText()
		col = Gtk.TreeViewColumn(_('Size'), renderer, text=self.COL_SIZE_STR)
		col.set_sort_column_id(self.COL_SIZE_BYTES)
		self._treeview.append_column(col)

		scrolled = Gtk.ScrolledWindow()
		scrolled.set_shadow_type(Gtk.ShadowType.IN)
		scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
		scrolled.add(self._treeview)
		self.vbox.pack_start(scrolled, True, True, 0)

		# Status label
		self._status_label = Gtk.Label(label='')
		self._status_label.set_xalign(0.0)
		self.vbox.pack_start(self._status_label, False, True, 4)

		# Button row: select all / none
		btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
		btn_all = Gtk.Button.new_with_mnemonic(_('Select _All'))
		btn_all.connect('clicked', lambda b: self._select_all(True))
		btn_none = Gtk.Button.new_with_mnemonic(_('Select _None'))
		btn_none.connect('clicked', lambda b: self._select_all(False))
		btn_box.pack_start(btn_all, False, True, 0)
		btn_box.pack_start(btn_none, False, True, 0)
		self.vbox.pack_start(btn_box, False, True, 4)

		# Action buttons
		self.add_button(_('_Cancel'), Gtk.ResponseType.CANCEL)
		self._btn_trash = self.add_button(_('Move to _Trash'), Gtk.ResponseType.OK)
		self._btn_trash.set_sensitive(False)
		self._btn_trash.get_style_context().add_class('destructive-action')

		self.show_all()

	def _start_scan(self):
		self._scan_active = True
		self._scan_gen = self._scan_generator()
		GLib.idle_add(self._scan_step)

	def _scan_step(self):
		if not self._scan_active:
			return False
		try:
			next(self._scan_gen)
			return True
		except StopIteration:
			self._scan_active = False
			return False

	def on_destroy(self):
		self._scan_active = False
		Dialog.on_destroy(self)

	def _scan_generator(self):
		scanner = OrphanScanner(self.notebook)
		pages = list(self.notebook.pages.walk())
		total = len(pages)
		referenced = set()

		# Pass 1: collect all references
		for i, record in enumerate(pages):
			if total > 0:
				self._progress_bar.set_fraction(i / (total * 2))
			self._progress_label.set_text(
				_('Scanning references: %s') % record.name  # T: progress label
			)
			page = self.notebook.get_page(record)
			tree = page.get_parsetree()
			if tree is not None:
				attach_dir = self.notebook.get_attachments_dir(page)
				scanner.collect_refs_for_page(tree, attach_dir, referenced)
			yield

		# Pass 2: find orphans
		orphans = []
		for i, record in enumerate(pages):
			if total > 0:
				self._progress_bar.set_fraction((total + i) / (total * 2))
			self._progress_label.set_text(
				_('Checking attachments: %s') % record.name  # T: progress label
			)
			page = self.notebook.get_page(record)
			attach_dir = self.notebook.get_attachments_dir(page)
			if attach_dir.exists():
				for f in attach_dir.list_files():
					real_path = os.path.realpath(f.path)
					if real_path not in referenced:
						try:
							size = os.path.getsize(f.path)
						except OSError:
							size = 0
						orphans.append((f, record.name, size))
			yield

		self._on_scan_complete(orphans)

	def _on_scan_complete(self, orphans):
		self._progress_box.hide()

		orphans.sort(key=lambda x: (x[1], x[0].basename.lower()))
		icon_theme = Gtk.IconTheme.get_default()

		self._store.clear()
		for f, page_name, size in orphans:
			icon = self._get_file_icon(f.basename, icon_theme)
			self._store.append([
				True,
				icon,
				f.basename,
				page_name,
				format_file_size(size),
				size,
				f.path,
			])

		self._update_status()

		if orphans:
			self._btn_trash.set_sensitive(True)
		else:
			self._status_label.set_text(_('No orphaned attachments found.'))

	@staticmethod
	def _get_file_icon(basename, icon_theme):
		try:
			content_type, _ = mimetypes.guess_type(basename)
			if content_type:
				gicon = Gio.content_type_get_icon(content_type)
				icon_info = icon_theme.lookup_by_gicon(gicon, 16, 0)
				if icon_info:
					return icon_info.load_icon()
		except Exception:
			pass
		try:
			return icon_theme.load_icon('text-x-generic', 16, 0)
		except Exception:
			return None

	def _on_toggle(self, renderer, path):
		it = self._store.get_iter(path)
		self._store[it][self.COL_SELECTED] = not self._store[it][self.COL_SELECTED]
		self._update_status()

	def _select_all(self, state):
		for row in self._store:
			row[self.COL_SELECTED] = state
		self._update_status()

	def _update_status(self):
		count = 0
		total_bytes = 0
		for row in self._store:
			if row[self.COL_SELECTED]:
				count += 1
				total_bytes += row[self.COL_SIZE_BYTES]

		n_total = len(self._store)
		if n_total == 0:
			return

		if count == 0:
			self._status_label.set_text(
				_('%d orphans found, none selected') % n_total
			)
			self._btn_trash.set_sensitive(False)
		else:
			self._status_label.set_markup(
				'<b>%d</b> / %d selected \u00b7 %s' % (
					count, n_total, format_file_size(total_bytes)
				)
			)
			self._btn_trash.set_sensitive(True)

	def do_response_ok(self):
		selected = []
		for row in self._store:
			if row[self.COL_SELECTED]:
				selected.append(row[self.COL_FILE_PATH])

		if not selected:
			return True

		trash = TrashHelper()
		errors = []
		deleted = 0

		for path in selected:
			try:
				trash.trash(LocalFile(path))
				deleted += 1
			except TrashNotSupportedError as e:
				errors.append('%s: %s' % (os.path.basename(path), e))
				break

		if errors:
			ErrorDialog(
				self,
				_('Could not move some files to trash:\n%s') % '\n'.join(errors)
			).run()

		logger.info('Attachment cleaner: trashed %d files', deleted)
		return True
