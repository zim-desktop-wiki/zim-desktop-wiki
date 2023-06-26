
# Copyright 2008,2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Spell check plugin based on gtkspell'''

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

# Try which of the two bindings is available
try:
	gi.require_version('Gtk','3.0') # see issue #2301
	import gtkspellcheck
except ImportError:
	gtkspellcheck = None

	try:
		gi.require_version('GtkSpell', '3.0')
		from gi.repository import GtkSpell as gtkspell
	except:
		gtkspell = None
else:
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

	plugin_notebook_properties = (
		('language', 'string', 'Default Language', ''),
	)

	@classmethod
	def check_dependencies(klass):
		return bool(gtkspellcheck or gtkspell), [
			('gtkspellcheck', not gtkspellcheck is None, True),
			('gtkspell', not gtkspell is None, True)
		]


class SpellPageViewExtension(PageViewExtension):

	def __init__(self, plugin, pageview):
		PageViewExtension.__init__(self, plugin, pageview)

		properties = self.plugin.notebook_properties(self.pageview.notebook)
		self._language = properties['language']
		self.connectto(properties, 'changed', self.on_properties_changed)

		self._adapter_cls = self._choose_adapter_cls()
		self.uistate.setdefault('active', False)
		self.toggle_spellcheck(self.uistate['active'])
		self.connectto(self.pageview, 'page-changed', order=SIGNAL_AFTER)

	def on_properties_changed(self, properties):
		self._language = properties['language']
		textview = self.pageview.textview
		checker = getattr(textview, '_gtkspell', None)
		if checker:
			self.setup()

	def _choose_adapter_cls(self):
		if gtkspellcheck:
			version = tuple(
				map(int, re.findall('\d+', gtkspellcheck.__version__))
			)
			if version >= (4, 0, 3):
				return GtkspellcheckAdapter
			else:
				logger.warning(
					'Using gtkspellcheck %s. Versions before 4.0.3 might cause memory leak.',
					gtkspellcheck.__version__
				)
				return OldGtkspellcheckAdapter
		else:
			return GtkspellAdapter

	@toggle_action(_('Check _spelling'), accelerator='F7') # T: menu item
	def toggle_spellcheck(self, active):
		textview = self.pageview.textview
		checker = getattr(textview, '_gtkspell', None)

		if active:
			if checker:
				checker.enable()
			else:
				self.setup()
		elif not active:
			if checker:
				checker.disable()
			# else pass

		self.uistate['active'] = active

	def on_page_changed(self, pageview, page):
		textview = pageview.textview
		checker = getattr(textview, '_gtkspell', None)
		if checker:
			# A new buffer may be initialized, but it could also be an existing buffer linked to page
			checker.check_buffer_initialized()

	def setup(self):
		textview = self.pageview.textview
		lang = self._language or locale.getdefaultlocale()[0]
		logger.debug('Spellcheck language: %s', lang)
		try:
			checker = self._adapter_cls(textview, lang)
		except:
			ErrorDialog(self.pageview, (
				_('Could not load spell checking'),
					# T: error message
				_('This could mean you don\'t have the proper\ndictionaries installed')
					# T: error message explanation
			)).run()
		else:
			textview._gtkspell = checker

	def teardown(self):
		textview = self.pageview.textview
		if hasattr(textview, '_gtkspell') \
		and textview._gtkspell is not None:
			textview._gtkspell.detach()
			textview._gtkspell = None


class AdapterBase(ConnectorMixin, object):

	def on_begin_insert_tree(self, o, *a):
		self._checker.disable()

	def on_end_insert_tree(self, o, *a):
		self._checker.enable()


class GtkspellcheckAdapter(AdapterBase):

	def __init__(self, textview, lang):
		self._lang = lang
		self._textview = textview
		self._textbuffer = None
		self._checker = None
		self._active = False

		self.enable()

	def check_buffer_initialized(self):
		if self._checker and not self._check_tag_table():
			self._checker.buffer_initialize()

	def enable(self):
		if self._checker:
			self._checker.enable()
		else:
			self._clean_tag_table()
			self._checker = gtkspellcheck.SpellChecker(self._textview, self._lang)

		self._textbuffer = self._textview.get_buffer()
		self.connectto_all(self._textbuffer, ('begin-insert-tree', 'end-insert-tree'))
		self._active = True

	def disable(self):
		if self._checker:
			self._checker.disable()
			self.disconnect_from(self._textbuffer)
			self._textbuffer = None

		self._active = False

	def detach(self):
		if self._checker:
			self.disable()
			self._clean_tag_table()
			self._checker = None

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

	def check_buffer_initialized(self):
		if self._checker and not self._check_tag_table():
			# wanted to use checker.buffer_initialize() here,
			# but gives issue, see https://github.com/koehlma/pygtkspellcheck/issues/24
			if self._active:
				self.detach()
				self.enable()
			else:
				self.detach()


class GtkspellAdapter(AdapterBase):

	def __init__(self, textview, lang):
		self._lang = lang
		self._textview = textview
		self._textbuffer = None
		self._checker = None
		self.enable()

	def check_buffer_initialized(self):
		pass

	def enable(self):
		if not self._checker:
			self._checker = gtkspell.Checker()
			self._checker.set_language(self._lang)
			self._checker.attach(self._textview)
			self._textbuffer = self._textview.get_buffer()
			self.connectto_all(self._textbuffer, ('begin-insert-tree', 'end-insert-tree'))

	def disable(self):
		self.detach()

	def detach(self):
		if self._checker:
			self.disconnect_from(self._textbuffer)
			self._textbuffer = None
			self._checker.detach()
			self._checker = None
