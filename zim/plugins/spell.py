
# Copyright 2008,2015,2023-2025 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import re
import locale
import logging

logger = logging.getLogger('zim.plugins.spell')


from zim.plugins import PluginClass
from zim.signals import SIGNAL_AFTER, ConnectorMixin
from zim.actions import toggle_action

from zim.gui.pageview import PageViewExtension
from zim.gui.widgets import ErrorDialog

import gi

# Try which of the bindings is available

gtkspellcheck = None
gtkspell = None
Gspell = None


try:
	gi.require_version('Gtk','3.0') # see issue #2301
	import gtkspellcheck
except:
	gtkspellcheck = None

if not gtkspellcheck:
	try:
		gi.require_version('Gspell', '1')
		from gi.repository import Gspell
		
		langs = Gspell.language_get_available()
		#for lang in langs:
		#	logger.debug('%s (%s) dict available', lang.get_name(), lang.get_code())
		if not langs:
			Gspell = None
	except:
		Gspell = None

if not Gspell:
	try:
		gi.require_version('GtkSpell', '3.0')
		from gi.repository import GtkSpell as gtkspell
	except:
		gtkspell = None



# Hotfix for robustness of loading languages in gtkspellcheck
# try to be robust for future versions breaking this or not needing it
# See https://github.com/koehlma/pygtkspellcheck/issues/22
#
# gtkspellchecker 5 has removed "pylocales", so if not present the fix is no
# longer working. Not sure if it is still needed with this release.
try:
	import pylocales
except ImportError:
	pylocales = None

if gtkspellcheck and pylocales \
and hasattr(gtkspellcheck.SpellChecker, '_LanguageList') \
and hasattr(gtkspellcheck.SpellChecker._LanguageList, 'from_broker'):
	from pylocales import code_to_name

	orig_from_broker = gtkspellcheck.SpellChecker._LanguageList.from_broker

	@classmethod
	def new_from_broker(cls, broker):
		try:
			return orig_from_broker(broker)
		except:
			lang = []
			for language in broker.list_languages():
				try:
					lang.append((language, code_to_name(language)))
				except:
					logger.exception('While loading language for: %s', language)

			return cls(sorted(lang, key=lambda language: language[1]))

	gtkspellcheck.SpellChecker._LanguageList.from_broker = new_from_broker
#####



# Silence gtkspellcheck logging, it is very verbose
mylogger = logging.getLogger('gtkspellcheck')
mylogger.setLevel(logging.INFO)
#####


def choose_adapter_cls():
	if gtkspellcheck:
		version = tuple(
			map(int, re.findall(r'\d+', gtkspellcheck.__version__))
		)
		if version >= (4, 0, 3):
			return GtkspellcheckAdapter
		else:
			logger.warning(
				'Using gtkspellcheck %s. Versions before 4.0.3 might cause memory leak.',
				gtkspellcheck.__version__
			)
			return OldGtkspellcheckAdapter
	elif Gspell:
		return GspellAdapter
	else:
		return GtkspellAdapter


class SpellPlugin(PluginClass):

	plugin_info = {
		'name': _('Spell Checker'), # T: plugin name
		'description': _('''\
Adds spell checking support using 
gtkspellchecker, Gspell, or gtkspell libraries.

This is a core plugin shipping with zim.
'''), # T: plugin description
		'author': 'Jaap Karssenberg',
		'help': 'Plugins:Spell Checker',
	}

	plugin_notebook_properties = (
		('language', 'string', 'Default Language', ''),
	)

	@classmethod
	def check_dependencies(klass):
		return any((gtkspellcheck, Gspell, gtkspell)), [
			('gtkspellcheck', not gtkspellcheck is None, True),
			('Gspell', not Gspell is None, True),
			('gtkspell', not gtkspell is None, True)
		]


class SpellPageViewExtension(PageViewExtension):

	def __init__(self, plugin, pageview):
		PageViewExtension.__init__(self, plugin, pageview)
		self._adapter_cls = choose_adapter_cls()
		self.checker = None

		self.uistate.setdefault('active', False)
		self.toggle_spellcheck(self.uistate['active'])

		self.properties = self.plugin.notebook_properties(self.pageview.notebook)
		self.on_properties_changed(self.properties)
		self.connectto(self.properties, 'changed', self.on_properties_changed)

		self.connectto(self.pageview, 'page-changed', order=SIGNAL_AFTER)

	def on_properties_changed(self, properties):
		if self.checker:
			self.checker.teardown()

		textview = self.pageview.textview
		lang = self.properties['language'] or locale.getdefaultlocale()[0]
		logger.debug('Spellcheck language: %s', lang)
		try:
			self.checker = self._adapter_cls(textview, lang)
			if self.uistate['active']:
				self.checker.enable()
			else:
				self.checker.disable()
		except:
			ErrorDialog(self.pageview, (
				_('Could not load spell checking'),
					# T: error message
				_('This could mean you don\'t have the proper\ndictionaries installed')
					# T: error message explanation
			)).run()

	def on_page_changed(self, pageview, page):
		# A new buffer may be initialized, but it could also be an existing buffer linked to page
		if self.checker:
			self.checker.on_buffer_changed(pageview.textview, self.uistate['active'])

	@toggle_action(_('Check _spelling'), accelerator='F7') # T: menu item
	def toggle_spellcheck(self, active):
		if self.checker:
			if active:
				self.checker.enable()
			else:
				self.checker.disable()

		self.uistate['active'] = active

	def teardown(self):
		if self.checker:
			self.checker.teardown()
		self.checker = None


class AdapterBase(ConnectorMixin, object):

	def __init__(self, textview, language):
		'''Contructor
		@param textview: a C{Gtk.TextView} to apply spellchecking to
		@param langage: a language code as string
		'''
		raise NotImplementedError

	def on_buffer_changed(self, textview, active):
		'''Callback for when the C{Gtk.TextBuffer} in the C{Gtk.TextView} was changed
		@param textview: a C{Gtk.TextView} to apply spellchecking to
		@param active: whether spellchecking is toggled on or off
		'''
		pass

	def enable(self):
		'''Toggle on the spell check behavior'''
		raise NotImplementedError

	def disable(self):
		'''Toggle off the spell check behavior'''
		raise NotImplementedError

	def teardown(self):
		'''Clean up object state before destruction'''
		raise NotImplementedError


class GtkspellcheckAdapter(AdapterBase):

	def __init__(self, textview, lang):
		self._lang = lang
		self._textview = textview

		self._clean_tag_table() # Just in case
		self._checker = gtkspellcheck.SpellChecker(self._textview, self._lang)

	def on_buffer_changed(self, textview, active):
		# Check whether buffer was initialized already by inspecting tag table
		if not self._check_tag_table():
			self._checker.buffer_initialize()

	def enable(self):
		self._checker.enable()

	def disable(self):
		self._checker.disable()

	def teardown(self):
		self._checker.disable()
		self._clean_tag_table()

	def _check_tag_table(self):
		tags = []

		def filter_spell_tags(t):
			name = t.get_property('name')
			if name and name.startswith('gtkspellchecker'):
				tags.append(t)

		table = self._textview.get_buffer().get_tag_table()
		table.foreach(filter_spell_tags)
		return tags

	def _clean_tag_table(self):
		## cleanup tag table - else next loading will fail
		table = self._textview.get_buffer().get_tag_table()
		for tag in self._check_tag_table():
			table.remove(tag)


class OldGtkspellcheckAdapter(GtkspellcheckAdapter):

	def on_buffer_changed(self, textview, active):
		# Check whether buffer was initialized already by inspecting tag table
		# wanted to use checker.buffer_initialize() here,
		# but gives issue, see https://github.com/koehlma/pygtkspellcheck/issues/24
		# So, just re-initialize
		if not self._check_tag_table():
			self._checker.disable()
			self._clean_tag_table()
			self._checker = gtkspellcheck.SpellChecker(self._textview, self._lang)
			if active:
				self._checker.enable()


class GtkspellAdapter(AdapterBase):

	def __init__(self, textview, lang):
		self._lang = lang
		self._textview = textview
		self._checker = gtkspell.Checker()
		self._checker.set_language(self._lang)

	def enable(self):
		self._checker.attach(self._textview)

	def disable(self):
		self._checker.detach()

	def teardown(self):
		self._checker.detach()


class GspellAdapter(AdapterBase):

	def __init__(self, textview, lang):
		gspell_language = Gspell.language_lookup(lang)
		self._checker = Gspell.Checker.new(gspell_language)
		self.on_buffer_changed(textview, False)
		self._gspell_view = Gspell.TextView.get_from_gtk_text_view(textview)
		self.enable()

	def on_buffer_changed(self, textview, active):
		buffer = Gspell.TextBuffer.get_from_gtk_text_buffer(textview.get_buffer())
		buffer.set_spell_checker(self._checker)

	def enable(self):
		self._gspell_view.set_inline_spell_checking(True)
		self._gspell_view.set_enable_language_menu(True)
		
	def disable(self):
		self._gspell_view.set_inline_spell_checking(False)
		self._gspell_view.set_enable_language_menu(False)

	def teardown(self):
		self.disable() # No real teardown (?)

