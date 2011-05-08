
from tests import get_test_notebook, TestCase

from zim.search import *
from zim.notebook import Path

class TestSearchRegex(TestCase):

	def runTest(self):
		'''Test regex compilation for search terms'''
		regex_func = SearchSelection(None)._content_regex

		for word, regex in (
			('foo', r'\bfoo\b'),
			('*foo', r'\b\S*foo\b'),
			('foo*', r'\bfoo\S*\b'),
			('*foo*', r'\b\S*foo\S*\b'),
			('foo$', r'\bfoo\$'),
			('foo bar', r'\bfoo\ bar\b'),
		):
			#print '>>', word, regex
			self.assertEqual(regex_func(word), re.compile(regex, re.I | re.U))


		text = 'foo foobar FooBar Foooo Foo!'
		regex = regex_func('foo')
		new, n = regex.subn('', text)
		self.assertEqual(n, 2)
		self.assertEqual(new, ' foobar FooBar Foooo !')

		text = 'foo foobar FooBar Foooo Foo!'
		regex = regex_func('foo*')
		new, n = regex.subn('', text)
		self.assertEqual(n, 5)



class TestSearch(TestCase):

	def setUp(self):
		self.notebook = get_test_notebook()

	def runTest(self):
		'''Test search API'''
		self.notebook.index.update()
		results = SearchSelection(self.notebook)

		query = Query('foo bar')
		self.assertTrue(query.root.operator == OPERATOR_AND)
		self.assertEqual(query.root, [
				QueryTerm('contentorname', 'foo'),
				QueryTerm('contentorname', 'bar')
			] )
		results.search(query)
		#~ print results
		self.assertTrue(len(results) > 0)
		self.assertFalse(Path('TODOList:foo') in results)
		self.assertTrue(Path('Test:foo') in results)
		self.assertTrue(Path('Test:foo:bar') in results)
		self.assertTrue(set(results.scores.keys()) == results)
		self.assertTrue(all(results.scores.values()))

		query = Query('+TODO -bar')
		self.assertTrue(query.root.operator == OPERATOR_AND)
		self.assertEqual(query.root, [
				QueryTerm('contentorname', 'TODO'),
				QueryTerm('contentorname', 'bar', inverse=True)
			] )
		results.search(query)
		#~ print results
		self.assertTrue(len(results) > 0)
		self.assertTrue(Path('TODOList:foo') in results)
		self.assertFalse(Path('Test:foo') in results)
		self.assertFalse(Path('Test:foo:bar') in results)
		self.assertTrue(set(results.scores.keys()) == results)
		self.assertTrue(all(results.scores.values()))

		query = Query('TODO not bar')
		self.assertTrue(query.root.operator == OPERATOR_AND)
		self.assertEqual(query.root, [
				QueryTerm('contentorname', 'TODO'),
				QueryTerm('contentorname', 'bar', inverse=True)
			] )
		results.search(query)
		#~ print results
		self.assertTrue(len(results) > 0)
		self.assertTrue(Path('TODOList:foo') in results)
		self.assertFalse(Path('Test:foo') in results)
		self.assertFalse(Path('Test:foo:bar') in results)
		self.assertTrue(set(results.scores.keys()) == results)
		self.assertTrue(all(results.scores.values()))

		query = Query('TODO or bar')
		self.assertTrue(query.root.operator == OPERATOR_AND)
		self.assertTrue(query.root[0].operator == OPERATOR_OR)
		self.assertEqual(query.root, [ [
				QueryTerm('contentorname', 'TODO'),
				QueryTerm('contentorname', 'bar')
			] ] )
		results.search(query)
		#~ print results
		self.assertTrue(len(results) > 0)
		self.assertTrue(Path('TODOList:foo') in results)
		self.assertTrue(Path('Test:foo') in results)
		self.assertTrue(Path('Test:foo:bar') in results)
		self.assertTrue(set(results.scores.keys()) == results)
		self.assertTrue(all(results.scores.values()))

		query = Query('LinksTo: "Linking:Foo:Bar"')
		self.assertTrue(query.root.operator == OPERATOR_AND)
		self.assertEqual(query.root, [QueryTerm('linksto', 'Linking:Foo:Bar')])
		results.search(query)
		#~ print results
		self.assertTrue(Path('Linking:Dus:Ja') in results)
		self.assertTrue(set(results.scores.keys()) == results)
		self.assertTrue(all(results.scores.values()))

		query = Query('NOT LinksTo:"Linking:Foo:Bar"')
		self.assertTrue(query.root.operator == OPERATOR_AND)
		self.assertEqual(query.root, [QueryTerm('linksto', 'Linking:Foo:Bar', True)])
		results.search(query)
		#~ print results
		self.assertFalse(Path('Linking:Dus:Ja') in results)
		self.assertTrue(set(results.scores.keys()) == results)
		self.assertTrue(all(results.scores.values()))

		query = Query('LinksFrom: "Linking:Dus:Ja"')
		self.assertTrue(query.root.operator == OPERATOR_AND)
		self.assertEqual(query.root, [QueryTerm('linksfrom', 'Linking:Dus:Ja')])
		query = Query('Links: "Linking:Dus:Ja"') # alias for LinksFrom
		self.assertTrue(query.root.operator == OPERATOR_AND)
		self.assertEqual(query.root, [QueryTerm('linksfrom', 'Linking:Dus:Ja')])
		results.search(query)
		#~ print results
		self.assertTrue(Path('Linking:Foo:Bar') in results)
		self.assertTrue(set(results.scores.keys()) == results)
		self.assertTrue(all(results.scores.values()))

		query = Query('Namespace: "TODOList" fix')
		self.assertTrue(query.root.operator == OPERATOR_AND)
		self.assertEqual(query.root, [QueryTerm('namespace', 'TODOList'), QueryTerm('contentorname', 'fix')])
		results.search(query)
		#~ print results
		self.assertTrue(Path('TODOList:foo') in results)

		query = Query('Tag: tags')
		self.assertTrue(query.root.operator == OPERATOR_AND)
		self.assertEqual(query.root, [QueryTerm('tag', 'tags')])
		query = Query('@tags')
		self.assertTrue(query.root.operator == OPERATOR_AND)
		self.assertEqual(query.root, [QueryTerm('tag', 'tags')])
		results.search(query)
		#~ print results
		self.assertTrue(Path('Test:tags') in results and len(results) == 1)

		# TODO test ContentOrName versus Content
		# TODO test Name


def get_files_notebook(name):
	from tests import create_tmp_dir, get_test_data
	from zim.fs import Dir
	from zim.notebook import init_notebook, Notebook

	dir = Dir(create_tmp_dir(name))
	init_notebook(dir)
	notebook = Notebook(dir=dir)
	for name, text in get_test_data('wiki'):
		page = notebook.get_page(Path(name))
		page.parse('wiki', text)
		notebook.store_page(page)

	return notebook


class TestSearchFiles(TestSearch):

	slowTest = True

	def setUp(self):
		self.notebook = get_files_notebook('search_TestSearchFiles')

	def runTest(self):
		'''Test search API with file based notebook'''
		TestSearch.runTest(self)
