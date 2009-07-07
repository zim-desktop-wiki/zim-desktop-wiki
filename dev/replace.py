#!/usr/bin/python

'''Tool to replace a string in a whole bunch of files'''

import os
import sys

def replace_in_dir(root, old, new):
	total = 0
	for dir, dirs, files in os.walk(root):
		for subdir in dirs[:]:
			if subdir.startswith('.'):
				dirs.remove(subdir)
		for file in files:
			total += replace_in_file(dir+'/'+file, old, new)
	print '%i total in %s' % (total, root)

def replace_in_file(file, old, new):
	fh = open(file)
	content = fh.read()
	fh.close()
	i = content.count(old)
	if i > 0:
		print '%i in %s' % (i, file)
		content = content.replace(old, new)
		fh = open(file, 'w')
		fh.write(content)
		fh.close()
	return i
	
	
if __name__ == '__main__':
	if len(sys.argv) == 4:
		replace_in_dir(*sys.argv[1:])
	else:
		print 'Usage: replace.py dir oldstring newstring'
