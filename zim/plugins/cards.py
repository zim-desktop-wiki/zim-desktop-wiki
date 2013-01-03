# -*- coding: utf-8 -*-

# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import gtk
import pango
import re

from zim.plugins import PluginClass
from zim.objectmanager import ObjectManager, CustomObjectClass
from zim.gui.pageview import CustomObjectBin, POSITION_BEGIN, POSITION_END
from zim.gui.widgets import InputForm, encode_markup_text, ScrolledWindow

OBJECT_TYPE = 'card'

#~ ui_xml = '''
#~ <ui>
#~ <menubar name='menubar'>
	#~ <menu action='insert_menu'>
		#~ <placeholder name='plugin_items'>
			#~ <menuitem action='insert_sourceview'/>
		#~ </placeholder>
	#~ </menu>
#~ </menubar>
#~ </ui>
#~ '''

#~ ui_actions = (
	#~ # name, stock id, label, accelerator, tooltip, readonly
	#~ ('insert_sourceview', None, _('Code Block'), None, '', False), # T: menu item
#~ )


ABBREVIATIONS = {
	'p': 'page',
	's': 'string',
}


class CardObject(CustomObjectClass):

	_field_re = re.compile(r'^(:([\w\-]+)\s*((?:\(\w+\))?)\s*:)((?:\s+.*)?)')
		# name can contain letter, number or "-"
		# type can only contain letter and is optional
	#~ _continue_re = re.compile('^(\s+)(?=\S)')

	def __init__(self, attrib, text, ui=None):
		CustomObjectClass.__init__(self, attrib, text, ui)
		self.attrib = attrib
		self.inputs = ()
		self.values = {}
		self.definitions = {}
		self._text = text
		self.parse(text)

	def get_widget(self):
		return CardWidget(self)

	def get_attrib(self):
		return self.attrib

	def get_data(self):
		return self._text

	def parse(self, text):
		inputs = []
		values = {}
		definitions = {}
		for line in text.splitlines():
			match = self._field_re.match(line)
			if match:
				#~ print 'MATCH', match.groups()
				definition, name, type, value = match.groups()
				value = value.strip()
				if type:
					type = type.strip('()')
					type = ABBREVIATIONS.get(type, type)
					# FIXME test we are robust for unknown types - default to string ?
				else:
					type = 'string'
				inputs.append((name, type, name))
				definitions[name] = definition
				values[name] = value
			else:
				#~ print 'SKIP', line
				pass # FIXME - error ? pass on literal string ?

		self.inputs = self.inputs + tuple(inputs)
		self.values.update(values)
		self.definitions.update(definitions)


class CardWidget(CustomObjectBin):

	def __init__(self, object):
		CustomObjectBin.__init__(self)

		vbox = gtk.VBox()
		vbox.set_border_width(5)
		self.add(ScrolledWindow(vbox, gtk.POLICY_NEVER, gtk.POLICY_NEVER, gtk.SHADOW_OUT))
			# We just want the shadow, not the scroll bars ...

		label = gtk.Label()
		type = object.attrib.get('type', _('Card'))
		label.set_markup('<i>%s</i>' % encode_markup_text(type))
		label.set_alignment(0.0, 0.5)
		vbox.pack_start(label, False)

		## TODO, next to label icon for editing source of the card
		## maybe another button to bring up a search for all cards
		## of this type ?

		self.form = CardInputForm(
			self._update_text,
			object.inputs,
			values=object.values,
			notebook=object.ui.notebook
		)
		self.form.set_border_width(0) # Make it flush with label
		vbox.add(self.form)

		## TODO connect to 'last-activated' and push cursor outside
		## of form

		## TODO connect to signal to allow cursor to move into the form

		self.object = object

	def _update_text(self, form):
		text = []
		for input in self.object.inputs:
			name = input[0]
			definition = self.object.definitions[name]
			value = unicode(form[name])
			line = definition + ' ' + unicode(value) + '\n'
			text.append(line)

		self.object._text = ''.join(text)

	def set_values(self, values):
		pass

	def get_values(self):
		pass


class CardsPlugin(PluginClass):

	plugin_info = {
		'name': _('Cards'), # T: plugin name
		'description': _('''\
This plugin allows inserting forms with structured (meta-)data.
Effectivly turning a wiki page into a card with structured data.
'''), # T: plugin description
		'author': 'Jaap Karssenberg',
		'help': 'Plugins:Cards',
		'object_types': (OBJECT_TYPE, ),
	}

	#~ plugin_preferences = (
		#~ # key, type, label, default
	#~ )

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		ObjectManager.register_object(OBJECT_TYPE, self.create_object)

	def finalize_notebook(self, notebook):
		# This is done regardsless of the ui type of the application
		self.index = notebook.index
		self.index.connect('page-indexed', self.index_page)
		# Since we only use existing index tables like 'links' and
		# 'properties' we don't need to initialize, cleanup etc.
		# Just index the cards in the page

	def index_page(self, index, path, page):
		pass
		#~ parsetree = page.get_parsetree()
		#~ if not parsetree:
			#~ return

		#~ for object in parsetree.get_objects(OBJECT_TYPE):
			#~ print 'INDEX', object
			#~ prefix = 'card.'
			#~ if 'type' in object.attrib:
				#~ prefix += object.attrib['type'] + '.'

			#~ for input in object.inputs:
				#~ if input[1] == 'page':
					#~ # Index links
					#~ pass
				#~ else:
					#~ # Index properties
					#~ value = object.values.get(input[0])
					#~ if value is not None:
						#~ prefix + input[0]
						#~ index.add_property(page, property, value)

	def create_object(self, attrib, text, ui=None):
		'''Factory method for SourceViewObject objects'''
		obj = CardObject(attrib, text, ui)
		#~ obj.set_preferences(self.preferences)
		return obj

	#~ def do_preferences_changed(self):
		#~ '''Update preferences on open objects'''
		#~ for obj in ObjectManager.get_active_objects(OBJECT_TYPE):
			#~ obj.set_preferences(self.preferences)

	#~ def initialize_ui(self, ui):
		#~ if self.ui.ui_type == 'gtk':
			#~ self.ui.add_actions(ui_actions, self)
			#~ self.ui.add_ui(ui_xml, self)

	def disconnect(self):
		ObjectManager.unregister_object(OBJECT_TYPE)
		PluginClass.disconnect(self)

	#~ def insert_sourceview(self):
		#~ '''Inserts new SourceView'''
		#~ lang = InsertCodeBlockDialog(self.ui).run()
		#~ if not lang:
			#~ return # dialog cancelled
		#~ else:
			#~ obj = SourceViewObject({'type': OBJECT_TYPE, 'lang': lang}, '', self.ui)
			#~ pageview = self.ui.mainwindow.pageview
			#~ pageview.insert_object(pageview.view.get_buffer(), obj)


#~ class InsertCodeBlockDialog(Dialog):
#~
	#~ def __init__(self, ui):
		#~ Dialog.__init__(self, ui, _('Insert Code Block')) # T: dialog title
		#~ names = sorted(LANGUAGES, key=lambda k: k.lower())
		#~ self.add_form(
			#~ (('lang', 'choice', _('Syntax'), names),) # T: input label
		#~ )
#~
		#~ # Set previous used language
		#~ if 'lang' in self.uistate:
			#~ for name, id in LANGUAGES.items():
				#~ if self.uistate['lang'] == id:
					#~ try:
						#~ self.form['lang'] = name
					#~ except ValueError:
						#~ pass
#~
					#~ break
#~
	#~ def do_response_ok(self):
		#~ name = self.form['lang']
		#~ self.result = LANGUAGES[name]
		#~ self.uistate['lang'] = LANGUAGES[name]
		#~ return True


class CardInputForm(InputForm):
	## Bit of a hack to know when the user changes the form ....

	def __init__(self, callback, *arg, **kwarg):
		InputForm.__init__(self, *arg, **kwarg)
		self.callback = callback

	def on_activate_widget(self, widget):
		InputForm.on_activate_widget(self, widget)
		self.callback(self)
