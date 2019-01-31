
# Copyright 2008-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Plugin to serve as work-around for the lack of printing support'''

from gi.repository import Gtk

from functools import partial


from zim.plugins import PluginClass
from zim.actions import action
from zim.fs import TmpFile

import zim.templates
import zim.formats

from zim.export.template import ExportTemplateContext
from zim.export.linker import StaticExportLinker

from zim.gui.pageview import PageViewExtension
from zim.gui.applications import open_url

from zim.plugins.tasklist.gui import TaskListDialogExtension


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


class PrintToBrowserPageViewExtension(PageViewExtension):

	@action(_('_Print to Browser'), accelerator='<Primary>P', menuhints='page') # T: menu item
	def print_to_browser(self, page=None):
		notebook = self.pageview.notebook
		page = page or self.pageview.page
		file = self.plugin.print_to_file(notebook, page)
		open_url(self.pageview, 'file://%s' % file) # XXX
			# Try to force web browser here - otherwise it goes to the
			# file browser which can have unexpected results


class PrintTaskListDialogExtension(TaskListDialogExtension):

	def __init__(self, plugin, dialog):
		TaskListDialogExtension.__init__(self, plugin, dialog)

		button = Gtk.Button.new_with_mnemonic(_('_Print')) # T: Button label
		button.connect('clicked', self.on_print_tasklist)
		self.add_dialog_button(button)

	def on_print_tasklist(self, o):
		html = self.dialog.task_list.get_visible_data_as_html()
		file = TmpFile('print-to-browser.html', persistent=True, unique=False)
		file.write(html)
		open_url(self.dialog, 'file://%s' % file) # XXX
			# Try to force web browser here - otherwise it goes to the
			# file browser which can have unexpected results
