
# Copyright 2009-2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>



from gi.repository import Pango
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GObject

import logging
import locale

from zim.gui.widgets import Dialog, BrowserTreeView, \
	ScrolledWindow, ScrolledTextView, InputForm, input_table_factory, get_window, help_text_factory
from zim.gui.applications import CustomizeOpenWithDialog, open_folder_prompt_create, ApplicationManager

from zim.plugins import PLUGIN_FOLDER
from zim.config import String, ConfigManager
from zim.plugins import PluginManager
from zim.main import ZIM_APPLICATION

from zim.gui.applications import ui_preferences as application_preferences
from zim.gui.mainwindow import ui_preferences as interface_preferences
from zim.gui.pageview import ui_preferences as pageview_preferences


logger = logging.getLogger('zim.gui.preferencesdialog')


# define section labels here so xgettext can fing them
_label = _('Interface') # T: Tab in preferences dialog
_label = _('Editing') # T: Tab in preferences dialog


def localeWarningBar(enc):
	bar = Gtk.InfoBar()
	bar.set_message_type(Gtk.MessageType.WARNING)
	label = Gtk.Label(_(
		'Your system encoding is set to %s, if you want support for special characters\n'
		'or see errors due to encoding, please ensure to configure your system to use "UTF-8"') % enc)
		# T: warning message, %s is the current locale - e.g. "NL_nl"
	label.set_line_wrap(True)
	label.set_xalign(0)
	bar.get_content_area().pack_start(label, False, False, 0)
	return bar


class PreferencesDialog(Dialog):

	def __init__(self, widget, show_tab=None, select_plugin=None):
		'''Constructor
		@param show_tab: tab to present in the dialog
		@select_plugin: plugin to present in the dialog
		'''
		Dialog.__init__(self, widget, _('Preferences')) # T: Dialog title
		self.preferences = ConfigManager.preferences
		self.main_window = widget

		# warning for locale
		_pref_enc = locale.getpreferredencoding()
		if _pref_enc in ('ascii', 'us-ascii', 'ANSI_X3.4-1968'):
			self.vbox.pack_start(localeWarningBar(_pref_enc), True, True, 0)

		# saves a list of loaded plugins to be used later
		self.plugins = PluginManager()
		self.p_save_loaded = list(self.plugins)

		# Dynamic tabs
		gtknotebook = Gtk.Notebook()
		self.vbox.pack_start(gtknotebook, True, True, 0)
		self.forms = {}

		############################### needs rewrite to make defintion more robust
		for category in ('Interface', 'Editing'):
			vbox = Gtk.VBox()
			index = gtknotebook.append_page(vbox, Gtk.Label(label=_(category)))
			# From GTK Doc: Note that due to historical reasons, GtkNotebook refuses
			# to switch to a page unless the child widget is visible.
			vbox.show()
			if category == show_tab:
				gtknotebook.set_current_page(index)

			fields = []
			values = {}
			sections = {}

			for section, preferences in (
				('GtkInterface', interface_preferences),
				('Application', application_preferences),
				('PageView', pageview_preferences)
			):
				for p in [p for p in preferences if p[2] == category]:
					# key, type, category, label, default, (check)
					if len(p) == 5:
						key, type, cat, label, default = p
						self.preferences[section].setdefault(key, default)
						fields.append((key, type, label))
					else:
						key, type, cat, label, default, check = p
						self.preferences[section].setdefault(key, default, check)
						fields.append((key, type, label, check))

					values[key] = self.preferences[section][key]
					sections[key] = section

			form = InputForm(fields, values)
			form.preferences_sections = sections
			vbox.pack_start(form, False, True, 0)
			self.forms[category] = form

			if category == 'Interface':
				self._add_font_selection(form)

		# Styles tab
		#~ gtknotebook.append_page(StylesTab(self), Gtk.Label(label=_('Styles')))

		# Keybindings tab
		gtknotebook.append_page(KeyBindingsTab(self), Gtk.Label(label=_('Key bindings')))
				# T: Heading in preferences dialog

		# Plugins tab
		self.plugins_tab = PluginsTab(self, self.plugins)
		plugins_tab_index = gtknotebook.append_page(self.plugins_tab, Gtk.Label(label=_('Plugins')))
				# T: Heading in preferences dialog
		self.plugins_tab.show()
		if show_tab == "Plugins" or select_plugin is not None:
			gtknotebook.set_current_page(plugins_tab_index)
			if not select_plugin is None:
					self.plugins_tab.select_plugin(select_plugin)

		# Applications tab
		gtknotebook.append_page(ApplicationsTab(self), Gtk.Label(label=_('Applications')))
			# T: Heading in preferences dialog

	def _add_font_selection(self, table):
		# need to hardcode this, cannot register it as a preference
		table.add_inputs((
			('use_custom_font', 'bool', _('Use a custom font')),
			# T: option in preferences dialog
		))
		table.preferences_sections['use_custom_font'] = 'GtkInterface'

		self.fontbutton = Gtk.FontButton()
		self.fontbutton.set_use_font(True) # preview in button
		self.fontbutton.set_sensitive(False)
		text_style = ConfigManager.get_config_dict('style.conf')
		try:
			font = text_style['TextView']['font']
			if font:
				self.fontbutton.set_font_name(font)
				self.fontbutton.set_sensitive(True)
				table['use_custom_font'] = True
		except KeyError:
			pass

		table.widgets['use_custom_font'].connect('toggled',
			lambda o: self.fontbutton.set_sensitive(o.get_active()))

		self.fontbutton.set_size_request(100, -1)
		input_table_factory(((None, self.fontbutton),), table)

	def do_response_ok(self):
		# Get dynamic tabs
		newpreferences = {}
		for form in list(self.forms.values()):
			for key, value in list(form.items()):
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

		text_style = ConfigManager.get_config_dict('style.conf')
		text_style['TextView'].define(font=String(None))
		text_style['TextView']['font'] = font
		#

		with self.preferences.block_signals('changed'):
			# note we do not block signal on section dicts
			for section in newpreferences:
				self.preferences[section].update(newpreferences[section])

		self.preferences.emit('changed') # delayed emission

		return True

	def do_response_cancel(self):
		# Obtain an updated list of loaded plugins
		now_loaded = list(self.plugins)

		# Restore previous situation if the user changed something
		# in this dialog session
		with self.preferences.block_signals('changed'):
			for name in self.plugins.list_installed_plugins():
				if name in self.p_save_loaded and name not in now_loaded:
					try:
						self.plugins.load_plugin(name)
					except:
						logger.exception('Could not restore plugin: %s', name)
				elif name not in self.p_save_loaded and name in now_loaded:
					self.plugins.remove_plugin(name)

		self.preferences.emit('changed') # delayed emission

		return True


class PluginsTab(Gtk.VBox):

	def __init__(self, dialog, plugins):
		GObject.GObject.__init__(self)
		self.set_spacing(5)
		self.dialog = dialog
		self.plugins = plugins

		self.hbox = Gtk.HBox(self, spacing=12)
		self.hbox.set_border_width(5)
		self.add(self.hbox)

		#~ logger.debug('Plugins that are loaded: %s' % list(plugins))

		self.treeview = PluginsTreeView(self.plugins)
		self.treeselection = self.treeview.get_selection()
		self.treeselection.connect('changed', self.do_selection_changed)
		swindow = ScrolledWindow(self.treeview, hpolicy=Gtk.PolicyType.NEVER)
		self.hbox.pack_start(swindow, False, True, 0)

		vbox = Gtk.VBox()
		self.hbox.add(vbox)

		# Textview with scrollbars to show plugins info. Required by small screen devices
		swindow, textview = ScrolledTextView()
		textview.set_cursor_visible(False)
		self.textbuffer = textview.get_buffer()
		self.textbuffer.create_tag('bold', weight=Pango.Weight.BOLD)
		self.textbuffer.create_tag('red', foreground='#FF0000')
		vbox.pack_start(swindow, True, True, 0)

		hbox = Gtk.HBox(spacing=5)
		vbox.pack_end(hbox, False, True, 0)

		self.plugin_help_button = \
			Gtk.Button.new_with_mnemonic(_('_More')) # T: Button in plugin tab
		self.plugin_help_button.connect('clicked', self.on_help_button_clicked)
		hbox.pack_start(self.plugin_help_button, False, True, 0)

		self.configure_button = \
			Gtk.Button.new_with_mnemonic(_('C_onfigure')) # T: Button in plugin tab
		self.configure_button.connect('clicked', self.on_configure_button_clicked)
		hbox.pack_start(self.configure_button, False, True, 0)

		self.properties_button = \
			Gtk.Button.new_with_mnemonic(_('_Properties'))  # T: Button in plugin tab
		hbox.pack_start(self.properties_button, False, True, 0)
		self.properties_button.connect('clicked', self.on_properties_button_clicked)

		try:
			self.treeselection.select_path(0)
		except:
			pass # maybe loading plugins failed

		## Add buttons to get and install new plugins
		hbox = Gtk.HButtonBox()
		hbox.set_border_width(5)
		hbox.set_layout(Gtk.ButtonBoxStyle.START)
		self.pack_start(hbox, False, True, 0)

		open_button = Gtk.Button.new_with_mnemonic(_('Open plugins folder'))
			# T: button label
		open_button.connect('clicked',
			lambda o: open_folder_prompt_create(o, PLUGIN_FOLDER)
		)
		hbox.pack_start(open_button, False, True, 0)

		url_button = Gtk.LinkButton(
			'https://zim-wiki.org/more_plugins.html',
			_('Get more plugins online') # T: label for button with URL
		)
		hbox.pack_start(url_button, False, True, 0)


	def do_selection_changed(self, selection):
		treeview = selection.get_tree_view()
		selected = selection.get_selected()
		path = selected[0].get_path(selected[1])

		key, active, activatable, name, klass = treeview.get_model()[path]
		self._current_plugin = key
		logger.debug('[GUI/Preferences/Plugins]: Plugin[%s] is selected.', name)

		if not activatable:
			logger.debug('[GUI/Preferences/Plugins]: Plugin[%s] is not activatable, try to load it again.', name)
			try:
				klass = PluginManager().load_plugin(key)
			except Exception:
				logger.debug("[GUI/Preferences/Plugins]: Failed to load plugin[%s] again.", name)
				activatable = False
			else:
				activatable = True
				treeview.get_model()[path][2] = activatable
				treeview.get_model()[path][4] = klass

		# Insert plugin info into textview with proper formatting
		# TODO use our own widget with formatted text here...
		buffer = self.textbuffer
		def insert(text, style=None):
			if style:
				buffer.insert_with_tags_by_name(buffer.get_end_iter(), text, style)
			else:
				buffer.insert_at_cursor(text)

		buffer.delete(*buffer.get_bounds()) # clear

		check, dependencies = klass.check_dependencies() if klass else (False, [])

		if not activatable:
			# Each dependency is a 3-tuple of (name, available, required). If any
			# dependency is required but not available we can inform the user.
			if any(dep for dep in dependencies if not dep[1] and dep[2]):
				insert(
					_(
						'This plugin cannot be enabled due to missing dependencies.\n'
						'Please see the dependencies section below for details.\n\n'
					), # T: help text when plugin cannot be activated
					'red'
				)
			else:
				# Dependencies are ok so there is some other reason for this plugin
				# not being loaded. This can happen if there is a problem
				# (e.g. syntax error) in the extension's Python module. Such issues
				# are caught when the PluginsTreeModel is init'ed.
				insert(_('There was a problem loading this plugin\n\n'), 'red')
					# T: help text when plugin cannot be loaded due to bug / issue

				if not klass:
					self.configure_button.set_sensitive(False)
					self.plugin_help_button.set_sensitive(False)
					return

		insert(_('Name') + '\n', 'bold') # T: Heading in plugins tab of preferences dialog
		insert(klass.plugin_info['name'].strip() + '\n\n')
		insert(_('Description') + '\n', 'bold') # T: Heading in plugins tab of preferences dialog
		insert(klass.plugin_info['description'].strip() + '\n\n')
		insert(_('Dependencies') + '\n', 'bold') # T: Heading in plugins tab of preferences dialog

		if not dependencies:
			insert(_('No dependencies') + '\n') # T: label in plugin info in preferences dialog
		else:
			# Construct dependency list, missing dependencies are marked red
			for dependency in dependencies:
				text, ok, required = dependency
				if ok:
					insert('\u2022 %s - %s\n' % (text, _('OK'))) # T: dependency is OK
				elif required:
					insert('\u2022 %s - %s\n' % (text, _('Failed')), 'red') # T: dependency failed
				else:
					insert('\u2022 %s - %s (%s)\n' % (text,
						_('Failed'), # T: dependency failed
						_('Optional') # T: optional dependency
					))
		insert('\n')

		insert(_('Author') + '\n', 'bold') # T: Heading in plugins tab of preferences dialog
		insert(klass.plugin_info['author'].strip())

		self.configure_button.set_sensitive(active and bool(klass.plugin_preferences))
		self.properties_button.set_sensitive(active and bool(klass.plugin_notebook_properties))
		self.plugin_help_button.set_sensitive('help' in klass.plugin_info)

	def on_help_button_clicked(self, button):
		klass = self.plugins.get_plugin_class(self._current_plugin)
		page = klass.plugin_info['help']
		if page:
			ZIM_APPLICATION.run('--manual', page)

	def on_configure_button_clicked(self, button):
		plugin = self.plugins[self._current_plugin]
		PluginConfigureDialog(self.dialog, plugin).run()

	def on_properties_button_clicked(self, button):
		from zim.gui.propertiesdialog import PropertiesDialog
		PropertiesDialog(self.dialog.main_window,
						 self.dialog.main_window.notebook,
						 chosen_plugin=self._current_plugin).run()

	def select_plugin(self, name):
		model = self.treeview.get_model()
		def find(model, path, iter):
			if name in model[iter]: # either key or localized name
				self.treeview.scroll_to_cell(path)
				self.treeview.set_cursor(path)
				self.do_selection_changed(self.treeselection)
				return True
			return False # keep the foreach going
		model.foreach(find)


class PluginsTreeModel(Gtk.ListStore):

	def __init__(self, plugins):
		#columns are: key, active, activatable, name, klass
		Gtk.ListStore.__init__(self, str, bool, bool, str, object)
		self.plugins = plugins

		allplugins = []
		for key in self.plugins.list_installed_plugins():
			klass, name, loaded = None, key, False

			try:
				klass = self.plugins.get_plugin_class(key)
				name = klass.plugin_info['name']
				loaded = True
			except:
				logger.exception('Could not load plugin %s', key)
			finally:
				allplugins.append((name, key, klass, loaded))

		allplugins.sort() # sort by translated name

		for name, key, klass, loaded in allplugins:
			active = key in self.plugins
			try:
				activatable = loaded and klass.check_dependencies_ok()
			except:
				activatable = False
				logger.exception('Could not load plugin %s', name)
			finally:
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

		cellrenderer = Gtk.CellRendererToggle()
		cellrenderer.connect('toggled', lambda o, p: model.do_toggle_path(p))
		self.append_column(
			Gtk.TreeViewColumn(_('Enabled'), cellrenderer, active=1, activatable=2))
			# T: Column in plugin tab
		self.append_column(
			Gtk.TreeViewColumn(_('Plugin'), Gtk.CellRendererText(), text=3))
			# T: Column in plugin tab


class PluginConfigureDialog(Dialog):

	def __init__(self, dialog, plugin):
		Dialog.__init__(self, dialog, _('Configure Plugin')) # T: Dialog title
		self.plugin = plugin

		label = Gtk.Label()
		label.set_markup(
			'<b>' + _('Options for plugin %s') % plugin.plugin_info['name'] + '</b>')
			# T: Heading for 'configure plugin' dialog - %s is the plugin name
		self.vbox.add(label)

		self.add_form(
			inputs=self.plugin.form_fields(self.plugin.plugin_preferences),
			values=self.plugin.preferences
		)

		if plugin.plugin_notebook_properties:
			hbox = Gtk.Box(spacing=12)
			hbox.add(Gtk.Image.new_from_icon_name('dialog-information', Gtk.IconSize.DIALOG))
			label = Gtk.Label()
			label.set_markup(
				'<i>' +
				_('This plugin also has properties,\nsee the notebook properties dialog') + # T: info text in the preferences dialog
				'</i>'
			)
			hbox.add(label)
			self.vbox.pack_start(hbox, False, False, 18)

	def do_response_ok(self):
		# First let the plugin receive the changes, then save them.
		# The plugin could do some conversion on the fly (e.g. Path to string)
		self.plugin.preferences.update(self.form)
		return True


class ApplicationsTab(Gtk.VBox):

	def __init__(self, dialog):
		GObject.GObject.__init__(self)
		self.set_border_width(5)
		self.set_spacing(5)
		self.dialog = dialog

		button = Gtk.Button.new_with_mnemonic(_('Set default text editor'))
			# T: button in preferences dialog to change default text editor
		button.connect('clicked', self.on_set_texteditor)
		self.pack_start(button, False, True, 0)

		button = Gtk.Button.new_with_mnemonic(_('Set default browser'))
			# T: button in preferences dialog to change default browser
		button.connect('clicked', self.on_set_browser)
		self.pack_start(button, False, True, 0)

	def on_set_texteditor(self, o):
		CustomizeOpenWithDialog(self.dialog, 'text/plain').run()

	def on_set_browser(self, o):
		CustomizeOpenWithDialog(self.dialog, 'text/html').run()
		app = ApplicationManager.get_default_application('text/html')
		for alt in ('x-scheme-handler/http', 'x-scheme-handler/https'):
			ApplicationManager.set_default_application(alt, app)


class StylesTab(Gtk.VBox):

	def __init__(self, dialog):
		GObject.GObject.__init__(self)
		self.add(Gtk.Label(label='TODO add treeview with styles'))


class StylesTreeModel(Gtk.ListStore):

	def __init__(self):
		#'weight', 'scale', 'style', 'background', 'foreground', 'strikethrough',
		# 'family', 'wrap-mode', 'indent', 'underline'
		Gtk.ListStore.__init__(self, bool, str, object)


class KeyBindingsTab(Gtk.VBox):
	def __init__(self, dialog):
		GObject.GObject.__init__(self)
		help = _(
			'Key bindings can be changed by clicking on a field with a key combination\n'
			'in the list and then press the new key binding.\n'
			'To disable a keybinding, select it in the list and use <tt>&lt;Backspace&gt;</tt>.'
		) # T: help text in preferences dialog for modifying keybindings
		self.add(ScrolledWindow(KeyBindingTreeView()))
		self.pack_end(help_text_factory(help), False, True, 12)


class KeyBindingTreeView(Gtk.TreeView):
	def __init__(self):
		GObject.GObject.__init__(self)
		model = Gtk.ListStore(str, int, Gdk.ModifierType) # accel_path, accel_key, accel_mods

		def _append(data, accel_path, accel_key, accel_mods, changed):
			if not accel_path.endswith('_menu'):
				model.append((accel_path, accel_key, accel_mods))
		Gtk.AccelMap.foreach(None, _append)

		model.set_sort_column_id(0, Gtk.SortType.ASCENDING)
		self.set_model(model)

		column = Gtk.TreeViewColumn(_('Action'))
			# T: Column header for keybinding list
		column.set_expand(True)
		column.set_sort_column_id(0)
		self.append_column(column)

		cr = Gtk.CellRendererText()
		cr.set_property('ellipsize', Pango.EllipsizeMode.MIDDLE)
		column.pack_start(cr, True)
		column.set_attributes(cr, text=0)

		column = Gtk.TreeViewColumn(_('Key Binding'))
			# T: Column header for keybinding list
		column.set_sort_column_id(1)
		self.append_column(column)

		cr = Gtk.CellRendererAccel()
		cr.set_property('editable', True)
		column.pack_start(cr, True)
		column.set_attributes(cr, accel_key=1, accel_mods=2)

		def _update(cr, tree_path, accel_key, accel_mods, hw_int):
			accel_path = model[tree_path][0]
			Gtk.AccelMap.change_entry(accel_path, accel_key, accel_mods, True)
			# Update of ListStore happens via AccelMap changed signal

		cr.connect('accel-edited', _update)

		def _clear(cr, tree_path):
			accel_path = model[tree_path][0]
			Gtk.AccelMap.change_entry(accel_path, 0, 0, False)

		cr.connect('accel-cleared', _clear)

		def _on_changed(map, accel_path, accel_key, accel_mods):
			for row in model:
				if row[0] == accel_path:
					row[1] = accel_key
					row[2] = accel_mods
					break
			else:
				model.append((accel_path, accel_key, accel_mods))

		accelmap = Gtk.AccelMap.get()
		sid = accelmap.connect('changed', _on_changed)
		self.connect('destroy', lambda o: accelmap.disconnect(sid))
