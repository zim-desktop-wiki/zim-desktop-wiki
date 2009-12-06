# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Spell check plugin based on gtkspell'''

import gobject

from zim.plugins import PluginClass

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
Please make sure gtkspell is installed.

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
	def check(cls):
		if gtkspell is None:
			return False, 'Could not load gtkspell'
		else:
			return True

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
			# TODO check language in page / notebook / default
			if self.spell is None:
				lang = self.preferences['language'] or None
				self.spell = gtkspell.Spell(textview, lang)
				textview.gtkspell = self.spell # used by hardcoded hook in pageview
			else:
				pass
		else:
			if self.spell is None:
				pass
			else:
				self.spell.detach()
				self.spell = None
				textview.gtkspell = None

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

