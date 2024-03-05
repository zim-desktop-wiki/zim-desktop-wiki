# Copyright 2012-2024 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Functions for dynamic loading of modules and klasses'''

import inspect


def get_module(name):
	'''Import a module

	@param name: the module name
	@returns: module object
	@raises ImportError: if the given name does not exist
	'''
	# __import__ has some quirks, see the reference manual
	mod = __import__(name)
	for part in name.split('.')[1:]:
		mod = getattr(mod, part)
	return mod


def lookup_subclasses(module, klass):
	'''Look for all subclasses of klass in the module

	@param module: module object
	@param klass: base class
	'''
	subclasses = []
	for name, obj in inspect.getmembers(module, inspect.isclass):
		if issubclass(obj, klass) \
		and obj.__module__.startswith(module.__name__):
			subclasses.append(obj)

	return subclasses


def lookup_subclass(module, klass):
	'''Look for a subclass of klass in the module

	This function is used in several places in zim to get extension
	classes. Typically L{get_module()} is used first to get the module
	object, then this lookup function is used to locate a class that
	derives of a base class (e.g. PluginClass).

	@param module: module object
	@param klass: base class

	@note: don't actually use this method to get plugin classes, see
	L{PluginManager.get_plugin_class()} instead.
	'''
	subclasses = lookup_subclasses(module, klass)
	if len(subclasses) > 1:
		raise AssertionError('BUG: Multiple subclasses found of type: %s' % klass)
	elif subclasses:
		return subclasses[0]
	else:
		return None