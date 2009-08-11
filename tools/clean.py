#!/usr/bin/python

'''Tool to cleanup the source directory'''

import os
import sys
import shutil
from subprocess import Popen, PIPE

def main(remove=False):
	pipe = Popen('bzr ls --ignored', shell=True, stdout=PIPE).stdout
	print 'rm *.pyc'
	for line in pipe.readlines():
		file = line.strip()
		if os.path.isfile(file):
			if not file.endswith('.pyc'):
				print 'rm %s' % file
			if remove:
				os.remove(file)
		elif os.path.isdir(file):
			print 'rmtree %s' % file
			if remove:
				shutil.rmtree(file)
	pipe.close()

if __name__ == '__main__':
	warning = '\n### This is a test run, use --force to really delete\n'

	if len(sys.argv) == 2 and sys.argv[1] == '--force':
		main(remove=True)
	else:
		print warning
		main(remove=False)
		print warning
