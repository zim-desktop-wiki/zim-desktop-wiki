#!/usr/bin/python

import gtk
import sys

sys.path.insert(0, '.')

from class_tree import *
from zim._lib import xdot


class Graph(object):

	def __init__(self, dir):
		self.dir = dir

	def get_dotcode(self):
		text = self._code_for_module(self.dir)
		return 'digraph G { \n'       \
		       'graph [rankdir=LR]'   \
		       'node [shape=box fontsize=14]'  \
		       '%s }' % text

	def _code_for_module(self, module):
		text = '"%s" [shape=ellips]' % module.name
		for item in module.items():
			if isinstance(item, basestring):
				text += '\n"%s"' % item
				text +='\n"%s" -> "%s"' % (module.name, item)
			else:
				text += self._code_for_module(item) # recurs
				text +='\n"%s" -> "%s"' % (module.name, item.name)
		return text


if __name__ == '__main__':
	graph = Graph(ModuleDir('./zim'))
	window = xdot.DotWindow()
	window.connect('destroy', lambda o: gtk.main_quit())
	#print graph.get_dotcode()
	window.set_dotcode(graph.get_dotcode())
	window.show_all()
	gtk.main()
