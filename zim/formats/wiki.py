
# Copyright 2008, 2012-2019 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module handles parsing and dumping wiki text'''

import re
import logging

logger = logging.getLogger('zim.formats.wiki')

from zim.parser import Rule, fix_line_end, convert_space_to_tab
from zim.parser import Parser as RuleParser
from zim.parsing import url_encode, URL_ENCODE_DATA, \
	escape_string, unescape_string, split_escaped_string
from zim.parsing import url_re as old_url_re
from zim.formats import *
from zim.formats.plain import Dumper as TextDumper

old_url_re = old_url_re.p


WIKI_FORMAT_VERSION = 'zim 0.6'
assert WIKI_FORMAT_VERSION != 'zim 0.26' # skip number for historic reasons
# History:
# - 0.6  new url parsing logic
# - 0.5  support nested formatting
# - 0.4  parser rewrite, specifically changed parsing indented blocks
# - 0.26 oldest format supported in python branch


info = {
	'name': 'wiki',
	'desc': 'Zim Wiki Format',
	'mimetype': 'text/x-zim-wiki',
	'extension': 'txt',
	'native': True,
	'import': True,
	'export': True,
	'usebase': True,
}


bullet_pattern = '(?:[\\*\u2022]|\\[[ \\*x>]\\]|\\d+\\.|[a-zA-Z]\\.)[\\ \\t]+'
	# bullets can be '*' or 0x2022 for normal items
	# and '[ ]', '[*]', '[x]' or '[>]' for checkbox items
	# and '1.', '10.', or 'a.' for numbered items (but not 'aa.')

bullet_line_re = re.compile(r'^(\t*)(%s)(.*\n)$' % bullet_pattern)
	# matches list item: prefix, bullet, text

number_bullet_re = re.compile('^(\d+|[a-zA-Z])\.$')
def check_number_bullet(bullet):
	'''If bullet is a numbered bullet this returns the number or letter,
	C{None} otherwise
	'''
	m = number_bullet_re.match(bullet)
	if m:
		return m.group(1)
	else:
		return None

param_re = re.compile('([\w-]+)=("(?:[^"]|"{2})*"|\S*)')
	# matches parameter list for objects
	# allow name="foo bar" and name=Foo

empty_lines_re = re.compile(r'((?:^[ \t]*\n)+)', re.M | re.U)
	# match multiple empty lines

unindented_line_re = re.compile('^\S', re.M)
	# match any unindented line


def _remove_indent(text, indent):
	return re.sub('(?m)^' + indent, '', text)
		# Specify "(?m)" instead of re.M since "flags" keyword is not
		# supported in python 2.6


# NOTE: we follow rules of GFM spec, except:
#  - we allow any URL scheme
#  - we add a file URI match
# For GFM Markdown parser, remove these exceptions
#
# File paths cannot contain '\', '/', ':', '*', '?', '"', '<', '>', '|'
# These are valid URL / path seperators: / \ : ? |
# So restrict matching " < > and also '
url_re = re.compile(
	'\\b(?P<url>'

	'(www\.|https?://|\w+://)'			# autolink & autourl prefix
	'(?P<domain>([\w\-]+\.)+[\w\-]+)' 	# 2 or more domain sections
	'[^\s<]*'					# any non-space char except "<"

	')|(?P<email>'

	'(mailto:)?'
	'[\w\.\-_+]+@'				# email prefix
	'([\w\-_]+\.)+[\w\-_]+'	# email domain

	')|(?P<fileuri>'

	'file:/+'
	'[^\s"<>\']+'

	')', re.U
)

url_trailing_punctuation = ('?', '!', '.', ',', ':', '*', '_', '~')


def is_url(text):
	'''Matches url_re and number of closing brackets matches
	See L{https://github.github.com/gfm/#autolinks-extension-}
	@param text: text to match as url
	@returns: C{True} if C{text} is a valid url according to GFM rules
	'''
	url = match_url(text)
	return url == text # No trailing puntuation or ")" excluded


def match_url(text):
	'''Match regex and count number of closing brackets
	See L{https://github.github.com/gfm/#autolinks-extension-}
	@param text: text to match as url
	@returns: the url or None
	'''
	m = url_re.match(text)
	if m:
		url = m.group(0)
		if m.lastgroup == 'email':
			# Do not allow end in "-" or "_", use trailing "."
			while url:
				if url[-1] == '.':
					url = url[:-1]
				elif url[-1] in ('-', '_'):
					return None
				else:
					break
			return url or None

		# continue processing regular URL or file URI
		if m.lastgroup == 'url':
			domain = m.group('domain').split('.')
			if '_' in domain[-1] or '_' in domain[-2]:
				# Last two domain sections cannot contain "_"
				return None
	else:
		return None

	while url:
		if url[-1] in url_trailing_punctuation \
			or (url[-1] == ')' and url.count(')') > url.count('(')):
				url = url[:-1]
		elif url[-1] == ';':
			m = re.search('&\w+;$', url)
			if m:
				ref = m.group(0)
				url = url[:-len(ref)]
			else:
				url = url[:-1]
		else:
			return url
	else:
		return None


class WikiParser(object):
	# This parser uses 3 levels of rules. The top level splits up
	# paragraphs, verbatim paragraphs, images and objects.
	# The second level further splits paragraphs in lists and indented
	# blocks. The third level does the inline formatting for all
	# text.

	BULLETS = {
		'[ ]': UNCHECKED_BOX,
		'[x]': XCHECKED_BOX,
		'[*]': CHECKED_BOX,
		'[>]': MIGRATED_BOX,
		'*': BULLET,
	}

	def __init__(self, backward_indented_blocks=False, backward_url_parsing=False):
		self.backward_indented_blocks = backward_indented_blocks
		self.backward_url_parsing = backward_url_parsing
		self.inline_parser = self._init_inline_parse()
		self.list_and_indent_parser = self._init_intermediate_parser()
		self.block_parser = self._init_block_parser()

	def __call__(self, builder, text):
		builder.start(FORMATTEDTEXT)
		self.block_parser(builder, text)
		builder.end(FORMATTEDTEXT)

	def _init_inline_parse(self):
		# Rules for inline formatting, links and tags
		my_url_re = old_url_re if self.backward_url_parsing else url_re
		descent = lambda *a: self.inline_parser(*a)

		self.nested_inline_parser = (
			Rule(TAG, r'(?<!\S)@\w+', process=self.parse_tag)
			| Rule(EMPHASIS, r'//(?!/)(.*?)(?<!:)//', descent=descent) # no ':' at the end (ex: 'http://')
			| Rule(STRONG, r'\*\*(?!\*)(.*?)\*\*', descent=descent)
			| Rule(MARK, r'__(?!_)(.*?)__', descent=descent)
			| Rule(SUBSCRIPT, r'_\{(?!~)(.+?)\}', descent=descent)
			| Rule(SUPERSCRIPT, r'\^\{(?!~)(.+?)\}', descent=descent)
			| Rule(STRIKE, r'~~(?!~)(.+?)~~', descent=descent)
			| Rule(VERBATIM, r"''(?!')(.+?)''")

		)

		return (
			Rule(LINK, my_url_re, process=self.parse_url)
			| Rule(LINK, r'\[\[(?!\[)(.*?\]*)\]\]', process=self.parse_link)
			| Rule(IMAGE, r'\{\{(?!\{)(.*?)\}\}', process=self.parse_image)
			| self.nested_inline_parser
		)

	def _init_intermediate_parser(self):
		# Intermediate level, breaks up lists and indented blocks
		# TODO: deprecate this by taking lists out of the para
		#       and make a new para for each indented block
		p = RuleParser(
			Rule(
				'X-Bullet-List',
				r'''(
					^ %s .* \n								# Line starting with bullet
					(?:
						^ \t* %s .* \n						# Line with same or more indent and bullet
					)*										# .. repeat
				)''' % (bullet_pattern, bullet_pattern),
				process=self.parse_list
			),
			Rule(
				'X-Indented-Bullet-List',
				r'''(
					^(?P<list_indent>\t+) %s .* \n			# Line with indent and bullet
					(?:
						^(?P=list_indent) \t* %s .* \n		# Line with same or more indent and bullet
					)*										# .. repeat
				)''' % (bullet_pattern, bullet_pattern),
				process=self.parse_list
			),
			Rule(
				'X-Indented-Block',
				r'''(
					^(?P<block_indent>\t+) .* \n			# Line with indent
					(?:
						^(?P=block_indent) (?!\t|%s) .* \n	# Line with _same_ indent, no bullet
					)*										# .. repeat
				)''' % bullet_pattern,
				process=self.parse_indent
			),
		)
		p.process_unmatched = self.inline_parser
		return p

	def _init_block_parser(self):
		# Top level parser, to break up block level items
		p = RuleParser(
			Rule(VERBATIM_BLOCK, r'''
				^(?P<pre_indent>\t*) \'\'\' \s*?				# 3 "'"
				( (?:^.*\n)*? )									# multi-line text
				^(?P=pre_indent) \'\'\' \s*? \n					# another 3 "'" with matching indent
				''',
				process=self.parse_pre
			),
			Rule(OBJECT, r'''
				^(?P<obj_indent>\t*) \{\{\{ \s*? (\S+:.*\n)		# "{{{ object_type: attrib=..."
				( (?:^.*\n)*? ) 								# multi-line body
				^(?P=obj_indent) \}\}\} \s*? \n					# "}}}" with matching indent
				''',
				process=self.parse_object
			),
			Rule(HEADING,
				r'^( ==+ [\ \t]+ \S.*? ) [\ \t]* =* \n',		# "==== heading ===="
				process=self.parse_heading
			),
			# standard table format
			Rule(TABLE, r'''
				^(\|.*\|) \s*? \n								# starting and ending with |
				^( (?:\| [ \|\-:]+ \| \s*? \n)? )				# column align
				( (?:^\|.*\| \s*? \n)+ )							# multi-lines: starting and ending with |
				''',
				process=self.parse_table
			),
			# line format
			Rule(LINE, r'(?<=\n)-{5,}(?=\n)', process=self.parse_line) # \n----\n

		)
		p.process_unmatched = self.parse_para
		return p

	def parse_heading(self, builder, text):
		'''Parse heading and determine it's level'''
		assert text.startswith('=')
		for i, c in enumerate(text):
			if c != '=':
				break

		level = 7 - min(6, i)
			# == is level 5
			# === is level 4
			# ...
			# ======= is level 1
		text = text[i:].lstrip() + '\n'

		builder.start(HEADING, {'level': level})
		self.inline_parser(builder, text)
		builder.end(HEADING)


	@staticmethod
	def parse_pre(builder, indent, text):
		'''Verbatim block with indenting'''
		if indent:
			text = _remove_indent(text, indent)
			attrib = {'indent': len(indent)}
		else:
			attrib = None

		builder.append(VERBATIM_BLOCK, attrib, text)

	def parse_object(self, builder, indent, header, body):
		'''Custom object'''
		otype, param = header.split(':', 1)
		otype = otype.strip().lower()

		if otype == 'table':
			# Special case to ensure backward compatibility for versions where
			# tables could be stored as objects
			if param.strip() != '':
				logger.warn('Table object had unexpected parameters: %s', param.strip())
			lines = body.splitlines(True)
			headerrow = lines[0]
			alignstyle = lines[1]
			body = ''.join(lines[2:])
			try:
				return self.parse_table(builder, headerrow, alignstyle, body)
			except:
				logger.exception('Could not parse table object')

		self._parse_object(builder, indent, otype, param, body)

	def _parse_object(self, builder, indent, otype, param, body):
		attrib = {}
		for match in param_re.finditer(param):
			key = match.group(1).lower()
			value = match.group(2)
			if value.startswith('"') and len(value) > 1: # Quoted string
				value = value[1:-1].replace('""', '"')
			attrib[key] = value

		# Defined after parsing head, so these attrib can not be overruled
		# accidentally
		### FIXME FIXME FIXME - need to separate two types of attrib ###
		attrib['type'] = otype
		if indent:
			body = _remove_indent(body, indent)
			attrib['indent'] = len(indent)
		builder.append(OBJECT, attrib, body)

	def check_multi_attribute(self, attrib, key, default, list_length):
		'''
		Correct multi-attributes, so they do fit with column length of table
		:param attrib: key-value store
		:param key: key to select of attribute
		:param default: default value for one list entry
		:param list_length: required length of selected attribute
		:return: attribute-value as list of different options
		'''
		if attrib and key in attrib and attrib[key]:
			values = attrib[key].split(',')
		else:
			values = []

		while len(values) > list_length:
			values.pop()
		while len(values) < list_length:
			values.append(default)
		return ','.join(values)

	def parse_table(self, builder, headerline, alignstyle, body):
		headerrow = split_escaped_string(headerline.strip().strip('|'), '|')
		rows = [
				split_escaped_string(line.strip().strip('|'), '|')
					for line in body.split('\n')[:-1]
		]

		n_cols = max(len(headerrow), max(len(bodyrow) for bodyrow in rows))

		aligns = []
		for celltext in alignstyle.strip().strip('|').split('|'):
			celltext = celltext.strip()
			if celltext.startswith(':') and celltext.endswith(':'):
				alignment = 'center'
			elif celltext.startswith(':'):
				alignment = 'left'
			elif celltext.endswith(':'):
				alignment = 'right'
			else:
				alignment = 'normal'
			aligns.append(alignment)

		while len(aligns) < n_cols:
			aligns.append('normal')

		# collect wrap settings from first table row
		headers = []
		wraps = []
		for celltext in headerrow:
			if celltext.rstrip().endswith('<'):
				celltext = celltext.rstrip().rstrip('<')
				wraps.append(1)
			else:
				wraps.append(0)
			headers.append(celltext)

		while len(headers) < n_cols:
			headers.append('')
			wraps.append(0)

		attrib = {'aligns': ','.join(aligns), 'wraps': ','.join(map(str, wraps))}
		builder.start(TABLE, attrib)

		builder.start(HEADROW)
		for celltext in headers:
			celltext = unescape_string(celltext.strip()) or ' ' # must contain at least one character
			builder.append(HEADDATA, {}, celltext)
		builder.end(HEADROW)

		for bodyrow in rows:
			while len(bodyrow) < n_cols:
				bodyrow.append('')

			builder.start(TABLEROW)
			for celltext in bodyrow:
				builder.start(TABLEDATA)
				celltext = unescape_string(celltext.strip()) or ' ' # must contain at least one character
				self.inline_parser(builder, celltext)
				builder.end(TABLEDATA)
			builder.end(TABLEROW)

		builder.end(TABLE)

	def parse_para(self, builder, text):
		'''Split a text into paragraphs and empty lines'''
		if text.isspace():
			builder.text(text)
		else:
			for block in empty_lines_re.split(text):
				if not block: # empty string due to split
					pass
				elif block.isspace():
					builder.text(block)
				elif self.backward_indented_blocks \
				and not unindented_line_re.search(block):
					# Before zim 0.29 all indented paragraphs were
					# verbatim.
					builder.append(VERBATIM_BLOCK, None, block)
				else:
					block = convert_space_to_tab(block)
					builder.start(PARAGRAPH)
					self.list_and_indent_parser(builder, block)
					builder.end(PARAGRAPH)

	def parse_list(self, builder, text, indent=None):
		'''Parse lists into items and recurse to get inline formatting
		per list item
		'''
		if indent:
			text = _remove_indent(text, indent)
			attrib = {'indent': len(indent)}
		else:
			attrib = None

		lines = text.splitlines(True)
		self.parse_list_lines(builder, lines, 0, attrib)

	def parse_list_lines(self, builder, lines, level, attrib=None):
		listtype = None
		first = True
		while lines:
			line = lines[0]
			m = bullet_line_re.match(line)
			assert m, 'Line does not match a list item: >>%s<<' % line
			prefix, bullet, text = m.groups()
			bullet = bullet.rstrip()

			if first:
				number = check_number_bullet(bullet)
				if number:
					listtype = NUMBEREDLIST
					if not attrib:
						attrib = {}
					attrib['start'] = number
				else:
					listtype = BULLETLIST
				builder.start(listtype, attrib)
				first = False

			mylevel = len(prefix)
			if mylevel > level:
				self.parse_list_lines(builder, lines, level + 1) # recurs
			elif mylevel < level:
				builder.end(listtype)
				return
			else:
				if listtype == NUMBEREDLIST:
					if bullet in self.BULLETS:
						builder.end(listtype)
						return self.parse_list_lines(builder, lines, level) # recurs
					else:
						attrib = None
				else: # BULLETLIST
					if bullet in self.BULLETS:
						attrib = {'bullet': self.BULLETS[bullet]}
					elif number_bullet_re.match(bullet):
						builder.end(listtype)
						return self.parse_list_lines(builder, lines, level) # recurs
					else:
						attrib = {'bullet': BULLET}
				builder.start(LISTITEM, attrib)
				self.inline_parser(builder, text)
				builder.end(LISTITEM)

				lines.pop(0)

		builder.end(listtype)

	def parse_indent(self, builder, text, indent):
		'''Parse indented blocks and turn them into 'div' elements'''
		text = _remove_indent(text, indent)
		builder.start(BLOCK, {'indent': len(indent)})
		self.inline_parser(builder, text)
		builder.end(BLOCK)

	def parse_link(self, builder, text):
		text = text.strip('|') # old bug producing "[[|link]]", or "[[link|]]" or "[[||]]"
		if not text or text.isspace():
			return

		href = None
		if '|' in text:
			href, text = text.split('|', 1)
			text = text.strip('|') # stuff like "[[foo||bar]]"

		if text.endswith(']'):
			delta = text.count(']') - text.count('[')
			if delta > 0:
				self.inline_parser.backup_parser_offset(delta)
				text = text[:-delta]

		if href is None:
			builder.append(LINK, {'href': text}, text)
		else:
			builder.start(LINK, {'href': href})
			self.nested_inline_parser(builder, text)
			builder.end(LINK)

	@staticmethod
	def parse_image(builder, text):
		if '|' in text:
			url, text = text.split('|', 1)
		else:
			url, text = text, None

		attrib = ParserClass.parse_image_url(url)
		if text:
			attrib['alt'] = text

		if attrib.get('type'):
			# Backward compatibility of image generators < zim 0.70
			attrib['type'] = 'image+' + attrib['type']
			builder.append(OBJECT, attrib)
		else:
			builder.append(IMAGE, attrib)

	def parse_url(self, builder, *a):
		text = a[0]
		if self.backward_url_parsing:
			builder.append(LINK, {'href': text}, text)
		else:
			url = match_url(text)
			if url is None:
				self.inline_parser.backup_parser_offset(len(text) - 1)
			elif url != text:
				self.inline_parser.backup_parser_offset(len(text) - len(url))
			builder.append(LINK, {'href': url}, url)

	@staticmethod
	def parse_tag(builder, text):
		builder.append(TAG, {'name': text[1:]}, text)

	@staticmethod
	def parse_line(builder, text):
		builder.append(LINE)



wikiparser = WikiParser() #: singleton instance


# FIXME FIXME we are redefining Parser here !
class Parser(ParserClass):

	def __init__(self, version=WIKI_FORMAT_VERSION):
		self.version = version

	def parse(self, input, partial=False, file_input=False):
		if not isinstance(input, str):
			input = ''.join(input)

		if not partial:
			input = fix_line_end(input)

		meta, version = None, False
		if file_input:
			input, meta = parse_header_lines(input)
			version = meta.get('Wiki-Format')

		# Support backward compatibility - see history notes WIKI_FORMAT_VERSION
		version = version or self.version
		if version == 'zim 0.6':
			mywikiparser = wikiparser
		elif version in ('zim 0.4', 'zim 0.5'):
			mywikiparser = WikiParser(backward_url_parsing=True)
		else:
			mywikiparser = WikiParser(backward_indented_blocks=True, backward_url_parsing=True)

		builder = ParseTreeBuilder(partial=partial)
		mywikiparser(builder, input)

		parsetree = builder.get_parsetree()
		if meta is not None:
			for k, v in list(meta.items()):
				# Skip headers that are only interesting for the parser
				#
				# Also remove "Modification-Date" here because it causes conflicts
				# when merging branches with version control, use mtime from filesystem
				# If we see this header, remove it because it will not be updated.
				if k not in ('Content-Type', 'Wiki-Format', 'Modification-Date'):
					parsetree.meta[k] = v
		return parsetree


class Dumper(TextDumper):

	BULLETS = {
		UNCHECKED_BOX: '[ ]',
		XCHECKED_BOX: '[x]',
		CHECKED_BOX: '[*]',
		MIGRATED_BOX: '[>]',
		BULLET: '*',
	}

	TAGS = {
		EMPHASIS: ('//', '//'),
		STRONG: ('**', '**'),
		MARK: ('__', '__'),
		STRIKE: ('~~', '~~'),
		VERBATIM: ("''", "''"),
		TAG: ('', ''), # No additional annotation (apart from the visible @)
		SUBSCRIPT: ('_{', '}'),
		SUPERSCRIPT: ('^{', '}'),
	}

	def dump(self, tree, file_output=False):
		# If file_output=True we add meta headers to the output
		# would be nicer to handle this via a template, but works for now
		if file_output:
			header = (
				('Content-Type', 'text/x-zim-wiki'),
				('Wiki-Format', WIKI_FORMAT_VERSION),
			)
			return [dump_header_lines(header, getattr(tree, 'meta', {})), '\n'] \
						+ TextDumper.dump(self, tree)
		else:
			return TextDumper.dump(self, tree)

	def dump_pre(self, tag, attrib, strings):
		# Indent and wrap with "'''" lines
		strings.insert(0, "'''\n")
		strings.append("'''\n")
		strings = self.dump_indent(tag, attrib, strings)
		return strings

	def dump_h(self, tag, attrib, strings):
		# Wrap line with number of "=="
		level = int(attrib['level'])
		if level < 1:
			level = 1
		elif level > 5:
			level = 5
		tag = '=' * (7 - level)
		strings.insert(0, tag + ' ')
		strings.append(' ' + tag)
		return strings

	def dump_link(self, tag, attrib, strings=None):
		assert 'href' in attrib, \
			'BUG: link misses href: %s "%s"' % (attrib, strings)
		href = attrib['href']

		if not strings or href == ''.join(strings):
			if is_url(href):
				return (href,) # no markup needed
			else:
				return ('[[', href, ']]')
		else:
			return ('[[', href, '|') + tuple(strings) + (']]',)

	def dump_img(self, tag, attrib, strings=None):
		src = attrib['src'] or ''
		alt = attrib.get('alt')
		opts = []
		items = sorted(attrib.items())
		for k, v in items:
			if k in ('src', 'alt') or k.startswith('_'):
				continue
			elif v: # skip None, "" and 0
				data = url_encode(str(v), mode=URL_ENCODE_DATA)
				opts.append('%s=%s' % (k, data))
		if opts:
			src += '?%s' % '&'.join(opts)

		if alt:
			return ('{{', src, '|', alt, '}}')
		else:
			return('{{', src, '}}')

		# TODO use text for caption (with full recursion)

	def dump_object_fallback(self, tag, attrib, strings=None):
		assert "type" in attrib, "Undefined type of object"

		opts = []
		for key, value in sorted(list(attrib.items())):
			# TODO: sorted to make order predictable for testing - prefer use of OrderedDict
			if key in ('type', 'indent') or value is None:
				continue
			# double quotes are escaped by doubling them
			opts.append(' %s="%s"' % (key, str(value).replace('"', '""')))

		if not strings:
			strings = []
		return ['{{{', attrib['type'], ':'] + opts + ['\n'] + strings + ['}}}\n']

		# TODO put content in attrib, use text for caption (with full recursion)
		# See img

	def dump_table(self, tag, attrib, strings):
		rows = strings
		n = len(rows[0])
		assert all(len(r) == n for r in rows), rows

		aligns, wraps = TableParser.get_options(attrib)
		maxwidths = TableParser.width2dim(rows)

		lines = [
			TableParser.headline(rows[0], maxwidths, aligns, wraps) + '\n',
			TableParser.headsep(maxwidths, aligns, x='|', y='-') + '\n'
		] + [
			TableParser.rowline(row, maxwidths, aligns) + '\n' for row in rows[1:]
		]
		return lines

	def dump_td(self, tag, attrib, strings):
		text = ''.join(strings) if strings else ''
		return [escape_string(text, '|')]

	dump_th = dump_td
