# -*- coding: utf-8 -*-

# Copyright 2010 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains code for defining and managing custom
commands.
'''

import gtk
import logging


from zim.gui.applications import CustomToolManager
from zim.gui.widgets import Dialog, IconButton, IconChooserButton
from zim.fs import File


logger = logging.getLogger('zim.gui')


class CustomToolManagerDialog(Dialog):

	def __init__(self, ui):
		Dialog.__init__(self, ui, _('Custom Tools'), buttons=gtk.BUTTONS_CLOSE) # T: Dialog title
		self.set_help(':Help:Custom Tools')
		self.manager = CustomToolManager()

		self.add_help_text(_(
			'You can configure custom tools that will appear\n'
			'in the tool menu and in the tool bar or context menus.'
		) ) # T: help text in "Custom Tools" dialog

		hbox = gtk.HBox(spacing=5)
		self.vbox.add(hbox)

		self.listview = CustomToolList(self.manager)
		hbox.add(self.listview)

		vbox = gtk.VBox(spacing=5)
		hbox.pack_start(vbox, False)

		for stock, handler, data in (
			(gtk.STOCK_ADD, self.__class__.on_add, None),
			(gtk.STOCK_EDIT, self.__class__.on_edit, None),
			(gtk.STOCK_DELETE, self.__class__.on_delete, None),
			(gtk.STOCK_GO_UP, self.__class__.on_move, -1),
			(gtk.STOCK_GO_DOWN, self.__class__.on_move, 1),
		):
			button = IconButton(stock) # TODO tooltips for icon button
			if data:
				button.connect_object('clicked', handler, self, data)
			else:
				button.connect_object('clicked', handler, self)
			vbox.pack_start(button, False)

	def on_add(self):
		properties = EditCustomToolDialog(self).run()
		if properties:
			self.manager.create(**properties)
		self.listview.refresh()

	def on_edit(self):
		name = self.listview.get_selected()
		if name:
			tool = self.manager.get_tool(name)
			properties = EditCustomToolDialog(self, tool=tool).run()
			if properties:
				tool.update(**properties)
				tool.write()
		self.listview.refresh()

	def on_delete(self):
		name = self.listview.get_selected()
		if name:
			self.manager.delete(name)
			self.listview.refresh()

	def on_move(self, step):
		name = self.listview.get_selected()
		if name:
			i = self.manager.index(name)
			self.manager.reorder(name, i + step)
			self.listview.refresh()
			self.listview.select(i+step)


class CustomToolList(gtk.TreeView):

	PIXBUF_COL = 0
	TEXT_COL = 1
	NAME_COL = 2

	def __init__(self, manager):
		self.manager = manager

		model = gtk.ListStore(gtk.gdk.Pixbuf, str, str)
				# PIXBUF_COL, TEXT_COL, NAME_COL

		gtk.TreeView.__init__(self, model)
		self.get_selection().set_mode(gtk.SELECTION_BROWSE)
		self.set_headers_visible(False)

		cr = gtk.CellRendererPixbuf()
		column = gtk.TreeViewColumn('_pixbuf_', cr, pixbuf=self.PIXBUF_COL)
		self.append_column(column)

		cr = gtk.CellRendererText()
		column = gtk.TreeViewColumn('_text_', cr, markup=self.TEXT_COL)
		self.append_column(column)

		self.refresh()

	def get_selected(self):
		model, iter = self.get_selection().get_selected()
		if model and iter:
			return model[iter][self.NAME_COL]
		else:
			return None

	def select(self, i):
		path = (i, )
		self.get_selection().select_path(path)

	def refresh(self):
		from zim.gui.widgets import encode_markup_text
		model = self.get_model()
		model.clear()
		for tool in self.manager:
			pixbuf = tool.get_pixbuf(gtk.ICON_SIZE_MENU)
			text = '<b>%s</b>\n%s' % (encode_markup_text(tool.name), encode_markup_text(tool.comment))
			model.append((pixbuf, text, tool.key))


class EditCustomToolDialog(Dialog):

	def __init__(self, ui, tool=None):
		Dialog.__init__(self, ui, _('Edit Custom Tool')) # T: Dialog title
		self.set_help(':Help:Custom Tools')
		self.vbox.set_spacing(12)

		if tool:
			name = tool.name
			comment = tool.comment
			execcmd = tool.execcmd
			readonly = tool.isreadonly
			toolbar = tool.showintoolbar
			replaceselection = tool.replaceselection
		else:
			name = ''
			comment = ''
			execcmd = ''
			readonly = False
			toolbar = False
			replaceselection = False

		self.add_form((
			('Name', 'string', _('Name')), # T: Input in "Edit Custom Tool" dialog
			('Comment', 'string', _('Description')), # T: Input in "Edit Custom Tool" dialog
			('X-Zim-ExecTool', 'string', _('Command')), # T: Input in "Edit Custom Tool" dialog
		), {
			'Name': name,
			'Comment': comment,
			'X-Zim-ExecTool': execcmd,
		}, trigger_response=False)

		# FIXME need ui builder to take care of this as well
		self.iconbutton = IconChooserButton(stock=gtk.STOCK_EXECUTE)
		if tool and tool.icon and tool.icon != gtk.STOCK_EXECUTE:
			try:
				self.iconbutton.set_file(File(tool.icon))
			except Exception, error:
				logger.exception('Could not load: %s', tool.icon)
		label = gtk.Label(_('Icon')+':') # T: Input in "Edit Custom Tool" dialog
		label.set_alignment(0.0, 0.5)
		hbox = gtk.HBox()
		i = self.form.get_property('n-rows')
		self.form.attach(label, 0,1, i,i+1, xoptions=0)
		self.form.attach(hbox, 1,2, i,i+1)
		hbox.pack_start(self.iconbutton, False)

		self.form.add_inputs((
			('X-Zim-ReadOnly', 'bool', _('Command does not modify data')), # T: Input in "Edit Custom Tool" dialog
			('X-Zim-ReplaceSelection', 'bool', _('Output should replace current selection')), # T: Input in "Edit Custom Tool" dialog
			('X-Zim-ShowInToolBar', 'bool', _('Show in the toolbar')), # T: Input in "Edit Custom Tool" dialog
		))
		self.form.update({
			'X-Zim-ReadOnly': readonly,
			'X-Zim-ReplaceSelection': replaceselection,
			'X-Zim-ShowInToolBar': toolbar,
		})

		self.add_help_text(_('''\
The following parameters will be substituted
in the command when it is executed:
<tt>
<b>%f</b> the page source as a temporary file
<b>%d</b> the attachment directory of the current page
<b>%s</b> the real page source file (if any)
<b>%n</b> the notebook location (file or folder)
<b>%D</b> the document root (if any)
<b>%t</b> the selected text or word under cursor
<b>%T</b> the selected text including wiki formatting
</tt>
''') ) # T: Short help text in "Edit Custom Tool" dialog. The "%" is literal - please include the html formatting

	def do_response_ok(self):
		fields = self.form.copy()
		fields['Icon'] = self.iconbutton.get_file() or None
		self.result = fields
		return True
