# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module supports dumping to HTML'''

# TODO paragraph indenting using margin CSS ?
# TODO use global CSS for checkboxes instead of inline style - needs also support from tempalte etc

import re

from zim.formats import *
from zim.parsing import TextBuffer, link_type

info = {
	'name':  'Html',
	'mime':  'text/html',
	'extension': 'html',
	'read':	  False,
	'write':  False,
	'import': False,
	'export': True,
}


def html_encode(text):
	if not text is None:
		text = text.replace('&', '&amp;')
		text = text.replace('<', '&lt;')
		text = text.replace('>', '&gt;')
		return text
	else:
		return ''


_indent_re = re.compile('^(\t+)', re.M)

def _replace_indent(match):
	return '&nbsp;' * len(match.group(1)) * 4

def encode_whitespace(text):
	if not text is None:
		text = text.replace('\n', '<br>\n')
		text = _indent_re.sub(_replace_indent, text)
		return text
	else:
		return ''


class Dumper(DumperClass):

	def dump(self, tree):
		assert isinstance(tree, ParseTree)
		assert self.linker, 'HTML dumper needs a linker object'
		self.linker.set_usebase(True)
		output = TextBuffer()
		self._dump_children(tree.getroot(), output, istoplevel=True)
		return output.get_lines(end_with_newline=not tree.ispartial)

	def _dump_children(self, list, output, istoplevel=False):
		for element in list.getchildren():
			text = html_encode(element.text)
			if not element.tag == 'pre':
				# text that goes into the element
				# always encode excepts for <pre></pre>
				text = encode_whitespace(text)

			if element.tag == 'h':
				tag = 'h' + str(element.attrib['level'])
				if self.isrtl(element):
					output += ['<', tag, ' dir=\'rtl\'>', text, '</', tag, '>']
				else:
					output += ['<', tag, '>', text, '</', tag, '>']
			elif element.tag in ('p', 'div'):
				tag = element.tag
				if self.isrtl(element):
					tag += ' dir=\'rtl\''
				if 'indent' in element.attrib:
					level = int(element.attrib['indent'])
					tag += ' style=\'padding-left: %ipt\'' % (30 * level)
				output += ['<', tag, '>\n', text]
				self._dump_children(element, output) # recurs
				output.append('</%s>\n' % element.tag)
			elif element.tag == 'pre':
				tag = 'pre'
				if self.isrtl(element):
					tag += ' dir=\'rtl\''
				if 'indent' in element.attrib:
					level = int(element.attrib['indent'])
					tag += ' style=\'padding-left: %ipt\'' % (30 * level)
				output += ['<', tag, '>\n', text, '</pre>\n']
			elif element.tag is 'ul':
				tag = 'ul'
				if 'indent' in element.attrib:
					level = int(element.attrib['indent'])
					tag += ' style=\'padding-left: %ipt\'' % (30 * level)
				output += ['<' + tag + '>\n', text]
				self._dump_children(element, output) # recurs
				output.append('</ul>\n')
			elif element.tag == 'li':
				if 'bullet' in element.attrib and element.attrib['bullet'] != '*':
					icon = self.linker.icon(element.attrib['bullet'])
					output += ['<li style="list-style-image: url(%s)">' % icon, text]
				else:
					output += ['<li>', text]
				self._dump_children(element, output) # recurs
				output.append('</li>\n')
			elif element.tag == 'img':
				src = self.linker.img(element.attrib['src'])
				opt = ''
				for o in ('width', 'height'):
					if o in element.attrib and int(float(element.attrib[o])) > 0:
						opt = ' %s="%s"' % (o, element.attrib[o])
				output.append('<img src="%s" alt="%s"%s>' % (src, text, opt))
			elif element.tag == 'link':
				href = self.linker.link(element.attrib['href'])
				title = text.replace('"', '&quot;')
				output.append('<a href="%s" title="%s">%s</a>' % (href, title, text))
			elif element.tag in ['emphasis', 'strong', 'mark', 'strike', 'code','sub','sup']:
				if element.tag == 'mark': tag = 'u'
				elif element.tag == 'emphasis': tag = 'em'
				else: tag = element.tag
				output += ['<', tag, '>', text, '</', tag, '>']
			elif element.tag == 'tag':
				output += ['<span class="zim-tag">', text, '</span>']
			else:
				assert False, 'Unknown node type: %s' % element

			if not element.tail is None:
				tail = html_encode(element.tail)
				if not (istoplevel and tail.isspace()):
					# text in between elements, skip encoding
					# for whitespace between headings, paras etc.
					tail = encode_whitespace(tail)
				output.append(tail)


