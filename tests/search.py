# -*- coding: utf-8 -*-

# Copyright 2011 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

from zim.search import *
from zim.notebook import Path

class TestSearchRegex(tests.TestCase):

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



class TestSearch(tests.TestCase):

	def setUp(self):
		self.notebook = tests.new_notebook()

	def callback_check(self, selection, path):
		self.assertIsInstance(selection, (SearchSelection, type(None)))
		self.assertIsInstance(path, (Path, type(None)))
		return True

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
		results.search(query, callback=self.callback_check)
		#~ print results
		self.assertTrue(len(results) > 0)
		self.assertFalse(Path('TaskList:foo') in results)
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
		results.search(query, callback=self.callback_check)
		#~ print results
		self.assertTrue(len(results) > 0)
		self.assertTrue(Path('TaskList:foo') in results)
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
		results.search(query, callback=self.callback_check)
		#~ print results
		self.assertTrue(len(results) > 0)
		self.assertTrue(Path('TaskList:foo') in results)
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
		results.search(query, callback=self.callback_check)
		#~ print results
		self.assertTrue(len(results) > 0)
		self.assertTrue(Path('TaskList:foo') in results)
		self.assertTrue(Path('Test:foo') in results)
		self.assertTrue(Path('Test:foo:bar') in results)
		self.assertTrue(set(results.scores.keys()) == results)
		self.assertTrue(all(results.scores.values()))

		query = Query('ThisWordDoesNotExistingInTheTestNotebook')
		results.search(query, callback=self.callback_check)
		self.assertFalse(results)

		query = Query('LinksTo: "Linking:Foo:Bar"')
		self.assertTrue(query.root.operator == OPERATOR_AND)
		self.assertEqual(query.root, [QueryTerm('linksto', 'Linking:Foo:Bar')])
		results.search(query, callback=self.callback_check)
		#~ print results
		self.assertTrue(Path('Linking:Dus:Ja') in results)
		self.assertTrue(set(results.scores.keys()) == results)
		self.assertTrue(all(results.scores.values()))

		query = Query('NOT LinksTo:"Linking:Foo:Bar"')
		self.assertTrue(query.root.operator == OPERATOR_AND)
		self.assertEqual(query.root, [QueryTerm('linksto', 'Linking:Foo:Bar', True)])
		results.search(query, callback=self.callback_check)
		#~ print results
		self.assertFalse(Path('Linking:Dus:Ja') in results)
		self.assertTrue(set(results.scores.keys()) == results)
		self.assertTrue(all(results.scores.values()))

		query = Query('LinksTo:"NonExistingNamespace:*"')
		results.search(query, callback=self.callback_check)
		self.assertFalse(results)

		query = Query('LinksFrom: "Linking:Dus:Ja"')
		self.assertTrue(query.root.operator == OPERATOR_AND)
		self.assertEqual(query.root, [QueryTerm('linksfrom', 'Linking:Dus:Ja')])
		query = Query('Links: "Linking:Dus:Ja"') # alias for LinksFrom
		self.assertTrue(query.root.operator == OPERATOR_AND)
		self.assertEqual(query.root, [QueryTerm('linksfrom', 'Linking:Dus:Ja')])
		results.search(query, callback=self.callback_check)
		#~ print results
		self.assertTrue(Path('Linking:Foo:Bar') in results)
		self.assertTrue(set(results.scores.keys()) == results)
		self.assertTrue(all(results.scores.values()))

		query = Query('LinksFrom:"NonExistingNamespace:*"')
		results.search(query, callback=self.callback_check)
		self.assertFalse(results)

		query = Query('Namespace: "TaskList" fix')
		self.assertTrue(query.root.operator == OPERATOR_AND)
		self.assertEqual(query.root, [QueryTerm('namespace', 'TaskList'), QueryTerm('contentorname', 'fix')])
		results.search(query, callback=self.callback_check)
		#~ print results
		self.assertTrue(Path('TaskList:foo') in results)

		for text in (
			'Namespace: "Test:Foo Bar"',
			'Namespace:"Test:Foo Bar"'
			'Section: "Test:Foo Bar"'
			'Section:"Test:Foo Bar"'
		):
			# check if space in page name works - found bug for 2nd form
			query = Query(text)
			results.search(query, callback=self.callback_check)
			#~ print text, '>>' , results
			self.assertTrue(Path('Test:Foo Bar:Dus Ja Hmm') in results)

		query = Query('Namespace: "NonExistingNamespace"')
		results.search(query, callback=self.callback_check)
		#~ print results
		self.assertFalse(results)

		query = Query('Tag: tags')
		self.assertTrue(query.root.operator == OPERATOR_AND)
		self.assertEqual(query.root, [QueryTerm('tag', 'tags')])
		query = Query('@tags')
		self.assertTrue(query.root.operator == OPERATOR_AND)
		self.assertEqual(query.root, [QueryTerm('tag', 'tags')])
		results.search(query, callback=self.callback_check)
		#~ print results
		self.assertTrue(Path('Test:tags') in results and len(results) == 2)
			# Tasklist:all is the second match

		query = Query('Tag: NonExistingTag')
		results.search(query, callback=self.callback_check)
		self.assertFalse(results)

		# TODO test ContentOrName versus Content
		# TODO test Name


@tests.slowTest
class TestSearchFiles(TestSearch):

	def setUp(self):
		path = self.create_tmp_dir()
		self.notebook = tests.new_files_notebook(path)

	def runTest(self):
		'''Test search API with file based notebook'''
		TestSearch.runTest(self)
