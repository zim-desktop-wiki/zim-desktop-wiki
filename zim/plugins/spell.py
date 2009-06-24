# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

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
	# name, stock id, label, accelerator, tooltip, None, initial state
	('toggle_spellcheck', 'gtk-spell-check', 'Check _spelling', 'F7', 'Spell check', None, False),
)

class SpellPlugin(PluginClass):
	'''FIXME'''

	plugin_info = {
		'name': 'Spell',
		'description': '''\
Adds spell checking support using gtkspell.
Please make sure gtkspell is installed.

This is a core plugin shipping with zim.
''',
		'author': 'Jaap Karssenberg',
		'manualpage': 'Plugins:Spell',
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
			# TODO use setting to control behavior
			self.ui.connect_after('open-page', self.do_open_page)

	@classmethod
	def check(cls):
		if gtkspell is None:
			return False, 'Could not load gtkspell'
		else:
			return True

	def toggle_spellcheck(self):
		self.ui.actiongroup.get_action('toggle_spellcheck').activate()

	def do_toggle_spellcheck(self):
		if not self.uistate['active']:
			self.enable_spellcheck()
		else:
			self.disable_spellcheck()

	def enable_spellcheck(self):
		# TODO check language in page / notebook / default
		self.uistate['active'] = True
		if self.spell is None:
			textview = self.ui.mainwindow.pageview.view
			lang = self.preferences['language'] or None
			self.spell = gtkspell.Spell(textview, lang)
			textview.gtkspell = self.spell # used by hardcoded hook in pageview
		# TODO action_show_active

		return False # we can be called from idle event

	def disable_spellcheck(self):
		self.uistate['active'] = False
		if not self.spell is None:
			textview = self.ui.mainwindow.pageview.view
			textview.gtkspell = None
			self.spell.detach()
			self.spell = None
		# TODO action_show_active

	def do_open_page(self, ui, page, record):
		# Assume the old object is detached by hard coded
		# hook in TextView, just attach a new one.
		# Use idle timer to avoid lag in page loading.
		self.spell = None
		if self.uistate['active']:
			gobject.idle_add(self.enable_spellcheck)
