# -*- coding: utf-8 -*-

# Copyright 2008 Johannes Reinhardt <jreinhardt@ist-dein-freund.de>
# Copyright 2012-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This modules handles export of LaTeX Code'''

import re
import string
import logging

from zim.fs import File, FileNotFoundError
from zim.formats import *
from zim.formats.plain import Dumper as TextDumper
from zim.config.dicts import Choice

logger = logging.getLogger('zim.formats.latex')


info = {
	'name': 'latex',
	'desc':	'LaTeX',
	'mimetype': 'application/x-tex',
	'extension': 'tex',
	'native': False,
	'import': False,
	'export': True,
	'usebase': False,
}


encode_re = re.compile(r'(\&|\$|\^|\%|\#|\_|\\|\<|\>|\n)')
encode_dict = {
	'\\': '$\\backslash$',
	'&': '\\$',
	'$': '\\$ ',
	'^': '\\^{}',
	'%': '\\%',
	'#': '\\# ',
	'_': '\\_',
	'>': '\\textgreater{}',
	'<': '\\textless{}',
	'\n': '\n\n',
}


class Dumper(TextDumper):

	BULLETS = {
		UNCHECKED_BOX : '\\item[\\Square]',
		XCHECKED_BOX  : '\\item[\\XBox]',
		CHECKED_BOX   : '\\item[\\CheckedBox]',
		BULLET        : '\\item',
	}

	SECTIONING = {
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

	TAGS = {
		EMPHASIS:		('\\emph{', '}'),
		STRONG:			('\\textbf{', '}'),
		MARK:			('\\uline{', '}'),
		STRIKE:			('\\sout{', '}'),
		TAG:			('', ''), # No additional annotation (apart from the visible @)
		SUBSCRIPT:		('$_{', '}$'),
		SUPERSCRIPT:	('$^{', '}$'),
	}

	TEMPLATE_OPTIONS = {
		'document_type': Choice('report', ('report', 'article','book'))
	}

	def dump(self, tree):
		assert isinstance(tree, ParseTree)
		assert self.linker, 'LaTeX dumper needs a linker object'
		self.document_type = self.template_options['document_type']
		logger.info('used document type: %s' % self.document_type)
		return TextDumper.dump(self, tree)

	@staticmethod
	def encode_text(tag, text):
		return encode_re.sub(lambda m: encode_dict[m.group(1)], text)

	def dump_pre(self, tag, attrib, strings):
		indent = int(attrib.get('indent', 0))
		text = u''.join(strings)
		text = text.replace('\n\n', '\n') # remove newlines introduces by encode_text
		strings = text.splitlines(True)
		if indent:
			strings = self.prefix_lines('    ' * indent, strings)

		strings.insert(0, '\n\\begin{lstlisting}\n')
		strings.append('\n\\end{lstlisting}\n')
		return strings

	def dump_h(self, tag, attrib, strings):
		level = int(attrib['level'])
		if level < 1: level = 1
		elif level > 5: level = 5

		text = u''.join(strings)
		return [self.SECTIONING[self.document_type][level] % text]

	def dump_ul(self, tag, attrib, strings):
		strings.insert(0, '\\begin{itemize}\n')
		strings.append('\\end{itemize}\n')

		return TextDumper.dump_ul(self, tag, attrib, strings)

	def dump_ol(self, tag, attrib, strings):
		start = attrib.get('start', 1)
		if start in string.lowercase:
			type = 'a'
			start = string.lowercase.index(start) + 1
		elif start in string.uppercase:
			type = 'A'
			start = string.uppercase.index(start) + 1
		else:
			type = '1'
			start = int(start)

		strings.insert(0, '\\begin{enumerate}[%s]\n' % type)
		if start > 1:
			strings.insert(1, '\setcounter{enumi}{%i}\n' % (start-1))
		strings.append('\\end{enumerate}\n')

		return TextDumper.dump_ol(self, tag, attrib, strings)

	def dump_li(self, tag, attrib, strings):
		# Always return "\item" for numbered lists

		if self.context[-1].tag == BULLETLIST:
			if 'bullet' in attrib \
			and attrib['bullet'] in self.BULLETS:
				bullet = self.BULLETS[attrib['bullet']]
			else:
				bullet = self.BULLETS[BULLET]
		elif self.context[-1].tag == NUMBEREDLIST:
			bullet = self.BULLETS[BULLET]
		else:
			assert False, 'Unnested li element'

		return (bullet, ' ') + tuple(strings) + ('\n',)


	def dump_img(self, tag, attrib, strings=None):
		# We try to get images about the same visual size,
		# therefore need to specify dot density 96 dpi seems to be
		# common for computer monitors
		dpi = 96

		if attrib.get('type') == 'equation':
			try:
				# Try to find the source, otherwise fall back to image
				src = attrib['src'][:-4] + '.tex'
				file = self.linker.resolve_source_file(src)
				if file is not None:
					equation = file.read().strip()
				else:
					equation = None
			except FileNotFoundError:
				logger.warn('Could not find latex equation: %s', src)
			else:
				if equation:
					return ['\\begin{math}\n', equation, '\n\\end{math}']

		if 'width' in attrib and not 'height' in attrib:
			options = 'width=%fin, keepaspectratio=true' \
					% ( float(attrib['width']) / dpi )
		elif 'height' in attrib and not 'width' in attrib:
			options = 'height=%fin, keepaspectratio=true' \
					% ( float(attrib['height']) / dpi )
		elif 'height' in attrib and 'width' in attrib:
			options = 'height=%fin, width=%fin' \
					% ( float(attrib['height']) / dpi, float(attrib['width']) / dpi )
		else:
			options = ''

		imagepath = self.linker.img(attrib['src'])
		if imagepath.startswith('file://'):
			imagepath = File(imagepath).path # avoid URIs here
		image = '\\includegraphics[%s]{%s}' % (options, imagepath)

		if 'href' in attrib:
			href = self.linker.link(attrib['href'])
			return ['\\href{%s}{%s}' % (href, image)]
		else:
			return [image]

	def dump_link(self, tag, attrib, strings=None):
		href = self.linker.link(attrib['href'])
		if strings:
			text = u''.join(strings)
		else:
			text = href
		return ['\\href{%s}{%s}' % (href, text)]

	def dump_code(self, tag, attrib, strings):
		# Here we try several possible delimiters for the inline verb
		# command of LaTeX
		text = u''.join(strings)
		for delim in '+*|$&%!-_':
			if not delim in text:
				return ['\\lstinline'+delim+text+delim]
		else:
			assert False, 'Found no suitable delimiter for verbatim text: %s' % element

	dump_object_fallback = dump_pre
