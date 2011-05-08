# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import pango
import gtk
import logging

import zim.plugins
from zim.gui.applications import ApplicationManager, NewApplicationDialog
from zim.gui.widgets import Dialog, Button, BrowserTreeView, scrolled_text_view, InputForm, input_table_factory
from zim.gui.pageview import PageView


logger = logging.getLogger('zim.gui.preferencesdialog')


# define section labels here so xgettext can fing them
_label = _('Interface') # T: Tab in preferences dialog
_label = _('Editing') # T: Tab in preferences dialog


class PreferencesDialog(Dialog):
	'''Preferences dialog consisting of tabs with various options and
	a tab with plugins. Options are not defined here, but need to be
	registered using GtkInterface.register_preferences().
	'''

	OTHER_APP = _('Other Application') + '...'
		# T: label to pop dialog with more applications in 'open with' menu

	def __init__(self, ui):
		Dialog.__init__(self, ui, _('Preferences')) # T: Dialog title
		gtknotebook = gtk.Notebook()
		self.vbox.add(gtknotebook)

		# saves a list of loaded plugins to be used later
		self.p_save_loaded = [p.__class__ for p in self.ui.plugins]

		# Dynamic tabs
		self.forms = {}
		for category, preferences in ui.preferences_register.items():
			vbox = gtk.VBox()
			gtknotebook.append_page(vbox, gtk.Label(_(category)))

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
		#~ gtknotebook.append_page(StylesTab(self), gtk.Label('Styles'))

		# Keybindings tab
		#~ gtknotebook.append_page(KeyBindingsTab(self), gtk.Label('Key bindings'))

		# Applications tab
		vbox = gtk.VBox()
		gtknotebook.append_page(vbox, gtk.Label(_('Applications')))
				# T: Heading in preferences dialog

		form = InputForm( (
			('file_browser', 'choice', _('File browser'), ()),
				# T: Input for application type in preferences dialog
			('web_browser', 'choice', _('Web browser'), ()),
				# T: Input for application type in preferences dialog
			('email_client', 'choice', _('Email client'), ()),
				# T: Input for application type in preferences dialog
			('text_editor', 'choice', _('Text Editor'), ()),
				# T: Input for application type in preferences dialog
		) )
		for type, widget in form.widgets.items():
			self._append_applications(type, widget)

		vbox.pack_start(form, False)
		self.applicationsform = form

		# Plugins tab
		gtknotebook.append_page(PluginsTab(self), gtk.Label(_('Plugins')))
				# T: Heading in preferences dialog

	def _add_font_selection(self, table):
		# need to hardcode this, can not register it as a preference
		table.add_inputs( (
			('use_custom_font', 'bool', _('Use a custom font')),
			# T: option in preferences dialog
		) )
		table.preferences_sections['use_custom_font'] = 'GtkInterface'

		self.fontbutton = gtk.FontButton()
		self.fontbutton.set_use_font(True) # preview in button
		self.fontbutton.set_sensitive(False)
		try:
			font = PageView.style['TextView']['font']
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

	def _append_applications(self, type, widget):
		manager = ApplicationManager()

		current = self.ui.preferences['GtkInterface'][type]
		apps = manager.list_helpers(type)
		if not current is None \
		and not current in [app.key for app in apps]:
			app = manager.get_application(current)
			if app:
				apps.insert(0, app)
			else:
				logger.warn('Could not find application: %s', current)

		name_map = {}
		setattr(self, '%s_map' % type, name_map)

		for app in apps:
			name = app.name
			name_map[name] = app.key
			widget.append_text(name)

		widget.append_text(self.OTHER_APP)
		widget.connect('changed', self._on_combo_changed, type)

		widget.current_app = 0
		try:
			active = [app.key for app in apps].index(current)
			widget.current_app = active
			widget.set_active(active)
		except ValueError:
			pass

	def _on_combo_changed(self, combobox, type):
		name = combobox.get_active_text()
		if name == self.OTHER_APP:
			app = NewApplicationDialog(self, type=type).run()
			if app:
				# add new application and select it
				len = combobox.get_model().iter_n_children(None)
				name = app.name
				name_map = getattr(self, '%s_map' % type)
				name_map[name] = app.key
				combobox.insert_text(len-2, name)
				combobox.set_active(len-2)
			else:
				# dialog was cancelled - set back to current
				active = combobox.current_app
				combobox.set_active(active)

	def do_response_ok(self):
		# Get applications
		for type, name in self.applicationsform.items():
			name_map = getattr(self, '%s_map' % type)
			self.ui.preferences['GtkInterface'][type] = name_map.get(name)

		# Get dynamic tabs
		for form in self.forms.values():
			for key, value in form.items():
				section = form.preferences_sections[key]
				self.ui.preferences[section][key] = value

		# Set font - special case, consider it a HACK
		custom = self.ui.preferences['GtkInterface'].pop('use_custom_font')
		if custom:
			font = self.fontbutton.get_font_name()
		else:
			font = None
		PageView.style['TextView']['font'] = font
		PageView.style.write()

		# Save all
		self.ui.save_preferences()
		return True

	def do_response_cancel(self):
		# Obtain an updated list of loaded plugins
		now_loaded = [p.__class__ for p in self.ui.plugins]

		# Restore previous situation if the user changed something
		# in this dialog session
		for name in zim.plugins.list_plugins():
			klass = zim.plugins.get_plugin(name)
			activatable = klass.check_dependencies_ok()

			if klass in self.p_save_loaded and activatable and klass not in now_loaded:
				self.ui.load_plugin(klass.plugin_key)
			elif klass not in self.p_save_loaded and klass in now_loaded:
				self.ui.unload_plugin(klass.plugin_key)

		self.ui.save_preferences()
		return True

class PluginsTab(gtk.HBox):

	def __init__(self, dialog):
		gtk.HBox.__init__(self, spacing=12)
		self.set_border_width(5)
		self.dialog = dialog

		treeview = PluginsTreeView(self.dialog.ui)
		treeview.connect('row-activated', self.do_row_activated)
		swindow = gtk.ScrolledWindow()
		swindow.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
		swindow.set_shadow_type(gtk.SHADOW_IN)
		self.pack_start(swindow, False)
		swindow.add(treeview)

		vbox = gtk.VBox()
		self.add(vbox)

		# Textview with scrollbars to show plugins info. Required by small screen devices
		swindow, textview = scrolled_text_view()
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

		self.do_row_activated(treeview, (0,), 0)

	def do_row_activated(self, treeview, path, col):
		active = treeview.get_model()[path][0]
		name = treeview.get_model()[path][2]
		klass = treeview.get_model()[path][3]
		self._klass = klass
		logger.debug('Loading description for "%s"', name)

		# Insert plugin info into textview with proper formatting
		self.textbuffer.delete(*self.textbuffer.get_bounds()) # clear
		self.textbuffer.insert_with_tags_by_name(
			self.textbuffer.get_end_iter(),
			_('Name') + '\n', 'bold') # T: Heading in plugins tab of preferences dialog
		self.textbuffer.insert(
			self.textbuffer.get_end_iter(),
			klass.plugin_info['name'].strip() + '\n\n')
		self.textbuffer.insert_with_tags_by_name(
			self.textbuffer.get_end_iter(),
			_('Description') + '\n', 'bold') # T: Heading in plugins tab of preferences dialog
		self.textbuffer.insert(
			self.textbuffer.get_end_iter(),
			klass.plugin_info['description'].strip() + '\n\n')
		self.textbuffer.insert_with_tags_by_name(
			self.textbuffer.get_end_iter(),
			_('Dependencies') + '\n', 'bold') # T: Heading in plugins tab of preferences dialog

		#construct dependency list, missing dependencies are marked red
		dependencies = klass.check_dependencies()
		if not(dependencies):
			self.textbuffer.insert(
				self.textbuffer.get_end_iter(),
				_('No dependencies') + '\n') # T: label in plugin info in preferences dialog
		else:
			for dependency in dependencies:
				text, ok = dependency
				if ok:
					self.textbuffer.insert(
						self.textbuffer.get_end_iter(),
						u'\u2022 ' + text + ' - ' + _('OK') + '\n') # T: dependency is OK
				else:
					self.textbuffer.insert_with_tags_by_name(
						self.textbuffer.get_end_iter(),
						u'\u2022 ' + text +' - ' + _('Failed') + '\n', 'red') # T: dependency failed

		self.textbuffer.insert_with_tags_by_name(
			self.textbuffer.get_end_iter(),
			'\n' + _('Author') + '\n', 'bold') # T: Heading in plugins tab of preferences dialog
		self.textbuffer.insert(
			self.textbuffer.get_end_iter(),
			klass.plugin_info['author'].strip())

		self.configure_button.set_sensitive(active and bool(klass.plugin_preferences))
		self.plugin_help_button.set_sensitive('help' in klass.plugin_info)

	def on_help_button_clicked(self, button):
		self.dialog.ui.show_help(self._klass.plugin_info['help'])

	def on_configure_button_clicked(self, button):
		PluginConfigureDialog(self.dialog, self._klass).run()


class PluginsTreeModel(gtk.ListStore):

	def __init__(self, ui):
		#columns are: loaded, activable, name, plugin instance
		gtk.ListStore.__init__(self, bool, bool, str, object)
		self.ui = ui
		loaded = [p.__class__ for p in self.ui.plugins]
		for name in zim.plugins.list_plugins():
			try:
				klass = zim.plugins.get_plugin(name)
				isloaded = klass in loaded
				activatable = klass.check_dependencies_ok()
			except:
				logger.exception('Could not load plugin %s', name)
				continue
			else:
				self.append((isloaded, activatable, klass.plugin_info['name'], klass))

	def do_toggle_path(self, path):
		loaded, activatable, name, klass = self[path]
		if not activatable:
			return

		if loaded:
			self.ui.unload_plugin(klass.plugin_key)
			self[path][0] = False
		else:
			self.ui.load_plugin(klass.plugin_key)
			self[path][0] = True


class PluginsTreeView(BrowserTreeView):

	def __init__(self, ui):
		BrowserTreeView.__init__(self)

		model = PluginsTreeModel(ui)
		self.set_model(model)

		cellrenderer = gtk.CellRendererToggle()
		cellrenderer.connect('toggled', lambda o, p: model.do_toggle_path(p))
		self.append_column(
			gtk.TreeViewColumn(_('Enabled'), cellrenderer, active=0, activatable=1))
			# T: Column in plugin tab
		self.append_column(
			gtk.TreeViewColumn(_('Plugin'), gtk.CellRendererText(), text=2))
			# T: Column in plugin tab


class PluginConfigureDialog(Dialog):

	def __init__(self, dialog, klass):
		Dialog.__init__(self, dialog, _('Configure Plugin')) # T: Dialog title
		self.ui = dialog.ui

		classes = [p.__class__ for p in self.ui.plugins]
		i = classes.index(klass)
		self.plugin = self.ui.plugins[i]

		label = gtk.Label()
		label.set_markup(
			'<b>'+_('Options for plugin %s') % klass.plugin_info['name']+'</b>')
			# T: Heading for 'configure plugin' dialog - %s is the plugin name
		self.vbox.add(label)

		fields = []
		self.preferences = dialog.ui.preferences[klass.__name__]
		for pref in klass.plugin_preferences:
			if len(pref) == 4:
				key, type, label, default = pref
				self.preferences.setdefault(key, default) # just to be sure
			else:
				key, type, label, default, check = pref
				self.preferences.setdefault(key, default, check=check) # just to be sure

			if type in ('int', 'choice'):
				fields.append((key, type, label, check))
			else:
				fields.append((key, type, label))

		self.add_form(fields, self.preferences)

	def do_response_ok(self):
		# First let the plugin recieve the changes, then save them.
		# The plugin could do som conversion on the fly (e.g. Path to string)
		self.preferences.update(self.form)
		self.plugin.emit('preferences-changed')
		self.ui.save_preferences()
		return True


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
