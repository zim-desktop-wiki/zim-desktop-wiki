
# Copyright 2016-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

from zim.tokenparser import *
from zim.formats import ParseTreeBuilder

class TestTokenParser(tests.TestCase):

	def testRoundtrip(self):
		tree = tests.new_parsetree()
		#~ print tree
		tb = TokenBuilder()
		tree.visit(tb)
		tokens = tb.tokens
		#~ import pprint; pprint.pprint(tokens)

		testTokenStream(tokens)

		builder = ParseTreeBuilder()
		TokenParser(builder).parse(tokens)
		newtree = builder.get_parsetree()

		self.assertEqual(tree.tostring(), newtree.tostring())


	def testTopLevelLists(self):
		tree = tests.new_parsetree()
		tb = TokenBuilder()
		tree.visit(tb)
		tokens = tb._tokens # using raw tokens

		newtokens = topLevelLists(tokens)
		testTokenStream(newtokens)
		revtokens = reverseTopLevelLists(newtokens)

		def correct_none_attrib(t):
			if t[0] == PARAGRAPH and not t[1]:
				return (PARAGRAPH, {})
			else:
				return t

		revtokens = list(map(correct_none_attrib, revtokens))

		self.assertEqual(revtokens, tokens)


class TestFunctions(tests.TestCase):

	def testCollectTokens(self):
		# simple
		self.assertEqual(
			collect_until_end_token(
				[('B', {}), ('T', ''), (END, 'B'), (END, 'A'), ('T', '')],
				'A'
			),
			[('B', {}), ('T', ''), (END, 'B')]
		)
		# nested
		self.assertEqual(
			collect_until_end_token(
				[('A', {}), ('T', ''), (END, 'A'), (END, 'A'), ('T', '')],
				'A'
			),
			[('A', {}), ('T', ''), (END, 'A')]
		)
		# error case: no closing tag found
		with self.assertRaises(EndOfTokenListError):
			collect_until_end_token(
				[('B', {}), ('T', ''), (END, 'B'), ('T', '')],
				'A'
			)

	def testFilterTokens(self):
		self.assertEqual(
			list(filter_token(
				[('T', 'pre'), ('A', {}), ('T', 'inner'), (END, 'A'), ('T', 'post')],
				'A'
			)),
			[('T', 'pre'), ('T', 'post')]
		)
		self.assertEqual(
			list(filter_token(
				[('T', 'pre'), ('A', {}), ('A', {}), ('T', 'inner'), (END, 'A'), (END, 'A'), ('T', 'post')],
				'A'
			)),
			[('T', 'pre'), ('T', 'post')]
		)

	def testTokensToText(self):
		self.assertEqual(
			tokens_to_text([('B', {}), ('T', 'Foo'), (END, 'B'), ('T', 'Bar')]),
			'FooBar'
		)
