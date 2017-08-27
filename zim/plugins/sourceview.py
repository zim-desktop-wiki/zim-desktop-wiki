# -*- coding: utf-8 -*-

# Copyright 2011 Jiří Janoušek <janousek.jiri@gmail.com>
# Copyright 2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# This plugin can work without GUI for just the export
# Be nice about gtk, since it may not be present in a server CLI only version
try:
    import gtk
    import pango
except:
    gtk = None

try:
    from zim.gui.widgets import Dialog, ScrolledWindow
    from zim.gui.objectmanager import CustomObjectWidget, TextViewWidget
except:
    class Dialog():
        pass

    class TextViewWidget():
        pass

import logging

logger = logging.getLogger('zim.pugin.sourceview')

try:
    import gtksourceview2
except:
    gtksourceview2 = None

from zim.plugins import PluginClass, WindowExtension, extends
from zim.actions import action
from zim.utils import WeakSet
from zim.objectmanager import ObjectManager, CustomObjectClass
from zim.config import String, Boolean
from zim.formats.html import html_encode

if gtksourceview2:
    lm = gtksourceview2.LanguageManager()
    lang_ids = lm.get_language_ids()
    lang_names = [lm.get_language(i).get_name() for i in lang_ids]

    LANGUAGES = dict((lm.get_language(i).get_name(), i) for i in lang_ids)
else:
    LANGUAGES = {}
#~ print LANGUAGES

OBJECT_TYPE = 'code'


class SourceViewPlugin(PluginClass):

    plugin_info = {
        'name': _('Source View'),  # T: plugin name
        'description': _('''\
This plugin allows inserting 'Code Blocks' in the page. These will be
shown as emdedded widgets with syntax highlighting, line numbers etc.
'''),  # T: plugin description
        'author': 'Jiří Janoušek',
        'help': 'Plugins:Source View',
        'object_types': (OBJECT_TYPE, ),
    }

    plugin_preferences = (
        # key, type, label, default
        ('auto_indent', 'bool', _('Auto indenting'), True),
        # T: preference option for sourceview plugin
        ('smart_home_end', 'bool', _('Smart Home key'), True),
        # T: preference option for sourceview plugin
        ('highlight_current_line', 'bool', _('Highlight current line'), False),
        # T: preference option for sourceview plugin
        ('show_right_margin', 'bool', _('Show right margin'), False),
        # T: preference option for sourceview plugin
        ('right_margin_position', 'int', _('Right margin position'), 72, (1, 1000)),
        # T: preference option for sourceview plugin
        ('tab_width', 'int', _('Tab width'), 4, (1, 80)),
        # T: preference option for sourceview plugin
    )

    @classmethod
    def check_dependencies(klass):
        check = gtk is None or not gtksourceview2 is None
        return check, [('gtksourceview2', check, True)]

    def __init__(self, config=None):
        PluginClass.__init__(self, config)
        ObjectManager.register_object(OBJECT_TYPE, self.create_object)  # register the plugin in the main init so it works for a non-gui export
        self.connectto(self.preferences, 'changed', self.on_preferences_changed)

    def teardown(self):
        ObjectManager.unregister_object(OBJECT_TYPE)

    def create_object(self, attrib, text):
        '''Factory method for SourceViewObject objects'''
        obj = SourceViewObject(attrib, text, self.preferences)
        return obj

    def on_preferences_changed(self, preferences):
        '''Update preferences on open objects'''
        for obj in ObjectManager.get_active_objects(OBJECT_TYPE):
            obj.preferences_changed()


@extends('MainWindow')
class MainWindowExtension(WindowExtension):

    uimanager_xml = '''
		<ui>
		<menubar name='menubar'>
			<menu action='insert_menu'>
				<placeholder name='plugin_items'>
					<menuitem action='insert_sourceview'/>
				</placeholder>
			</menu>
		</menubar>
		</ui>
	'''

    def __init__(self, plugin, window):
        WindowExtension.__init__(self, plugin, window)

    @action(_('Code Block'), readonly=False)  # T: menu item
    def insert_sourceview(self):
        '''Inserts new SourceView'''
        lang = InsertCodeBlockDialog(self.window.ui).run()  # XXX
        if not lang:
            return  # dialog cancelled
        else:
            obj = self.plugin.create_object({'type': OBJECT_TYPE, 'lang': lang}, '')
            pageview = self.window.pageview  # XXX
            pageview.insert_object(obj)


class InsertCodeBlockDialog(Dialog):

    def __init__(self, ui):
        Dialog.__init__(self, ui, _('Insert Code Block'))  # T: dialog title
        names = sorted(LANGUAGES, key=lambda k: k.lower())
        self.add_form(
            (('lang', 'choice', _('Syntax'), names),)  # T: input label
        )

        # Set previous used language
        self.uistate.define(lang=String(None))
        if 'lang' in self.uistate:
            for name, id in LANGUAGES.items():
                if self.uistate['lang'] == id:
                    try:
                        self.form['lang'] = name
                    except ValueError:
                        pass

                    break

    def do_response_ok(self):
        name = self.form['lang']
        if name:
            self.result = LANGUAGES[name]
            self.uistate['lang'] = LANGUAGES[name]
            return True
        else:
            return False  # no syntax selected


class SourceViewObject(CustomObjectClass):

    OBJECT_ATTR = {
        'type': String('code'),
        'lang': String(None),
        'linenumbers': Boolean(True),
    }

    def __init__(self, attrib, data, preferences):
        if data.endswith('\n'):
            data = data[:-1]
            # If we have trailing \n it looks like an extra empty line
            # in the buffer, so we default remove one
        CustomObjectClass.__init__(self, attrib, data)
        self.preferences = preferences
        self.buffer = None
        self._widgets = WeakSet()

    def get_widget(self):
        if not self.buffer:
            self.buffer = gtksourceview2.Buffer()
            self.buffer.set_text(self._data)
            self.buffer.connect('modified-changed', self.on_modified_changed)
            self.buffer.set_highlight_matching_brackets(True)
            self.buffer.set_modified(False)
            self._data = None

            try:
                if self._attrib['lang']:
                    self.buffer.set_language(lm.get_language(self._attrib['lang']))
            except:
                logger.exception('Could not set language for sourceview: %s', lang)

        widget = SourceViewWidget(self, self.buffer)
        self._widgets.add(widget)

        widget.view.set_show_line_numbers(self._attrib['linenumbers'])
        widget.set_preferences(self.preferences)
        return widget

    def preferences_changed(self):
        for widget in self._widgets:
            widget.set_preferences(self.preferences)

    def on_modified_changed(self, buffer):
        # Sourceview changed, set change on oject, reset state of
        # sourceview buffer so we get a new signal with next change
        if buffer.get_modified():
            self.set_modified(True)
            buffer.set_modified(False)

    def get_data(self):
        '''Returns data as text.'''
        if self.buffer:
            bounds = self.buffer.get_bounds()
            text = self.buffer.get_text(bounds[0], bounds[1])
            text += '\n'  # Make sure we always have a trailing \n
            return text
        else:
            return self._data

    def dump(self, format, dumper, linker=None):
        if format == "html":
            if self._attrib['lang']:
                ''' to use highlight.js add the following to your template:
                <link rel="stylesheet" href="http://cdnjs.cloudflare.com/ajax/libs/highlight.js/9.5.0/styles/default.min.css">
                <script src="http://cdnjs.cloudflare.com/ajax/libs/highlight.js/9.5.0/highlight.min.js"></script>
                <script>hljs.initHighlightingOnLoad();</script>
                Map GtkSourceView language ids match with Highlight.js language ids.
                http://packages.ubuntu.com/precise/all/libgtksourceview2.0-common/filelist
                http://highlightjs.readthedocs.io/en/latest/css-classes-reference.html
'''
                sh_map = {'dosbatch': 'dos'}
                sh_lang = sh_map[self._attrib['lang']] if self._attrib['lang'] in sh_map else self._attrib['lang']
                # TODO: some template instruction to be able to use other highlighters as well?
                output = ['<pre><code class="%s">' % html_encode(sh_lang)]  # for syntaxhigligther
                '''' class="brush: language;" works with SyntaxHighlighter 2.0.278, 3 & 4
				output = ['<pre class="brush: %s;">' % html_encode(sh_lang)] # for syntaxhigligther
				'''
            else:
                output = ['<pre>\n']
            data = self.get_data()
            data = html_encode(data)  # XXX currently dumper gives encoded lines - NOK
            # if self._attrib['linenumbers']:
            #	for i, l in enumerate(data.splitlines(1)):
            #		output.append('%i&nbsp;' % (i+1) + l)
            # else:
            output.append(data)  # ignoring numbering for html - syntaxhighlighter takes care of that
            if self._attrib['lang']:
                output.append('</code></pre>\n')
            else:
                output.append('</pre>\n')
            return output
        return CustomObjectClass.dump(self, format, dumper, linker)

    def set_language(self, lang):
        '''Set language in SourceView.'''
        self._attrib['lang'] = lang
        self.set_modified(True)

        if self.buffer:
            if lang is None:
                self.buffer.set_language(None)
            else:
                self.buffer.set_language(lm.get_language(lang))

    def show_line_numbers(self, show):
        '''Toggles line numbers in SourceView.'''
        self._attrib['linenumbers'] = show
        self.set_modified(True)

        for widget in self._widgets:
            widget.view.set_show_line_numbers(show)


class SourceViewWidget(TextViewWidget):

    def __init__(self, obj, buffer):
        CustomObjectWidget.__init__(self)
        self.set_has_cursor(True)
        self.buffer = buffer
        self.obj = obj

        self.view = gtksourceview2.View(self.buffer)
        self.view.modify_font(pango.FontDescription('monospace'))
        self.view.set_auto_indent(True)
        self.view.set_smart_home_end(True)
        self.view.set_highlight_current_line(True)
        self.view.set_right_margin_position(80)
        self.view.set_show_right_margin(True)
        self.view.set_tab_width(4)

        # simple toolbar
        #~ bar = gtk.HBox() # FIXME: use gtk.Toolbar stuff
        #~ lang_selector = gtk.combo_box_new_text()
        #~ lang_selector.append_text('(None)')
        #~ for l in lang_names: lang_selector.append_text(l)
        #~ try:
        #~ lang_selector.set_active(lang_ids.index(self._attrib['lang'])+1)
        #~ self.set_language(self._attrib['lang'] or None, False)
        #~ except (ValueError, KeyError):
        #~ lang_selector.set_active(0)
        #~ self.set_language(None, False)
        #~ lang_selector.connect('changed', self.on_lang_changed)
        #~ bar.pack_start(lang_selector, False, False)

        #~ line_numbers = gtk.ToggleButton('Line numbers')
        #~ try:
        #~ line_numbers.set_active(self._attrib['linenumbers']=='true')
        #~ self.show_line_numbers(self._attrib['linenumbers'], False)
        #~ except (ValueError, KeyError):
        #~ line_numbers.set_active(True)
        #~ self.show_line_numbers(True, False)
        #~ line_numbers.connect('toggled', self.on_line_numbers_toggled)
        #~ bar.pack_start(line_numbers, False, False)

        # TODO: other toolbar options
        # TODO: autohide toolbar if textbuffer is not active

        # Pack everything
        #~ self.vbox.pack_start(bar, False, False)
        win = ScrolledWindow(self.view, gtk.POLICY_AUTOMATIC, gtk.POLICY_NEVER, gtk.SHADOW_NONE)
        # only horizontal scroll
        self.vbox.pack_start(win)

        # Hook up signals
        self._init_signals()
        self.view.connect('populate-popup', self.on_populate_popup)

    def set_preferences(self, preferences):
        self.view.set_auto_indent(preferences['auto_indent'])
        self.view.set_smart_home_end(preferences['smart_home_end'])
        self.view.set_highlight_current_line(preferences['highlight_current_line'])
        self.view.set_right_margin_position(preferences['right_margin_position'])
        self.view.set_show_right_margin(preferences['show_right_margin'])
        self.view.set_tab_width(preferences['tab_width'])

    #~ def on_lang_changed(self, selector):
        #~ '''Callback for language selector'''
        #~ lang = selector.get_active()
        #~ self.set_language(lang_ids[lang-1] if lang>0 else '')

    #~ def on_line_numbers_toggled(self, button):
        #~ '''Callback for toggling line numbers.'''
        #~ self.show_line_numbers(button.get_active())

    def on_populate_popup(self, view, menu):
        menu.prepend(gtk.SeparatorMenuItem())

        def activate_linenumbers(item):
            self.obj.show_line_numbers(item.get_active())

        item = gtk.CheckMenuItem(_('Show Line Numbers'))
        # T: preference option for sourceview plugin
        item.set_active(self.obj._attrib['linenumbers'])
        item.set_sensitive(self.view.get_editable())
        item.connect_after('activate', activate_linenumbers)
        menu.prepend(item)

        def activate_lang(item):
            self.obj.set_language(item.zim_sourceview_languageid)

        item = gtk.MenuItem(_('Syntax'))
        item.set_sensitive(self.view.get_editable())
        submenu = gtk.Menu()
        for lang in sorted(LANGUAGES, key=lambda k: k.lower()):
            langitem = gtk.MenuItem(lang)
            langitem.connect('activate', activate_lang)
            langitem.zim_sourceview_languageid = LANGUAGES[lang]
            submenu.append(langitem)
        item.set_submenu(submenu)
        menu.prepend(item)

        menu.show_all()

    # TODO: undo(), redo() stuff
