# -*- coding: utf-8 -*-

# Copyright 2008 Johannes Reinhardt <jreinhardt@ist-dein-freund.de>

'''This modules handles export of LaTeX Code'''

import re
import logging

from zim.fs import File
from zim.formats import *
from zim.parsing import TextBuffer

logger = logging.getLogger('zim.formats.latex')


info = {
	'name':		'LaTeX',
	'mime': 	'application/x-tex',
	'extension': 'tex',
	'read':		False,
	'write':	False,
	'import':	False,
	'export':	True,
}

# reverse dict
bullet_types = {
	UNCHECKED_BOX : '\\item[\\Square] ',
	XCHECKED_BOX  : '\\item[\\XBox] ',
	CHECKED_BOX   : '\\item[\\CheckedBox] ',
	BULLET        : '\\item ',
}

sectioning = {
	'report': {
		1:'\\chapter{%s}',
		2:'\\section{%s}',
		3:'\\subsection{%s}',
		4:'\\subsubsection{%s}',
		5:'\\paragraph{%s}'
	},
	'article': {
		1:'\\section{%s}',
		2:'\\subsection{%s}',
		3:'\\subsubsection{%s}',
		4:'\\paragraph{%s}',
		5:'\\subparagraph{%s}'
	},
	'book': {
		1:'\\part{%s}',
		2:'\\chapter{%s}',
		3:'\\section{%s}',
		4:'\\subsection{%s}',
		5:'\\subsubsection{%s}'
	}
}



encode_re = re.compile(r'(\&|\$|\^|\%|\#|\_|\\|\<|\>)')
encode_dict = {
	'\\': '$\\backslash$',
	'&': '\\$',
	'$': '\\$ ',
	'^': '\\^{}',
	'%': '\\%',
	'#': '\\# ',
	'_': '\\_',
	'>': '\\textgreater',
	'<': '\\textless',
}


def tex_encode(text):
	if not text is None:
		return encode_re.sub(lambda m: encode_dict[m.group(1)], text)
	else:
		return ''


class Dumper(DumperClass):

	def dump(self, tree):
		assert isinstance(tree, ParseTree)
		assert self.linker, 'LaTeX dumper needs a linker object'
		self.linker.set_usebase(False)

		self.document_type = self.template_options.get('document_type')
			# Option set in template - potentially tainted value
		if not self.document_type in ('report', 'article','book'):
			logger.warn('No document type set in template, assuming "report"')
			self.document_type = 'report' # arbitrary default
		else:
			logger.info('used document type: %s'%self.document_type)

		output = TextBuffer()
		self.dump_children(tree.getroot(), output)
		return output.get_lines()

	def dump_children(self, list, output, list_level = -1):
		if list.text:
			output.append(tex_encode(list.text))

		for element in list.getchildren():
			text = tex_encode(element.text)
			if element.tag in ('p', 'div'):
				if 'indent' in element.attrib:
					indent = int(element.attrib['indent'])
				else:
					indent = 0
				myoutput = TextBuffer()
				self.dump_children(element,myoutput)
				if indent:
					myoutput.prefix_lines('\t'*indent)
				output.extend(myoutput)
			elif element.tag == 'ul':
				output.append('\\begin{itemize}\n')
				self.dump_children(element,output,list_level=list_level+1)
				output.append('\\end{itemize}')
			elif element.tag == 'h':
				level = int(element.attrib['level'])
				if level < 1: level = 1
				elif level > 5: level = 5
				output.append(sectioning[self.document_type][level]%(text))
			elif element.tag == 'li':
				if 'indent' in element.attrib:
					list_level = int(element.attrib['indent'])
				if 'bullet' in element.attrib:
					bullet = bullet_types[element.attrib['bullet']]
				else:
					bullet = bullet_types[BULLET]
				output.append('\t'*list_level+bullet)
				self.dump_children(element, output, list_level=list_level) # recurse
				output.append('\n')
			elif element.tag == 'pre':
				indent = 0
				if 'indent' in element.attrib:
					indent = int(element.attrib['indent'])
				myoutput = TextBuffer()
				myoutput.append(element.text)
				if indent:
					myoutput.prefix_lines('    ' * indent)
				output.append('\n\\begin{lstlisting}\n')
				output.extend(myoutput)
				output.append('\n\\end{lstlisting}\n')
			elif element.tag == 'sub':
				output.append('$_{%s}$' % element.text)
			elif element.tag == 'sup':
				output.append('$^{%s}$' % element.text)
			elif element.tag == 'img':
				#we try to get images about the same visual size, therefore need to specify dot density
				#96 dpi seems to be common for computer monitors
				dpi = 96
				done = False
				if 'type' in element.attrib and element.attrib['type'] == 'equation':
					try:
						# Try to find the source, otherwise fall back to image
						equri = self.linker.link(element.attrib['src'])
						eqfid = File(url_decode(equri[:-4] + '.tex'))
						output.append('\\begin{math}\n')
						output.extend(eqfid.read().strip())
						output.append('\n\\end{math}')
					except:
						logger.exception('Could not find latex equation:')
					else:
						done = True

				if not done:
					if 'width' in element.attrib and not 'height' in element.attrib:
						options = 'width=%fin, keepaspectratio=true' \
								% ( float(element.attrib['width']) / dpi )
					elif 'height' in element.attrib and not 'width' in element.attrib:
						options = 'height=%fin, keepaspectratio=true' \
								% ( float(element.attrib['height']) / dpi )
					else:
						options = ''

					imagepath = File(self.linker.link(element.attrib['src'])).path
					image = '\\includegraphics[%s]{%s}' % (options, imagepath)
					if 'href' in element.attrib:
						output.append('\\href{%s}{%s}' % (element.attrib['href'], image))
					else:
						output.append(image)
			elif element.tag == 'link':
				href = self.linker.link(element.attrib['href'])
				output.append('\\href{%s}{%s}\n' % (href, text))
			elif element.tag == 'emphasis':
				output.append('\\emph{'+text+'}')
			elif element.tag == 'strong':
				output.append('\\textbf{'+text+'}')
			elif element.tag == 'mark':
				output.append('\\uline{'+text+'}')
			elif element.tag == 'strike':
				output.append('\\sout{'+text+'}')
			elif element.tag == 'code':
				success = False
				#Here we try several possible delimiters for the inline verb command of LaTeX
				for delim in '+*|$&%!-_':
					if not delim in text:
						success = True
						output.append('\\lstinline'+delim+text+delim)
						break
				if not success:
					assert False, 'Found no suitable delimiter for verbatim text: %s' % element
					pass
			elif element.tag == 'tag':
				# LaTeX doesn't have anything similar to tags afaik
				output.append(text)
			else:
				assert False, 'Unknown node type: %s' % element

			if element.tail:
				output.append(tex_encode(element.tail))
