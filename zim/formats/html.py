# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''FIXME

We do not put pagebreaks in normal paragraphs. Use the following
CSS in your template if you want to preserve tabs and linebreaks.

	<style>
		p {white-space:pre;}
	</style>

'''

from zim.fs import *
from zim.formats import *

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


class Dumper(DumperClass):

	def dump(self, tree, output):
		assert isinstance(tree, ParseTree)
		assert isinstance(output, (File, Buffer))
		file = output.open('w')
		self.dump_children(tree.getroot(), file, top=True)
		file.close()

	def dump_children(self, list, file, top=False):
		'''FIXME'''
		for element in list.getchildren():
			text = html_encode(element.text)

			if element.tag == 'p':
				file.write('<p>\n')
				if text:
					file.write(text)
				self.dump_children(element, file) # recurs
				file.write('</p>\n')
			elif element.tag == 'h':
				tag = 'h' + str(element.attrib['level'])
				file.write('<'+tag+'>'+text+'</'+tag+'>')
			elif element.tag == 'pre':
				file.write('<pre>\n'+text+'</pre>\n')
			elif element.tag == 'img':
				src = url_encode(element.attrib['src'])
				file.write('<img src="%s" alt="%s">' % (src, text))
			elif element.tag == 'link':
				href = url_encode(element.attrib['href'])
				file.write('<link href="%s">%s</link>' % (href, text))
			elif element.tag in ['em', 'strong', 'mark', 'strike', 'code']:
				if element.tag == 'mark': tag = 'u'
				else: tag = element.tag
				file.write('<'+tag+'>'+text+'</'+tag+'>')
			else:
				assert False, 'Unknown node type: '+node.__str__()

			if not element.tail is None:
				tail = html_encode(element.tail)
				file.write(tail)
