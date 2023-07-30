
# Copyright 2013-2020 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Action interface classes.

Objects can have "actions", which are basically attributes of the
class L{Action} or L{ToggleAction}. These objects are callable as bound
methods. So actions are kind of special methods that define some
interface parameters, like what icon and label to use in the menu.

Use the L{action} and L{toggle_action} decorators to create actions.

The classes defined here can cooperate with C{Gio.Action} to tie into the
Gtk action framework. Also they can use Gtk widgets like C{Gtk.Button} as
a "proxy" to trigger the action and reflect the state.

## Menuhints

The "menuhints" attribute for actions sets one or more hints of where the action
should be in the menu and the behavior of the action. Multiple hints can
be separated with ":" in the string. The first one determines the menu, other
can modify the behavior.

Known values include:

  - notebook -- notebook section in "File" menu
  - page -- page section in "File" menu
  - edit -- "Edit" menu - modifies page, insensitive for read-only page
  - insert -- "Insert" menu & editor actionbar - modifies page, insensitive for read-only page
  - view -- "View" menu
  - tools -- "Tools" menu - also shown in toolbar plugin if an icon is provided and tool and not the "headerbar" hint
  - go -- "Go" menu
  - accelonly -- do not show in menu, shortcut key only
  - headerbar -- place action in the headerbar of the window, will place "view"
    menu items on the right, others on the left
  - toolbar -- used by toolbar plugin

Other values are ignored silently

 TODO: find right place in the documentation for this and update list

'''

import inspect
import weakref
import logging
import re

import zim.errors

from zim.signals import SignalHandler


logger = logging.getLogger('zim')

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from gi.repository import Gio
from gi.repository import GLib

def _get_modifier_mask():
	x, mod = Gtk.accelerator_parse('<Primary>')
	return mod

PRIMARY_MODIFIER_STRING = '<Primary>'
PRIMARY_MODIFIER_MASK = _get_modifier_mask()


def hasaction(obj, actionname):
	'''Like C{hasattr} but for attributes that define an action'''
	actionname = actionname.replace('-', '_')
	return hasattr(obj.__class__, actionname) \
		and isinstance(getattr(obj.__class__, actionname), ActionDescriptor)


class ActionDescriptor(object):

	_bound_class = None

	def __get__(self, instance, klass):
		if instance is None:
			return self # class access
		else:
			if instance not in self._bound_actions:
				self._bound_actions[instance] = self._bound_class(instance, self)
			return self._bound_actions[instance]


def action(label, accelerator='', icon=None, verb_icon=None, menuhints='', alt_accelerator=None, tooltip=None):
	'''Decorator to turn a method into an L{ActionMethod} object
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
	@param tooltip: tooltip label, defaults to C{label}
	'''
	def _action(function):
		return ActionClassMethod(function.__name__, function, label, icon, verb_icon, accelerator, alt_accelerator, menuhints, tooltip)

	return _action


class BoundActionMethod(object):

	def __init__(self, instance, action):
		self._instance = instance
		self._action = action
		self._sensitive = True
		self._proxies = set()
			# NOTE: Wanted to use WeakSet() here, but somehow we loose refs to
			#       widgets still being displayed
		self._gaction = None

	def __call__(self, *args, **kwargs):
		if not self._sensitive:
			raise AssertionError('Action not senitive: %s' % self.name)
		return self._action.func(self._instance, *args, **kwargs)

	def __getattr__(self, name):
		return getattr(self._action, name)

	def get_sensitive(self):
		return self._sensitive

	def set_sensitive(self, sensitive):
		self._sensitive = sensitive

		if self._gaction:
			self._gaction.set_enabled(sensitive)

		for proxy in self._proxies:
			proxy.set_sensitive(sensitive)

	def get_gaction(self):
		if self._gaction is None:
			self._gaction = Gio.SimpleAction.new(self.name)
			self._gaction.set_enabled(self._sensitive)
			self._gaction.connect('activate', self._on_activate)
		return self._gaction

	def _on_activate(self, proxy, value):
		# "proxy" can either be Gtk.Button, Gtk.Action or Gio.Action
		logger.debug('Action: %s', self.name)
		try:
			self.__call__()
		except:
			zim.errors.exception_handler(
				'Exception during action: %s' % self.name)

	def _connect_gtkaction(self, gtkaction):
		gtkaction.connect('activate', self._on_activate_proxy)
		gtkaction.set_sensitive(self._sensitive)
		self._proxies.add(gtkaction)


class ActionMethod(BoundActionMethod):

	_button_class = Gtk.Button
	_tool_button_class = Gtk.ToolButton

	def create_button(self):
		button = self._button_class.new_with_mnemonic(self.label)
		button.set_tooltip_text(self.tooltip)
		self.connect_button(button)
		return button

	def create_icon_button(self, fallback_icon=None):
		icon_name = self.verb_icon or self.icon or fallback_icon
		assert icon_name, 'No icon or verb_icon defined for action "%s"' % self.name
		icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON)
		button = self._button_class()
		button.set_image(icon)
		button.set_tooltip_text(self.tooltip) # icon button should always have tooltip
		self.connect_button(button)
		return button

	def create_tool_button(self, fallback_icon=None, connect_button=True):
		icon_name = self.verb_icon or self.icon or fallback_icon
		assert icon_name, 'No icon or verb_icon defined for action "%s"' % self.name
		button = self._tool_button_class()
		button.set_label(self.label)
		button.set_use_underline(True)
		button.set_icon_name(icon_name)
		button.set_tooltip_text(self.tooltip) # icon button should always have tooltip

		if connect_button:
			self.connect_button(button)
		return button

	def connect_button(self, button):
		button.connect('clicked', self._on_activate_proxy)
		button.set_sensitive(self._sensitive)
		self._proxies.add(button)
		button.connect('destroy', self._on_destroy_proxy)

	def _on_destroy_proxy(self, proxy):
		self._proxies.discard(proxy)

	def _on_activate_proxy(self, proxy):
		self._on_activate(proxy, None)


class ActionClassMethod(ActionDescriptor):

	_bound_class = ActionMethod
	_n_args = 1 # self

	def __init__(self, name, func, label, icon=None, verb_icon=None, accelerator='', alt_accelerator=None, menuhints='', tooltip=None):
		assert self._assert_args(func), '%s() has incompatible argspec' % func.__name__
		tooltip = tooltip or label.replace('_', '')
		self.name = name
		self.func = func
		self.label = label
		self.tooltip = tooltip
		self.icon = icon
		self.verb_icon = verb_icon
		self.hasicon = bool(self.verb_icon or self.icon)
		self.menuhints = menuhints.split(':')

		self._attr = (self.name, label, tooltip, icon or verb_icon)
		self._alt_attr = (self.name + '_alt1', label, tooltip, icon or verb_icon)
		self._accel = accelerator
		self._alt_accel = alt_accelerator

		self._bound_actions = weakref.WeakKeyDictionary()

	def _assert_args(self, func):
		spec = inspect.getfullargspec(func)
		if spec.defaults:
			return len(spec.defaults) == len(spec.args) - self._n_args
		else:
			return len(spec.args) == self._n_args


def toggle_action(label, accelerator='', icon=None, verb_icon=None, init=False, menuhints='', tooltip=None):
	'''Decorator to turn a method into an L{ToggleActionMethod} object

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
	@param tooltip: tooltip label, defaults to C{label}
	'''
	def _toggle_action(function):
		return ToggleActionClassMethod(function.__name__, function, label, icon, verb_icon, accelerator, init, menuhints, tooltip)

	return _toggle_action


class ToggleActionMethod(ActionMethod):

	_button_class = Gtk.ToggleButton
	_tool_button_class = Gtk.ToggleToolButton

	def __init__(self, instance, action):
		ActionMethod.__init__(self, instance, action)
		self._state = action._init

	def __call__(self, active=None):
		if not self._sensitive:
			raise AssertionError('Action not senitive: %s' % self.name)

		if active is None:
			active = not self._state
		elif active == self._state:
			return # nothing to do

		with self._on_activate.blocked():
			self._action.func(self._instance, active)
		self.set_active(active)

	def create_tool_button(self, fallback_icon=None, connect_button=True):
		if connect_button:
			raise NotImplementedError # Should work but gives buggy behavior, try using gaction + set_action_name() instead
		return ActionMethod.create_tool_button(self, fallback_icon, connect_button)

	def connect_button(self, button):
		'''Connect a C{Gtk.ToggleAction} or C{Gtk.ToggleButton} to this action'''
		button.set_active(self._state)
		button.set_sensitive(self._sensitive)
		button.connect('toggled', self._on_activate_proxy)
		self._proxies.add(button)

	_connect_gtkaction = connect_button

	def _on_activate_proxy(self, proxy):
		self._on_activate(proxy, proxy.get_active())

	@SignalHandler
	def _on_activate(self, proxy, active):
		'''Callback for activate signal of connected objects'''
		if active != self._state:
			logger.debug('Action: %s(%s)', self.name, active)
			try:
				self.__call__(active)
			except Exception as error:
				zim.errors.exception_handler(
					'Exception during toggle action: %s(%s)' % (self.name, active))

	def get_active(self):
		return self._state

	def set_active(self, active):
		'''Change the state of the action without triggering the action'''
		if active == self._state:
			return
		self._state = active

		if self._gaction:
			self._gaction.set_state(GLib.Variant.new_boolean(self._state))

		with self._on_activate.blocked():
			for proxy in self._proxies:
				if isinstance(proxy, Gtk.ToggleToolButton):
					pass
				else:
					proxy.set_active(active)

	def get_gaction(self):
		if self._gaction is None:
			self._gaction = Gio.SimpleAction.new_stateful(self.name, None, GLib.Variant.new_boolean(self._state))
			self._gaction.set_enabled(self._sensitive)
			self._gaction.connect('activate', self._on_activate)
		return self._gaction


class ToggleActionClassMethod(ActionClassMethod):
	'''Toggle action, used by the L{toggle_action} decorator'''

	_bound_class = ToggleActionMethod
	_n_args = 2 # self, active

	def __init__(self, name, func, label, icon=None, verb_icon=None, accelerator='', init=False, menuhints='', tooltip=None):
		# The ToggleAction instance lives in the client class object;
		# using weakkeydict to store instance attributes per
		# client object
		ActionClassMethod.__init__(self, name, func, label, icon, verb_icon, accelerator, menuhints=menuhints, tooltip=tooltip)
		self._init = init

	def _assert_args(self, func):
		spec = inspect.getfullargspec(func)
		return len(spec.args) == 2 # (self, active)


def radio_action(menulabel, *radio_options, menuhints=''):
	def _action(function):
		return RadioActionClassMethod(function.__name__, function, menulabel, radio_options, menuhints)

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


class RadioActionMethod(BoundActionMethod):

	def __init__(self, instance, action):
		BoundActionMethod.__init__(self, instance, action)
		self._state = None

	def __call__(self, key):
		if not key in self.keys:
			raise ValueError('Invalid key: %s' % key)
		self.func(self._instance, key)
		self.set_state(key)

	def get_state(self):
		return self._state

	def set_state(self, key):
		self._state = key
		for proxy in self._proxies:
			gtk_radioaction_set_current(proxy, key)

	def get_gaction(self):
		raise NotImplementedError # TODO

	def _connect_gtkaction(self, gtkaction):
		gtkaction.connect('changed', self._on_gtkaction_changed)
		self._proxies.add(gtkaction)
		if self._state is not None:
			gtk_radioaction_set_current(gtkaction, self._state)

	def _on_gtkaction_changed(self, gaction, current):
		try:
			name = current.get_name()
			assert name.startswith(self.name + '_')
			key = name[len(self.name) + 1:]
			if self._state == key:
				pass
			else:
				logger.debug('Action: %s(%s)', self.name, key)
				self.__call__(key)
		except:
			zim.errors.exception_handler(
				'Exception during action: %s(%s)' % (self.name, key))


class RadioActionClassMethod(ActionDescriptor):

	_bound_class = RadioActionMethod

	def __init__(self, name, func, menulabel, radio_options, menuhints=''):
		self.name = name
		self.func = func
		self.menulabel = menulabel
		self.keys = [opt[0] for opt in radio_options]
		self._entries = tuple(
			(name + '_' + opt[0],) + opt[1:] + (i,)
				for i, opt in enumerate(radio_options)
		)
		self.hasicon = False
		self.menuhints = menuhints.split(':')
		self._bound_actions = weakref.WeakKeyDictionary()


def get_actions(obj):
	'''Returns bound actions for object

	NOTE: See also L{zim.plugins.list_actions()} if you want to include actions
	of plugin extensions
	'''
	actions = []
	for name, action in inspect.getmembers(obj.__class__, lambda m: isinstance(m, ActionDescriptor)):
		actions.append((name, action.__get__(obj, obj.__class__)))
	return actions


def get_gtk_actiongroup(obj):
	'''Return a C{Gtk.ActionGroup} for an object using L{Action}
	objects as attributes.

	Defines the attribute C{obj.actiongroup} if it does not yet exist.

	This method can only be used when gtk is available
	'''
	if hasattr(obj, 'actiongroup') \
	and obj.actiongroup is not None:
		return obj.actiongroup

	obj.actiongroup = Gtk.ActionGroup(obj.__class__.__name__)

	for name, action in get_actions(obj):
		if isinstance(action, RadioActionMethod):
			obj.actiongroup.add_radio_actions(action._entries)
			gtkaction = obj.actiongroup.get_action(action._entries[0][0])
			action._connect_gtkaction(gtkaction)
		else:
			_gtk_add_action_with_accel(obj, obj.actiongroup, action, action._attr, action._accel)
			if action._alt_accel:
				_gtk_add_action_with_accel(obj, obj.actiongroup, action, action._alt_attr, action._alt_accel)

	return obj.actiongroup


def _gtk_add_action_with_accel(obj, actiongroup, action, attr, accel):
	if isinstance(action, ToggleActionMethod):
		gtkaction = Gtk.ToggleAction(*attr)
	else:
		gtkaction = Gtk.Action(*attr)

	gtkaction.zim_readonly = not bool(
		'edit' in action.menuhints or 'insert' in action.menuhints
	)
	action._connect_gtkaction(gtkaction)
	actiongroup.add_action_with_accel(gtkaction, accel)


def initialize_actiongroup(obj, prefix):
	actiongroup = Gio.SimpleActionGroup()
	for name, action in get_actions(obj):
		gaction = action.get_gaction()
		actiongroup.add_action(gaction)
	obj.insert_action_group(prefix, actiongroup)
