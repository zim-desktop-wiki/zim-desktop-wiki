# -*- coding: utf-8 -*-

# Copyright 2009-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from __future__ import with_statement

import pango
import gtk
import logging

from zim.gui.widgets import Dialog, Button, BrowserTreeView, \
	ScrolledWindow, ScrolledTextView, InputForm, input_table_factory
from zim.gui.applications import CustomizeOpenWithDialog


logger = logging.getLogger('zim.gui.preferencesdialog')


# define section labels here so xgettext can fing them
_label = _('Interface') # T: Tab in preferences dialog
_label = _('Editing') # T: Tab in preferences dialog


class PreferencesDialog(Dialog):
	'''Preferences dialog consisting of tabs with various options and
	a tab with plugins. Options are not defined here, but need to be
	registered using GtkInterface.register_preferences().
	'''

	def __init__(self, ui, default_tab=None, select_plugin=None):
		Dialog.__init__(self, ui, _('Preferences')) # T: Dialog title
		gtknotebook = gtk.Notebook()
		self.vbox.add(gtknotebook)
		# saves a list of loaded plugins to be used later
		self.p_save_loaded = [p.__class__ for p in self.ui.plugins]

		# Dynamic tabs
		self.forms = {}
		for category, preferences in ui.preferences_register.items():
			vbox = gtk.VBox()
			index = gtknotebook.append_page(vbox, gtk.Label(_(category)))
			# From GTK Doc: Note that due to historical reasons, GtkNotebook refuses
			# to switch to a page unless the child widget is visible.
			vbox.show()
			if category == default_tab: gtknotebook.set_current_page(index)

			fields = []
			values = {}
			sections = {}
			for p in preferences:
				if len(p) == 4:
					section, key, type, label = p
					fields.append((key, type, label))
				else:
					section, key, type, label, check = p
					fields.append((key, type, label, check))

				values[key] = ui.preferences[section][key]
				sections[key] = section

			form = InputForm(fields, values)
			form.preferences_sections = sections
			vbox.pack_start(form, False)
			self.forms[category] = form

			if category == 'Interface':
				self._add_font_selection(form)

		# Styles tab
		#~ gtknotebook.append_page(StylesTab(self), gtk.Label(_('Styles')))

		# Keybindings tab
		#~ gtknotebook.append_page(KeyBindingsTab(self), gtk.Label(_('Key bindings')))

		# Plugins tab
		plugins_tab = PluginsTab(self, self.ui.plugins)
		plugins_tab_index = gtknotebook.append_page(plugins_tab, gtk.Label(_('Plugins')))
				# T: Heading in preferences dialog
		plugins_tab.show()
		#~ print default_tab, index
		if default_tab == "Plugins":
			gtknotebook.set_current_page(plugins_tab_index)
			if not select_plugin is None:
					plugins_tab.select_plugin(select_plugin)

		# Applications tab
		gtknotebook.append_page(ApplicationsTab(self), gtk.Label(_('Applications')))
			# T: Heading in preferences dialog


	def _add_font_selection(self, table):
		# need to hardcode this, cannot register it as a preference
		table.add_inputs( (
			('use_custom_font', 'bool', _('Use a custom font')),
			# T: option in preferences dialog
		) )
		table.preferences_sections['use_custom_font'] = 'GtkInterface'

		self.fontbutton = gtk.FontButton()
		self.fontbutton.set_use_font(True) # preview in button
		self.fontbutton.set_sensitive(False)
		text_style = self.ui.config.get_config_dict('<profile>/style.conf')
		try:
			font = text_style['TextView']['font']
			if font:
				self.fontbutton.set_font_name(font)
				self.fontbutton.set_sensitive(True)
				table['use_custom_font'] = True
		except KeyError:
			pass

		table.widgets['use_custom_font'].connect('toggled',
			lambda o: self.fontbutton.set_sensitive(o.get_active()) )

		self.fontbutton.set_size_request(100, -1)
		input_table_factory(((None, self.fontbutton),), table)

	def do_response_ok(self):
		# Get dynamic tabs
		newpreferences = {}
		for form in self.forms.values():
			for key, value in form.items():
				section = form.preferences_sections[key]
				if not section in newpreferences:
					newpreferences[section] = {}
				newpreferences[section][key] = value

		# Set font - special case, consider it a HACK
		customfont = newpreferences['GtkInterface'].pop('use_custom_font')
		if customfont:
			font = self.fontbutton.get_font_name()
		else:
			font = None

		text_style = self.ui.config.get_config_dict('<profile>/style.conf')
		text_style['TextView']['font'] = font
		#

		with self.ui.preferences.blocked_signals('changed'):
			# note we do not block signal on section dicts
			for section in newpreferences:
				self.ui.preferences[section].update(newpreferences[section])

		self.ui.preferences.emit('changed') # delayed emission

		return True

	def do_response_cancel(self):
		# TODO FIXME

		# Obtain an updated list of loaded plugins
		now_loaded = [p.__class__ for p in self.ui.plugins]

		# Restore previous situation if the user changed something
		# in this dialog session
		with self.ui.preferences.blocked_signals('changed'):
			for name in self.ui.plugins.list_installed_plugins():
				try:
					klass = self.ui.plugins.get_plugin_class(name)
				except:
					continue

				activatable = klass.check_dependencies_ok()

				if klass in self.p_save_loaded and activatable and klass not in now_loaded:
					self.ui.load_plugin(klass.plugin_key)
				elif klass not in self.p_save_loaded and klass in now_loaded:
					self.ui.unload_plugin(klass.plugin_key)

		self.ui.preferences.emit('changed') # delayed emission

		return True


class PluginsTab(gtk.VBox):

	def __init__(self, dialog, plugins):
		gtk.VBox.__init__(self, spacing=5)
		self.dialog = dialog
		self.plugins = plugins

		self.hbox = gtk.HBox(self, spacing=12)
		self.hbox.set_border_width(5)
		self.add(self.hbox)

		#~ logger.debug('Plugins that are loaded: %s' % list(plugins))

		self.treeview = PluginsTreeView(self.plugins)
		self.treeview.connect('row-activated', self.do_row_activated)
		swindow = ScrolledWindow(self.treeview, hpolicy=gtk.POLICY_NEVER)
		self.hbox.pack_start(swindow, False)

		vbox = gtk.VBox()
		self.hbox.add(vbox)

		# Textview with scrollbars to show plugins info. Required by small screen devices
		swindow, textview = ScrolledTextView()
		textview.set_cursor_visible(False)
		self.textbuffer = textview.get_buffer()
		self.textbuffer.create_tag('bold', weight=pango.WEIGHT_BOLD)
		self.textbuffer.create_tag('red', foreground='#FF0000')
		vbox.pack_start(swindow, True)

		hbox = gtk.HBox(spacing=5)
		vbox.pack_end(hbox, False)

		self.plugin_help_button = \
			Button(stock=gtk.STOCK_HELP, label=_('_More')) # T: Button in plugin tab
		self.plugin_help_button.connect('clicked', self.on_help_button_clicked)
		hbox.pack_start(self.plugin_help_button, False)

		self.configure_button = \
			Button(stock=gtk.STOCK_PREFERENCES, label=_('C_onfigure')) # T: Button in plugin tab
		self.configure_button.connect('clicked', self.on_configure_button_clicked)
		hbox.pack_start(self.configure_button, False)

		self.do_row_activated(self.treeview, (0,), 0)

		if gtk.gtk_version >= (2, 10):
			url_button = gtk.LinkButton(
				'https://github.com/jaap-karssenberg/zim-wiki/wiki/Plugins',
				_('Get more plugins online') # T: label for button with URL
			)
			self.pack_start(url_button, False)

	def do_row_activated(self, treeview, path, col):
		key, active, activatable, name, klass = treeview.get_model()[path]

		self._current_plugin = key
		logger.debug('Loading description for plugin: %s', key)

		# Insert plugin info into textview with proper formatting
		# TODO use our own widget with formatted text here...
		buffer = self.textbuffer
		def insert(text, style=None):
			if style:
				buffer.insert_with_tags_by_name(
					buffer.get_end_iter(), text, style)
			else:
				buffer.insert_at_cursor(text)

		buffer.delete(*buffer.get_bounds()) # clear
		insert(_('Name') + '\n', 'bold') # T: Heading in plugins tab of preferences dialog
		insert(klass.plugin_info['name'].strip() + '\n\n')
		insert(_('Description') + '\n', 'bold') # T: Heading in plugins tab of preferences dialog
		insert(klass.plugin_info['description'].strip() + '\n\n')
		insert(_('Dependencies') + '\n', 'bold') # T: Heading in plugins tab of preferences dialog

		check, dependencies = klass.check_dependencies()
		if not(dependencies):
			insert(_('No dependencies') + '\n') # T: label in plugin info in preferences dialog
		else:
			# Construct dependency list, missing dependencies are marked red
			for dependency in dependencies:
				text, ok, required = dependency
				if ok:
					insert(u'\u2022 %s - %s\n' % (text, _('OK'))) # T: dependency is OK
				elif required:
					insert(u'\u2022 %s - %s\n' % (text, _('Failed')), 'red') # T: dependency failed
				else:
					insert(u'\u2022 %s - %s (%s)\n' % (text,
						_('Failed'), # T: dependency failed
						_('Optional') # T: optional dependency
					) )
		insert('\n')

		insert(_('Author') + '\n', 'bold') # T: Heading in plugins tab of preferences dialog
		insert(klass.plugin_info['author'].strip())

		self.configure_button.set_sensitive(active and bool(klass.plugin_preferences))
		self.plugin_help_button.set_sensitive('help' in klass.plugin_info)

	def on_help_button_clicked(self, button):
		klass = self.plugins.get_plugin_class(self._current_plugin)
		self.dialog.ui.show_help(klass.plugin_info['help']) # XXX

	def on_configure_button_clicked(self, button):
		plugin = self.plugins[self._current_plugin]
		PluginConfigureDialog(self.dialog, plugin).run()

	def select_plugin(self, name):
		model = self.treeview.get_model()
		def find(model, path, iter):
			if model[iter][2] == name:
				self.treeview.scroll_to_cell(path)
				self.treeview.set_cursor(path)
				self.do_row_activated(self.treeview, path, 0)
				return True;
			return False # keep the foreach going
		model.foreach(find)


class PluginsTreeModel(gtk.ListStore):

	def __init__(self, plugins):
		#columns are: key, active, activatable, name, klass
		gtk.ListStore.__init__(self, str, bool, bool, str, object)
		self.plugins = plugins

		allplugins = []
		for key in self.plugins.list_installed_plugins():
			try:
				klass = self.plugins.get_plugin_class(key)
				name = klass.plugin_info['name']
				allplugins.append((name, key, klass))
			except:
				logger.exception('Could not load plugin %s', key)
		allplugins.sort() # sort by translated name

		for name, key, klass in allplugins:
			active = key in self.plugins
			try:
				activatable = klass.check_dependencies_ok()
			except:
				logger.exception('Could not load plugin %s', name)
			else:
				self.append((key, active, activatable, name, klass))


	def do_toggle_path(self, path):
		key, active, activatable, name, klass = self[path]
		if not activatable:
			return

		if active:
			self.plugins.remove_plugin(key)
			self[path][1] = False
		else:
			try:
				self.plugins.load_plugin(key)
			except:
				logger.exception('Could not load plugin %s', name)
				# TODO pop error dialog
			else:
				self[path][1] = True


class PluginsTreeView(BrowserTreeView):

	def __init__(self, plugins):
		BrowserTreeView.__init__(self)

		model = PluginsTreeModel(plugins)
		self.set_model(model)

		cellrenderer = gtk.CellRendererToggle()
		cellrenderer.connect('toggled', lambda o, p: model.do_toggle_path(p))
		self.append_column(
			gtk.TreeViewColumn(_('Enabled'), cellrenderer, active=1, activatable=2))
			# T: Column in plugin tab
		self.append_column(
			gtk.TreeViewColumn(_('Plugin'), gtk.CellRendererText(), text=3))
			# T: Column in plugin tab


class PluginConfigureDialog(Dialog):

	def __init__(self, dialog, plugin):
		Dialog.__init__(self, dialog, _('Configure Plugin')) # T: Dialog title
		self.plugin = plugin

		label = gtk.Label()
		label.set_markup(
			'<b>'+_('Options for plugin %s') % plugin.plugin_info['name']+'</b>')
			# T: Heading for 'configure plugin' dialog - %s is the plugin name
		self.vbox.add(label)

		fields = []
		for pref in self.plugin.plugin_preferences:
			if len(pref) == 4:
				key, type, label, default = pref
				self.plugin.preferences.setdefault(key, default) # just to be sure
			else:
				key, type, label, default, check = pref
				self.plugin.preferences.setdefault(key, default, check=check) # just to be sure

			if type in ('int', 'choice'):
				fields.append((key, type, label, check))
			else:
				fields.append((key, type, label))

		self.add_form(fields, self.plugin.preferences)

	def do_response_ok(self):
		# First let the plugin receive the changes, then save them.
		# The plugin could do some conversion on the fly (e.g. Path to string)
		self.plugin.preferences.update(self.form)
		return True


class ApplicationsTab(gtk.VBox):

	def __init__(self, dialog):
		gtk.VBox.__init__(self)
		self.set_border_width(5)
		self.dialog = dialog

		button = gtk.Button(_('Set default text editor'))
			# T: button in preferences dialog to change default text editor
		button.connect('clicked', self.on_set_texteditor)

		self.pack_start(button, False)

	def on_set_texteditor(self, o):
		CustomizeOpenWithDialog(self.dialog, 'text/plain').run()


class StylesTab(gtk.VBox):

	def __init__(self, dialog):
		gtk.VBox.__init__(self)
		self.add(gtk.Label('TODO add treeview with styles'))


class StylesTreeModel(gtk.ListStore):

	def __init__(self, ui):
		#'weight', 'scale', 'style', 'background', 'foreground', 'strikethrough',
		# 'family', 'wrap-mode', 'indent', 'underline'
		gtk.ListStore.__init__(self, bool, str, object)


class KeyBindingsTab(gtk.VBox):

	def __init__(self, dialog):
		gtk.VBox.__init__(self)
		self.add(gtk.Label('TODO add treeview with accelerators'))

#~ Build editable treeview of menu items + accelerators
#~
#~ Just getting action names does not give menu structure,
#~ so walk the menu.
#~
#~ Menus are containers, have a foreach
#~ Menutitems are bin, can have submenu
#~
#~ Get label using get_child() etc (probably gives a box with icon,
#~ label, accel, etc.)
#~
#~ Test get_submenu(),
#~ if is None: leaf item, get accelerator
#~ elif value: recurs
#~
#~ To get the accelerator:
#~ accel_path = menuitem.get_accel_path() (make sure this is not the mnemonic..)
#~ key, mod = gtk.accel_map_lookup_entry(accel_path)
#~
#~ To get / set accelerator labels in the UI use:
#~ gtk.accelerator_name() to get a name to display
#~
#~ To parse name set by user
#~ gtk.accelerator_parse()
#~ gtk.accelerator_valid()
#~
#~ To change the accelerator:
#~ Maybe first unlock path in accel_map and unlock the actiongroup..
#~ gtk.accel_map.change_entry(accel_path, key, mods, replace=True)
#~ check return value
#~
#~ To get updates for ui use:
#~ gtk.accel_map_get().connect('changed', func(o, accel_path, key, mods))
#~ This way we also get any accelerators that were deleted as result of
#~ replace=True
