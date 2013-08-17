# -*- coding: utf-8 -*-

# Copyright 2008,2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Spell check plugin based on gtkspell'''

import gobject

from zim.plugins import PluginClass, WindowExtension, extends
from zim.signals import SIGNAL_AFTER
from zim.actions import toggle_action
from zim.gui.widgets import ErrorDialog

try:
	import gtkspell
except ImportError:
	gtkspell = None


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

	@classmethod
	def check_dependencies(klass):
		return (not gtkspell is None), [('gtkspell', not gtkspell is None, True)]


@extends('MainWindow')
class MainWindowExtension(WindowExtension):

	uimanager_xml = '''
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

	def __init__(self, plugin, window):
		WindowExtension.__init__(self, plugin, window)
		self.spell = None
		self.uistate.setdefault('active', False)
		self.toggle_spellcheck(self.uistate['active'])
		self.connectto(self.window.ui, 'open-page', order=SIGNAL_AFTER) # XXX

	@toggle_action(
		_('Check _spelling'), # T: menu item
		stock='gtk-spell-check', accelerator='F7'
	)
	def toggle_spellcheck(self, active):
		if active and not self.spell:
			self.setup()
		elif not active and self.spell:
			self.teardown()
		self.uistate['active'] = active

	def on_open_page(self, ui, page, record):
		# Assume the old object is detached by hard coded
		# hook in TextView, just attach a new one.
		# Use idle timer to avoid lag in page loading.
		# This hook also synchronizes the state of the toggle with
		# the uistate when loading the first page
		if self.uistate['active']:
			gobject.idle_add(self.setup)

	def setup(self):
		textview = self.window.pageview.view
		lang = self.plugin.preferences['language'] or None
		try:
			self.spell = gtkspell.Spell(textview, lang)
		except:
			ErrorDialog(self.ui, (
				_('Could not load spell checking'),
					# T: error message
				_('This could mean you don\'t have the proper\ndictionaries installed')
					# T: error message explanation
			) ).run()
			self.spell = None
		else:
			textview.gtkspell = self.spell # HACK used by hardcoded hook in pageview

	def teardown(self):
		textview = self.window.pageview.view
		if textview.gtkspell:
			textview.gtkspell.detach()
			textview.gtkspell = None
		self.spell = None

