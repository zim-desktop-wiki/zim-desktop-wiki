# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Package with storage backends for notebooks.'''

def get_store(name):
	'''Returns the module object for a specific store type.'''
	# __import__ has some quirks, soo the reference manual
	mod = __import__('zim.stores.'+name)
	mod = getattr(mod, 'stores')
	mod = getattr(mod, name)
	assert mod.__store__ == name
	return mod
