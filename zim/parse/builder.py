# Copyright 2011 Jaap Karssenberg <jaap.karssenberg@gmail.com>

class Builder(object):
	'''This class defines a 'builder' interface.
	It is used by parsers to construct the parse tree while keeping the
	parser objects agnostic of how the resulting parse tree objects
	look.
	'''

	def start(self, tag, attrib=None):
		'''Start formatted region
		@param tag: the tag name
		@param attrib: optional dict with attributes
		@implementation: must be implemented by sub-classes
		'''
		raise NotImplemented

	def text(self, text):
		'''Append text
		@param text: text to be appended as string
		@implementation: must be implemented by sub-classes
		'''
		raise NotImplemented

	def end(self, tag):
		'''End formatted region
		@param tag: the tag name
		@raises XXX: when tag does not match current state
		@implementation: must be implemented by sub-classes
		'''
		raise NotImplemented

	def append(self, tag, attrib=None, text=None):
		'''Convenience function to open a tag, append text and close
		it immediatly. Only used for formatted text that has no
		sub-processing done.
		@param tag: the tag name
		@param attrib: optional dict with attributes
		@param text: formatted text
		@implementation: optional for subclasses, default implementation
		calls L{start()}, L{text()}, and L{end()}
		'''
		self.start(tag, attrib)
		if not text is None:
			self.text(text)
		self.end(tag)


class BuilderTextBuffer(Builder):
	'''Wrapper that buffers text going to a L{Builder} object
	such that the last piece of text remains accessible for inspection
	and can be modified.
	'''

	def __init__(self, builder):
		self.builder = builder
		self.buffer = []

	# Interface to handle text buffer

	def get_text(self):
		return ''.join(self.buffer)

	def set_text(self, text):
		self.buffer = [text]

	def clear_text(self):
		self.buffer = []

	def flush(self):
		text = ''.join(self.buffer)
		if text:
			self.builder.text(text)
		self.buffer = []

	# Builder interface

	def start(self, tag, attrib=None):
		if self.buffer:
			self.flush()
		self.builder.start(tag, attrib)

	def end(self, tag):
		if self.buffer:
			self.flush()
		self.builder.end(tag)

	def text(self, text):
		self.buffer.append(text)

	def append(self, tag, attrib=None, text=None):
		if self.buffer:
			self.flush()
		self.builder.append(tag, attrib, text)