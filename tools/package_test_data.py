#!/usr/bin/python

import sys

sys.path.insert(0, '.')

from zim.fs import *
from zim.notebook import Path
import zim.stores.files
import zim.stores.xml


def walk(store, path):
	for page in store.get_pagelist(path):
		yield page
		for child in walk(store, page):
			yield child


def package(dir, file):
	if file.exists():
		file.remove()
	fh = file.open('w')
	fh.write('<?xml version="1.0" econding="utf-8"?>\n')
	fh.write('<!-- this file is NOT in store.xml format -->\n')
	fh.write('<pagelist>\n')
	source = zim.stores.files.Store(None, Path(':'), dir=dir)
	for page in walk(source, Path(':')):
		if not page.hascontent:
			continue
		text = page.source.read()
		text = text.replace('&', '&amp;')
		text = text.replace('<', '&lt;')
		text = text.replace('>', '&gt;')
		fh.write('<page name="%s">\n' % page.name)
		fh.write(text)
		fh.write('</page>\n')
	fh.write('</pagelist>\n')
	fh.close()


def extract(file, dir):
	if dir.exists():
		raise Exception, 'dir exists alread'
	assert False, 'TODO'


if __name__ == '__main__':
	if len(sys.argv) == 4 and sys.argv[1] == '--package':
		package(Dir(sys.argv[2]), File(sys.argv[3]))
	elif len(sys.argv) == 4 and sys.argv[1] == '--extract':
		extract(File(sys.argv[2]), Dir(sys.argv[3]))
	else:
		print 'usage: %s --package DIR FILE\n' \
		      '       %s --extract FILE DIR' % (sys.argv[0], sys.argv[0])
