
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

		builder = ParseTreeBuilder(_parsetree_roundtrip=True)
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
		self.assertEqual(	# simple
			collect_untill_end_token(
				[('B', {}), ('T', ''), (END, 'B'), (END, 'A'), ('T', '')],
				'A'
			),
				[('B', {}), ('T', ''), (END, 'B')]
		)
		self.assertEqual(	# nested
			collect_untill_end_token(
				[('A', {}), ('T', ''), (END, 'A'), (END, 'A'), ('T', '')],
				'A'
			),
				[('A', {}), ('T', ''), (END, 'A')]
		)
		with self.assertRaises(EndOfTokenListError):
			collect_untill_end_token(
				[('B', {}), ('T', ''), (END, 'B'), ('T', '')],
				'A'
			)

	def testTokensToText(self):
		self.assertEqual(
			tokens_to_text([('B', {}), ('T', 'Foo'), (END, 'B'), ('T', 'Bar')]),
			'FooBar'
		)
