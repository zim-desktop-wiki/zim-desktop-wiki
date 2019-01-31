
# Copyright 2013-2018 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Action interface classes.

Objects can have "actions", which are basically attributes of the
class L{Action} or L{ToggleAction}. These objects are callable as bound
methods. So actions are kind of special methods that define some
interface parameters, like what icon and label to use in the menu.

Use the L{action} and L{toggle_action} decorators to create actions.

There is no direct relation with the C{Gtk.Action} and C{Gtk.ToggleAction}
classes, but it can cooperate with these classes and use them as proxies.
'''

import inspect
import weakref
import logging
import re

import zim.errors

logger = logging.getLogger('zim')



def _get_modifier_mask():
	import gi
	gi.require_version('Gtk', '3.0')
	from gi.repository import Gtk
	x, mod = Gtk.accelerator_parse('<Primary>')
	return mod

PRIMARY_MODIFIER_STRING = '<Primary>'
PRIMARY_MODIFIER_MASK = _get_modifier_mask()


def hasaction(obj, actionname):
	'''Like C{hasattr} but for attributes that define an action'''
	actionname = actionname.replace('-', '_')
	return hasattr(obj.__class__, actionname) \
		and isinstance(getattr(obj.__class__, actionname), ActionMethod)


class ActionMethod(object):
	pass


def action(label, accelerator='', icon=None, verb_icon=None, menuhints='', alt_accelerator=None):
	'''Decorator to turn a method into an L{Action} object
	Methods decorated with this decorator can have keyword arguments
	but no positional arguments.
	@param label: the label used e.g for the menu item (can use "_" for mnemonics)
	@param accelerator: accelerator key description
	@param icon: name of a "noun" icon - used together with the label. Only use
	this for "things and places", not for actions or commands, and only if the
	icon makes the item easier to recognize.
	@param verb_icon: name of a "verb" icon - only used for compact menu views
	@param menuhints: string with hints for menu placement and sensitivity
	@param alt_accelerator: alternative accelerator key binding
	'''
	def _action(function):
		return Action(function.__name__, function, label, icon, verb_icon, accelerator, alt_accelerator, menuhints)

	return _action


class Action(ActionMethod):
	'''Action, used by the L{action} decorator'''

	def __init__(self, name, func, label, icon=None, verb_icon=None, accelerator='', alt_accelerator=None, menuhints=''):
		assert self._assert_args(func), '%s() has incompatible argspec' % func.__name__
		tooltip = label.replace('_', '')
		self.name = name
		self.func = func
		self._attr = (self.name, label, tooltip, icon or verb_icon)
		self._alt_attr = (self.name + '_alt1', label, tooltip, icon or verb_icon)
		self._accel = accelerator
		self._alt_accel = alt_accelerator
		self.icon = icon
		self.verb_icon = verb_icon
		self.menuhints = menuhints.split(':')

	def _assert_args(self, func):
		args, varargs, keywords, defaults = inspect.getargspec(func)
		if defaults:
			return len(defaults) == len(args) - 1 # -1 for "self"
		else:
			return len(args) == 1 # self

	def __get__(self, instance, klass):
		if instance is None:
			return self # class access

		# instance acces, return bound method
		def func(*args, **kwargs):
			return self.func(instance, *args, **kwargs)

		return func

	def connect_actionable(self, instance, actionable):
		'''Connect a C{Gtk.Action} or C{Gtk.Button} to this action.
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


def toggle_action(label, accelerator='', icon=None, verb_icon=None, init=False, menuhints=''):
	'''Decorator to turn a method into an L{ToggleAction} object

	The decorated method should be defined as:
	C{my_toggle_method(self, active)}. The 'C{active}' parameter is a
	boolean that reflects the new state of the toggle.

	Users can also call the method without setting the C{active}
	parameter. In this case the wrapper determines how to toggle the
	state and calls the inner function with the new state.

	@param label: the label used e.g for the menu item (can use "_" for mnemonics)
	@param accelerator: accelerator key description
	@param icon: name of a "noun" icon - used together with the label. Only use
	this for "things and places", not for actions or commands, and only if the
	icon makes the item easier to recognize.
	@param verb_icon: name of a "verb" icon - only used for compact menu views
	@param init: initial state of the toggle
	@param menuhints: string with hints for menu placement and sensitivity
	'''
	def _toggle_action(function):
		return ToggleAction(function.__name__, function, label, icon, verb_icon, accelerator, init, menuhints)

	return _toggle_action


class ToggleAction(Action):
	'''Toggle action, used by the L{toggle_action} decorator'''

	def __init__(self, name, func, label, icon=None, verb_icon=None, accelerator='', init=False, menuhints=''):
		# The ToggleAction instance lives in the client class object;
		# using weakkeydict to store instance attributes per
		# client object
		Action.__init__(self, name, func, label, icon, verb_icon, accelerator, menuhints=menuhints)
		self._init = init
		self._state = weakref.WeakKeyDictionary()
		self._proxies = weakref.WeakKeyDictionary()

	def _assert_args(self, func):
		args, varargs, keywords, defaults = inspect.getargspec(func)
		return len(args) == 2 # (self, active)

	def __get__(self, instance, klass):
		if instance is None:
			return self # class access

		if not instance in self._state:
			self._state[instance] = self._init

		# instance acces, return bound method
		def func(active=None):
			if active is None:
				active = not self._state[instance]
			elif active == self._state[instance]:
				return # nothing to do

			self.func(instance, active)

			# Update state and notify actionables
			self._state[instance] = active
			for actionable in self._proxies.get(instance, []):
				actionable.set_active(active)

		return func

	def connect_actionable(self, instance, actionable):
		'''Connect a C{Gtk.ToggleAction} or C{Gtk.ToggleButton} to this action.
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

	def get_toggleaction_state(self, instance):
		'''Get the state for C{instance}'''
		# TODO: this should be method on bound object
		return self._state.get(instance, self._init)

	def set_toggleaction_state(self, instance, active):
		'''Change state for C{instance} *without* calling the action'''
		# TODO: this should be method on bound object
		self._state[instance] = active
		for actionable in self._proxies.get(instance, []):
			actionable.set_active(active)


def radio_action(menulabel, *radio_options, menuhints=''):
	def _action(function):
		return RadioAction(function.__name__, function, menulabel, radio_options, menuhints)

	return _action


def radio_option(key, label, accelerator=''):
	tooltip = label.replace('_', '')
	return (key, None, label, accelerator, tooltip)
		# tuple must match spec for actiongroup.add_radio_actions()


def gtk_radioaction_set_current(g_radio_action, key):
	# Gtk.radioaction.set_current is gtk >= 2.10
	for a in g_radio_action.get_group():
		if a.get_name().endswith('_' + key):
			a.activate()
			break


class RadioAction(ActionMethod):

	def __init__(self, name, func, menulabel, radio_options, menuhints=''):
		# The RadioAction instance lives in the client class object;
		# using weakkeydict to store instance attributes per
		# client object
		self.name = name
		self.func = func
		self.menulabel = menulabel
		self.keys = [opt[0] for opt in radio_options]
		self._entries = tuple(
			(name + '_' + opt[0],) + opt[1:] + (i,)
				for i, opt in enumerate(radio_options)
		)
		self._state = weakref.WeakKeyDictionary()
		self._proxies = weakref.WeakKeyDictionary()
		self.menuhints = menuhints.split(':')

	def _assert_args(self, func):
		args, varargs, keywords, defaults = inspect.getargspec(func)
		return len(args) == 2 # (self, key)

	def __get__(self, instance, klass):
		if instance is None:
			return self # class access

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


def get_actions(obj):
	return inspect.getmembers(obj.__class__, lambda m: isinstance(m, ActionMethod))


def get_gtk_actiongroup(obj):
	'''Return a C{Gtk.ActionGroup} for an object using L{Action}
	objects as attributes.

	Defines the attribute C{obj.actiongroup} if it does not yet exist.

	This method can only be used when gtk is available
	'''
	from gi.repository import Gtk

	if hasattr(obj, 'actiongroup') \
	and obj.actiongroup is not None:
		return obj.actiongroup

	obj.actiongroup = Gtk.ActionGroup(obj.__class__.__name__)

	for name, action in get_actions(obj):
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
	from gi.repository import Gtk

	if isinstance(action, ToggleAction):
		gaction = Gtk.ToggleAction(*attr)
	else:
		gaction = Gtk.Action(*attr)

	gaction.zim_readonly = not bool(
		'edit' in action.menuhints or 'insert' in action.menuhints
	)
	action.connect_actionable(obj, gaction)
	actiongroup.add_action_with_accel(gaction, accel)
