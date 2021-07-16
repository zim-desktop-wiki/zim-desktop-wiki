
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
from zim.parsing import url_re, escape_string
from zim.formats.plain import Dumper as TextDumper


info = {
	'name': 'markdown',
	'desc': 'Markdown Text (pandoc)',
	'mimetype': 'text/markdown',
	'extension': 'md', # Most common extention used on github.
	'native': False,
	'import': False,
	'export': True,
	'usebase': True,
}



class Dumper(TextDumper):
	# Inherit from wiki format Dumper class, only overload things that
	# are different

	BULLETS = {
		UNCHECKED_BOX: '* \u2610',
		XCHECKED_BOX: '* \u2612',
		CHECKED_BOX: '* \u2611',
		MIGRATED_BOX: '* \u25B7',
		BULLET: '*',
	}

	TAGS = {
		EMPHASIS: ('*', '*'),
		STRONG: ('**', '**'),
		MARK: ('__', '__'), # OPEN ISSUE: not available in pandoc
		STRIKE: ('~~', '~~'),
		VERBATIM: ("``", "``"),
		TAG: ('', ''), # No additional annotation (apart from the visible @)
		SUBSCRIPT: ('~', '~'),
		SUPERSCRIPT: ('^', '^'),
		LINE_RETURN: ('', ''), # TODO
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
		text = ''.join(strings) or href
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

	def dump_table(self, tag, attrib, strings):
		table = []  # result table
		rows = strings

		aligns, _wraps = TableParser.get_options(attrib)
		maxwidths = TableParser.width2dim(rows)
		headsep = TableParser.headsep(maxwidths, aligns, x='|', y='-')
		rowline = lambda row: TableParser.rowline(row, maxwidths, aligns)

		# print table
		table += [rowline(rows[0])]
		table.append(headsep)
		table += [rowline(row) for row in rows[1:]]
		return [line + "\n" for line in table]

	def dump_td(self, tag, attrib, strings):
		text = ''.join(strings) if strings else ''
		return [escape_string(text.replace('\n', '<br>'), '|')]

	dump_th = dump_td

	def dump_line(self, tag, attrib, strings=None):
		return '\n{}\n'.format('*' * 5)
