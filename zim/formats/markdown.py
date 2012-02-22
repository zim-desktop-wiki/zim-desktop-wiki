# -*- coding: utf-8 -*-

# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module handles dumping markdown text with pandoc extensions'''

# OPEN ISSUES
# - how to deal with underline ?
#   now rendering as bold
# - how to deal with indented paragraphs ?
#   in pandoc indent is verbatim
#   so now all indent is dropped
# - how to deal with image re-size ?
# - how to deal with tags / anchors ?
# - check does zim always produce a blank line before a heading ?

# TODO
# - links are not resolved at the moment -- need export linker
# - add \ before line ends to match line breaks from user

import re

from zim.formats import *
from zim.parsing import Re, TextBuffer, url_re


info = {
	'name': 'markdown',
	'desc': 'Markdown Text (pandoc)',
	'mimetype': 'text/x-markdown',
	'extension': 'markdown',
		# No official file extension, but this is often used
	'native': False,
	'import': False,
	'export': True,
}




TABSTOP = 4
bullet_re = u'[\\*\u2022]|\\[[ \\*x]\\]'
	# bullets can be '*' or 0x2022 for normal items
	# and '[ ]', '[*]' or '[x]' for checkbox items

bullets = {
	u'* \u2610': UNCHECKED_BOX,
	u'* \u2612': XCHECKED_BOX,
	u'* \u2611': CHECKED_BOX,
	'*': BULLET,
}

# reverse dict
bullet_types = {}
for bullet in bullets:
	bullet_types[bullets[bullet]] = bullet


dumper_tags = {
	'emphasis': '*',
	'strong':   '**',
	'mark':     '__', # OPEN ISSUE: not availalbe in pandoc
	'strike':   '~~',
	'code':     '``',
	'sub':      '~',
	'sup':      '^',
	'tag':      '', # No additional annotation (apart from the visible @)
}


class Dumper(DumperClass):

	def dump(self, tree):
		#~ print 'DUMP WIKI', tree.tostring()
		assert isinstance(tree, ParseTree)
		assert self.linker, 'Markdown dumper needs a linker object'
		self.linker.set_usebase(True)
		output = TextBuffer()
		self.dump_children(tree.getroot(), output)
		return output.get_lines(end_with_newline=not tree.ispartial)

	def dump_children(self, list, output, list_level=-1, list_type=None, list_iter='0'):
		if list.text:
			output.append(list.text)

		for element in list.getchildren():
			if element.tag in ('p', 'div'):
				indent = 0
				if 'indent' in element.attrib:
					indent = int(element.attrib['indent'])
				myoutput = TextBuffer()
				self.dump_children(element, myoutput) # recurs
				# OPEN ISSUE: no indent for para
				#if indent:
				#	myoutput.prefix_lines('\t'*indent)
				output.extend(myoutput)
			elif element.tag == 'h':
				level = int(element.attrib['level'])
				if level < 1:   level = 1
				elif level > 5: level = 5

				if level in (1, 2):
					# setext-style headers for lvl 1 & 2
					if level == 1: char = '='
					else: char = '-'
					heading = element.text
					line = char * len(heading)
					output.append(heading + '\n')
					output.append(line)
				else:
					# atx-style headers for deeper levels
					tag = '#' * level
					output.append(tag + ' ' + element.text)
			elif element.tag in ('ul', 'ol'):
				indent = int(element.attrib.get('indent', 0))
				start = element.attrib.get('start')
				myoutput = TextBuffer()
				self.dump_children(element, myoutput, list_level=list_level+1, list_type=element.tag, list_iter=start) # recurs
				# OPEN ISSUE: no indent for para
				#if indent:
				#	myoutput.prefix_lines('\t'*indent)
				if list_level == -1:
					# Need empty lines around lists in markdown
					output.append('\n')
					output.extend(myoutput)
					output.append('\n')
				else:
					output.extend(myoutput)
			elif element.tag == 'li':
				if 'indent' in element.attrib:
					# HACK for raw trees from pageview
					list_level = int(element.attrib['indent'])

				if list_type == 'ol':
					bullet = str(list_iter) + '.'
					list_iter = increase_list_iter(list_iter) or '1' # fallback if iter not valid
				else:
					bullet = bullet_types[element.attrib.get('bullet', BULLET)]
				output.append('\t'*list_level+bullet+' ')
				self.dump_children(element, output, list_level=list_level) # recurs
				output.append('\n')
			elif element.tag == 'pre':
				indent = 0
				if 'indent' in element.attrib:
					indent = int(element.attrib['indent'])
				myoutput = TextBuffer()
				myoutput.append(element.text)
				# OPEN ISSUE: no indent for para
				#if indent:
				#	myoutput.prefix_lines('\t'*indent)
				myoutput.prefix_lines('\t') # verbatim is always indented
				output.extend(myoutput)
			elif element.tag == 'link':
				assert 'href' in element.attrib, \
					'BUG: link %s "%s"' % (element.attrib, element.text)
				href = self.linker.link(element.attrib['href'])
				text = element.text or href
				if href == text and url_re.match(href):
					output.append('<' + href + '>')
				else:
					output.append('[%s](%s)' % (text, href))
			elif element.tag == 'img':
				src = self.linker.img(element.attrib['src'])
				# OPEN ISSUE: image properties used in zim not supported in pandoc
				#opts = []
				#items = element.attrib.items()
				# we sort params only because unit tests don't like random output
				#items.sort()
				#for k, v in items:
				#	if k == 'src' or k.startswith('_'):
				#		continue
				#	elif v: # skip None, "" and 0
				#		opts.append('%s=%s' % (k, v))
				#if opts:
				#	src += '?%s' % '&'.join(opts)

				text = element.text or ''
				output.append('![%s](%s)' % (text, src))
			elif element.tag in dumper_tags:
				if element.text:
					tag = dumper_tags[element.tag]
					output.append(tag + element.text + tag)
			else:
				assert False, 'Unknown node type: %s' % element

			if element.tail:
				output.append(element.tail)
