# -*- coding: utf-8 -*-

# Copyright 2013-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Action interface classes.

Objects can have "actions", which are basically attributes of the
class L{Action} or L{ToggleAction}. These objects are callable as bound
methods. So actions are kind of special methods that define some
interface parameters, like what icon and label to use in the menu.

Use the L{action} and L{toggle_action} decorators to create actions.

There is no direct relation with the C{gtk.Action} and C{gtk.ToggleAction}
classes, but it can cooperate with these classes and use them as proxies.
'''

import inspect
import weakref
import logging
import re

import zim.errors

logger = logging.getLogger('zim')


# We want to switch between <Control> for linux and windows and
# <Command> for OS X. The gtk solution is to use the abstract <Primary>
# modifier key. Unfortunately, this is not supported in gtk before
# version gtk_version 2.24.7. Therefore we try to detect whether this
# abstract key is supported or not, and if not, we fall back to <Control>.
#
# Secondary use of the PRIMARY_MODIFIER constant is that it can be
# shown in user menus.

_accelerator_preparse_re = re.compile('(?i)<Primary>')


def gtk_accelerator_preparse(code, force=False):
    '''Pre-parse the accelerator code to change <Primary> into
    <Control> or <Command> if <Primary> is not supported.
    @param code: accelerator code
    @param force: if C{True} <Primary> is replaced even if not needed
    @returns: same or modified accelerator code
    '''
    if not code:
        return code  # tolerate None ...

    m = _accelerator_preparse_re.search(code)
    if m:
        import gtk
        x, mod = gtk.accelerator_parse('<Primary>')
        if not mod:
            # <Primary> is not supported - anyway to detect OS X?
            return _accelerator_preparse_re.sub('<Control>', code)
        elif force:
            if mod == gtk.gdk.META_MASK:
                return _accelerator_preparse_re.sub('<Command>', code)
            else:
                return _accelerator_preparse_re.sub('<Control>', code)
        else:
            return code
    else:
        return code

try:
    import gtk
    PRIMARY_MODIFIER_STRING = gtk_accelerator_preparse('<primary>', force=True)
    PRIMARY_MODIFIER_MASK = gtk.gdk.META_MASK if PRIMARY_MODIFIER_STRING == '<Command>' else gtk.gdk.CONTROL_MASK
except ImportError:
    PRIMARY_MODIFIER_STRING = None
    PRIMARY_MODIFIER_MASK = None


# FIXME - temporary helper method - remove it again when all users are refactored
def gtk_accelerator_preparse_list(actions):
    myactions = []
    for action in actions:
        if len(action) > 3:
            a = list(action)
            a[3] = gtk_accelerator_preparse(a[3])
            action = tuple(a)
        myactions.append(action)
    return myactions


class ActionMethod(object):
    pass


def action(label, stock=None, accelerator='', tooltip='', readonly=True, alt_accelerator=None):
    '''Decorator to turn a method into an L{Action} object
    Methods decorated with this decorator can have keyword arguments
    but no positional arguments.
    @param label: the label used e.g for the menu item
    @param stock: stock item to define the icon
    @param accelerator: accelerator key description
    @param tooltip: tooltip text, if C{None} will default to C{label}
    @param readonly: if C{True} this action should also be available
    for readonly notebooks
    @param alt_accelerator: alternative accelerator key binding
    '''
    # TODO see where "readonly" should go
    def _action(function):
        return Action(function.__name__, function, label, stock, accelerator, tooltip, readonly, alt_accelerator)

    return _action


class Action(ActionMethod):
    '''Action, used by the L{action} decorator'''

    def __init__(self, name, func, label, stock=None, accelerator='', tooltip='', readonly=True, alt_accelerator=None):
        assert not (stock and '<' in stock), 'Looks like stock contains accelerator: %s %s' % (name, stock)
        assert self._assert_args(func), '%s() has incompatible argspec' % func.__name__
        if not tooltip:
            tooltip = label.replace('_', '')

        self.name = name
        self.readonly = readonly
        self.func = func
        self._attr = (self.name, label, tooltip, stock)
        self._alt_attr = (self.name + '_alt1', label, tooltip, stock)
        self._accel = gtk_accelerator_preparse(accelerator)
        self._alt_accel = gtk_accelerator_preparse(alt_accelerator)

    def _assert_args(self, func):
        args, varargs, keywords, defaults = inspect.getargspec(func)
        if defaults:
            return len(defaults) == len(args) - 1  # -1 for "self"
        else:
            return len(args) == 1  # self

    def __get__(self, instance, klass):
        if instance is None:
            return self  # class access

        # instance acces, return bound method
        def func(*args, **kwargs):
            self.func(instance, *args, **kwargs)

        return func

    def connect_actionable(self, instance, actionable):
        '''Connect a C{gtk.Action} or C{gtk.Button} to this action.
        @param instance: the object instance that owns this action
        @param actionable: proxy object, needs to have methods
        C{set_active(is_active)} and C{get_active()} and a signal
        'C{activate}'.
        '''
        actionable.connect('activate', self.do_activate, instance)

    def do_activate(self, actionable, instance):
        '''Callback for activate signal of connected objects'''
        logger.debug('Action: %s', self.name)
        try:
            self.__get__(instance, instance.__class__)()
        except:
            zim.errors.exception_handler(
                'Exception during action: %s' % self.name)


def toggle_action(label, stock=None, accelerator='', tooltip='', readonly=True, init=False):
    '''Decorator to turn a method into an L{ToggleAction} object

    The decorated method should be defined as:
    C{my_toggle_method(self, active)}. The 'C{active}' parameter is a
    boolean that reflects the new state of the toggle.

    Users can also call the method without setting the C{active}
    parameter. In this case the wrapper determines how to toggle the
    state and calls the inner function with the new state.

    @param label: the label used e.g for the menu item
    @param stock: stock item to define the icon
    @param accelerator: accelerator key description
    @param tooltip: tooltip text, if C{None} will default to C{label}
    @param readonly: if C{True} this action should also be available
    for readonly notebooks
    @param init: initial state of the toggle
    '''
    # TODO see where "readonly" should go
    def _toggle_action(function):
        return ToggleAction(function.__name__, function, label, stock, accelerator, tooltip, readonly, init)

    return _toggle_action


class ToggleAction(Action):
    '''Toggle action, used by the L{toggle_action} decorator'''

    def __init__(self, name, func, label, stock=None, accelerator='', tooltip='', readonly=True, init=False):
        # The ToggleAction instance lives in the client class object;
        # using weakkeydict to store instance attributes per
        # client object
        Action.__init__(self, name, func, label, stock, accelerator, tooltip, readonly)
        self._init = init
        self._state = weakref.WeakKeyDictionary()
        self._proxies = weakref.WeakKeyDictionary()

    def _assert_args(self, func):
        args, varargs, keywords, defaults = inspect.getargspec(func)
        return len(args) == 2  # (self, active)

    def __get__(self, instance, klass):
        if instance is None:
            return self  # class access

        if not instance in self._state:
            self._state[instance] = self._init

        # instance acces, return bound method
        def func(active=None):
            if active is None:
                active = not self._state[instance]
            elif active == self._state[instance]:
                return  # nothing to do

            self.func(instance, active)

            # Update state and notify actionables
            self._state[instance] = active
            for actionable in self._proxies.get(instance, []):
                actionable.set_active(active)

        return func

    def connect_actionable(self, instance, actionable):
        '''Connect a C{gtk.ToggleAction} or C{gtk.ToggleButton} to this action.
        @param instance: the object instance that owns this action
        @param actionable: proxy object, needs to have methods
        C{set_active(is_active)} and C{get_active()} and a signal
        'C{toggled}'.
        '''
        actionable.set_active(self._state.get(instance, self._init))
        actionable.connect('toggled', self.do_activate, instance)

        if not instance in self._proxies:
            self._proxies[instance] = []
        self._proxies[instance].append(actionable)

    def do_activate(self, actionable, instance):
        '''Callback for activate signal of connected objects'''
        active = actionable.get_active()
        if active != self._state.get(instance, self._init):
            logger.debug('Action: %s(%s)', self.name, active)
            try:
                self.__get__(instance, instance.__class__)()
            except Exception as error:
                zim.errors.exception_handler(
                    'Exception during toggle action: %s(%s)' % (self.name, active))


def radio_action(*radio_options):
    def _action(function):
        return RadioAction(function.__name__, function, radio_options)

    return _action


def radio_option(key, label, stock=None, accelerator='', tooltip=''):
    return (key, stock, label, accelerator, tooltip)
    # switching stock & label to match actiongroup.add_radio_actions()


def gtk_radioaction_set_current(g_radio_action, key):
    # gtk.radioaction.set_current is gtk >= 2.10
    for a in g_radio_action.get_group():
        if a.get_name().endswith('_' + key):
            a.activate()
            break


class RadioAction(ActionMethod):

    def __init__(self, name, func, radio_options):
        # The RadioAction instance lives in the client class object;
        # using weakkeydict to store instance attributes per
        # client object
        self.name = name
        self.func = func
        self.keys = [opt[0] for opt in radio_options]
        self._entries = tuple(
            (name + '_' + opt[0],) + opt[1:] + (i,)
            for i, opt in enumerate(radio_options)
        )
        self._state = weakref.WeakKeyDictionary()
        self._proxies = weakref.WeakKeyDictionary()

    def _assert_args(self, func):
        args, varargs, keywords, defaults = inspect.getargspec(func)
        return len(args) == 2  # (self, key)

    def __get__(self, instance, klass):
        if instance is None:
            return self  # class access

        # instance acces, return bound method
        def func(key):
            if not key in self.keys:
                raise ValueError('Invalid key: %s' % key)
            self.func(instance, key)

            # Update state and notify actionables
            self._state[instance] = key
            for actionable in self._proxies.get(instance, []):
                gtk_radioaction_set_current(actionable, key)

        return func

    def do_changed(self, gaction, current, instance):
        '''Callback for activate signal of connected objects'''
        try:
            name = current.get_name()
            assert name.startswith(self.name + '_')
            key = name[len(self.name) + 1:]
            if instance in self._state and key == self._state[instance]:
                pass
            else:
                logger.debug('Action: %s(%s)', self.name, key)
                self.__get__(instance, instance.__class__)(key)
        except:
            zim.errors.exception_handler(
                'Exception during action: %s(%s)' % (self.name, key))


def get_gtk_actiongroup(obj):
    '''Return a C{gtk.ActionGroup} for an object using L{Action}
    objects as attributes.

    Defines the attribute C{obj.actiongroup} if it does not yet exist.

    This method can only be used when gtk is available
    '''
    import gtk

    if hasattr(obj, 'actiongroup') \
            and obj.actiongroup is not None:
        return obj.actiongroup

    obj.actiongroup = gtk.ActionGroup(obj.__class__.__name__)

    for name, action in inspect.getmembers(obj.__class__, lambda m: isinstance(m, ActionMethod)):
        if isinstance(action, RadioAction):
            obj.actiongroup.add_radio_actions(action._entries)
            gaction = obj.actiongroup.get_action(action._entries[0][0])
            gaction.connect('changed', action.do_changed, obj)
            if not obj in action._proxies:
                action._proxies[obj] = []
            action._proxies[obj].append(gaction)
            if obj in action._state:
                key = action._state[obj]
                gtk_radioaction_set_current(gaction, key)
        else:
            _gtk_add_action_with_accel(obj, obj.actiongroup, action, action._attr, action._accel)
            if action._alt_accel:
                _gtk_add_action_with_accel(obj, obj.actiongroup, action, action._alt_attr, action._alt_accel)

    return obj.actiongroup


def _gtk_add_action_with_accel(obj, actiongroup, action, attr, accel):
    import gtk

    if isinstance(action, ToggleAction):
        gaction = gtk.ToggleAction(*attr)
    else:
        gaction = gtk.Action(*attr)

    gaction.zim_readonly = action.readonly  # HACK
    action.connect_actionable(obj, gaction)
    actiongroup.add_action_with_accel(gaction, accel)
