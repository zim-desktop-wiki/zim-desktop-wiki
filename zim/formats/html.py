# -*- coding: utf-8 -*-

# Copyright 2008-2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module supports dumping to HTML'''

# TODO paragraph indenting using margin CSS ?
# TODO use global CSS for checkboxes instead of inline style - needs also support from tempalte etc

import re
import string

from zim.formats import *
from zim.parsing import TextBuffer, link_type
from zim.config.dicts import Choice


info = {
	'name': 'html',
	'desc': 'HTML',
	'mimetype': 'text/html',
	'extension': 'html',
	'native': False,
	'import': False,
	'export': True,
	'usebase': True,
}


def html_encode(text):
	if not text is None:
		text = text.replace('&', '&amp;')
		text = text.replace('<', '&lt;')
		text = text.replace('>', '&gt;')
		return text
	else:
		return ''


class Dumper(DumperClass):

	TAGS = {
		EMPHASIS:		('<i>', '</i>'),
		STRONG: 		('<b>', '</b>'),
		MARK:			('<u>', '</u>'),
		STRIKE: 		('<s>', '</s>'),
		VERBATIM:		('<tt>', '</tt>'),
		TAG:			('<span class="zim-tag">', '</span>'),
		SUBSCRIPT:		('<sub>', '</sub>'),
		SUPERSCRIPT:	('<sup>', '</sup>'),

	}

	TEMPLATE_OPTIONS = {
		'empty_lines': Choice('default', ('default', 'remove')),
		'line_breaks': Choice('default', ('default', 'remove')),
	}

	def dump(self, tree):
		# FIXME should be an init function for this
		self._isrtl = None
		return DumperClass.dump(self, tree)

	def encode_text(self, tag, text):
		# if _isrtl is already set the direction was already
		# determined for this section
		if self._isrtl is None and not text.isspace():
			self._isrtl = self.isrtl(text)

		text = html_encode(text)
		if tag not in (VERBATIM_BLOCK, VERBATIM, OBJECT) \
		and not self.template_options['line_breaks'] == 'remove':
			text = text.replace('\n', '<br>\n')

		return text

	def text(self, text):
		if self.context[-1].tag == FORMATTEDTEXT \
		and	text.isspace():
			# Reduce top level empty lines
			if self.template_options['empty_lines'] == 'remove':
				self.context[-1].text.append('\n')
			else:
				l = text.count('\n') - 1
				if l > 0:
					self.context[-1].text.append('\n' + ('<br>\n' * l) + '\n')
				elif l == 0:
					self.context[-1].text.append('\n')
		else:
			DumperClass.text(self, text)

	def dump_h(self, tag, attrib, strings):
		h = 'h' + str(attrib['level'])
		if self._isrtl:
			start = '<' + h + ' dir=\'rtl\'>'
		else:
			start = '<' + h + '>'
		self._isrtl = None # reset
		end = '</' + h + '>\n'
		strings.insert(0, start)
		strings.append(end)
		return strings

	def dump_block(self, tag, attrib, strings, _extra=None):
		if strings and strings[-1].endswith('<br>\n'):
			strings[-1] = strings[-1][:-5]
		elif strings and strings[-1].endswith('\n'):
			strings[-1] = strings[-1][:-1]

		start = '<' + tag
		if self._isrtl:
			start += ' dir=\'rtl\''
		self._isrtl = None # reset

		if 'indent' in attrib:
			level = int(attrib['indent'])
			start += ' style=\'padding-left: %ipt\'' % (30 * level)

		if _extra:
			start += ' ' + _extra
		start += '>\n'

		if tag in ('ul', 'ol'):
			end = '</' + tag + '>\n'

			if strings:
				# close last <li> element
				strings.append('</li>\n')

			if self.context[-1].tag in ('ul', 'ol'):
				# Nested list
				start = '\n' + start
		else:
			end = '\n</' + tag + '>\n'

		strings.insert(0, start)
		strings.append(end)
		return strings

	dump_p = dump_block
	dump_div = dump_block
	dump_pre = dump_block
	dump_ul = dump_block

	def dump_ol(self, tag, attrib, strings):
		myattrib = ''
		if 'start' in attrib:
			start = attrib['start']
			if start in string.lowercase:
				type = 'a'
				start = string.lowercase.index(start) + 1
			elif start in string.uppercase:
				type = 'A'
				start = string.uppercase.index(start) + 1
			else:
				type = '1'
			return self.dump_block(tag, attrib, strings,
				_extra='type="%s" start="%s"' % (type, start) )
		else:
			return self.dump_block(tag, attrib, strings)

	def dump_li(self, tag, attrib, strings):
		bullet = attrib.get('bullet', BULLET)
		if self.context[-1].tag == BULLETLIST and bullet != BULLET:
			start = '<li class="%s"' % bullet
		else:
			start = '<li'

		if self._isrtl:
			start += ' dir=\'rtl\'>'
		else:
			start += '>'
		self._isrtl = None # reset

		strings.insert(0, start)

		if self.context[-1].text:
			# we are not the first <li> element, close previous
			strings.insert(0, '</li>\n')

		return strings

	def dump_link(self, tag, attrib, strings=None):
		href = self.linker.link(attrib['href'])
		type = link_type(attrib['href'])
		if strings:
			text = u''.join(strings)
		else:
			text = attrib['href']
		title = text.replace('"', '&quot;')
		return [
			'<a href="%s" title="%s" class="%s">%s</a>'
				% (href, title, type, text) ]

	def dump_img(self, tag, attrib, strings=None):
		src = self.linker.img(attrib['src'])
		opt = ''
		if 'alt' in attrib:
			opt += ' alt="%s"' % html_encode(attrib['alt']).replace('"', '&quot;')
		for o in ('width', 'height'):
			if o in attrib and int(float(attrib[o])) > 0:
				opt += ' %s="%s"' % (o, attrib[o])
		if 'href' in attrib:
			href = self.linker.link(attrib['href'])
			return ['<a href="%s"><img src="%s"%s></a>' % (href, src, opt)]
		else:
			return ['<img src="%s"%s>' % (src, opt)]

	def dump_object(self, *arg, **kwarg):
		strings = DumperClass.dump_object(self, *arg, **kwarg)
		strings.insert(0, '<div class="zim-object">\n')
		strings.append('</div>\n')
		return strings

	def dump_object_fallback(self, tag, attrib, strings=None):
		# Fallback to verbatim paragraph
		strings.insert(0, '<pre>\n')
		strings.append('</pre>\n')
		return strings

		# TODO put content in attrib, use text for caption (with full recursion)
		# See img
