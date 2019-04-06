
# Copyright 2008-2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import logging

logger = logging.getLogger('zim.gui')


from gi.repository import Gtk

from zim.plugins import PluginManager
from zim.gui.widgets import Dialog, get_window, InputForm
from zim.parsing import is_interwiki_keyword_re

notebook_properties = (
	('name', 'string', _('Name')), # T: label for properties dialog
	('interwiki', 'string', _('Interwiki Keyword'), lambda v: not v or is_interwiki_keyword_re.search(v)), # T: label for properties dialog
	('home', 'page', _('Home Page')), # T: label for properties dialog
	('icon', 'image', _('Icon')), # T: label for properties dialog
	('document_root', 'dir', _('Document Root')), # T: label for properties dialog
	# 'shared' property is not shown in properties anymore
)


class PropertiesDialog(Dialog):

	def __init__(self, parent, notebook):
		Dialog.__init__(self, parent, _('Properties'), help='Help:Properties') # T: Dialog title
		self.notebook = notebook

		stack = Gtk.Stack()
		sidebar = Gtk.StackSidebar()
		sidebar.set_stack(stack)

		hbox = Gtk.Box()
		hbox.add(sidebar)
		hbox.add(stack)
		self.vbox.add(hbox)

		self.form = InputForm(
			inputs=notebook_properties,
			values=notebook.config['Notebook']
		)
		self.form.widgets['icon'].set_use_relative_paths(self.notebook)
		if self.notebook.readonly:
			for widget in list(self.form.widgets.values()):
				widget.set_sensitive(False)
		box = Gtk.VBox()
		box.pack_start(self.form, False, False, 0)
		stack.add_titled(box, 'notebook', _('Notebook'))

		self.plugin_forms = {}
		plugins = PluginManager()
		for name in plugins:
			plugin = plugins[name]
			if plugin.plugin_notebook_properties:
				key = plugin.config_key
				form = InputForm(
					inputs=plugin.form_fields(plugin.plugin_notebook_properties),
					values=notebook.config[key]
				)
				self.plugin_forms[key] = form
				if self.notebook.readonly:
					for widget in list(form.widgets.values()):
						widget.set_sensitive(False)

				box = Gtk.VBox()
				box.pack_start(form, False, False, 0)
				stack.add_titled(box, name, plugin.plugin_info['name'])

	def do_response_ok(self):
		if not self.notebook.readonly:
			properties = self.form.copy()

			self.notebook.save_properties(**properties)

			for key, form in self.plugin_forms.items():
				self.notebook.config[key].update(form)

			if hasattr(self.notebook.config, 'write'): # XXX Check needed for tests
				logger.debug('Write notebook properties')
				self.notebook.config.write()

		return True

## TODO: put a number of properties in an expander with a label "Advanced"
