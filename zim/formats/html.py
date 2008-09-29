# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

from zim.formats import *

__format__ = 'html'

class Dumper(DumperClass):

	tags = {
		'Verbatim': 'pre',
		'italic': 'i',
		'bold': 'b',
		'underline': 'u',
		'verbatim': 'tt',
		'head1': 'h1',
		'head2': 'h2',
		'head3': 'h3',
		'head4': 'h4',
		'head5': 'h5',
	}

	def dump(self, tree, file):
		for node in tree:
			if isinstance(node, NodeList):
				file.write('<p>')
				self.dump(node, file) # recurs
				file.write('</p>')
			elif isinstance(node, LinkNode):
				href = node.link
				# TODO html encode text
				file.write('<a href="%s">%s</a>' % (href, node.string))
			elif isinstance(node, ImageNode):
				# TODO dump image
				pass
			elif isinstance(node, TextNode):
				style = node.style
				if style:
					tag = self.tags[style]
					# TODO html encode text
					file.write('<'+tag+'>'+node.string+'</'+tag+'>')
				else:
					# TODO html encode text
					file.write(node.string)
			#else:
			#	raise ...
