# -*- coding: utf-8 -*-

# Copyright 2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

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

import zim.errors

logger = logging.getLogger('zim')

class Action(object):
	'''Action, used by the L{action} decorator'''

	def __init__(self, name, func, label, stock=None, accelerator='', tooltip='', readonly=True):
		assert self._assert_args(func), '%s() has incompatible argspec' % func.__name__
		if not tooltip:
			tooltip = label.replace('_', '')

		self.name = name
		self.readonly = readonly
		self.func = func
		self._attr = (self.name, label, tooltip, stock)
		self._accel = accelerator

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
		def func(*arg, **kwarg):
			logger.debug('Action: %s', self.name)
			try:
				self.func(instance, *arg, **kwarg)
			except:
				zim.errors.exception_handler(
					'Exception during action: %s' % self.name)

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
		self.__get__(instance, instance.__class__)()


class ToggleAction(Action):
	'''Toggle action, used by the L{toggle_action} decorator'''

	def __init__(self, name, func, label, stock=None, accelerator='', tooltip='', readonly=True, default=False):
		# Default is a class attribute
		# Using weakkeydict to store instance attributes
		Action.__init__(self, name, func, label, stock, accelerator, tooltip, readonly)
		self._default = default
		self._state = weakref.WeakKeyDictionary()
		self._proxies = weakref.WeakKeyDictionary()

	def _assert_args(self, func):
		args, varargs, keywords, defaults = inspect.getargspec(func)
		return len(args) == 2 # (self, active)

	def __get__(self, instance, klass):
		if instance is None:
			return self # class access

		if not instance in self._state:
			self._state[instance] = self._default

		# instance acces, return bound method
		def func(active=None):
			if active is None:
				active = not self._state[instance]
			elif active == self._state[instance]:
				return # nothing to do

			logger.debug('Action: %s(%s)', self.name, active)
			try:
				self.func(instance, active)
			except Exception, error:
				zim.errors.exception_handler(
					'Exception during toggle action: %s(%s)' % (self.name, active))
			else:
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
		actionable.set_active(self._state.get(instance, self._default))
		actionable.connect('toggled', self.do_activate, instance)

		if not instance in self._proxies:
			self._proxies[instance] = []
		self._proxies[instance].append(actionable)

	def do_activate(self, actionable, instance):
		'''Callback for activate signal of connected objects'''
		if actionable.get_active() != self._state.get(instance, self._default):
			self.__get__(instance, instance.__class__)()


def action(label, stock=None, accelerator='', tooltip='', readonly=True):
	'''Decorator to turn a method into an L{Action} object
	Methods decorated with this decorator can have keyword arguments
	but no positional arguments.
	@param label: the label used e.g for the menu item
	@param stock: stock item to define the icon
	@param accelerator: accelerator key description
	@param tooltip: tooltip text, if C{None} will default to C{label}
	@param readonly: if C{True} this action should also be available
	for readonly notebooks
	'''
	# TODO see where "readonly" should go
	def _action(function):
		return Action(function.__name__, function, label, stock, accelerator, tooltip, readonly)

	return _action


def toggle_action(label, stock=None, accelerator='', tooltip='', readonly=True):
	'''Decorator to turn a method into an L{ToggleAction} object
	Methods decorated with this decorator can only have a single
	boolean argument for the state being toggled.
	@param label: the label used e.g for the menu item
	@param stock: stock item to define the icon
	@param accelerator: accelerator key description
	@param tooltip: tooltip text, if C{None} will default to C{label}
	@param readonly: if C{True} this action should also be available
	for readonly notebooks
	'''
	# TODO see where "readonly" should go
	def _toggle_action(function):
		return ToggleAction(function.__name__, function, label, stock, accelerator, tooltip, readonly)

	return _toggle_action


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

	for name, action in inspect.getmembers(obj.__class__, lambda m: isinstance(m, Action)):
		if isinstance(action, ToggleAction):
			gaction = gtk.ToggleAction(*action._attr)
		else:
			gaction = gtk.Action(*action._attr)

		action.connect_actionable(obj, gaction)
		obj.actiongroup.add_action_with_accel(gaction, action._accel)

	return obj.actiongroup
