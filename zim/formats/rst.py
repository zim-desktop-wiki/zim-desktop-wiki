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
