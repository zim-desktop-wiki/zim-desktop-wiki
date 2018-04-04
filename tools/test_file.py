#!/usr/bin/python

# Simple helper script to find and call the test case for a source file
# Intended to be called from a hotkey from an IDE while editing
# source files

# Assumes CWD is set by the IDE to the folder of the file to be tested
# Need to figure out the above project folder to run tests.


import os
import re
import subprocess


comment_re = re.compile('^\s*#\s*Tests\s*:', re.I)


def get_project_dir(file):
	pwd = os.getcwd()
	file = os.path.join(pwd, file)
	if pwd.endswith('tests'):
		pwd, x = file.rsplit('tests', 1)
	else:
		pwd, x = file.rsplit('zim', 1)
	return pwd, file[len(pwd):]


def get_test_names(file):
	basename, ext = os.path.basename(file).split('.', 1)
	if basename == '__init__':
		dir = os.path.dirname(file)
		basename = os.path.basename(dir)

	for line in open(file):
		m = comment_re.match(line)
		if m:
			i = len(m.group(0))
			tests = line[i:].strip().split()
			break
	else:
		tests = [basename]

	if "plugins" in os.path.dirname(file):
		tests.insert(0, 'plugins')

	return tests

def run_tests(pwd, names):
	argv = [os.path.join(pwd, 'test.py')] + names
	print(' '.join(argv))
	return subprocess.call(argv, cwd=pwd)


if __name__ == '__main__':
	import sys
	file = sys.argv[1]
	pwd, file = get_project_dir(file)
	names = get_test_names(os.path.join(pwd, file))
	re = run_tests(pwd, names)
	sys.exit(re)
