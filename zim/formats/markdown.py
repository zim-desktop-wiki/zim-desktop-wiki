# -*- coding: utf-8 -*-

# Copyright 2012,2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module handles dumping markdown text with pandoc extensions'''

# OPEN ISSUES
# - how to deal with indented paragraphs ?
#   in pandoc indent is verbatim, so now all indent is dropped
# - how to deal with image re-size ?
# - how to deal with tags / anchors ?
# - check does zim always produce a blank line before a heading ?
# - add \ before line ends to match line breaks from user

import re

from zim.formats import *
from zim.parsing import url_re
from zim.formats.plain import Dumper as TextDumper


info = {
	'name': 'markdown',
	'desc': 'Markdown Text (pandoc)',
	'mimetype': 'text/x-markdown',
	'extension': 'markdown',
		# No official file extension, but this is often used
	'native': False,
	'import': False,
	'export': True,
	'usebase': True,
}



class Dumper(TextDumper):
	# Inherit from wiki format Dumper class, only overload things that
	# are different

	BULLETS = {
		UNCHECKED_BOX:	u'* \u2610',
		XCHECKED_BOX:	u'* \u2612',
		CHECKED_BOX:	u'* \u2611',
		BULLET:			u'*',
	}

	TAGS = {
		EMPHASIS:		('*', '*'),
		STRONG:			('**', '**'),
		MARK:			('__', '__'), # OPEN ISSUE: not availalbe in pandoc
		STRIKE:			('~~', '~~'),
		VERBATIM:		("``", "``"),
		TAG:			('', ''), # No additional annotation (apart from the visible @)
		SUBSCRIPT:		('~', '~'),
		SUPERSCRIPT:	('^', '^'),
	}

	def dump(self, tree):
		assert self.linker, 'Markdown dumper needs a linker object'
		return TextDumper.dump(self, tree)

	def dump_indent(self, tag, attrib, strings):
		# OPEN ISSUE: no indent for para
		return strings

	dump_p = dump_indent
	dump_div = dump_indent

	def dump_list(self, tag, attrib, strings):
		# OPEN ISSUE: no indent for lists
		if 'indent' in attrib:
			del attrib['indent']
		strings = TextDumper.dump_list(self, tag, attrib, strings)

		if self.context[-1].tag in (BULLETLIST, NUMBEREDLIST):
			# sub-list
			return strings
		else:
			# top level list, wrap in empty lines
			strings.insert(0, '\n')
			strings.append('\n')
			return strings

	dump_ul = dump_list
	dump_ol = dump_list

	def dump_pre(self, tag, attrib, strings):
		# OPEN ISSUE: no indent for verbatim blocks
		return self.prefix_lines('\t', strings)

	def dump_link(self, tag, attrib, strings=None):
		assert 'href' in attrib, \
			'BUG: link misses href: %s "%s"' % (attrib, strings)
		href = self.linker.link(attrib['href'])
		text = u''.join(strings) or href
		if href == text and url_re.match(href):
			return ['<', href, '>']
		else:
			return ['[%s](%s)' % (text, href)]

	def dump_img(self, tag, attrib, strings=None):
		# OPEN ISSUE: image properties used in zim not supported in pandoc
		src = self.linker.img(attrib['src'])
		text = attrib.get('alt', '')
		return ['![%s](%s)' % (text, src)]

	def dump_object_fallback(self, tag, attrib, strings=None):
		# dump object as verbatim block
		return self.prefix_lines('\t', strings)


