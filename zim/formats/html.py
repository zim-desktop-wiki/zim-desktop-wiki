# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

from zim.fs import *
from zim.formats import *

__format__ = 'html'

tags = {
	'Verbatim': 'pre',
	'italic': 'i',
	'bold': 'b',
	'underline': 'u',
	'strike': 'strike',
	'verbatim': 'tt',
	'head1': 'h1',
	'head2': 'h2',
	'head3': 'h3',
	'head4': 'h4',
	'head5': 'h5',
}

class Dumper(DumperClass):

	def url_encode(self, link):
		link.replace(' ', '%20')
		# FIXME what other chars do we need ?
		return link

	def html_encode(self, text):
		text = text.replace('&', '&amp;')
		text = text.replace('"', '&quot;')
		text = text.replace('<', '&lt;')
		text = text.replace('>', '&gt;')
		return text

	def dump(self, tree, output):
		assert isinstance(tree, NodeTree)
		assert isinstance(output, (File, Buffer))
		file = output.open('w')
		self.dump_nodelist(tree, file)
		file.close()

	def dump_nodelist(self, tree, file):
		'''FIXME'''
		for node in tree:
			if isinstance(node, NodeList):
				file.write('<p>')
				self.dump_nodelist(node, file) # recurs
				file.write('</p>')
			elif isinstance(node, HeadingNode):
				style = 'head%i'% node.level
				tag = tags[style]
				text = self.html_encode(node.string)
				file.write('<'+tag+'>'+text+'</'+tag+'>')
			elif isinstance(node, ImageNode):
				href = self.url_encode(node.link)
				text = self.html_encode(node.string)
				file.write('<img src="%s" alt="%s">' % (href, text))
				pass
			elif isinstance(node, LinkNode):
				href = self.url_encode(node.link)
				text = self.html_encode(node.string)
				file.write('<a href="%s">%s</a>' % (href, text))
			elif isinstance(node, TextNode):
				style = node.style
				text = self.html_encode(node.string)
				if not text.isspace() and style != 'Verbatim':
					text = text.replace('\n', '<br>\n')
				if style:
					tag = tags[style]
					file.write('<'+tag+'>'+text+'</'+tag+'>')
				else:
					file.write(text)
			else:
				assert False, 'Unknown node type: '+node.__str__()
