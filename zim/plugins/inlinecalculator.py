# -*- coding: utf-8 -*-

# Copyright 2010 Jaap Karssenberg <pardus@cpan.org>

from __future__ import with_statement
from __future__ import division # We are doing math in this module ...


import gtk
import logging
import re

from zim.plugins import PluginClass
from zim.errors import Error


logger = logging.getLogger('zim.plugins.insertsymbol')


ui_xml = '''
<ui>
<menubar name='menubar'>
	<menu action='tools_menu'>
		<placeholder name='plugin_items'>
			<menuitem action='eval_math'/>
		</placeholder>
	</menu>
</menubar>
</ui>
'''

ui_actions = (
	# name, stock id, label, accelerator, tooltip, readonly
	('eval_math', None, _('Evaluate _Math'), '', '', False), # T: menu item
)


class ExpressionError(Error):
	
	description = _(
		'The inline calculator plugin was not able\n'
		'to evaluate the expression at the cursor.' )
		# T: error description


class InlineCalculatorPlugin(PluginClass):

	plugin_info = {
		'name': _('Inline Calculator'), # T: plugin name
		'description': _('''\
This plugin allows you to quickly evaluate simple
mathematical expressions in zim.

This is a core plugin shipping with zim.
'''), # T: plugin description
		'author': 'Jaap Karssenberg',
		'help': 'Plugins:Inline Calculator',
	}

	#~ plugin_preferences = (
		# key, type, label, default
	#~ )


	_multiline_re = re.compile('--+\s+[+-]')
		# for multiline summation with "--- +" and similar

	def initialize_ui(self, ui):
		if self.ui.ui_type == 'gtk':
			self.ui.add_actions(ui_actions, self)
			self.ui.add_ui(ui_xml, self)

	def eval_math(self):
		'''Action called by the menu item or key binding,
		will look at the cursor for an expression to evaluate.
		'''
		buffer = self.ui.mainwindow.pageview.view.get_buffer()
			# FIXME - way to long chain of objects here
		
		# FIXME: what do we do for selections ?

		cursor = buffer.get_iter_at_mark(buffer.get_insert())
		start, end = buffer.get_line_bounds(cursor.get_line())
		line = buffer.get_text(start, end)

		if not line or line.isspace():
			# Empty line, look at previous line
			if cursor.get_line() > 1:
				start, end = buffer.get_line_bounds(cursor.get_line() - 1)
				cursor = end.copy()
				cursor.backward_char()
				line = buffer.get_text(start, end)
			else:
				return # silent fail

		if self._multiline_re.match(line):
			# Search for start of block - iterate back to empty line
			lineno = cursor.get_line()
			while lineno > 1:
				mystart, myend = buffer.get_line_bounds(lineno)
				myline = buffer.get_text(mystart, myend)
				if not myline or myline.isspace():
					break
				else:
					start = mystart
					lineno -= 1
		else:
			# One line expression, just pass it on
			# FIXME skip forward past next word if any if last char is '='
			end = cursor
			
		orig = buffer.get_text(start, end)
		new = self.process_text(orig)
		with buffer.user_action:
			buffer.delete(start, end)
			buffer.insert_at_cursor(new)

	def process_text(self, text):
		'''Takes a piece of text and parses it for expressions 
		to evaluate. Returns the text with result inserted or replaced.
		Will raise an exception on errors.
		'''
		# This method is separated from eval_math() for easy testing

		if '\n' in text:
			return self._process_multiline(text)
		else:
			return self._process_line(text)

	def _process_line(self, line):
		# Check for non-math prefix
		prefix = ''
		if ':' in line:
			i = line.rindex(':') + 1
			prefix = line[:i]
			line = line[i:]
		
		# Allow for chaining like "1 + 2 = 3 + 0.5 = 3.5" etc.
		if line.count('=') > 1:
			parts = line.split('=')
			prefix += '='.join(parts[:-2]) + '='
			line = '='.join(parts[-2:])

		# Check for whitespace postfix after previous answer
		postfix = ''
		stripped = line.rstrip()
		if '=' in line \
		and stripped != line and not stripped.endswith('='):
			i = len(line) - len(stripped)
			postfix = line[-i:]
			line = stripped

		# Strip previous answer and '='
		if '=' in line:
			i = line.index('=')
			line = line[:i]

		result = self.safe_eval(line)

		return prefix + line + '= ' + str(result) + postfix

	def _process_multiline(self, text):
		lines = text.splitlines()
		for i, line in enumerate(lines):
			if self._multiline_re.match(line):
				operator = line.strip()[-1]
				break
		else:
			raise ExpressionError, _('Could not parse expression')
				# T: error message

		sep = ' %s ' % operator
		expression = sep.join('(%s)' % l for l in lines[:i])
		result = self.safe_eval(expression)

		lines = lines[:i+1] + [str(result)]
		return '\n'.join(lines) + '\n'


	def safe_eval(self, expression):
		'''Safe evaluation of a python expression'''
		try:
			return eval(expression, {'__builtins__': None}, {})
		except Exception, error:
			msg = '%s: %s' % (error.__class__.__name__, error)
			raise ExpressionError, msg

