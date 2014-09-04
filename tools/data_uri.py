#!/usr/bin/python

import base64

from zim.fs import File

def data_uri(file):
	if file.basename.endswith('.png'):
		mime = 'image/png'
	else:
		mime = file.get_mimetype()
	data64 = u''.join(base64.encodestring(file.raw()).splitlines())
	return u'data:%s;base64,%s' % (mime, data64)


if __name__ == '__main__':
	import sys
	file = File(sys.argv[1])
	print data_uri(file)
