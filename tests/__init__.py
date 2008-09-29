# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Zim test suite'''

import codecs

__all__ = ['fs', 'formats', 'templates', 'stores', 'notebook']

def get_notebook_data(format):
	'''Generator function for test data'''
	assert format == 'wiki' # No other formats available for now
	file = codecs.open('tests/notebook-wiki.txt', encoding='utf8')
	pagename = None
	buffer = u''
	for line in file:
		if line.startswith('%%%%'):
			# new page start, yield previous page
			if not pagename is None:
				yield (pagename, buffer)
			pagename = line.strip('% \n')
			buffer = u''
		else:
			buffer += line
	yield (pagename, buffer)

def	get_test_notebook(format='wiki'):
	'''Returns a notebook with a memory store and some test data'''
	notebook = Notebook()
	store = notebook.add_store('', 'memory')
	for name, text in get_notebook_data(format):
			store._set_node(name, text)
	return notebook
