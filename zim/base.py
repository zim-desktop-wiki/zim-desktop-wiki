# -*- coding: utf-8 -*-

# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>


from .signals import ConnectorMixin, SignalEmitter


class Object(ConnectorMixin, SignalEmitter):
	'''Base class for zim classes that want to use signals'''
	pass

# TODO add some logic for properties, preferences, state
