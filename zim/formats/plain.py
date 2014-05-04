# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module handles parsing and dumping input in plain text'''

import re

import zim.parser
from zim.parser import prepare_text, Rule

from zim.formats import *
from zim.parsing import url_re


info = {
	'name': 'plain',
	'desc': 'Plain text',
	'mimetype': 'text/plain',
	'extension': 'txt',
	'native': False,
	'import': True,
	'export': True,
	'usebase': True,
}


class Parser(ParserClass):

	# TODO parse constructs like *bold* and /italic/ same as in email,
	# but do not remove the "*" and "/", just display text 1:1

	# TODO also try at least to parse bullet and checkbox lists
	# common base class with wiki format

	# TODO parse markdown style headers

	def parse(self, input, partial=False):
		if not isinstance(input, basestring):
			input = ''.join(input)

		if not partial:
			input = prepare_text(input)

		parser = zim.parser.Parser(
			Rule(LINK, url_re.r, process=self.parse_url) # FIXME need .r atribute because url_re is a Re object
		)

		builder = ParseTreeBuilder(partial=partial)
		builder.start(FORMATTEDTEXT)
		parser(builder, input)
		builder.end(FORMATTEDTEXT)
		return builder.get_parsetree()

	@staticmethod
	def parse_url(builder, text):
		builder.append(LINK, {'href': text}, text)


class Dumper(DumperClass):

	# We dump more constructs than we can parse. Reason for this
	# is to ensure dumping a page to plain text will still be
	# readable.

	BULLETS = {
		UNCHECKED_BOX:	u'[ ]',
		XCHECKED_BOX:	u'[x]',
		CHECKED_BOX:	u'[*]',
		BULLET:			u'*',
	}

	# No additional formatting for these tags, otherwise copy-pasting
	# as plain text is no longer plain text
	TAGS = {
		EMPHASIS:		('', ''),
		STRONG:			('', ''),
		MARK:			('', ''),
		STRIKE:			('', ''),
		VERBATIM:		('', ''),
		TAG:			('', ''),
		SUBSCRIPT:		('', ''),
		SUPERSCRIPT:	('', ''),
	}

	def dump_indent(self, tag, attrib, strings):
		# Prefix lines with one or more tabs
		if attrib and 'indent' in attrib:
			prefix = '\t' * int(attrib['indent'])
			return self.prefix_lines(prefix, strings)
			# TODO enforces we always end such a block with \n unless partial
		else:
			return strings

	dump_p = dump_indent
	dump_div = dump_indent
	dump_pre = dump_indent

	def dump_h(self, tag, attrib, strings):
		# Markdown style headers
		level = int(attrib['level'])
		if level < 1:   level = 1
		elif level > 5: level = 5

		if level in (1, 2):
			# setext-style headers for lvl 1 & 2
			if level == 1: char = '='
			else: char = '-'
			heading = u''.join(strings)
			underline = char * len(heading)
			return [heading + '\n', underline]
		else:
			# atx-style headers for deeper levels
			tag = '#' * level
			strings.insert(0, tag + ' ')
			return strings

	def dump_list(self, tag, attrib, strings):
		if 'indent' in attrib:
			# top level list with specified indent
			prefix = '\t' * int(attrib['indent'])
			return self.prefix_lines('\t', strings)
		elif self.context[-1].tag in (BULLETLIST, NUMBEREDLIST):
			# indent sub list
			prefix = '\t'
			return self.prefix_lines('\t', strings)
		else:
			# top level list, no indent
			return strings

	dump_ul = dump_list
	dump_ol = dump_list

	def dump_li(self, tag, attrib, strings):
		# Here is some logic to figure out the correct bullet character
		# depends on parent list element

		# TODO accept multi-line content here - e.g. nested paras

		if self.context[-1].tag == BULLETLIST:
			if 'bullet' in attrib \
			and attrib['bullet'] in self.BULLETS:
				bullet = self.BULLETS[attrib['bullet']]
			else:
				bullet = self.BULLETS[BULLET]
		elif self.context[-1].tag == NUMBEREDLIST:
			iter = self.context[-1].attrib.get('_iter')
			if not iter:
				# First item on this level
				iter = self.context[-1].attrib.get('start', 1)
			bullet = iter + '.'
			self.context[-1].attrib['_iter'] = increase_list_iter(iter) or '1'
		else:
			# HACK for raw tree from pageview
			# support indenting
			# support any bullet type (inc numbered)

			bullet = attrib.get('bullet', BULLET)
			if bullet in self.BULLETS:
				bullet = self.BULLETS[attrib['bullet']]
			# else assume it is numbered..

			if 'indent' in attrib:
				prefix = int(attrib['indent']) * '\t'
				bullet = prefix + bullet

		return (bullet, ' ') + tuple(strings) + ('\n',)

	def dump_link(self, tag, attrib, strings=None):
		# Just plain text, either text of link, or link href
		assert 'href' in attrib, \
			'BUG: link misses href: %s "%s"' % (attrib, strings)
		href = attrib['href']

		if strings:
			return strings
		else:
			return href

	def dump_img(self, tag, attrib, strings=None):
		# Just plain text, either alt text or src
		src = attrib['src']
		alt = attrib.get('alt')
		if alt:
			return alt
		else:
			return src

	def dump_object_fallback(self, tag, attrib, strings):
		return strings
