import ntpath
import os
import pathlib

import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from zim.gui.widgets import Dialog, InputEntry
from zim.newfs import localFileOrFolder, LocalFile, LocalFolder


class FileRenameDialog(Dialog):
	""" A dialog for renaming a file. """

	def __init__(self, parent, file):
		title = _('Rename file')
		Dialog.__init__(self, parent, title)

		assert isinstance(file, LocalFile) and not isinstance(file, LocalFolder)
		self.old_file = file
		self.new_file = file

		# Add field for entering new filename.
		self.txt_filename = InputEntry()
		self.txt_filename.set_text(self.old_file.basename)
		self.txt_filename.set_activates_default(True)  # Make ENTER key press trigger the OK button.
		self.txt_filename.connect("changed", self.do_validate, parent)

		# Add field for showing hints when an error occurs (e.g. filename already exists).
		self.txt_error = Gtk.Label()
		self.txt_error.set_visible(False)

		# Add ok button.
		self.btn_ok = self.get_widget_for_response(response_id=Gtk.ResponseType.OK)
		self.btn_ok.set_can_default(True)
		self.btn_ok.grab_default()
		self.btn_ok.set_sensitive(False)

		# Configure dialog.
		self.set_modal(True)
		self.set_default_size(380, 100)
		self.vbox.pack_start(self.txt_filename, False, True, 0)
		self.vbox.pack_start(self.txt_error, False, True, 0)

		# Set focus to search field
		self.txt_filename.grab_focus()

	def do_validate(self, widget, data):
		""" Validating new file name, show error when validation fails and enable/disable ok button. """

		def is_filename(filename):
			""" Returns True when filename does not contain any path declaration. """
			return filename == os.path.basename(filename)

		def does_file_already_exist(filename):
			""" Checks whether the new filename is already taken. """
			return self.old_file.parent().file(filename).exists()

		def show_error(msg):
			""" Displays an error and disables the OK button. """
			self.txt_error.set_text(msg)
			self.txt_error.set_visible(True)
			self.btn_ok.set_sensitive(False)
			return False

		if not widget.get_text():
			return show_error(_('File name should not be blank.'))

		if does_file_already_exist(widget.get_text()):
			return show_error(_('A file with that name already exists.'))

		if not is_filename(widget.get_text()):
			return show_error(_('File name should not contain path declaration.'))

		# No errors, hide error label and enable OK button.
		self.txt_error.hide()
		self.btn_ok.set_sensitive(True)
		return True

	def do_response_ok(self):
		self.new_file = self.old_file.parent().file(self.txt_filename.get_text())
		self.result = Gtk.ResponseType.OK
		self.close()
