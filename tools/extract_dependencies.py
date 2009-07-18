#!/usr/bin/python

import os

def extract_deps(file):
	#~ print 'Extracting from %s' % file
	deps = set()
	for line in open(file).readlines():
		line = line.strip()
		if line.startswith('import') or line.startswith('from'):
			words = line.split()
			if words[0] == 'import' or (words[0] == 'from' and words[2] == 'import'):
				deps.add(words[1])
	return deps

def main():
	deps = set()
	deps.update( extract_deps('zim.py') )
	for dir, dirs, files in os.walk('zim/'):
		for file in filter(lambda f: f.endswith('.py'), files):
			deps.update( extract_deps(dir+'/'+file) )
	deps = [d for d in deps if not d.startswith('zim')]
	deps.sort()

	for d in deps:
		print d

if __name__ == '__main__':
	main()
