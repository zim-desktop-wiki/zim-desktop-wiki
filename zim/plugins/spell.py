# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Spell check plugin based on gtkspell'''

import os
import gobject

from zim.plugins import PluginClass
from zim.gui.widgets import ErrorDialog

try:
	import gtkspell
except:
	gtkspell = None

ui_xml = '''
<ui>
	<menubar name='menubar'>
		<menu action='tools_menu'>
			<placeholder name='page_tools'>
				<menuitem action='toggle_spellcheck'/>
			</placeholder>
		</menu>
	</menubar>
	<toolbar name='toolbar'>
		<placeholder name='tools'>
			<toolitem action='toggle_spellcheck'/>
		</placeholder>
	</toolbar>
</ui>
'''

ui_toggle_actions = (
	# name, stock id, label, accelerator, tooltip, initial state, readonly
	('toggle_spellcheck', 'gtk-spell-check', _('Check _spelling'), 'F7', 'Spell check', False, True), # T: menu item
)

class SpellPlugin(PluginClass):

	plugin_info = {
		'name': _('Spell Checker'), # T: plugin name
		'description': _('''\
Adds spell checking support using gtkspell.

This is a core plugin shipping with zim.
'''), # T: plugin description
		'author': 'Jaap Karssenberg',
		'help': 'Plugins:Spell Checker',
	}

	plugin_preferences = (
		('language', 'string', 'Default Language', ''),
	)

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		self.spell = None
		self.uistate.setdefault('active', False)
		if self.ui.ui_type == 'gtk':
			self.ui.add_toggle_actions(ui_toggle_actions, self)
			self.ui.add_ui(ui_xml, self)
			self.ui.connect_after('open-page', self.do_open_page)

	@classmethod
	def check_dependencies(klass):
		return [('gtkspell',not gtkspell is None)]

	def toggle_spellcheck(self, enable=None):
		action = self.actiongroup.get_action('toggle_spellcheck')
		if enable is None or enable != action.get_active():
			action.activate()
		else:
			self.do_toggle_spellcheck(enable=enable)

	def do_toggle_spellcheck(self, enable=None):
		#~ print 'do_toggle_spellcheck', enable
		if enable is None:
			action = self.actiongroup.get_action('toggle_spellcheck')
			enable = action.get_active()

		textview = self.ui.mainwindow.pageview.view
		if enable:
			if self.spell is None:
				lang = self.preferences['language'] or None
				try:
					self.spell = gtkspell.Spell(textview, lang)
				except:
					lang = lang or os.environ.get('LANG') or os.environ.get('LANGUAGE')
					ErrorDialog(self.ui, (
						_('Could not load spell checking for language: "%s"') % lang,
							# T: error message - %s is replace with language codes like "en", "en_US"m or "nl_NL"
						_('This could mean you don\'t have the proper\ndictionaries installed')
							# T: error message explanation
					) ).run()
					return
				else:
					textview.gtkspell = self.spell # HACK used by hardcoded hook in pageview
			else:
				pass
		else:
			if self.spell is None:
				pass
			else:
				if textview.gtkspell \
				and textview.gtkspell == self.spell:
					textview.gtkspell.detach()
					textview.gtkspell = None
				self.spell = None

		self.uistate['active'] = enable
		return False # we can be called from idle event

	def do_open_page(self, ui, page, record):
		# Assume the old object is detached by hard coded
		# hook in TextView, just attach a new one.
		# Use idle timer to avoid lag in page loading.
		# This hook also synchronizes the state of the toggle with
		# the uistate when loading the first page
		self.spell = None
		if self.uistate['active']:
			gobject.idle_add(self.toggle_spellcheck, True)

