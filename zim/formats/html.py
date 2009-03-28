# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

# TODO paragraph indenting using margin CSS ?
# TODO use global CSS for checkboxes instead of inline style - needs also support from tempalte etc

import re

from zim.formats import *
from zim.config import data_file
from zim.parsing import TextBuffer, link_type

info = {
	'name':  'Html',
	'mime':  'text/html',
	'read':	  False,
	'write':  False,
	'import': False,
	'export': True,
}


def url_encode(link):
	if not link is None:
		link.replace(' ', '%20')
		# FIXME what other chars do we need ?
		return link
	else:
		return ''


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
		output = TextBuffer()
		self._dump_children(tree.getroot(), output, istoplevel=True)
		return output.get_lines()

	def _dump_children(self, list, output, istoplevel=False):
		'''FIXME'''

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
				if self.isrtl(element):
					output += ['<p dir=\'rtl\'>\n', text]
				else:
					output += ['<p>\n', text]
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
				if 'bullet' in element.attrib:
					icon = self.icon(element.attrib['bullet'])
					output += ['<li style="list-style-image: url(%s)">' % icon, text]
				else:
					output += ['<li>', text]
				self._dump_children(element, output) # recurs
				output.append('</li>\n')
			elif element.tag == 'img':
				src = self.href(element.attrib['src'])
				output.append('<img src="%s" alt="%s">' % (src, text))
			elif element.tag == 'link':
				href = self.href(element.attrib['href'])
				output.append('<a href="%s">%s</a>' % (href, text))
			elif element.tag in ['em', 'strong', 'mark', 'strike', 'code']:
				if element.tag == 'mark': tag = 'u'
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

	def href(self, href):
		# TODO need a way to set a base url (+ seperate base for files for www server)
		# TODO use link object if available
		type = link_type(href)
		if type == 'page':
			href = href.replace(':', '/') + '.html'
			if not href.startswith('/'):
				href = '/' + href
		elif type == 'file':
			pass # TODO parse file links for html output
		elif type == 'mailto':
			if not href.startswith('mailto:'):
				href = 'mailto:' + link
		else:
			pass # I dunno, some url ?

		return url_encode(href)

	def icon(self, name):
		return data_file('pixmaps/%s.png' % name)
		#return '/+icon/' + name + '.png'
