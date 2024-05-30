# Copyright 2011 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains classes to work with simple tree structure
representation of formatted text.
'''

from .tokenlist import TEXT, END
from .builder import Builder



class SimpleTreeElement(list):
	'''This class represents (part of) a simple tree structure
	of formatted text.

	The attributes `tag` and `attrib` contain the element name
	and a dictionary with properties. If the element has no
	properties `attrib` can be `None` instead.

	It can be accessed as a list to find the child elements.
	All child elements are either a string with plain text
	or a nested `SimpleTreeElement`.

	The L{SimpleTreeBuilder} and L{SimpleTreeParser} classes can help
	to construct and process these tree structures.
	See also L{simpletree_to_tokens()} and L{tokens_to_simpletree()}
	'''

	__slots__ = ('tag', 'attrib')

	def __init__(self, tag, attrib=None, children=None):
		self.tag = tag
		self.attrib = attrib
		if children:
			self.extend(children)

	def set(self, key, value):
		'''Set attribute'''
		if self.attrib is None:
			self.attrib = {}
		self.attrib[key] = value

	def get(self, key, default=None):
		'''Get attribute'''
		if self.attrib:
			return self.attrib.get(key, default)
		else:
			return default

	def __eq__(self, other):
		if self.tag == other.tag \
		and self.attrib == other.attrib \
		and len(self) == len(other):
			return all(s == o for s, o in zip(self, other))
		else:
			return False

	def __repr__(self):
		if len(self) > 0:
			return '<%s:\n%s>' % (self.__class__.__name__, self.pprint(level=1))
		else:
			return '<%s: %s>' % (self.__class__.__name__, self.pprint(level=0).strip())

	def __str__(self):
		return self.__repr__()

	def pprint(self, level=0):
		'''Returns pretty-printed text representation'''
		prefix = '  ' * level
		if len(self) > 0:
			lines = [prefix + '%s %r [\n' % (self.tag, self.attrib)]
			for item in self:
				if isinstance(item, SimpleTreeElement):
					lines.append(item.pprint(level=level + 1))
				elif isinstance(item, str):
					for line in item.splitlines(True):
						lines.append(prefix + '  %r\n' % line)
				else:
					lines.append(prefix + '  %r\n' % item)
			lines.append(prefix + ']\n')
			return ''.join(lines)
		else:
			return prefix + '%s %r []\n' % (self.tag, self.attrib)


class SimpleTreeBuilder(Builder):
	'''Builder class that builds a tree of L{SimpleTreeElement}s'''

	def __init__(self, elementfactory=SimpleTreeElement):
		self.elementfactory = elementfactory
		self.toplevel = []
		self.stack = [self.toplevel]

	def get_root(self):
		'''Return top level element
		raises `AssertionError` if content not complete (e.g. unclosed tags) or no single toplevel element
		'''
		if not len(self.stack) == 1:
			raise AssertionError('Did not finish processing: %r' % [t.tag for t in self.stack[1:]])
		elif not len(self.toplevel) == 1:
			raise AssertionError('Not a single toplevel element: %r' % [t.tag for t in self.toplevel])
		return self.toplevel[0]

	# Builder interface

	def start(self, tag, attrib=None):
		element = self.elementfactory(tag, attrib)
		self.stack[-1].append(element)
		self.stack.append(element)

	def end(self, tag):
		element = self.stack.pop()
		if element.tag != tag:
			raise AssertionError('Unmatched %s at end of %s' % (element.tag, tag))

	def text(self, text):
		self.stack[-1].append(text)

	def append(self, tag, attrib=None, text=None):
		element = self.elementfactory(tag, attrib)
		if text:
			element.append(text)
		self.stack[-1].append(element)


class SimpleTreeParser():
	'''Parser that walks a tree structure if L{SimpleTreeElement}s and calls a L{Builder} object'''

	def __init__(self, builder: Builder):
		self.builder = builder

	def parse(self, elt: SimpleTreeElement):
		self.builder.start(elt.tag, elt.attrib)
		for t in elt:
			if isinstance(t, str):
				self.builder.text(t)
			else:
				self.parse(t) # recurs
		self.builder.end(elt.tag)


def tokens_to_simpletree(tokens) -> SimpleTreeElement:
	'''Helper function to convert between tokens and SimpleTree structure'''
	# Could be aciheved by chaining SimpleTreeBuilder and TokenParser
	# but this is more direct implementation.
	root = SimpleTreeElement(*tokens[0])
	stack = [root]
	for t in tokens[1:]:
		if t[0] == TEXT:
			stack[-1].append(t[1])
		elif t[0] == END:
			assert t[1] == stack[-1].tag
			stack.pop()
		else:
			elt =  SimpleTreeElement(*t)
			stack[-1].append(elt)
			stack.append(elt)

	assert len(stack) == 0
	return root


def simpletree_to_tokens(elt: SimpleTreeElement):
	'''Helper function to convert between SimpleTree structure tokens'''
	# Could be aciheved by chaining TokenBuilder and SimpleTreeParser
	# but this is more direct implementation.
	tokens = [(elt.tag, elt.attrib)]
	for t in elt:
		if isinstance(t, str):
			tokens.append((TEXT, t))
		else:
			tokens.extend(simpletree_to_tokens(t)) # recurs
	tokens.append((END, elt.tag))
	return tokens
