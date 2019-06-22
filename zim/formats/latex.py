
# Copyright 2008 Johannes Reinhardt <jreinhardt@ist-dein-freund.de>
# Copyright 2012-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This modules handles export of LaTeX Code'''

import os
import re
import string
import logging

from zim.fs import File, FileNotFoundError
from zim.formats import *
from zim.formats.plain import Dumper as TextDumper
from zim.parsing import url_encode, URL_ENCODE_READABLE
from zim.config.dicts import Choice

logger = logging.getLogger('zim.formats.latex')


info = {
	'name': 'latex',
	'desc': 'LaTeX',
	'mimetype': 'application/x-tex',
	'extension': 'tex',
	'native': False,
	'import': False,
	'export': True,
	'usebase': True,
}


encode_re = re.compile(r'([&$^%#_\\<>\n])')
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
		UNCHECKED_BOX: '\\item[\\Square]',
		XCHECKED_BOX: '\\item[\\XBox]',
		CHECKED_BOX: '\\item[\\CheckedBox]',
		MIGRATED_BOX: '\\item[\\RIGHTarrow]',
		BULLET: '\\item',
	}

	SECTIONING = {
		'report': {
			1: '\\chapter{%s}',
			2: '\\section{%s}',
			3: '\\subsection{%s}',
			4: '\\subsubsection{%s}',
			5: '\\paragraph{%s}'
		},
		'article': {
			1: '\\section{%s}',
			2: '\\subsection{%s}',
			3: '\\subsubsection{%s}',
			4: '\\paragraph{%s}',
			5: '\\subparagraph{%s}'
		},
		'book': {
			1: '\\part{%s}',
			2: '\\chapter{%s}',
			3: '\\section{%s}',
			4: '\\subsection{%s}',
			5: '\\subsubsection{%s}'
		}
	}

	TAGS = {
		EMPHASIS: ('\\emph{', '}'),
		STRONG: ('\\textbf{', '}'),
		MARK: ('\\uline{', '}'),
		STRIKE: ('\\sout{', '}'),
		TAG: ('', ''), # No additional annotation (apart from the visible @)
		SUBSCRIPT: ('$_{', '}$'),
		SUPERSCRIPT: ('$^{', '}$'),
	}

	TEMPLATE_OPTIONS = {
		'document_type': Choice('report', ('report', 'article', 'book'))
	}

	def dump(self, tree):
		assert isinstance(tree, ParseTree)
		assert self.linker, 'LaTeX dumper needs a linker object'
		self.document_type = self.template_options['document_type']
		logger.info('used document type: %s' % self.document_type)
		return TextDumper.dump(self, tree)

	@staticmethod
	def encode_text(tag, text):
		if tag not in (VERBATIM_BLOCK, VERBATIM, OBJECT):
			return encode_re.sub(lambda m: encode_dict[m.group(1)], text)
		else:
			return text

	def dump_pre(self, tag, attrib, strings):
		indent = int(attrib.get('indent', 0))
		text = ''.join(strings)
		text = text.replace('\n\n', '\n') # remove newlines introduces by encode_text
		strings = text.splitlines(True)
		if indent:
			strings = self.prefix_lines('    ' * indent, strings)

		strings.insert(0, '\n\\begin{lstlisting}\n')
		strings.append('\n\\end{lstlisting}\n')
		return strings

	def dump_h(self, tag, attrib, strings):
		level = int(attrib['level'])
		if level < 1:
			level = 1
		elif level > 5:
			level = 5

		text = ''.join(strings)
		return [self.SECTIONING[self.document_type][level] % text]

	def dump_ul(self, tag, attrib, strings):
		strings.insert(0, '\\begin{itemize}\n')
		strings.append('\\end{itemize}\n')

		return TextDumper.dump_ul(self, tag, attrib, strings)

	def dump_ol(self, tag, attrib, strings):
		start = attrib.get('start', 1)
		if start in string.ascii_lowercase:
			type = 'a'
			start = string.ascii_lowercase.index(start) + 1
		elif start in string.ascii_uppercase:
			type = 'A'
			start = string.ascii_uppercase.index(start) + 1
		else:
			type = '1'
			start = int(start)

		strings.insert(0, '\\begin{enumerate}[%s]\n' % type)
		if start > 1:
			strings.insert(1, '\setcounter{enumi}{%i}\n' % (start - 1))
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

		if 'width' in attrib and not 'height' in attrib:
			options = 'width=%fin, keepaspectratio=true' \
					% (float(attrib['width']) / dpi)
		elif 'height' in attrib and not 'width' in attrib:
			options = 'height=%fin, keepaspectratio=true' \
					% (float(attrib['height']) / dpi)
		elif 'height' in attrib and 'width' in attrib:
			options = 'height=%fin, width=%fin' \
					% (float(attrib['height']) / dpi, float(attrib['width']) / dpi)
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
		href = url_encode(href, URL_ENCODE_READABLE)
		if strings:
			text = ''.join(strings)
		else:
			text = href
		return ['\\href{%s}{%s}' % (href, text)]

	def dump_code(self, tag, attrib, strings):
		# Here we try several possible delimiters for the inline verb
		# command of LaTeX
		text = ''.join(strings)
		for delim in '+*|$&%!-_':
			if not delim in text:
				return ['\\lstinline' + delim + text + delim]
		else:
			assert False, 'Found no suitable delimiter for verbatim text: %s' % element

	dump_object_fallback = dump_pre

	def dump_table(self, tag, attrib, strings):
		table = []  # result table
		rows = strings

		aligns, _wraps = TableParser.get_options(attrib)
		rowline = lambda row: '&'.join([' ' + cell + ' ' for cell in row]) + '\\tabularnewline\n\hline'
		aligns = ['l' if a == 'left' else 'r' if a == 'right' else 'c' if a == 'center' else 'l' for a in aligns]

		for i, row in enumerate(rows):
			for j, (cell, align) in enumerate(zip(row, aligns)):
				if '\n' in cell:
					rows[i][j] = '\shortstack[' + align + ']{' + cell.replace("\n", "\\") + '}'

		# print table
		table.append('\\begin{tabular}{ |' + '|'.join(aligns) + '| }')
		table.append('\hline')

		table += [rowline(rows[0])]
		table.append('\hline')
		table += [rowline(row) for row in rows[1:]]

		table.append('\end{tabular}')
		return [line + "\n" for line in table]

	def dump_line(self, tag, attrib, strings=None):
		return '\n\\hrule\n'
