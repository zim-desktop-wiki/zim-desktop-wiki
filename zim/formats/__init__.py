
def get_format(name):
	'''...'''
	# __import__ has some quirks, soo the reference manual
	mod = __import__('zim.formats.'+name)
	mod = getattr(mod, 'formats')
	mod = getattr(mod, name)
	return mod
