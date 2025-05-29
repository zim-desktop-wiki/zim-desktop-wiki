# Copyright 2008-2023 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import logging

from gi.repository import Gtk

import os
import zim.datetimetz as datetime

from zim.errors import Error
from zim.config import ConfigManager
from zim.formats import get_format
from zim.notebook import HRef, PageNotFoundError
from zim.parse.links import link_type
from zim.templates.expression import ExpressionFunction
from zim.gui.widgets import Dialog, FileDialog, ErrorDialog, BrowserTreeView, ScrolledWindow
from zim.gui.base.images import image_file_get_dimensions
from zim.gui.applications import edit_config_file, open_folder


logger = logging.getLogger('zim.gui.pageview')



class InsertDateDialog(Dialog):
	'''Dialog to insert a date-time in the page'''

	FORMAT_COL = 0 # format string
	DATE_COL = 1 # strfime rendering of the format

	def __init__(self, parent, buffer, notebook, page):
		Dialog.__init__(
			self,
			parent,
			_('Insert Date and Time'), # T: Dialog title
			button=_('_Insert'), # T: Button label
			use_default_button=True
		)
		self.buffer = buffer
		self.notebook = notebook
		self.page = page
		self.date = datetime.now()

		self.uistate.setdefault('lastusedformat', '')
		self.uistate.setdefault('linkdate', False)

		## Add Calendar widget
		from zim.plugins.journal import Calendar # FIXME put this in zim.gui.widgets

		label = Gtk.Label()
		label.set_markup('<b>' + _("Date") + '</b>') # T: label in "insert date" dialog
		label.set_alignment(0.0, 0.5)
		self.vbox.pack_start(label, False, False, 0)

		self.calendar = Calendar()
		self.calendar.set_display_options(
			Gtk.CalendarDisplayOptions.SHOW_HEADING |
			Gtk.CalendarDisplayOptions.SHOW_DAY_NAMES |
			Gtk.CalendarDisplayOptions.SHOW_WEEK_NUMBERS)
		self.calendar.connect('day-selected', lambda c: self.set_date(c.get_date()))
		self.vbox.pack_start(self.calendar, False, True, 0)

		## Add format list box
		label = Gtk.Label()
		label.set_markup('<b>' + _("Format") + '</b>') # T: label in "insert date" dialog
		label.set_alignment(0.0, 0.5)
		self.vbox.pack_start(label, False, False, 0)

		model = Gtk.ListStore(str, str) # FORMAT_COL, DATE_COL
		self.view = BrowserTreeView(model)
		self.vbox.pack_start(ScrolledWindow(self.view), True, True, 0)

		cell_renderer = Gtk.CellRendererText()
		column = Gtk.TreeViewColumn('_date_', cell_renderer, text=1)
		self.view.append_column(column)
		self.view.set_headers_visible(False)
		self.view.connect('row-activated',
			lambda *a: self.response(Gtk.ResponseType.OK))

		## Add Link checkbox and Edit button
		self.linkbutton = Gtk.CheckButton.new_with_mnemonic(_('_Link to date'))
			# T: check box in InsertDate dialog
		self.linkbutton.set_active(self.uistate['linkdate'])
		self.vbox.pack_start(self.linkbutton, False, True, 0)

		button = Gtk.Button.new_with_mnemonic(_('_Edit')) # T: Button label
		button.connect('clicked', self.on_edit)
		self.action_area.add(button)
		self.action_area.reorder_child(button, 1)

		## Setup data
		self.load_file()
		self.set_date(self.date)

	def load_file(self):
		lastused = None
		model = self.view.get_model()
		model.clear()
		file = ConfigManager.get_config_file('dates.list')
		for line in file.readlines():
			line = line.strip()
			if not line or line.startswith('#'):
				continue
			try:
				format = line
				iter = model.append((format, format))
				if format == self.uistate['lastusedformat']:
					lastused = iter
			except:
				logger.exception('Could not parse date: %s', line)

		if len(model) == 0:
			# file not found ?
			model.append(("%c", "%c"))

		if not lastused is None:
			path = model.get_path(lastused)
			self.view.get_selection().select_path(path)

	def set_date(self, date):
		self.date = date

		def update_date(model, path, iter):
			format = model[iter][self.FORMAT_COL]
			try:
				string = datetime.strftime(format, date)
			except ValueError:
				string = 'INVALID: ' + format
			model[iter][self.DATE_COL] = string

		model = self.view.get_model()
		model.foreach(update_date)

		link = date.strftime('%Y-%m-%d') # YYYY-MM-DD
		self.link = self.notebook.suggest_link(self.page, link)
		self.linkbutton.set_sensitive(not self.link is None)

	#def run(self):
		#self.view.grab_focus()
		#Dialog.run(self)

	def save_uistate(self):
		model, iter = self.view.get_selection().get_selected()
		if iter:
			format = model[iter][self.FORMAT_COL]
			self.uistate['lastusedformat'] = format
		self.uistate['linkdate'] = self.linkbutton.get_active()

	def on_edit(self, button):
		file = ConfigManager.get_config_file('dates.list') # XXX
		if edit_config_file(self, file):
			self.load_file()

	def do_response_ok(self):
		model, iter = self.view.get_selection().get_selected()
		if iter:
			text = model[iter][self.DATE_COL]
		else:
			text = model[0][self.DATE_COL]

		if self.link and self.linkbutton.get_active():
			self.buffer.insert_link_at_cursor(text, self.link.name)
		else:
			self.buffer.insert_at_cursor(text)

		return True


class InsertImageDialog(FileDialog):
	'''Dialog to insert an image in the page'''

	def __init__(self, parent, buffer, notebook, path, file=None):
		FileDialog.__init__(
			self, parent, _('Insert Image'), Gtk.FileChooserAction.OPEN)
			# T: Dialog title

		self.buffer = buffer
		self.notebook = notebook
		self.path = path

		self.uistate.setdefault('attach_inserted_images', False)
		self.uistate.setdefault('last_image_folder', None, check=str)

		self.add_shortcut(notebook, path)
		self.add_filter_images()

		checkbox = Gtk.CheckButton.new_with_mnemonic(_('Attach image first'))
			# T: checkbox in the "Insert Image" dialog
		checkbox.set_active(self.uistate['attach_inserted_images'])
		self.filechooser.set_extra_widget(checkbox)

		if file:
			self.set_file(file)
		else:
			self.load_last_folder()

	def do_response_ok(self):
		file = self.get_file()
		if file is None:
			return False

		try:
			image_file_get_dimensions(file.path)
		except AssertionError:
			ErrorDialog(self, _('File type not supported: %s') % file.mimetype()).run()
				# T: Error message when trying to insert a not supported file as image
			return False

		self.save_last_folder()

		# Similar code in AttachFileDialog
		checkbox = self.filechooser.get_extra_widget()
		self.uistate['attach_inserted_images'] = checkbox.get_active()
		if self.uistate['attach_inserted_images']:
			folder = self.notebook.get_attachments_dir(self.path)
			if not file.ischild(folder):
				file = attach_file(self, self.notebook, self.path, file)
				if file is None:
					return False # Cancelled overwrite dialog

		src = self.notebook.relative_filepath(file, self.path) or file.uri
		self.buffer.insert_image_at_cursor(file, src)
		return True


class AttachFileDialog(FileDialog):

	def __init__(self, parent, buffer, notebook, path, file=None):
		assert path, 'Need a page here'
		FileDialog.__init__(self, parent, _('Attach File'), multiple=True) # T: Dialog title
		self.buffer = buffer
		self.notebook = notebook
		self.path = path

		dir = notebook.get_attachments_dir(path)
		if dir is None:
			ErrorDialog(self, _('Page "%s" does not have a folder for attachments') % self.path)
				# T: Error dialog - %s is the full page name
			raise Exception('Page "%s" does not have a folder for attachments' % self.path)

		self.add_shortcut(notebook, path)
		if file:
			self.set_file(file)
		else:
			self.load_last_folder()

	def do_response_ok(self):
		files = self.get_files()
		if not files:
			return False

		self.save_last_folder()

		inserted = False
		last = len(files) - 1
		for i, file in enumerate(files):
			file = attach_file(self, self.notebook, self.path, file)
			if file is not None:
				inserted = True
				text = self.notebook.relative_filepath(file, path=self.path)
				self.buffer.insert_link_at_cursor(text, href=text)
				if i != last:
					self.buffer.insert_at_cursor(' ')

		return inserted # If nothing is inserted, return False and do not close dialog


def attach_file(widget, notebook, path, file, force_overwrite=False):
	folder = notebook.get_attachments_dir(path)
	if folder is None:
		raise Error('%s does not have an attachments dir' % path)

	dest = folder.file(file.basename)
	if dest.exists() and not force_overwrite:
		dialog = PromptExistingFileDialog(widget, dest)
		dest = dialog.run()
		if dest is None:
			return None	# dialog was cancelled
		elif dest.exists():
			dest.remove()

	file.copyto(dest)
	return dest


class PromptExistingFileDialog(Dialog):
	'''Dialog that is used e.g. when a file should be attached to zim,
	but a file with the same name already exists in the attachment
	directory. This Dialog allows to suggest a new name or overwrite
	the existing one.

	For this dialog C{run()} will return either the original file
	(for overwrite), a new file, or None when the dialog was canceled.
	'''

	def __init__(self, widget, file):
		Dialog.__init__(self, widget, _('File Exists'), buttons=None) # T: Dialog title
		self.add_help_text( _('''\
A file with the name <b>"%s"</b> already exists.
You can use another name or overwrite the existing file.''' % file.basename),
		) # T: Dialog text in 'new filename' dialog
		self.folder = file.parent()
		self.old_file = file

		suggested_filename = self.folder.new_file(file.basename).basename
		self.add_form((
				('name', 'string', _('Filename')), # T: Input label
			), {
				'name': suggested_filename
			}
		)
		self.form.widgets['name'].set_check_func(self._check_valid)

		# all buttons are defined in this class, to get the ordering right
		# [show folder]      [overwrite] [cancel] [ok]
		button = Gtk.Button.new_with_mnemonic(_('_Browse')) # T: Button label
		button.connect('clicked', self.do_show_folder)
		self.action_area.add(button)
		self.action_area.set_child_secondary(button, True)

		button = Gtk.Button.new_with_mnemonic(_('Overwrite')) # T: Button label
		button.connect('clicked', self.do_response_overwrite)
		self.add_action_widget(button, Gtk.ResponseType.NONE)

		self.add_button(_('_Cancel'), Gtk.ResponseType.CANCEL) # T: Button label
		self.add_button(_('_OK'), Gtk.ResponseType.OK) # T: Button label
		self._no_ok_action = False

		self.form.widgets['name'].connect('focus-in-event', self._on_focus)

	def _on_focus(self, widget, event):
		# filename length without suffix
		length = len(os.path.splitext(widget.get_text())[0])
		widget.select_region(0, length)

	def _check_valid(self, filename):
		# Only valid when same dir and does not yet exist
		file = self.folder.file(filename)
		return file.ischild(self.folder) and not file.exists()

	def do_show_folder(self, *a):
		open_folder(self, self.folder)

	def do_response_overwrite(self, *a):
		logger.info('Overwriting %s', self.old_file.path)
		self.result = self.old_file

	def do_response_ok(self):
		if not self.form.widgets['name'].get_input_valid():
			return False

		newfile = self.folder.file(self.form['name'])
		logger.info('Selected %s', newfile.path)
		assert newfile.ischild(self.folder) # just to be real sure
		assert not newfile.exists() # just to be real sure
		self.result = newfile
		return True


class EditImageDialog(Dialog):
	'''Dialog to edit properties of an embedded image'''

	def __init__(self, parent, buffer, notebook, path):
		Dialog.__init__(self, parent, _('Edit Image')) # T: Dialog title
		self.buffer = buffer
		self.notebook = notebook
		self.path = path

		iter = buffer.get_iter_at_mark(buffer.get_insert())
		image_data = self.buffer.get_image_data(iter)
		if image_data is None:
			iter.backward_char()
			image_data = self.buffer.get_image_data(iter)
			assert image_data, 'No image found'
		self._image_data = image_data.copy()
		self._iter = iter.get_offset()

		src = image_data['src']
		if '?' in src:
			i = src.find('?')
			src = src[:i]
		href = image_data.get('href', '')
		anchor = image_data.get('id', '')
		self.add_form([
				('file', 'image', _('Location')), # T: Input in 'edit image' dialog
				('href', 'link', _('Link to'), path), # T: Input in 'edit image' dialog
				('width', 'int', _('Width'), (0, 1)), # T: Input in 'edit image' dialog
				('height', 'int', _('Height'), (0, 1)), # T: Input in 'edit image' dialog
				('anchor', 'string', _('Id'))
			],
			{'file': src, 'href': href, 'anchor': anchor}
			# range for width and height are set in set_ranges()
		)
		self.form.widgets['file'].set_use_relative_paths(notebook, path)
		self.form.widgets['file'].allow_empty = False
		self.form.widgets['file'].show_empty_invalid = True
		self.form.widgets['file'].update_input_valid()

		reset_button = Gtk.Button.new_with_mnemonic(_('_Reset Size'))
			# T: Button in 'edit image' dialog
		hbox = Gtk.HBox()
		hbox.pack_end(reset_button, False, True, 0)
		self.vbox.add(hbox)

		reset_button.connect_object('clicked',
			self.__class__.reset_dimensions, self)
		self.form.widgets['file'].connect_object('changed',
			self.__class__.do_file_changed, self)
		self.form.widgets['width'].connect_object('value-changed',
			self.__class__.do_width_changed, self)
		self.form.widgets['height'].connect_object('value-changed',
			self.__class__.do_height_changed, self)

		# Init ranges based on original
		self.reset_dimensions()

		# Set current scale if any
		if 'width' in image_data:
			self.form.widgets['width'].set_value(int(image_data['width']))
		elif 'height' in image_data:
			self.form.widgets['height'].set_value(int(image_data['height']))

	def reset_dimensions(self):
		self._image_data.pop('width', None)
		self._image_data.pop('height', None)
		width = self.form.widgets['width']
		height = self.form.widgets['height']
		file = self.form['file']
		try:
			if file is None:
				raise AssertionError
			w, h = image_file_get_dimensions(file.path) # can raise
		except:
			logger.warning('Could not get size for image: %s', file.path)
			width.set_sensitive(False)
			height.set_sensitive(False)
		else:
			width.set_sensitive(True)
			height.set_sensitive(True)
			self._block = True
			width.set_range(0, 4 * w)
			width.set_value(w)
			height.set_range(0, 4 * w)
			height.set_value(h)
			self._block = False
			self._ratio = float(w) / h

	def do_file_changed(self):
		# Prevent images becoming one pixel wide
		file = self.form['file']
		if file is None:
			return
		try:
			if self._image_data['width'] == 1:
				self.reset_dimensions()
		except KeyError:
			# width hasn't been set
			pass

	def do_width_changed(self):
		if hasattr(self, '_block') and self._block:
			return
		self._image_data.pop('height', None)
		self._image_data['width'] = int(self.form['width'])
		h = int(float(self._image_data['width']) / self._ratio)
		self._block = True
		self.form['height'] = h
		self._block = False

	def do_height_changed(self):
		if hasattr(self, '_block') and self._block:
			return
		self._image_data.pop('width', None)
		self._image_data['height'] = int(self.form['height'])
		w = int(self._ratio * float(self._image_data['height']))
		self._block = True
		self.form['width'] = w
		self._block = False

	def do_response_ok(self):
		file = self.form['file']
		if file is None:
			return False

		attrib = self._image_data
		attrib['src'] = self.notebook.relative_filepath(file, self.path) or file.uri

		href = self.form['href']
		if href:
			type = link_type(href)
			if type == 'file':
				# Try making the path relative
				linkfile = self.form.widgets['href'].get_file()
				href = self.notebook.relative_filepath(linkfile, self.path) or linkfile.uri
			attrib['href'] = href
		else:
			attrib.pop('href', None)

		id = self.form['anchor']
		if id:
			attrib['id'] = id
		else:
			attrib.pop('id', None)

		iter = self.buffer.get_iter_at_offset(self._iter)
		bound = iter.copy()
		bound.forward_char()
		with self.buffer.user_action:
			self.buffer.delete(iter, bound)
			self.buffer.insert_image_at_cursor(file, **attrib)
		return True


class InsertTextFromFileDialog(FileDialog):
	'''Dialog to insert text from an external file into the page'''

	def __init__(self, parent, buffer, notebook, page):
		FileDialog.__init__(
			self, parent, _('Insert Text From File'), Gtk.FileChooserAction.OPEN)
			# T: Dialog title
		self.load_last_folder()
		self.add_shortcut(notebook, page)
		self.buffer = buffer

	def do_response_ok(self):
		file = self.get_file()
		if file is None:
			return False
		parser = get_format('plain').Parser()
		tree = parser.parse(file.readlines())
		self.buffer.insert_parsetree_at_cursor(tree)
		self.save_last_folder()
		return True


class InsertLinkDialog(Dialog):
	'''Dialog to insert a new link in the page or edit properties of
	an existing link
	'''

	def __init__(self, parent, pageview):
		self.pageview = pageview
		href, text = self._get_link_from_buffer()

		if href:
			title = _('Edit Link') # T: Dialog title
		else:
			title = _('Insert Link') # T: Dialog title

		Dialog.__init__(self, parent, title, button=_('_Link'), help='Help:Links')  # T: Dialog button

		self.uistate.setdefault('short_links', pageview.notebook.config['Notebook']['short_links'])
		self.add_form(
			[
				('href', 'link', _('Link to'), pageview.page), # T: Input in 'insert link' dialog
				('text', 'string', _('Text')), # T: Input in 'insert link' dialog
				('short_links', 'bool', _('Prefer short link names for pages')), # T: Input in 'insert link' dialog
			], {
				'href': href,
				'text': text,
				'short_links': self.uistate['short_links'],
			},
			notebook=pageview.notebook
		)

		# Hook text entry to copy text from link when apropriate
		self.form.widgets['href'].connect('changed', self.on_href_changed)
		self.form.widgets['text'].connect('changed', self.on_text_changed)
		self.form.widgets['short_links'].connect('toggled', self.on_short_link_pref_changed)
		self._text_for_link = self._link_to_text(href)
		self._copy_text = self._text_for_link == text and not self._selected_text

	def _get_link_from_buffer(self):
		# Get link and text from the text buffer
		href, text = '', ''

		buffer = self.pageview.textview.get_buffer()
		if buffer.get_has_selection():
			buffer.strip_selection()
			link = buffer.get_has_link_selection()
		else:
			link = buffer.select_link()
			if not link:
				buffer.select_word()

		if buffer.get_has_selection():
			start, end = buffer.get_selection_bounds()
			text = start.get_text(end)
			self._selection_bounds = (start.get_offset(), end.get_offset())
				# Interaction in the dialog causes buffer to loose selection
				# maybe due to clipboard focus !??
				# Anyway, need to remember bounds ourselves.
			if link:
				href = link['href']
				self._selected_text = False
			else:
				href = text
				self._selected_text = True
		else:
			self._selection_bounds = None
			self._selected_text = False

		return href, text

	def on_href_changed(self, o):
		# Check if we can also update text
		self._text_for_link = self._link_to_text(self.form['href'])
		if self._copy_text:
			self.form['text'] = self._text_for_link
			self._copy_text = True # just to be sure

	def on_text_changed(self, o):
		# Check if we should stop updating text
		self._copy_text = self.form['text'] == self._text_for_link

	def on_short_link_pref_changed(self, o):
		self.on_href_changed(None)

	def _link_to_text(self, link):
		if not link:
			return ''
		elif self.form['short_links'] and link_type(link) == 'page':
				# Similar to 'short_links' notebook property but using uistate instead
				try:
					href = HRef.new_from_wiki_link(link)
				except ValueError:
					return ''
				else:
					return href.short_name()
		else:
			return link

	def do_response_ok(self):
		self.uistate['short_links'] = self.form['short_links']

		href = self.form['href']
		if not href:
			self.form.widgets['href'].set_input_valid(False)
			return False

		type = link_type(href)
		if type == 'file':
			# Try making the path relative
			try:
				file = self.form.widgets['href'].get_file()
				page = self.pageview.page
				notebook = self.pageview.notebook
				href = notebook.relative_filepath(file, page) or file.uri
			except:
				pass # E.g. malformed path

		text = self.form['text'] or href

		buffer = self.pageview.textview.get_buffer()
		with buffer.user_action:
			if self._selection_bounds:
				start, end = list(map(
					buffer.get_iter_at_offset, self._selection_bounds))
				buffer.delete(start, end)
			buffer.insert_link_at_cursor(text, href)

		return True


class WordCountDialog(Dialog):
	'''Dialog showing line, word, and character counts'''

	def __init__(self, pageview):
		Dialog.__init__(self, pageview,
			_('Word Count'), buttons=Gtk.ButtonsType.CLOSE) # T: Dialog title
		self.set_resizable(False)

		def count(buffer, bounds):
			start, end = bounds
			lines = end.get_line() - start.get_line() + 1
			chars = end.get_offset() - start.get_offset()

			strings = start.get_text(end).strip().split()
			non_space_chars = sum(len(s) for s in strings)

			words = 0
			iter = start.copy()
			while iter.compare(end) < 0:
				if iter.forward_word_end():
					words += 1
				elif iter.compare(end) == 0:
					# When end is end of buffer forward_end_word returns False
					words += 1
					break
				else:
					break

			return lines, words, chars, non_space_chars

		buffer = pageview.textview.get_buffer()
		buffercount = count(buffer, buffer.get_bounds())
		insert = buffer.get_iter_at_mark(buffer.get_insert())
		start = buffer.get_iter_at_line(insert.get_line())
		end = start.copy()
		end.forward_line()
		paracount = count(buffer, (start, end))
		if buffer.get_has_selection():
			selectioncount = count(buffer, buffer.get_selection_bounds())
		else:
			selectioncount = (0, 0, 0, 0)

		table = Gtk.Table(3, 4)
		table.set_row_spacings(5)
		table.set_col_spacings(12)
		self.vbox.add(table)

		plabel = Gtk.Label(label=_('Page')) # T: label in word count dialog
		alabel = Gtk.Label(label=_('Paragraph')) # T: label in word count dialog
		slabel = Gtk.Label(label=_('Selection')) # T: label in word count dialog
		wlabel = Gtk.Label(label='<b>' + _('Words') + '</b>:') # T: label in word count dialog
		llabel = Gtk.Label(label='<b>' + _('Lines') + '</b>:') # T: label in word count dialog
		clabel = Gtk.Label(label='<b>' + _('Characters') + '</b>:') # T: label in word count dialog
		dlabel = Gtk.Label(label='<b>' + _('Characters excluding spaces') + '</b>:') # T: label in word count dialog

		for label in (wlabel, llabel, clabel, dlabel):
			label.set_use_markup(True)
			label.set_alignment(0.0, 0.5)

		# Heading
		table.attach(plabel, 1, 2, 0, 1)
		table.attach(alabel, 2, 3, 0, 1)
		table.attach(slabel, 3, 4, 0, 1)

		# Lines
		table.attach(llabel, 0, 1, 1, 2)
		table.attach(Gtk.Label(label=str(buffercount[0])), 1, 2, 1, 2)
		table.attach(Gtk.Label(label=str(paracount[0])), 2, 3, 1, 2)
		table.attach(Gtk.Label(label=str(selectioncount[0])), 3, 4, 1, 2)

		# Words
		table.attach(wlabel, 0, 1, 2, 3)
		table.attach(Gtk.Label(label=str(buffercount[1])), 1, 2, 2, 3)
		table.attach(Gtk.Label(label=str(paracount[1])), 2, 3, 2, 3)
		table.attach(Gtk.Label(label=str(selectioncount[1])), 3, 4, 2, 3)

		# Characters
		table.attach(clabel, 0, 1, 3, 4)
		table.attach(Gtk.Label(label=str(buffercount[2])), 1, 2, 3, 4)
		table.attach(Gtk.Label(label=str(paracount[2])), 2, 3, 3, 4)
		table.attach(Gtk.Label(label=str(selectioncount[2])), 3, 4, 3, 4)

		# Characters excluding spaces
		table.attach(dlabel, 0, 1, 4, 5)
		table.attach(Gtk.Label(label=str(buffercount[3])), 1, 2, 4, 5)
		table.attach(Gtk.Label(label=str(paracount[3])), 2, 3, 4, 5)
		table.attach(Gtk.Label(label=str(selectioncount[3])), 3, 4, 4, 5)


from zim.notebook import update_parsetree_and_copy_images

class MoveTextDialog(Dialog):
	'''This dialog allows moving a selected text to a new page
	The idea is to allow "refactoring" of pages more easily.
	'''

	def __init__(self, pageview, notebook, page, buffer, navigation):
		assert buffer.get_has_selection(), 'No Selection present'
		# save selection bounds (see #1963)
		self.bounds = buffer.get_selection_bounds()

		Dialog.__init__(
			self,
			pageview,
			_('Move Text to Other Page'), # T: Dialog title
			button=_('_Move')  # T: Button label
		)
		self.pageview = pageview
		self.notebook = notebook
		self.page = page
		self.buffer = buffer
		self.navigation = navigation

		self.uistate.setdefault('link', True)
		self.uistate.setdefault('open_page', False)
		self.uistate.setdefault('short_links', pageview.notebook.config['Notebook']['short_links'])
		self.add_form([
			('page', 'page', _('Move text to'), page), # T: Input in 'move text' dialog
			('link', 'bool', _('Leave link to new page')), # T: Input in 'move text' dialog
			('short_links', 'bool', _('Prefer short link names for pages')), # T: Input in 'move text' dialog
			('open_page', 'bool', _('Open new page')), # T: Input in 'move text' dialog

		], self.uistate)

		self.form.widgets['link'].connect('toggled', self.on_link_changed)
		self.on_link_changed()

	def on_link_changed(self, *a):
		# Set short link names toggle sensitivity according to link leaving toggle
		self.form.widgets['short_links'].set_sensitive(self.form['link'])

	def do_response_ok(self):
		newpage = self.form['page']
		if not newpage:
			return False

		try:
			newpage = self.notebook.get_page(newpage)
		except PageNotFoundError:
			return False

		# Copy text
		if not self.bounds:
			ErrorDialog(self, _('No text selected')).run() # T: error message in "move selected text" action
			return False

		if not newpage.exists():
			template = self.notebook.get_template(newpage,
				{'place_cursor': ExpressionFunction(lambda: '')} # FIXME, ideal would be to insert new content at cursor location
			)
			newpage.set_parsetree(template)

		parsetree = self.buffer.get_parsetree(self.bounds)
		newtree = update_parsetree_and_copy_images(parsetree, self.notebook, self.page, newpage)

		newpage.append_parsetree(newtree)
		self.notebook.store_page(newpage)

		# Delete text (after copy was successfull..)
		self.buffer.delete(*self.bounds)

		# Save link format preference
		self.uistate['short_links'] = self.form['short_links']

		# Insert Link
		self.uistate['link'] = self.form['link']
		if self.form['link']:
			href = self.form.widgets['page'].get_text()  # TODO add method to Path "get_link" which gives rel path formatted correctly
			try:
				text = HRef.new_from_wiki_link(href).short_name() if self.uistate['short_links'] else href
			except ValueError:
				text = href
			self.buffer.insert_link_at_cursor(text, href)

		# Show page
		self.uistate['open_page'] = self.form['open_page']
		if self.form['open_page']:
			self.navigation.open_page(newpage)

		return True


class NewFileDialog(Dialog):

	def __init__(self, parent, basename):
		Dialog.__init__(self, parent, _('New File')) # T: Dialog title
		self.add_form((
			('basename', 'string', _('Name')), # T: input for new file name
		), {
			'basename': basename
		})

	def show_all(self):
		Dialog.show_all(self)

		# Select only first part of name
		# TODO - make this a widget type in widgets.py
		text = self.form.widgets['basename'].get_text()
		if '.' in text:
			name, ext = text.split('.', 1)
			self.form.widgets['basename'].select_region(0, len(name))

	def do_response_ok(self):
		self.result = self.form['basename']
		return True
