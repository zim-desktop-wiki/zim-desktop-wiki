# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import gtk

from zim.gui import Dialog
import zim.formats
import zim.templates

class ExportDialog(Dialog):
	'''FIXME'''

	def __init__(self, ui):
		Dialog.__init__(self, ui, 'Export')
		#~ self.set_resizable(False)
		self.set_help('ExportDialog')
		if not hasattr(self, 'uistate'):
			self.uistate = {} # Used for debug mode

		# Pages ------------------------
		vbox = gtk.VBox(0, 5)
		vbox.set_border_width(12)
		self._add_with_frame(vbox, '<b>Pages</b>')

		all_pages_radio = gtk.RadioButton(None, '_Complete notebook')
		selection_radio = gtk.RadioButton(all_pages_radio, '_Selection')
		recursive_box = gtk.CheckButton('Recursive')
		vbox.add(all_pages_radio)
		vbox.add(selection_radio)
		selection_radio.set_sensitive(False)
		vbox.add(gtk.Label('TODO: selection input'))
		vbox.add(recursive_box)
		recursive_box.set_sensitive(False)

		# Output ------------------------
		table = gtk.Table(5, 3)
		table.set_border_width(12)
		table.set_row_spacings(5)
		table.set_col_spacings(12)
		self._add_with_frame(table, '<b>Output</b>')

		# Format
		table.attach(gtk.Label('Format:'), 0,1, 0,1)
		formats_combobox = gtk.combo_box_new_text()
		for name in zim.formats.list_formats(zim.formats.EXPORT_FORMAT):
			formats_combobox.append_text(name)
		table.attach(formats_combobox, 1,2, 0,1)

		# Template
		def set_templates(formats_combobox, templates_combobox):
			format = formats_combobox.get_active_text()
			# TODO clear templates_combobox
			templates = zim.templates.list_templates(format)
			for name in sorted(templates.keys()):
				templates_combobox.append_text(name)
			templates_combobox.append_text('Other...')
			templates_combobox.set_sensitive(True)

		table.attach(gtk.Label('Template:'), 0,1, 1,2)
		templates_combobox = gtk.combo_box_new_text()
		templates_combobox.set_sensitive(False)
		formats_combobox.connect('changed', set_templates, templates_combobox)
		table.attach(templates_combobox, 1,2, 1,2)
		other_template_selector = gtk.FileChooserButton('Please select a template file')
		other_template_selector.set_sensitive(False)
		templates_combobox.connect('changed',
			lambda o: other_template_selector.set_sensitive(
							o.get_active_text() == 'Other...') )
		table.attach(other_template_selector, 1,2, 2,3)

		# Folder
		table.attach(gtk.Label('Output folder:'), 0,1, 3,4)
		output_folder_selector = gtk.FileChooserButton('Please select a folder')
		output_folder_selector.set_action(gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER)
		table.attach(output_folder_selector, 1,2, 3,4)

		# Index
		table.attach(gtk.Label('Index page:'), 0,1, 4,5)
		table.attach(gtk.Entry(), 1,2, 4,5)

		# Documents ----------------------
		vbox = gtk.VBox(0, 5)
		vbox.set_border_width(12)
		self._add_with_frame(vbox, '<b>Documents</b>')

		document_url_box = gtk.CheckButton('Use URL for document folder:')
		document_url_entry = gtk.Entry()
		document_url_entry.set_sensitive(False)
		document_url_box.connect('toggled',
			lambda o: document_url_entry.set_sensitive(o.get_active()) )
		include_documents_box = gtk.CheckButton('Include a copy of linked documents')
		hbox = gtk.HBox(0, 5)
		hbox.add(document_url_box)
		hbox.add(document_url_entry)
		vbox.add(hbox)
		vbox.add(include_documents_box)


	def _add_with_frame(self, widget, title):
		frame = gtk.Frame()
		label = gtk.Label()
		label.set_markup(title)
		frame.set_label_widget(label)
		frame.add(widget)
		self.vbox.add(frame)

	def do_response_ok(self):
		return True


if __name__ == '__main__':
	dialog = ExportDialog(None)
	dialog.run()
