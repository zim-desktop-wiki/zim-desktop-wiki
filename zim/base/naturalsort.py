# Copyright 2012-2024 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''Functions for localized "natural" sorting'''


import locale
import re
import unicodedata


_num_re = re.compile(r'\d+')


def natural_sort_key(string, numeric_padding=5):
	'''Format string such that it gives 'natural' sorting on string
	compare. Will pad any numbers in the string with "0" such that "10"
	sorts after "9". Also includes C{locale.strxfrm()}.

	@note: sorting not 100% stable for case, so order between "foo" and
	"Foo" is not defined. For this reason when sort needs to be absolutely
	stable it is advised to sort based on tuples of
	C{(sort_key, original_string)}. Or use either L{natural_sort()} or
	L{natural_sorted()} instead.

	@param string: the string to format
	@param numeric_padding: number of digits to use for padding
	@returns: string transformed to sorting key
	'''
	templ = '%0' + str(numeric_padding) + 'i'
	string = string or ''  # Handle None by sorting as empty string
	string = unicodedata.normalize('NFC', string.strip())
	string = _num_re.sub(lambda m: templ % int(m.group()), string)
	string = string.lower() # sort case insensitive

	try:
		bytestring = locale.strxfrm(string)
			# 8-bit byte string - enode to hex -- in pyton3 check if byte data type is handled better by sqlite3 and others
	except MemoryError:
		# Known python issue :(
		bytestring = string

	key = ''.join(["%02x" % ord(c) for c in bytestring])
	return key


def natural_sort(list, key=None):
	'''Natural sort a list in place.
	See L{natural_sort_key} for details.
	@param list: list of strings to be sorted
	@param key: function producing strings for list items
	'''
	if key:
		def func(s):
			s = key(s)
			return (natural_sort_key(s), s)
	else:
		func = lambda s: (natural_sort_key(s), s)
	list.sort(key=func)


def natural_sorted(iter, key=None):
	'''Natural sort a list.
	See L{natural_sort_key} for details.
	@param iter: list or iterable of strings to be sorted
	@param key: function producing strings for list items
	@returns: sorted copy of the list
	'''
	l = list(iter) # cast to list and implicit copy
	natural_sort(l, key=key)
	return l
