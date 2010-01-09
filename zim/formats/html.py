# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''This module supports dumping to HTML'''

# TODO paragraph indenting using margin CSS ?
# TODO use global CSS for checkboxes instead of inline style - needs also support from tempalte etc

import re

from zim.formats import *
from zim.parsing import TextBuffer, link_type, url_encode

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
		return output.get_lines()

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
			elif element.tag == 'p':
				tag = 'p'
				if self.isrtl(element):
					tag += ' dir=\'rtl\''
				if 'indent' in element.attrib:
					level = int(element.attrib['indent'])
					tag += ' style=\'padding-left: %ipt\'' % (30 * level)
				output += ['<', tag, '>\n', text]
				self._dump_children(element, output) # recurs
				output.append('</p>\n')
			elif element.tag == 'pre':
				if self.isrtl(element):
					output += ['<pre dir=\'rtl\'>\n', text, '</pre>\n']
				else:
					output += ['<pre>\n', text, '</pre>\n']
			elif element.tag is 'ul':
				output += ['<ul>\n', text]
				self._dump_children(element, output) # recurs
				output.append('</ul>\n')
			elif element.tag == 'li':
				if 'bullet' in element.attrib and element.attrib['bullet'] != '*':
					icon = url_encode(self.linker.icon(element.attrib['bullet']))
					output += ['<li style="list-style-image: url(%s)">' % icon, text]
				else:
					output += ['<li>', text]
				self._dump_children(element, output) # recurs
				output.append('</li>\n')
			elif element.tag == 'img':
				src = url_encode(self.linker.img(element.attrib['src']))
				opt = ''
				for o in ('width', 'height'):
					if o in element.attrib and int(element.attrib[o]) > 0:
						opt = ' %s="%s"' % (o, element.attrib[o])
				output.append('<img src="%s" alt="%s"%s>' % (src, text, opt))
			elif element.tag == 'link':
				href = url_encode(self.linker.link(element.attrib['href']))
				title = text.replace('"', '&quot;')
				output.append('<a href="%s" title="%s">%s</a>' % (href, title, text))
			elif element.tag in ['emphasis', 'strong', 'mark', 'strike', 'code']:
				if element.tag == 'mark': tag = 'u'
				elif element.tag == 'emphasis': tag = 'em'
				else: tag = element.tag
				output += ['<', tag, '>', text, '</', tag, '>']
			else:
				assert False, 'Unknown node type: %s' % element

			if not element.tail is None:
				tail = html_encode(element.tail)
				if not (istoplevel and tail.isspace()):
					# text in between elements, skip encoding
					# for whitespace between headings, paras etc.
					tail = encode_whitespace(tail)
				output.append(tail)


