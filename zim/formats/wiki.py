# -*- coding: utf-8 -*-

# Copyright 2008, 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module handles parsing and dumping wiki text'''

import re

from zim.parser import *
from zim.parsing import url_re, url_encode, URL_ENCODE_DATA
from zim.formats import *
from zim.formats.plain import Dumper as TextDumper


WIKI_FORMAT_VERSION = 'zim 0.4'


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


bullet_pattern = u'(?:[\\*\u2022]|\\[[ \\*x>]\\]|\\d+\\.|[a-zA-Z]\\.)[\\ \\t]+'
# bullets can be '*' or 0x2022 for normal items
# and '[ ]', '[*]', '[x]' or '[>]' for checkbox items
# and '1.', '10.', or 'a.' for numbered items (but not 'aa.')

bullet_line_re = re.compile(ur'^(\t*)(%s)(.*\n)$' % bullet_pattern)
# matches list item: prefix, bullet, text

number_bullet_re = re.compile(u'^(\d+|[a-zA-Z])\.$')


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

empty_lines_re = re.compile(r'((?:^[\ \t]*\n)+)', re.M | re.U)
# match multiple empty lines

unindented_line_re = re.compile('^\S', re.M)
# match any unindented line


def _remove_indent(text, indent):
    return re.sub('(?m)^' + indent, '', text)
    # Specify "(?m)" instead of re.M since "flags" keyword is not
    # supported in python 2.6


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

    def __init__(self):
        self.inline_parser = self._init_inline_parse()
        self.list_and_indent_parser = self._init_intermediate_parser()
        self.block_parser = self._init_block_parser()

    def __call__(self, builder, text):
        builder.start(FORMATTEDTEXT)
        self.block_parser(builder, text)
        builder.end(FORMATTEDTEXT)

    def _init_inline_parse(self):
        # Rules for inline formatting, links and tags
        return (
            Rule(LINK, url_re.r, process=self.parse_url)  # FIXME need .r atribute because url_re is a Re object
            | Rule(TAG, r'(?<!\S)@\w+', process=self.parse_tag)
            | Rule(LINK, r'\[\[(?!\[)(.*?)\]\]', process=self.parse_link)
            | Rule(IMAGE, r'\{\{(?!\{)(.*?)\}\}', process=self.parse_image)
            | Rule(EMPHASIS, r'//(?!/)(.*?)//')
            | Rule(STRONG, r'\*\*(?!\*)(.*?)\*\*')
            | Rule(MARK, r'__(?!_)(.*?)__')
            | Rule(SUBSCRIPT, r'_\{(?!~)(.+?)\}')
            | Rule(SUPERSCRIPT, r'\^\{(?!~)(.+?)\}')
            | Rule(STRIKE, r'~~(?!~)(.+?)~~')
            | Rule(VERBATIM, r"''(?!')(.+?)''")
        )

    def _init_intermediate_parser(self):
        # Intermediate level, breaks up lists and indented blocks
        # TODO: deprecate this by taking lists out of the para
        #       and make a new para for each indented block
        p = Parser(
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
        p = Parser(
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
                 r'^( ==+ [\ \t]+ \S.*? ) [\ \t]* =* \n',  # "==== heading ===="
                 process=self.parse_heading
                 ),
            # standard table format
            Rule(TABLE, r'''
				^(\|.*\|)$\n								# starting and ending with |
				^( (?:\| [ \|\-:]+ \|$\n)? )				# column align
				( (?:^\|.*\|$\n)+ )							# multi-lines: starting and ending with |
				^(?= \s*? \n)							# empty line / only spaces
				''',
                 process=self.parse_table
                 ),
            # line format
            Rule(LINE, r'(?<=\n)-{5,}(?=\n)', process=self.parse_line)  # \n----\n

        )
        p.process_unmatched = self.parse_para
        return p

    @staticmethod
    def parse_heading(builder, text):
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
        builder.append(HEADING, {'level': level}, text)

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
        type, param = header.split(':', 1)
        type = type.strip().lower()

        attrib = {}
        for match in param_re.finditer(param):
            key = match.group(1).lower()
            value = match.group(2)
            if value.startswith('"') and len(value) > 1:  # Quoted string
                value = value[1:-1].replace('""', '"')
            attrib[key] = value

        # Defined after parsing head, so these attrib can not be overruled
        # accidentally
        ### FIXME FIXME FIXME - need to separate two types of attrib ###
        attrib['type'] = type
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

    def parse_table(self, builder, headerrow, alignstyle, body):
        '''Table parsing'''
        body = body.replace('\\|', '#124;')  # escaping
        rows = body.split('\n')[:-1]
        # get maximum number of columns - each columns must have same size
        nrcols = max([headerrow.count('|')] + [row.count('|') for row in rows]) - 1

        # transform header separator line into alignment definitions
        aligns = []
        while alignstyle.count('|') < nrcols + 1:
            alignstyle += '|'  # fill cells thus they match with nr of headers
        for celltext in alignstyle.split('|')[1:-1]:
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

        # collect wrap settings from first table row
        headers = []
        wraps = []
        for celltext in headerrow.split('|')[1:-1]:
            if celltext.rstrip().endswith('<'):
                celltext = celltext.rstrip().rstrip('<')
                wraps.append(1)
            else:
                wraps.append(0)
            headers.append(celltext)

        attrib = {'aligns': ','.join(aligns), 'wraps': ','.join(map(str, wraps))}

        # build table
        builder.start(TABLE, attrib)

        builder.start(HEADROW)
        for celltext in headers:
            celltext = celltext.replace('#124;', '|').replace('\\n', '\n').strip()
            if not celltext:
                celltext = ' '  # celltext must contain at least one character
            builder.append(HEADDATA, {}, celltext)
        builder.end(HEADROW)

        for bodyrow in rows:
            while bodyrow.count('|') < nrcols + 1:
                bodyrow += '|'  # fill cells thus they match with nr of headers
            builder.start(TABLEROW)
            for celltext in bodyrow.split('|')[1:-1]:
                builder.start(TABLEDATA)
                celltext = celltext.replace('#124;', '|').replace('\\n', '\n').strip()  # cleanup cell
                if not celltext:
                    celltext = ' '  # celltext must contain at least one character
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
                if not block:  # empty string due to split
                    pass
                elif block.isspace():
                    builder.text(block)
                elif self.backward \
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
                self.parse_list_lines(builder, lines, level + 1)  # recurs
            elif mylevel < level:
                builder.end(listtype)
                return
            else:
                if listtype == NUMBEREDLIST:
                    attrib = None
                elif bullet in self.BULLETS:  # BULLETLIST
                    attrib = {'bullet': self.BULLETS[bullet]}
                else:  # BULLETLIST
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

    @staticmethod
    def parse_link(builder, text):
        text = text.strip('|')  # old bug producing "[[|link]]", or "[[link|]]" or "[[||]]"
        if '|' in text:
            href, text = text.split('|', 1)
            text = text.strip('|')  # stuff like "[[foo||bar]]"
        else:
            href = text

        if href and not href.isspace():
            builder.append(LINK, {'href': href}, text)
        else:
            pass

    @staticmethod
    def parse_image(builder, text):
        if '|' in text:
            url, text = text.split('|', 1)
        else:
            url, text = text, None

        attrib = ParserClass.parse_image_url(url)
        if text:
            attrib['alt'] = text

        builder.append(IMAGE, attrib)

    @staticmethod
    def parse_url(builder, text):
        builder.append(LINK, {'href': text}, text)

    @staticmethod
    def parse_tag(builder, text):
        builder.append(TAG, {'name': text[1:]}, text)

    @staticmethod
    def parse_line(builder, text):
        builder.append(LINE)


wikiparser = WikiParser()  # : singleton instance


# FIXME FIXME we are redefining Parser here !
class Parser(ParserClass):

    def __init__(self, version=WIKI_FORMAT_VERSION):
        self.backward = version not in ('zim 0.26', WIKI_FORMAT_VERSION)

    def parse(self, input, partial=False):
        if not isinstance(input, basestring):
            input = ''.join(input)

        meta, backward = None, False
        if not partial:
            input = fix_line_end(input)
            input, meta = parse_header_lines(input)
            version = meta.get('Wiki-Format')
            if version and version not in ('zim 0.26', WIKI_FORMAT_VERSION):
                backward = True

        builder = ParseTreeBuilder(partial=partial)
        wikiparser.backward = backward or self.backward  # HACK
        wikiparser(builder, input)

        parsetree = builder.get_parsetree()
        if meta is not None:
            for k, v in meta.items():
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
        UNCHECKED_BOX: u'[ ]',
        XCHECKED_BOX: u'[x]',
        CHECKED_BOX: u'[*]',
        MIGRATED_BOX: u'[>]',
        BULLET: u'*',
    }

    TAGS = {
        EMPHASIS: ('//', '//'),
        STRONG: ('**', '**'),
        MARK: ('__', '__'),
        STRIKE: ('~~', '~~'),
        VERBATIM: ("''", "''"),
        TAG: ('', ''),  # No additional annotation (apart from the visible @)
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

        if not strings or href == u''.join(strings):
            if url_re.match(href):
                return (href,)  # no markup needed
            else:
                return ('[[', href, ']]')
        else:
            return ('[[', href, '|') + tuple(strings) + (']]',)

    def dump_img(self, tag, attrib, strings=None):
        src = attrib['src']
        alt = attrib.get('alt')
        opts = []
        items = sorted(attrib.items())
        for k, v in items:
            if k in ('src', 'alt') or k.startswith('_'):
                continue
            elif v:  # skip None, "" and 0
                data = url_encode(unicode(v), mode=URL_ENCODE_DATA)
                opts.append('%s=%s' % (k, data))
        if opts:
            src += '?%s' % '&'.join(opts)

        if alt:
            return ('{{', src, '|', alt, '}}')
        else:
            return('{{', src, '}}')

        # TODO use text for caption (with full recursion)

    def dump_object(self, tag, attrib, strings=None):
        assert "type" in attrib, "Undefined type of object"

        opts = []
        for key, value in attrib.items():
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
        #~ print "Dumping table: %s, %s" % (attrib, strings)
        n = len(strings[0])
        assert all(len(s) == n for s in strings), strings

        table = []  # result table
        rows = strings

        aligns, wraps = TableParser.get_options(attrib)
        maxwidths = TableParser.width2dim(rows)
        headsep = TableParser.headsep(maxwidths, aligns, x='|', y='-')
        rowline = lambda row: TableParser.rowline(row, maxwidths, aligns)

        # print table
        table += [TableParser.headline(rows[0], maxwidths, aligns, wraps)]
        table.append(headsep)
        table += [rowline(row) for row in rows[1:]]
        return map(lambda line: line + "\n", table)

    def dump_th(self, tag, attrib, strings):
        if not strings:
            return ['']  # force empty cell
        else:
            strings = map(lambda s: s.replace('\n', '\\n').replace('|', '\\|'), strings)
            return [self._concat(strings)]

    def dump_td(self, tag, attrib, strings):
        if not strings:
            return ['']  # force empty cell
        else:
            strings = map(lambda s: s.replace('\n', '\\n').replace('|', '\\|'), strings)
            strings = map(lambda s: s.replace('<br>', '\\n'), strings)
            return [self._concat(strings)]

    def dump_line(self, tag, attrib, strings = None):
        if not strings:
            strings = [LINE_TEXT]
        elif isinstance(strings, basestring):
            strings = [strings]
        return strings
