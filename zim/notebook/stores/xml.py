# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module reads an XML file defining zim pages.

For now the only XML tags which are supported are 'section' and 'page'. The
'section' tag serves as a container for multiple pages. The 'page' tag serves
as a container for the page content plus any sub-pages. Each page should have
an attribute 'name' giving it's basename, so the file can look like this::

	<section>
	<page name="Foo">
	Some text in page Foo
	<page name="Bar">
	This is text in page 'Foo:Bar'
	</page>
	</page>
	</section>

We read the whole file to memory, which puts certain limits on
scalability.
'''

# FUTURE: This module does not support attachments in the xml data

import zim.stores.memory
	# importing class from this module makes get_store() fail

from zim.formats import get_format, ElementTreeModule
from zim.notebook import Path
from zim.parsing import TextBuffer


class XMLStore(zim.stores.memory.MemoryStore):

	properties = {
		'read-only': True
	}

	def __init__(self, notebook, path, file=None):
		zim.stores.memory.MemoryStore.__init__(self, notebook, path)
		self.file = file
		if not self.store_has_file():
			raise AssertionError, 'XMl store needs file'
			# not using assert here because it could be optimized away
		self.format = get_format('wiki') # FIXME store format in XML header
		if self.file.exists():
			self.parse(self.file.read())

	def store_page(self, page):
		memory.Store.store_page(self, page)
		self.file.writelines(self.dump())

	def parse(self, content):
		if isinstance(content, list):
			content = ''.join(content)
		target = MemoryStoreTreeBuilder(self)
		builder = ElementTreeModule.XMLTreeBuilder(target=target)
		builder.feed(content)
		builder.close()

	def dump(self):
		text = TextBuffer([
			u'<?xml version="1.0" encoding="utf-8"?>\n',
			u'<section>\n' ])
		for node in self._nodetree:
			text += self._dump_node(node)
		text.append(u'</section>\n')
		return text.get_lines()

	def _dump_node(self, node):
		text = [u'<page name="%s">\n' % node.basename]
		if node.text:
			text.append(node.text)
		for n in node.children:
			text += self._dump_node(n) # recurs
		text.append('</page>\n')
		return text


class MemoryStoreTreeBuilder(object):

	def __init__(self, store):
		self.store = store
		self.path = Path(':')
		self.stack = []

	def start(self, tag, attrib):
		if tag == 'section':
			pass
		elif tag == 'page':
			assert 'name' in attrib
			self.path = self.path + attrib['name']
			node = self.store.get_node(self.path, vivificate=True)
			self.stack.append(node)
		else:
			assert False, 'Unknown tag'

	def data(self, data):
		if self.stack:
			node = self.stack[-1]
			if node.text:
				node.text += data
			else:
				node.text = data

	def end(self, tag):
		if tag == 'section':
			pass
		else:
			assert self.stack
			self.path = self.path.parent
			node = self.stack.pop()
			if node.text and node.text.isspace():
				node.text = ''
			elif node.text:
				node.text = unicode(node.text.strip('\n') + '\n')

	def close(self):
		pass
