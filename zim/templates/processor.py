# -*- coding: utf-8 -*-

# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains the main object to "execute" a template and
fill in the parameters, call functions etc. The L{TemplateProcessor}
defined here takes care of the template control flow ('IF', 'FOR', etc.).

Also see the L{expression} sub module that contains logic for executing
expressions in the template.
'''


import collections

from zim.utils import MovingWindowIter
from zim.parser import SimpleTreeElement

from zim.templates.expression import ExpressionDictObject, ExpressionParameter


class TemplateContextDict(ExpressionDictObject):
	'''This class defines a dict with template parameters

	These dicts can be modified when running the template, but nested
	dicts can only be modified if they are a TemplateContextDict
	themselves.
	'''

	_fmethods = ExpressionDictObject._fmethods + (
		'pop', 'clear', 'update', 'setdefault'
	) # adding methods for mutuable mapping here


class TemplateProcessor(object):
	'''The template processor takes a parsed template and "executes" it
	one or more times.
	'''

	# See Expression for remarks on safe eval of expressions.
	#
	# In addition here we set also parameters in the context rather
	# then just retrieving them. To make this safe we only allow
	# modification of C{TemplateContextDict} dicts and do not allow
	# any assignment to other dicts or objects.

	# Instructions supported here:
	#
	# 	'GET', 'SET',
	# 	'IF', 'ELIF', 'ELSE',
	# 	'FOR'
	# 	'INCLUDE',

	def __init__(self, parts):
		'''Constructor
		@param parts: A list of L{SimplerTreeElements} as produced by
		L{TemplateParser.parse()}
		'''
		self.main = None
		self.blocks = {}
		for item in parts:
			if item.tag == 'TEMPLATE':
				self.main = item
			elif item.tag == 'BLOCK':
				self.blocks[item.get('name')] = item
			else:
				raise AssertionError, 'Unknown tag: %s' % item.tag

		if self.main is None:
			raise AssertionError, 'Missing main part of template'

	def process(self, output, context):
		'''Execute the template once
		@param output: an object to recieve the template output, can be
		a C{list} and should support at least an C{append()} method to
		recieve string content
		@param context: a L{TemplateContextDict} object with the
		template parameters
		'''
		assert isinstance(context, TemplateContextDict)
		self.__call__(output, self.main, context)

	@staticmethod
	def _set(context, var, value):
		# We only allow setting in pre-defined TemplateContextDict's
		namespace = context
		for name in var.parts[:-1]:
			if namespace \
			and isinstance(namespace, TemplateContextDict):
				namespace = namespace.get(name)
			else:
				raise AssertionError, 'Can not assign: %s' % var.name

		if namespace is not None \
		and isinstance(namespace, TemplateContextDict):
			namespace[var.key] = value
		else:
			raise AssertionError, 'Can not assign: %s' % var.name

	def __call__(self, output, elements, context):
		n = len(elements)
		i = 0
		while i < n:
			try:
				element = elements[i]
				i += 1
				if isinstance(element, basestring):
					output.append(element)
				elif element.tag == 'GET':
					expr = element.attrib['expr']
					value = expr(context)
					output.append(unicode(value))
				elif element.tag == 'SET':
					var = element.attrib['var']
					expr = element.attrib['expr']
					value = expr(context)
					self._set(context, var, value)
				elif element.tag in ('IF', 'ELIF'):
					expr = element.attrib['expr']
					if bool(expr(context)):
						self.__call__(output, element, context) # recurs
						while i < n \
						and isinstance(elements[i], SimpleTreeElement) \
						and elements[i].tag in ('ELIF', 'ELSE'):
							# Skip subsequent ELIF / ELSE clauses
							i += 1
				elif element.tag == 'ELSE':
					self.__call__(output, element, context) # recurs
				elif element.tag == 'FOR':
					self._loop(output, element, context)
				elif element.tag == 'INCLUDE':
					expr = element.attrib['expr']
					if isinstance(expr, ExpressionParameter):
						name = expr.name
						if name in self.blocks:
							self.__call__(output, self.blocks[name], context) # recurs
						else:
							raise AssertionError, 'No such block defined: %s' % name
					else:
						raise AssertionError, 'TODO also allow files from template resources'
				else:
					raise AssertionError, 'Unknown instruction: %s' % element.tag
			except:
				#~ logger.exception('Exception in template')
				raise

	def _loop(self, output, element, context):
		var = element.attrib['var']
		expr = element.attrib['expr']
		items = expr(context)
		if not isinstance(items, collections.Iterable):
			raise TypeError, 'Can not iterate over: %s' % items
		elif not isinstance(items, collections.Sized):
			# cast to list to ensure we have a len()
			items = list(items)

		# set "loop"
		outer = context.get('loop')
		if isinstance(outer, TemplateLoopState):
			loop = TemplateLoopState(len(items), outer)
		else:
			loop = TemplateLoopState(len(items), None)
		context['loop'] = loop

		# do the iterations
		myiter = MovingWindowIter(items)
		for i, items in enumerate(myiter):
			loop._update(i, myiter)
			self._set(context, var, items[1]) # set var
			self.__call__(output, element, context) # recurs

		# restore "loop"
		context['loop'] = outer



class TemplateLoopState(object):
	'''Object used for the "loop" parameter in a FOR loop'''

	def __init__(self, size=None, outer=None):
		if size is None:
			self.size = None
			self.max = None
		else:
			self.size = size
			self.max = size - 1

		self.outer = outer

		self.prev = None
		self.current = None
		self.next = None
		self.index = None
		self.count = None
		self.first = None
		self.last = None
		self.parity	= None
		self.even = None
		self.odd = None

	def _update(self, i, movingwindowiter):
		self.prev = movingwindowiter.items[0]
		self.current = movingwindowiter.items[1]
		self.next = movingwindowiter.items[2]

		self.first = i == 0
		self.last = movingwindowiter.last

		self.index = i
		self.count = i + 1
		self.parity	= 'even' if i % 2 == 0 else 'odd'
		self.even = self.parity == 'even'
		self.odd = self.parity == 'odd'
