# -*- coding: utf-8 -*-

# Copyright 2009-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import gobject
import gtk

import logging

from zim.plugins import PluginClass, WindowExtension, extends
from zim.config import data_file, ConfigManager
from zim.main import GtkCommand
from zim.signals import SignalEmitter
from zim.notebook import get_notebook_list, NotebookInfo, NotebookInfoList


# Try if we are on Ubunutu with app-indicator support
try:
    import appindicator
except ImportError:
    appindicator = None


logger = logging.getLogger('zim.plugins.trayicon')


from zim.main import ZIM_APPLICATION


GLOBAL_TRAYICON = None
# The trayicon is global because you should only have one per process
# so in a sense it is an external resource represented by a global
# state.


def set_global_trayicon(classic=False):
    global GLOBAL_TRAYICON

    if appindicator and not classic:
        cls = AppIndicatorTrayIcon
    else:
        cls = StatusIconTrayIcon

    if GLOBAL_TRAYICON and isinstance(GLOBAL_TRAYICON, cls):
        pass
    else:
        new = cls()
        ZIM_APPLICATION.add_window(new)
        if GLOBAL_TRAYICON:
            GLOBAL_TRAYICON.destroy()
        GLOBAL_TRAYICON = new


class TrayIconPluginCommand(GtkCommand):
    '''Class to handle "zim --plugin trayicon" allows starting zim in
    the background and only show a trayicon
    '''

    def run(self):
        config = ConfigManager()
        preferences = config.get_config_dict('preferences.conf')['TrayIconPlugin']
        preferences.setdefault('classic', False)

        set_global_trayicon(preferences['classic'])


class TrayIconPlugin(PluginClass):

    plugin_info = {
            'name': _('Tray Icon'),  # T: plugin name
            'description': _('''\
This plugin adds a tray icon for quick access.

This plugin depends on Gtk+ version 2.10 or newer.

This is a core plugin shipping with zim.
'''),  # T: plugin description
            'author': 'Jaap Karssenberg',
            'help': 'Plugins:Tray Icon',
    }

    plugin_preferences = (
            # key, type, label, default
            ('classic', 'bool', _('Classic trayicon,\ndo not use new style status icon on Ubuntu'), False),  # T: preferences option
            ('standalone', 'bool', _('Show a separate icon for each notebook'), False),  # T: preferences option
    )

    @classmethod
    def check_dependencies(klass):
        version_ok = (gtk.gtk_version >= (2, 10, 0) and gtk.pygtk_version >= (2, 10, 0))
        return (version_ok, [
                ('GTK >= 2.10', version_ok, True),
                ('Unity appindicator', bool(appindicator), False),
        ])

    def __init__(self, config=None):
        PluginClass.__init__(self, config)
        self.preferences.connect('changed', self.on_preferences_changed)

    def on_preferences_changed(self, preferences):
        if GLOBAL_TRAYICON:
            # Only refresh once someone else loaded it
            self.load_trayicon()

    def load_trayicon(self):
        set_global_trayicon(self.preferences['classic'])


@extends('MainWindow')
class TrayIconMainWindowExtension(WindowExtension):

    def __init__(self, plugin, window):
        WindowExtension.__init__(self, plugin, window)
        self.window.ui.hideonclose = True  # XXX
        plugin.load_trayicon()

    def teardown(self):
        global GLOBAL_TRAYICON
        self.window.ui.hideonclose = False  # XXX
        if GLOBAL_TRAYICON:
            GLOBAL_TRAYICON.destroy()
            GLOBAL_TRAYICON = None


class TrayIconBase(object):
    '''Base class for the zim tray icon.
    Contains code to create the tray icon menus.
    '''

    def get_trayicon_menu(self):
        '''Returns the main 'tray icon menu'''
        menu = gtk.Menu()

        item = gtk.MenuItem(_('_Quick Note...'))  # T: menu item in tray icon menu
        item.connect_object('activate', self.__class__.do_quick_note, self)
        menu.append(item)

        menu.append(gtk.SeparatorMenuItem())

        notebooks = self.list_all_notebooks()
        self.populate_menu_with_notebooks(menu, notebooks)

        item = gtk.MenuItem('  ' + _('_Other...'))  # Hack - using '  ' to indent visually
        # T: menu item in tray icon menu
        item.connect_object('activate', self.__class__.do_open_notebook, self)
        menu.append(item)

        menu.append(gtk.SeparatorMenuItem())

        item = gtk.MenuItem(_('_Quit'))  # T: menu item in tray icon menu
        item.connect_object('activate', self.__class__.do_quit, self)
        menu.append(item)

        return menu

    def list_open_notebooks(self):
        '''Returns a list of open notebook.

        This method is to be implemented in child classes.

        @returns: a list of L{NotebookInfo} objects
        '''
        return []  # TODO
        #~ for uri in self.server.list_notebooks():
        #~ info = NotebookInfo(uri)
        #~ info.active = True
        #~ yield info

    def list_all_notebooks(self):
        '''Returns a list of all notebooks known in the current context

        This method mixes notebooks from L{list_open_notebooks()} with
        input from L{get_notebook_list()}. Open notebooks will have
        the C{active} attribute set.

        @returns: a list of L{NotebookInfo} objects
        '''
        uris = set()
        notebooks = [info for info in get_notebook_list()]
        for info in self.list_open_notebooks():
            if info in notebooks:
                # info from notebook list is updated already
                i = notebooks.index(info)
                notebooks[i].active = True
            else:
                info.update()
                info.active = True
                notebooks.append(info)

        for info in notebooks:
            if not info.active:
                info.active = False  # None -> False

        return notebooks

    def populate_menu_with_notebooks(self, menu, notebooks):
        '''Populate a menu with a list of notebooks'''
        # TODO put checkbox behind open notebooks ?
        item = gtk.MenuItem(_('Notebooks'))  # T: menu item in tray icon menu
        item.set_sensitive(False)
        menu.append(item)

        if isinstance(notebooks, NotebookInfoList):
            notebooks = [info for info in notebooks]  # copy

        notebooks.sort(key=lambda info: info.name)

        for info in notebooks:
            #~ print '>>>', info
            item = gtk.MenuItem('  ' + info.name)
            # Hack - using '  ' to indent visually
            if info.active:
                child = item.get_child()
                if isinstance(child, gtk.Label):
                    # FIXME this doesn't seem to work in Ubuntu menu :(
                    child.set_markup('  <b>' + info.name + '</b>')
                    # Hack - using '  ' to indent visually
            item.connect('activate', lambda o, u: self.do_activate_notebook(u), info.uri)
            menu.append(item)

    def do_activate_notebook(self, uri):
        '''Open a specific notebook.'''
        ZIM_APPLICATION.run('--gui', uri)

    def do_quit(self):
        '''Quit zim.'''
        if gtk.main_level() > 0:
            gtk.main_quit()

    def do_open_notebook(self):
        '''Opens the notebook dialogs'''
        from zim.gui.notebookdialog import NotebookDialog
        NotebookDialog.unique(self, None, callback=self.do_activate_notebook).show()

    def do_quick_note(self):
        '''Show the dialog from the quicknote plugin'''
        ZIM_APPLICATION.run('--plugin', 'quicknote')


class StatusIconTrayIcon(TrayIconBase, gtk.StatusIcon):
    '''Base class for a tray icon based on gtk.StatusIcon'''

    __gsignals__ = {
            'destroy': (gobject.SIGNAL_RUN_LAST, None, ())
    }

    def __init__(self):
        gtk.StatusIcon.__init__(self)

        icon_theme = gtk.icon_theme_get_default()
        if icon_theme.has_icon('zim-panel'):
            self.set_from_icon_name('zim-panel')
        else:
            icon = data_file('zim.png').path
            self.set_from_file(icon)

        self.set_tooltip(_('Zim Desktop Wiki'))  # T: tooltip for tray icon
        self.connect('popup-menu', self.__class__.do_popup_menu)

    def do_activate(self):
        open_notebooks = list(self.list_open_notebooks())
        if len(open_notebooks) == 0:
            # No open notebooks, open default or prompt full list
            notebooks = get_notebook_list()
            if notebooks.default:
                self.do_activate_notebook(notebooks.default.uri)
            else:
                self.do_popup_menu_notebooks(notebooks)
        elif len(open_notebooks) == 1:
            # Only one open notebook - present it
            self.do_activate_notebook(open_notebooks[0].uri)
        else:
            # Let the user choose from the open notebooks
            self.do_popup_menu_notebooks(open_notebooks)

    def do_popup_menu_notebooks(self, list, button=1, activate_time=0):
        menu = gtk.Menu()
        self.populate_menu_with_notebooks(menu, list)
        menu.show_all()
        menu.popup(None, None, gtk.status_icon_position_menu, button, activate_time, self)

    def do_popup_menu(self, button=3, activate_time=0):
        #~ print '>>', button, activate_time
        menu = self.get_trayicon_menu()
        menu.show_all()
        menu.popup(None, None, gtk.status_icon_position_menu, button, activate_time, self)

    def destroy(self):
        self.set_property('visible', False)
        self.emit('destroy')

# Need to register classes overriding gobject signals
gobject.type_register(StatusIconTrayIcon)


_GLOBAL_INDICATOR = None
# This item is global, because if we create one, we can not detroy it
# again and it remains active in the desktop as an external resource


class AppIndicatorTrayIcon(TrayIconBase, SignalEmitter):
    '''Trayicon using the daemon and based on appindicator'''

    __signals__ = {
            'destroy': (None, None, ())
    }

    def __init__(self):
        # Note that even though we specify the icon "zim", the
        # ubuntu appindicator framework will first check for an icon
        # "zim-panel". This way it finds the mono color icons.
        global _GLOBAL_INDICATOR

        if not _GLOBAL_INDICATOR:
            _GLOBAL_INDICATOR = appindicator.Indicator(
                    'zim-desktop-wiki', 'zim',
                    appindicator.CATEGORY_APPLICATION_STATUS
            )

        self.appindicator = _GLOBAL_INDICATOR
        self.appindicator.set_status(appindicator.STATUS_ACTIVE)
        self.on_notebook_list_changed()

    def on_notebook_list_changed(self):  # TODO connect somewhere
        menu = self.get_trayicon_menu()
        menu.show_all()
        self.appindicator.set_menu(menu)

    def destroy(self):
        self.appindicator.set_status(appindicator.STATUS_PASSIVE)
        self.emit('destroy')
