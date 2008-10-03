# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME

We do not put pagebreaks in normal paragraphs. Use the following
CSS in your template if you want to preserve tabs and linebreaks.

	<style>
		p {white-space:pre;}
	</style>

'''

from zim.fs import *
from zim.formats import *

__format__ = 'html'

tags = {
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

	def dump_nodelist(self, list, file):
		'''FIXME'''
		for node in list:
			if isinstance(node, NodeList):
				file.write('<p>\n')
				self.dump_nodelist(node, file) # recurs
				file.write('</p>\n')
			elif isinstance(node, HeadingNode):
				style = 'head%i'% node.level
				tag = tags[style]
				text = self.html_encode(node.string)
				file.write('<'+tag+'>'+text+'</'+tag+'>')
			elif isinstance(node, ImageNode):
				src = self.url_encode(node.src)
				if node.string:
					text = self.html_encode(node.string)
				else:
					text = ''
				file.write('<img src="%s" alt="%s">' % (src, text))
				pass
			elif isinstance(node, LinkNode):
				href = self.url_encode(node.link)
				text = self.html_encode(node.string)
				file.write('<a href="%s">%s</a>' % (href, text))
			elif isinstance(node, TextNode):
				style = node.style
				text = self.html_encode(node.string)
				if not style:
					file.write(text)
				elif style == 'Verbatim':
					file.write('<pre>\n'+text+'</pre>\n')
				else:
					tag = tags[style]
					file.write('<'+tag+'>'+text+'</'+tag+'>')
			else:
				assert False, 'Unknown node type: '+node.__str__()
