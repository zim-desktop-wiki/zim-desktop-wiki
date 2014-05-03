# -*- coding: utf-8 -*-

# Copyright 2008-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Plugin to serve as work-around for the lack of printing support'''

import gtk

from functools import partial


from zim.fs import TmpFile
from zim.plugins import PluginClass, WindowExtension, DialogExtension, extends
from zim.actions import action

import zim.templates
import zim.formats

from zim.export.template import ExportTemplateContext
from zim.export.linker import StaticExportLinker


class PrintToBrowserPlugin(PluginClass):

	plugin_info = {
		'name': _('Print to Browser'), # T: plugin name
		'description': _('''\
This plugin provides a workaround for the lack of
printing support in zim. It exports the current page
to html and opens a browser. Assuming the browser
does have printing support this will get your
data to the printer in two steps.

This is a core plugin shipping with zim.
'''), # T: plugin description
		'author': 'Jaap Karssenberg',
		'help': 'Plugins:Print to Browser'
	}

	def print_to_file(self, notebook, page):
		file = TmpFile('print-to-browser.html', persistent=True, unique=False)
		template = zim.templates.get_template('html', 'Print')

		linker_factory = partial(StaticExportLinker, notebook, template.resources_dir)
		dumper_factory = zim.formats.get_format('html').Dumper # XXX
		context = ExportTemplateContext(
			notebook, linker_factory, dumper_factory,
			page.basename, [page]
		)

		lines = []
		template.process(lines, context)
		file.writelines(lines)
		return file


@extends('MainWindow')
class MainWindowExtension(WindowExtension):

	uimanager_xml = '''
	<ui>
		<menubar name='menubar'>
			<menu action='file_menu'>
				<placeholder name='print_actions'>
					<menuitem action='print_to_browser'/>
				</placeholder>
			</menu>
		</menubar>
	</ui>
	'''

	@action(_('_Print to Browser'), 'gtk-print', '<ctrl>P') # T: menu item
	def print_to_browser(self, page=None):
		notebook = self.window.ui.notebook # XXX
		if page is None:
			page = self.window.ui.page # XXX
		file = self.plugin.print_to_file(notebook, page)
		self.window.ui.open_url('file://%s' % file) # XXX
			# Try to force web browser here - otherwise it goes to the
			# file browser which can have unexpected results


@extends('TaskListDialog')
class TaskListDialogExtension(DialogExtension):

	def __init__(self, plugin, window):
		DialogExtension.__init__(self, plugin, window)

		button = gtk.Button(stock='gtk-print')
		button.connect('clicked', self.on_print_tasklist)
		self.add_dialog_button(button)

	def on_print_tasklist(self, o):
		html = self.window.task_list.get_visible_data_as_html()
		file = TmpFile('print-to-browser.html', persistent=True, unique=False)
		file.write(html)
		self.window.ui.open_url('file://%s' % file) # XXX
			# Try to force web browser here - otherwise it goes to the
			# file browser which can have unexpected results

