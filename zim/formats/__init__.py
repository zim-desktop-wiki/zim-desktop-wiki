# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Package with source formats for pages.'''

def get_format(name):
	'''Returns the module object for a specific format.'''
	# __import__ has some quirks, soo the reference manual
	mod = __import__('zim.formats.'+name)
	mod = getattr(mod, 'formats')
	mod = getattr(mod, name)
	assert mod.__format__ == name
	return mod
