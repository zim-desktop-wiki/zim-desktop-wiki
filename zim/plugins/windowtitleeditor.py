
# Copyright 2022 introt <introt@koti.fimnet.fi>

# based on original work (c) Jaap Karssenberg <jaap.karssenberg@gmail.com>

from string import Template

from zim.config import Choice
from zim.plugins import PluginClass
from zim.actions import radio_action, radio_option
from zim.gui.mainwindow import MainWindowExtension, PageWindow, WindowBaseMixin

import logging
logger = logging.getLogger('zim.plugins.windowtitleeditor')

READONLY = ' [' + _('readonly') + '] '  # T: page status for title bar

FORMATS = (
		('zim_seventyfour', _('Page Path - Notebook Name')),  # T: Option for Window Title template
		('zim_sixties', _('Notebook Name - Zim')),  # T: Option for Window Title template
		('python_docs', _('Page Name — Page Title — Zim')),  # T: Option for Window Title template
		('title_source', _('Notebook Name: Page Title (Page Source Path)')),  # T: Option for Window Title template
		('custom', _('Custom')),  # T: Option for Window Title template
)

class WindowTitleEditorPlugin(PluginClass):
	plugin_info = {
		'name': _('Window Title Editor'),  # T: plugin name
		'description': _('''\
This plugin allows editing the window title.

Press "Configure" below to choose a preset
or to create a custom one.
'''),  # T: plugin description
		'author': 'introt',
		'help': 'Plugins:WindowTitleEditor',
	}

	plugin_preferences = (
		# key, type, label, default
		('format', 'choice', _('Title template'), 'custom', FORMATS),
			# T: window title editor preference option
		(
			'custom_format', 'string',
			_('Template string for custom format'),
			# T: window title editor preference option
			'$title - $notebook ($source)'),
	)


class WindowTitleEditorExtension(MainWindowExtension):
	def __init__(self, plugin, window):
		MainWindowExtension.__init__(self, plugin, window)  # init super

		self.templates = {
				'zim_seventyfour': Template('$path - $notebook'),  # default without plugin
				'zim_sixties': Template('$notebook - Zim'),  # old default
				'python_docs': Template('$page — $title — Zim'),  # inspired by Python docs
				'title_source': Template('$notebook: $title ($source)'),
				'custom': None,
		}

		self.window._update_window_title = self.update_window_title  # override default updater
		# override PageWindow's set_title - lambda allows us to access to both "selfs"
		PageWindow.set_title = lambda s, t: self.set_pagewindow_title(s, t)
		self.preferences = plugin.preferences
		self.on_preferences_changed(self.preferences)  # init the custom template
		self.connectto(
				self.preferences, 'changed',
				self.on_preferences_changed)  # connect for updates
		logger.debug('WindowTitleEditor loaded')

	def make_title(self, page, notebook):
		try:  # substitution is safe, but updates may introduce different defaults
			readonly = READONLY if notebook.readonly or (page and page.readonly) else ''

			if page:
				title = self.templates[
							self.preferences['format']
							].safe_substitute(
									path=page,
									page=page.basename,
									source=page.source_file,
									title=page.get_title(),
									notebook=notebook.name,
									folder=notebook.folder,
									ro=readonly,
									)
				if not readonly in title:
					title += readonly
			else:
				title = notebook.name + readonly
		except Exception as e:
			logger.warning('Caught "%s: %s" while trying to make_title ' + \
					'using format "%s", resetting preference to custom',
					type(e), e, self.preferences['format'])
			self.preferences['format'] = 'custom'  # thanks to safe subs, 'custom' is always ok :)
			title = _('Plugin error - check debug log! - Zim')  # T: window title in case of critical error

		return title.strip()

	def set_pagewindow_title(self, pagewindow, original_title):
		logger.debug('Set title for new pagewindow "%s"', original_title)
		WindowBaseMixin.set_title(pagewindow,
				self.make_title(pagewindow.page, pagewindow.notebook))

	def update_window_title(self):
		w = self.window
		w.set_title(self.make_title(w.page, w.notebook))

	def teardown(self):
		w = self.window  # rebind original method (no need to import types)
		w._update_window_title = w.__class__._update_window_title.__get__(w, type(w))
		w._update_window_title()
		PageWindow.set_title = WindowBaseMixin.set_title
		logger.debug('Original window title methods restored')

	def on_preferences_changed(self, preferences):
		self.templates['custom'] = Template(preferences['custom_format'])
		self.update_window_title()

