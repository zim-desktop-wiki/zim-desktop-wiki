# Copyright 2016-2022 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# Tokens come in 3 variants
#   tuple((tag, attrib))  e.g. (HEADING, {'level': 3})
#   tuple((TEXT, string))   e.g. (TEXT, 'Some heading ...')
#   tuple((END, tag))     e.g. (END, HEADING)
#
# Extra constraint is parsing must be per line, therefore a TEXT
# item cannot contain newline other than at the end of the string
#
# For tags that don't have attributes, the "attrib" field can be None
#
# Tags always come in pairs of opening + closing tokens, there is no
# "atomic" token for items that do not have content.
#
# Tags need to be properly nested, so they represent a hierarchy.

from .builder import Builder

TEXT = 'T'
END = '/'


def skip_to_end_token(token_iter, end_token):
	eol = 0
	nesting = 0
	for t in token_iter:
		if t[0] == end_token:
			nesting += 1
		elif t == (END, end_token):
			nesting -= 1
			if nesting < 0:
				break
		elif t[0] == TEXT:
			eol += t[1].count('\n')

	return eol


class EndOfTokenListError(AssertionError):
	pass


def collect_until_end_token(token_iter, tag):
	nesting = 0
	tokens = []
	end_token = (END, tag)
	for t in token_iter:
		if t[0] == tag:
			nesting += 1
		elif t == end_token:
			nesting -= 1
			if nesting < 0:
				break

		tokens.append(t)
	else:
		raise EndOfTokenListError('Did not find "%s" closing tag' % tag)

	return tokens


def filter_token(token_iter, token):
	"""
	Iterator removing all tokens enclosed by an opening/closing tag 'token'.
	Nested occurrence of 'token' is taken into account.
	"""
	nesting = 0
	for t in token_iter:
		if t[0] == token:
			nesting += 1
		elif t == (END, token):
			nesting -= 1
		elif nesting == 0:
			yield t
	if nesting != 0:
		raise EndOfTokenListError('Mismatch in opening/closing tags for "%s"' % token)


def tokens_to_text(tokens):
	text = [t[1] for t in tokens if t[0] == TEXT]
	return ''.join(text)


def tokens_by_line(tokens):
	line = []
	for t in tokens:
		line.append(t)
		if t[0] == TEXT and t[1].endswith('\n'):
			yield line
			line = []
	if line:
		yield line


def _changeList(tokeniter):
	# </li><ul>...</ul> --> <ul>...</ul></li>
	from zim.formats import NUMBEREDLIST, BULLETLIST, LISTITEM
	
	newtokens = []
	for t in tokeniter:
		if t[0] in (NUMBEREDLIST, BULLETLIST):
			assert newtokens and newtokens[-1] == (END, LISTITEM), 'Empty parent ?'
			newtokens.pop()
			newtokens.append(t)
			newtokens.extend(_changeList(tokeniter)) # recurs
			t = next(tokeniter)
			while t[0] in (NUMBEREDLIST, BULLETLIST):
				# There can be multiple list after each other
				newtokens.append(t)
				newtokens.extend(_changeList(tokeniter)) # recurs
				t = next(tokeniter)
			else:
				newtokens.append((END, LISTITEM))

		# note: no "elif" here ! can process remainder of above block
		if t[0] == END and t[1] in (NUMBEREDLIST, BULLETLIST):
			newtokens.append(t)
			break
		else:
			newtokens.append(t)

	return newtokens


def topLevelLists(tokens):
	# Make tree more HTML-like:
	# - Move UL / OL to top level, outside P
	# - Put sub-UL / sub-OL inside LI element
	#
	# Consider multiple lists one after the other as a single list
	# section here - this can happen for mixed bullet + numbered list items
	#
	# <p><ul>...</ul></p> --> <ul>...</ul>
	# <p><ul>...</ul>.. --> <ul>...</ul><p>..
	# ..<ul>...</ul>.. --> ..</p><ul>...</ul><p>..
	# ..<ul>...</ul></p> --> ..</p><ul>...</ul>
	#
	from zim.formats import NUMBEREDLIST, BULLETLIST, PARAGRAPH
	para_end = (END, PARAGRAPH)
	seen_para = False
	tokeniter = iter(tokens)
	newtokens = []
	for t in tokeniter:
		if t[0] in (NUMBEREDLIST, BULLETLIST):
			assert seen_para, 'Looks like tokenlist had top level lists to start with'
			if newtokens[-1][0] == PARAGRAPH:
				newtokens.pop()
			else:
				newtokens.append((END, PARAGRAPH))

			newtokens.append(t)
			newtokens.extend(_changeList(tokeniter))

			nexttoken = next(tokeniter)
			while nexttoken[0] in (BULLETLIST, NUMBEREDLIST):
				newtokens.append(nexttoken)
				newtokens.extend(_changeList(tokeniter))
				nexttoken = next(tokeniter)

			if nexttoken == (END, PARAGRAPH):
				pass
			else:
				newtokens.append((PARAGRAPH, None))
				newtokens.append(nexttoken)
		else:
			if t[0] == PARAGRAPH:
				seen_para = True
			elif t == para_end:
				seen_para = False
			newtokens.append(t)

	return newtokens


class TokenBuilder(Builder):

	def __init__(self):
		self._tokens = []

	@property
	def tokens(self):
		return topLevelLists(self._tokens)

	def start(self, tag, attrib=None):
		self._tokens.append((tag, attrib))

	def text(self, text):
		if '\n' in text:
			for line in text.splitlines(True):
				self._tokens.append((TEXT, line))
		else:
			self._tokens.append((TEXT, text))

	def end(self, tag):
		self._tokens.append((END, tag))

	def append(self, tag, attrib=None, text=None):
		if text:
			if '\n' in text:
				self._tokens.append((tag, attrib))
				for line in text.splitlines(True):
					self._tokens.append((TEXT, line))
				self._tokens.append((END, tag))
			else:
				self._tokens.extend([
					(tag, attrib),
					(TEXT, text),
					(END, tag)
				])
		else:
			self._tokens.extend([
				(tag, attrib),
				(END, tag)
			])


def _reverseChangeList(tokeniter):
	# <ul>...</ul></li> --> </li><ul>...</ul>
	from zim.formats import NUMBEREDLIST, BULLETLIST, LISTITEM
	newtokens = []
	for t in tokeniter:
		if t[0] in (NUMBEREDLIST, BULLETLIST):
			listtokens = [t] + _reverseChangeList(tokeniter) # recurs
			nexttoken = next(tokeniter)
			while nexttoken[0] in (NUMBEREDLIST, BULLETLIST):
				# There can be multiple list after each other
				listtokens.append(nexttoken)
				listtokens.extend(_reverseChangeList(tokeniter)) # recurs
				nexttoken = next(tokeniter)
			else:
				assert nexttoken == (END, LISTITEM), 'unexpected token: %s' % nexttoken
			newtokens.append((END, LISTITEM))
			newtokens.extend(listtokens)
		elif t[0] == END and t[1] in (NUMBEREDLIST, BULLETLIST):
			newtokens.append(t)
			break
		else:
			newtokens.append(t)

	return newtokens


def reverseTopLevelLists(tokens):
	# Undo effect of topLevelLists()
	#
	# Consider multiple lists one after the other as a single list
	# section here - this can happen for mixed bullet + numbered list items
	#
	# ..<ul>...</ul>.. --> <p><ul>...</ul></p>
	# ..<ul>...</ul><p>.. --> <p><ul>...</ul>..
	# ..</p><ul>...</ul><p>.. ..<ul>...</ul>..
	# ..</p><ul>...</ul>.. --> ..<ul>...</ul></p>
	#
	from zim.formats import NUMBEREDLIST, BULLETLIST, PARAGRAPH
	tokeniter = iter(tokens)
	newtokens = []
	for t in tokeniter:
		if t[0] in (NUMBEREDLIST, BULLETLIST):
			if newtokens and newtokens[-1] == (END, PARAGRAPH):
				newtokens.pop()
			else:
				newtokens.append((PARAGRAPH, None))

			newtokens.append(t)
			newtokens.extend(_reverseChangeList(tokeniter))

			nexttoken = next(tokeniter)
			while nexttoken[0] in (BULLETLIST, NUMBEREDLIST):
				newtokens.append(nexttoken)
				newtokens.extend(_reverseChangeList(tokeniter))
				nexttoken = next(tokeniter)

			if nexttoken[0] == PARAGRAPH:
				pass
			else:
				newtokens.append((END, PARAGRAPH))
				newtokens.append(nexttoken)
		else:
			newtokens.append(t)

	return newtokens


class TokenParser(object):

	def __init__(self, builder):
		self.builder = builder

	def parse(self, tokens):
		for t in reverseTopLevelLists(tokens):
			if t[0] == END:
				self.builder.end(t[1])
			elif t[0] == TEXT:
				self.builder.text(t[1])
			else:
				self.builder.start(*t)


def testTokenStream(token_iter):
	from zim.formats import NUMBEREDLIST, BULLETLIST, PARAGRAPH
	nesting = []
	for t in token_iter:
		assert isinstance(t, tuple) and len(t) == 2, 'Malformed token'
		if t[0] == END:
			assert nesting[-1] == t[1], 'Got /%s, expected /%s' % (t[1], nesting[-1])
			nesting.pop()
		elif t[0] == TEXT:
			assert isinstance(t[1], str), 'Wrong type for text'
			assert not '\n' in t[1][:-1], 'Text token should not cross line break: %r' % (t,)
		else:
			assert t[1] is None or isinstance(t[1], dict), 'Wrong type for attributes'

			if t[0] in (BULLETLIST, NUMBEREDLIST):
				assert PARAGRAPH not in nesting, 'Lists should not appear inside paragraphs'
			elif t[0] == PARAGRAPH:
				assert len(nesting) == 1, 'Paragraphs should only appear in top level - got %r' % nesting
			# TODO more semantic rules

			nesting.append(t[0])

	assert len(nesting) == 0, 'Open tags: %r' % nesting