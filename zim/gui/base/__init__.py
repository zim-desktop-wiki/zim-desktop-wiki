# Copyright 2026 Jaap Karssenberg <jaap.karssenberg@gmail.com>

from gi.repository import GObject


def schedule_on_idle(function, args=()):
	'''Helper function to schedule stuff that can be done later, it will
	be triggered on the gtk "idle" signal.

	@param function: function to call
	@param args: positional arguments
	'''
	def callback():
		function(*args)
		return False # delete signal
	GObject.idle_add(callback)
