
from base import *

class HTMLDumper:

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
		if isinstance(tree, NodeTree):
				file.write('<html>\n<head>\n')
				file.write('\t<title>Foo</title>\n')
				# TODO: need title
				# TODO: dump headers
				file.write('</head>\n<body>\n')

		for node in tree:
			if isinstance(node, NodeList):
				file.write('<p>')
				self.dump(node, file) # recurs
				file.write('</p>')
			elif isinstance(node, TextNode):
				style = node.style
				if style:
					tag = self.tags[style]
					file.write('<'+tag+'>'+node.string+'</'+tag+'>')
				else:
					file.write(node.string)
			elif isinstance(node, LinkNode):
				pass
			elif isinstance(node, ImageNode):
				pass
			#else:
			#	raise ...

		if isinstance(tree, NodeTree):
			file.write('</body>\n</html>\n')


# vim: tabstop=4
