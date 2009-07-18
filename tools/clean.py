#!/usr/bin/python

'''Tool to cleanup the source directory'''

import os
import sys
from subprocess import Popen, PIPE

def main(remove=False):
	pipe = Popen('bzr ls --ignored', shell=True, stdout=PIPE).stdout
	for line in pipe.readlines():
		file = line.strip()
		if os.path.isfile(file):
			print 'rm %s' % file
			if remove:
				os.remove(file)
	pipe.close()

if __name__ == '__main__':
	warning = '\n### This is a test run, use --force to really delete\n'

	if len(sys.argv) == 2 and sys.argv[1] == '--force':
		main(remove=True)
	else:
		print warning
		main(remove=False)
		print warning
