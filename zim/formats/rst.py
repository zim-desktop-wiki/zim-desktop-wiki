# -*- coding: utf-8 -*-

# Copyright 2012 Yao-Po Wang <blue119@gmail.com>
# Copyright 2013 Jaap Karssenberg <jaap.karssenberg@gmail.com>


'''This module handles dumping reStructuredText with sphinx extensions'''

from zim.formats import *
from zim.formats.plain import Dumper as TextDumper

info = {
	'name': 'reST',
	'desc': 'reST (Octopress)',
	'mimetype': 'text/x-rst',
	'extension': 'rst',
		# No official file extension, but this is often used
	'native': False,
	'import': False,
	'export': True,
	'usebase': True,
}


class Dumper(TextDumper):

	BULLETS = {
		UNCHECKED_BOX:	u'- \u2610',
		XCHECKED_BOX:	u'- \u2612',
		CHECKED_BOX:	u'- \u2611',
		BULLET:		u'-',
	}

	TAGS = {
		EMPHASIS:	('*', '*'),
		STRONG:		('**', '**'),
		MARK:		('', ''), # TODO, no directly way to do this in rst
		STRIKE:		('', ''), # TODO, no directly way to do this in rst
		VERBATIM:	("``", "``"),
		TAG:		('', ''), # No additional annotation (apart from the visible @)
		SUBSCRIPT:	('\\ :sub:`', '`\\ '),
		SUPERSCRIPT:	('\\ :sup:`', '`\\ '),
	}
	# TODO tags other than :sub: and :sup: may also need surrounding whitespace, deal with this in post process (join) action ?
	# IDEM for blocks like images and objects, how to enforce empty lines and how to deal with inline images..

	HEADING_UNDERLINE = ['=', '-', '^', '"']

	def dump(self, tree):
		assert self.linker, 'rst dumper needs a linker object'
		return TextDumper.dump(self, tree)

	def dump_h(self, tag, attrib, strings):
		# Underlined headings
		level = int(attrib['level'])
		if level < 1:   level = 1
		elif level > 4: level = 4
		char = self.HEADING_UNDERLINE[level-1]
		heading = u''.join(strings)
		underline = char * len(heading)
		return [heading + '\n', underline]

	def dump_pre(self, tag, attrib, strings):
		# prefix last line with "::\n\n"
		# indent with \t to get preformatted
		strings = self.prefix_lines('\t', strings)
		strings.insert(0, '::\n\n')
		return strings

	def dump_link(self, tag, attrib, strings=None):
		# Use inline url form, putting links at the end is more difficult
		assert 'href' in attrib, \
			'BUG: link misses href: %s "%s"' % (attrib, strings)
		href = self.linker.link(attrib['href'])
		text = u''.join(strings) or href
		return '`%s <%s>`_' % (text, href)

	def dump_img(self, tag, attrib, strings=None):
		src = self.linker.img(attrib['src'])
		text = '.. image:: %s\n' % src

		items = attrib.items()
		items.sort() # unit tests don't like random output
		for k, v in items:
			if k == 'src' or k.startswith('_'):
				continue
			elif v: # skip None, "" and 0
				text += '   :%s: %s\n' % (k, v)

		return text + '\n'

		# TODO use text for caption (with full recursion)
		# can be done using "figure" directive

	dump_object_fallback = dump_pre


	def dump_table(self, tag, attrib, strings):
		aligns = attrib['cols'].split(',')
		single_headers = strings[0]  # single line headers
		header_length = len(single_headers) # number of columns
		single_rows = strings[1::]  # body rows which are on a single-line
		maxwidths = []  # character width of each column
		rows = [] # normalized rows
		table = []  # result table

		# be aware of linebreaks within cells
		headers_list = [cell.split("\n") for cell in single_headers]
		header_lines = map(lambda *x: map(lambda e: e if e is not None else '', x), *headers_list)  # transpose h_list
		for single_row in single_rows:
			row_list = [cell.split("\n") for cell in single_row]
			rows.append(map(lambda *x: map(lambda e: e if e is not None else '', x), *row_list)) # transpose r_list

		for i in range(header_length):  # calculate maximum widths of columns
			header_max_characters = max([len(r[i]) for r in header_lines])
			row_max_characters = max([len(r[i]) for rowline in rows for r in rowline])
			maxwidths.append(max(0, header_max_characters, row_max_characters))

		# helper functions
		def rowsep(y='-', x='+'):  # example: rowsep('-', '+') -> +-----+--+
			return x + x.join(map(lambda width: (width+2) * y, maxwidths)) + x

		def rowline(row, x='|', y=' '):  # example: rowline(['aa',''], '+','-') -> +-aa--+--+
			cells = []
			for i, val in enumerate(row):
				align = aligns[i]
				if align == 'left':
					(lspace, rspace) = (1, maxwidths[i] - len(val) + 1)
				elif align == 'right':
					(lspace, rspace) = (maxwidths[i] - len(val) + 1, 1)
				elif align == 'center':
					lspace = (maxwidths[i] - len(val)) / 2 + 1
					rspace = (maxwidths[i] - lspace - len(val) + 2)
				else:
					(lspace, rspace) = (1, maxwidths[i] - len(val) + 1)
				cells.append(lspace * y + val + rspace * y)
			return x + x.join(cells) + x

		# print table
		table.append(rowsep('-'))
		table += [rowline(line) for line in header_lines]
		table.append(rowsep('='))
		for row in rows:
			table += [rowline(line) for line in row]
			table.append(rowsep('-'))
		return map(lambda line: line+"\n", table)

	def dump_thead(self, tag, attrib, strings):
		return [strings]

	def dump_th(self, tag, attrib, strings):
		return strings

	def dump_trow(self, tag, attrib, strings):
		return [strings]

	def dump_td(self, tag, attrib, strings):
		if len(strings) > 1:
			return [''.join(strings)]
		return strings
