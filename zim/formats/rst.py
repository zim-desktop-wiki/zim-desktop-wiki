# -*- coding: utf-8 -*-

'''This module handles dumping reStructuredText with sphinx extensions'''

from zim.formats import *
from zim.parsing import TextBuffer

info = {
	'name': 'reST',
	'desc': 'reST (Octopress)',
	'mimetype': 'text/x-rst',
	'extension': 'rst',
		# No official file extension, but this is often used
	'native': False,
	'import': False,
	'export': True,
}

level_tag = ['=', '-', '^', '"']

TABSTOP = 4
bullet_re = u'[\\*\u2022]|\\[[ \\*x]\\]'
	# bullets can be '*' or 0x2022 for normal items
	# and '[ ]', '[*]' or '[x]' for checkbox items

bullets = {
	u'* \u2610': UNCHECKED_BOX,
	u'* \u2612': XCHECKED_BOX,
	u'* \u2611': CHECKED_BOX,
	'-': BULLET,
}

# reverse dict
bullet_types = {}
for bullet in bullets:
	bullet_types[bullets[bullet]] = bullet

dumper_tags = {
	'emphasis': '*',
	'strong':   '**',
	'mark':     '', # TODO, no directly way to do this in rst
	'strike':   '', # TODO, no directly way to do this in rst
	'code':     '``',
	'sub':      ':sub:',
	'sup':      ':sup:',
	'tag':      '', # No additional annotation (apart from the visible @)
}

class Dumper(DumperClass):

	def dump(self, tree):
		assert isinstance(tree, ParseTree)
		assert self.linker, 'rst dumper needs a linker object'
		self.linker.set_usebase(True)
		output = TextBuffer()
		self.dump_children(tree.getroot(), output)
		return output.get_lines(end_with_newline=not tree.ispartial)

	def dump_children(self, list, output, list_level=-1, list_type=None, list_iter='0'):
		if list.text:
			output.append(list.text)

		for element in list.getchildren():
			if element.tag in ('p', 'div'):
				#~ print element.tag
				#~ print element.text
				indent = 0
				if 'indent' in element.attrib:
					indent = int(element.attrib['indent'])
				myoutput = TextBuffer()
				self.dump_children(element, myoutput) # recurs
				output.extend('\t'*indent)
				output.extend(myoutput)

			elif element.tag == 'h':
				level = int(element.attrib['level'])
				if level < 1:   level = 1
				elif level > 4: level = 4
				char = level_tag[level-1]
				heading = element.text
				line = char * len(heading)
				output.append(heading + '\n')
				output.append(line)

			elif element.tag in ('ul', 'ol'):
				indent = int(element.attrib.get('indent', 0))
				start = element.attrib.get('start')
				myoutput = TextBuffer()
				self.dump_children(element, myoutput, list_level=list_level+1, list_type=element.tag, list_iter=start) # recurs
				if list_level == -1:
					output.extend(myoutput)
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
				myoutput = TextBuffer()
				myoutput.append("::\n\n")
				text = [ '\t' + t for t in element.text.split('\n')]
				myoutput.append('\n'.join(text))
				output.extend(myoutput)

			elif element.tag == 'link':
				assert 'href' in element.attrib, \
					'BUG: link %s "%s"' % (element.attrib, element.text)
				href = self.linker.link(element.attrib['href'])
				text = element.text
				output.append('`%s <%s>`_' % (text, href))

			elif element.tag in ('sub', 'sup'):
				if element.text:
					tag = dumper_tags[element.tag]
					output.append("%s`%s`\ " % (tag, element.text))

			elif element.tag in ('mark', 'strike'):
				if element.text: output.append(element.text)

			elif element.tag in ('strong', 'emphasis'):
				if element.text:
					tag = dumper_tags[element.tag]
					msg = tag + element.text + tag + ' '
					if output: msg = ' ' + msg
					output.append(msg)

			elif element.tag == 'img':
				src = self.linker.img(element.attrib['src'])
				output.append('.. image:: %s' % src)

			elif element.tag in dumper_tags:
				if element.text:
					tag = dumper_tags[element.tag]
					output.append(' ' + tag + element.text + tag + ' ')
			else:
				assert False, 'Unknown node type: %s' % element

			if element.tail:
				output.append(element.tail)
