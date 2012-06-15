# -*- coding: utf-8 -*-

# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

import zim.config

from zim.plugins.cards import *

# Test data, 3-tuples of: form text, input fields, and values
FORMS = [
	('''\
:Author(p): Authors:
:Title(s):
:Publisher(s):
 ...
 ...
''',
		(
			# name, type, label
			('Author', 'page', 'Author'),
			('Title', 'string', 'Title'),
			('Publisher', 'string', 'Publisher'),
				# TODO how to code a 3 line multiling text field ?
		),
		{
			'Author': 'Authors:',
			'Title': '',
			'Publisher': '',
		}
	),
	#~ ('''\
#~ == Book ==
#~ :Author(p): Authors:
#~ :Title(s):
#~
#~ [Column width=64]
#~ :Cover(img):
#~ ''',
		#~ (),
		#~ {}
	#~ )
]


@tests.slowTest
class TestsCardsPlugin(tests.TestCase):

	def testParsing(self):
		attrib = {'type': 'Book'}
		for text, inputs, values in FORMS:
			obj = CardObject(attrib, text)
			self.assertEqual(obj.inputs, inputs)
			self.assertEqual(obj.values, values)

	#~ def testIndexing(self):
		#~ ui = MockUI()
		#~ plugin = CardsPlugin(ui)
		#~ index = ui.notebook.index
#~
		#~ index.flush()
		#~ index.update()
#~
		#~ self.assertEqual(index.list_properties(page), [])


class MockUI(tests.MockObject):

	def __init__(self):
		tests.MockObject.__init__(self)
		self.preferences = zim.config.ConfigDict()
		self.uistate = zim.config.ConfigDict()
		self.notebook = tests.new_notebook()
