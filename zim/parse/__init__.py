# Copyright 2009-2024 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains various classes and functions to help with parsing text content
and handling tokenlist or parse-tree structures.

These are utilities that are used in various parts of the application.

See also the various sub-modules
'''

import re



def convert_space_to_tab(text, tabstop=4):
	'''Convert spaces to tabs
	@param text: the input text
	@param tabstop: the number of spaces to represent a tab
	@returns: the fixed text
	'''
	# Fix tabs
	spaces = ' ' * tabstop
	pattern = '^(\t*)((?:%s)+)' % spaces
	text = re.sub(
		pattern,
		lambda m: m.group(1) + '\t' * (len(m.group(2)) // tabstop),
		text,
		flags=re.M
	)
	return text


def fix_unicode_whitespace(text):
	'''Replaces unicode whitespace characters
	These characters are recognized by "splitlines()" but not as end-of-line
	in regexes. See also issue #1760
	@param text: the input text
	@returns: the fixed text
	'''
	text = text.replace('\u2028', '\n') # LINE SEPARATOR
	text = text.replace('\u2029', ' ') # PARAGRAPH SEPARATOR
	return text
