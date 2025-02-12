# Copyright 2024 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import re

from .tokenlist import TEXT, END


def _attrib_to_xml(attrib):
	if not attrib:
		return ''
	else:
		text = []
		for k in sorted(attrib):
			v = _encode_xml_attrib(attrib[k]) if isinstance(attrib[k], str) else attrib[k]
			text.append(' %s="%s"' % (k, v))
		return ''.join(text)


def _xml_to_tag_and_attribute(string):
	# XXX: attrib type encoding is not robust, just some hard-coded heuristics
	tag = re.match('[\\w-]+', string).group(0)
	attrib = {}
	for k, v in re.findall(r'(\w+)="(.*?)"', string):
		if k in ('href', 'name', 'id') and v == 'None':
			attrib[k] = None
		elif k in ('indent', 'level'):
			attrib[k] = int(v)
		else:
			attrib[k] = _decode_xml(v)
	attrib = attrib if attrib else None
	return tag, attrib


def _encode_xml(text):
	return text.replace('&', '&amp;').replace('>', '&gt;').replace('<', '&lt;')

def _encode_xml_attrib(text):
	return text.replace('&', '&amp;').replace('>', '&gt;').replace('<', '&lt;').replace('"', '&quot;').replace("'", '&apos;')

def _decode_xml(text):
	chars = {'amp': '&', 'gt': '>', 'lt': '<', 'quot': '"', 'apos': "'"}
	return re.sub(r'&(\w+);', lambda m: chars[m.group(1)], text)


def simple_xml_to_token_parser(xml):
	'''Generator that parses xml and yields tokens
	Only validation is the check that tags are properly nested
	'''
	stack = []
	for part in re.split('(<.*?>)', xml):
		if not part:
			pass
		elif part[0] == '<':
			if part[1] == '/':
				tag = part[2:-1].strip()
				assert stack[-1] == tag, 'Unexpected end tag: %r expected %r' % (tag, stack[-1])
				stack.pop()
				yield (END, tag)
			else:
				t = _xml_to_tag_and_attribute(part[1:-1])
				yield t
				if part.endswith('/>'):
					yield (END, t[0])
				else:
					stack.append(t[0])
		else:
			yield (TEXT, _decode_xml(part))
	assert not stack, 'Missing end tags for: %r' % stack


def simple_token_to_xml_dumper(token_iter, tags_without_end_tag=()):
		'''Serialize tokens to xml
		Only validation is the check that tags are properly nested
		'''
		xml = []
		stack = []
		for t in token_iter:
			if t[0] == TEXT:
				xml.append(_encode_xml(t[1]))
			elif t[0] == END:
				assert stack and t[1] == stack[-1], 'Unexpected end tag: %r' % (t,)
				stack.pop()
				xml.append('</%s>' % t[1])
			elif t[0] in tags_without_end_tag:
				xml.append('<%s%s />' % (t[0], _attrib_to_xml(t[1])))
			else:
				stack.append(t[0])
				xml.append('<%s%s>' % (t[0], _attrib_to_xml(t[1])))

		return ''.join(xml)
