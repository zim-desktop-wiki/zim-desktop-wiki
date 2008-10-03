# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import re

from zim.fs import *
from zim.formats import *

__format__ = 'wiki'

parser_re = {
	'blockstart': re.compile("\A(''')\s*?\n"),
	'Verbatim':   re.compile("\A'''\s*?(^.*?)^'''\s*\Z", re.M | re.S),
	'splithead':  re.compile('^(==+\s+\S.*?\n)', re.M),
	'heading':    re.compile("\A((==+)\s+(.*?)(\s+==+)?\s*)\Z"),

	# All the experssions below will match the inner pair of
	# delimiters if there are more then two characters in a row.
	'link':       re.compile('\[\[(?!\[)(.+?)\]\]'),
	'image':      re.compile('\{\{(?!\{)(.+?)\}\}'),
	'italic':     re.compile('//(?!/)(.+?)//'),
	'bold':       re.compile('\*\*(?!\*)(.+?)\*\*'),
	'underline':  re.compile('__(?!_)(.+?)__'),
	'strike':     re.compile('~~(?!~)(.+?)~~'),
	'verbatim':   re.compile("''(?!')(.+?)''"),
}

dumper_tags = {
	'italic':    '/',
	'bold':      '*',
	'underline': '_',
	'strike':    '~',
	'verbatim':  "'",
}

class Parser(ParserClass):

	def parse(self, input):
		# Read the file and divide into paragraphs on the fly.
		# Blocks of empty lines are also treated as paragraphs for now.
		# We also check for blockquotes here and avoid splitting them up.
		assert isinstance(input, (File, Buffer))
		file = input.open('r')

		paras = ['']
		def para_start():
			# This function is called when we suspect the start of a new paragraph.
			# Returns boolean for success
			if len(paras[-1]) == 0:
				return False
			blockmatch = parser_re['blockstart'].search(paras[-1])
			if blockmatch:
				quote = blockmatch.group()
				blockend = re.search('\n'+quote+'\s*\Z', paras[-1])
				if not blockend:
					# We are in a block that is not closed yet
					return False
			# Else append empty paragraph to start new para
			paras.append('')
			return True

		para_isspace = False
		for line in file:
			# Try start new para when switching between text and empty lines or back
			if line.isspace() != para_isspace:
				if para_start():
					para_isspace = line.isspace() # decide type of new para
			paras[-1] += line

		# Now all text is read, start wrapping it into a document tree.
		# First check for meta data at the top of the file
		tree = NodeTree()
		if self.matches_headers(paras[0]):
			headers = paras.pop(0)
			tree.headers = self.parse_headers( headers )
			if paras[0].isspace: paras.pop(0)

		# Then continue with all other contents
		# Headings can still be in the middle of a para, so get them out.
		for para in paras:
			if parser_re['blockstart'].search(para):
				tree.append( self.parse_block(para) )
			else:
				parts = parser_re['splithead'].split(para)
				for i, p in enumerate(parts):
					if i % 2:
						# odd elements in the list are headings after split
						tree.append( self.parse_head(p) )
					elif len(p) > 0:
						tree.append( self.parse_para(p) )

		file.close()
		return tree

	def parse_block(self, block):
		m = parser_re['Verbatim'].match(block)
		assert m, 'Block does not match Verbatim'
		return TextNode(m.group(1), style='Verbatim')

	def parse_head(self, head):
		m = parser_re['heading'].match(head)
		assert m, 'Line does not match a heading: '+head
		level = 7 - min(6, len(m.group(2)))
		head = m.group(3)
		node = HeadingNode(level, head)
		return node

	def parse_para(self, para):
		if para.isspace():
			return TextNode(para)

		list = [para]
		list = self.walk_list(
				list, parser_re['verbatim'],
				lambda match: TextNode(match, style='verbatim') )

		def parse_link(match):
			parts = match.split('|', 2)
			link = parts[0]
			if len(parts) > 1:
				text = parts[1]
			else:
				text = link
			if len(link) == 0: # [[|link]] bug
					link = text
			#if email_re.match(link) and not link.startswith('mailto:'):
			#		link = 'mailto:'+link
			return LinkNode(text, link=link)

		list = self.walk_list(list, parser_re['link'], parse_link)

		def parse_image(match):
			parts = match.split('|', 2)
			src = parts[0]
			if len(parts) > 1:
				text = parts[1]
			else:
				text = None
			return ImageNode(src, text=text)

		list = self.walk_list(list, parser_re['image'], parse_image)

		for style in 'italic', 'bold', 'underline', 'strike':
			list = self.walk_list(
					list, parser_re[style],
					lambda match: TextNode(match, style=style) )

		# TODO: urls

		for i, v in enumerate(list):
			if not isinstance(v, TextNode):
				list[i] = TextNode(v)

		return NodeList(list)


class Dumper(DumperClass):
	'''FIXME'''

	def dump(self, tree, output):
		'''FIXME'''
		assert isinstance(tree, NodeTree)
		assert isinstance(output, (File, Buffer))
		file = output.open('w')

		file.write( self.dump_headers(tree.headers) )
		for node in tree.walk():
			if isinstance(node, HeadingNode):
				tag = '='*(7-node.level)
				file.write(tag+' '+node.string+' '+tag+'\n')
			elif isinstance(node, ImageNode):
				if node.string:
					file.write('{{'+node.src+'|'+node.string+'}}')
				else:
					file.write('{{'+node.src+'}}')
			elif isinstance(node, LinkNode):
				if node.link == node.string:
					file.write('[['+node.link+']]')
				else:
					file.write('[['+node.link+'|'+node.string+']]')
			elif isinstance(node, TextNode):
				if node.style is None:
					file.write(node.string)
				elif node.style == 'Verbatim':
					file.write("'''\n"+node.string+"'''\n")
				else:
					tag = dumper_tags[node.style]
					file.write(tag*2+node.string+tag*2)
			else:
				assert False, 'Unknown node type: '+node.__str__()

		file.close()

