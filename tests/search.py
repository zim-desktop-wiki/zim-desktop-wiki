
from tests import get_test_notebook, TestCase

from zim.search import *
from zim.notebook import Path

class TestSearchRegex(TestCase):

	def runTest(self):
		'''Test regex compilation for search terms'''
		for word, regex in (
			('foo', r'\bfoo\b'),
			('*foo', r'\b\S*foo\b'),
			('foo*', r'\bfoo\S*\b'),
			('*foo*', r'\b\S*foo\S*\b'),
			('foo$', r'\bfoo\$'),
			('foo bar', r'\bfoo\ bar\b'),
		):
			#print '>>', word, regex
			self.assertEqual(Query.regex(word), re.compile(regex, re.I))


		text = 'foo foobar FooBar Foooo Foo!'
		regex = Query.regex('foo')
		new, n = regex.subn('', text)
		self.assertEqual(n, 2)
		self.assertEqual(new, ' foobar FooBar Foooo !')

		text = 'foo foobar FooBar Foooo Foo!'
		regex = Query.regex('foo*')
		new, n = regex.subn('', text)
		self.assertEqual(n, 5)



class TestSearch(TestCase):

	def runTest(self):
		'''Test search API'''
		query = Query('foo bar')
		self.assertEqual(query.root,
			AndGroup([('content', 'foo'), ('content', 'bar')]) )

		notebook = get_test_notebook()
		searcher = Searcher(notebook)
		result = searcher.search(query)
		self.assertTrue(isinstance(result, ResultsSelection))
		self.assertTrue(len(result.pages) > 0)
		#~ print result.pages
		self.assertTrue(Path('Test:foo') in result.pages)
		self.assertTrue(Path('Test:foo:bar') in result.pages)
		scores = [result.scores[p] for p in result.pages]
		self.assertTrue(all(scores))

		#~ print result.pages

		notebook.index.update()
		query = Query('LinksTo: "Linking:Foo:Bar"')
		self.assertEqual(query.root,
			AndGroup([('linksto', 'Linking:Foo:Bar')]) )
		result = searcher.search(query)
		self.assertTrue(isinstance(result, ResultsSelection))
		self.assertTrue(Path('Linking:Dus:Ja') in result.pages)
		scores = [result.scores[p] for p in result.pages]
		self.assertTrue(all(scores))

		#~ print result.pages

# TODO subclass with file based notebook to test the 'grep' optimalisation
