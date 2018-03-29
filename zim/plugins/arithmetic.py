# Copyright 2011 Patricio Paez <pp@pp.com.mx>
#
# Plugin to use arithmetic in Zim wiki

from zim.inc.arithmetic import ParserGTK

from zim.plugins import PluginClass
from zim.actions import action

from zim.gui.pageview import PageViewExtension


class ArithmeticPlugin(PluginClass):

	plugin_info = {
		'name': _('Arithmetic'), # T: plugin name
		'description': _('''\
This plugin allows you to embed arithmetic calculations in zim.
It is based on the arithmetic module from
http://pp.com.mx/python/arithmetic.
'''), # T: plugin description
		'author': 'Patricio Paez',
		'help': 'Plugins:Arithmetic',
	}

	#~ plugin_preferences = (
		# key, type, label, default
	#~ )


class ArithmeticPageViewExtension(PageViewExtension):

	@action(_('_Arithmetic'), accelerator='F5') # T: menu item
	def calculate(self):
		"""Perform arithmetic operations"""

		# get the buffer
		buf = self.pageview.textview.get_buffer() # XXX

		# parse and return modified text
		parser = ParserGTK()
		parser.parse(buf)
