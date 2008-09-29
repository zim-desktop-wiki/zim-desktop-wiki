# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import re

from zim.formats import *

__format__ = 'wiki'

class Parser(ParserClass):

	def parse(self, file):
		# Read the file and divide into paragraphs on the fly.
		# Blocks of empty lines are also treated as paragraphs for now.
		# We also check for blockquotes here and avoid splitting them up.

		paras = ['']
		blockstart = re.compile("\A(''')\s*?\n")

		def para_start():
			# This function is called when we suspect the start of a new paragraph.
			# Returns boolean for success
			if len(paras[-1]) == 0:
				return False
			blockmatch = blockstart.search(paras[-1])
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
		heading = re.compile('^(==+\s+\S.*?\n)', re.M)
		for para in paras:
			if blockstart.search(para):
				tree.append( self.parse_block(para) )
			else:
				parts = heading.split(para)
				for i, p in enumerate(parts):
					if i % 2:
						# odd elements in the list are headings after split
						tree.append( self.parse_head(p) )
					elif len(p) > 0:
						tree.append( self.parse_para(p) )

		return tree

	def parse_block(self, block):
		m = re.match("\A'''\s*?(^.*?)^'''\s*\Z", block, re.M | re.S)
		if not m:
			raise ParserError(block, 'does not match Verbatim')
		return TextNode(m.group(1), style='Verbatim')

	def parse_head(self, head):
		m = re.match("\A(==+)\s+(.*?)(\s+==+)?\s*\Z", head)
		if not m:
			raise ParserError(head, 'does not match a heading')
		level = 7 - len( m.group(1) )
		head = m.group(2)
		return TextNode(head, style='head'+str(level))

	tags = {
		'italic':    '/',
		'bold':      '*',
		'underline': '_',
		'strike':    '~',
		'verbatim':  "'",
	}

	def parse_para(self, para):
		if para.isspace():
			return TextNode(para)

		def style_re(style):
			t = self.tags[style]
			return re.compile(('\\'+t)*2+'(?!\\'+t+')(.+?)'+('\\'+t)*2)

		list = [para]

		list = self.walk_list(
						list, style_re('verbatim'),
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

		list = self.walk_list(list, re.compile('\[\[(?!\[)(.+?)\]\]'), parse_link)

		# TODO: images

		for style in 'italic', 'bold', 'underline', 'strike':
			list = self.walk_list(
						list, style_re(style),
						lambda match: TextNode(match, style=style) )

		# TODO: urls

		for i, v in enumerate(list):
			if not isinstance(v, TextNode):
				list[i] = TextNode(v)

		return NodeList(list)

class Dumper(DumperClass):
	'''FIXME'''

	def dump(self, tree, file):
		'''FIXME'''
		print >>file, 'TODO'
