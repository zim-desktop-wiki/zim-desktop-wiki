#!/usr/bin/python

# Simple helper script to find and call the test case for a source file
# Intended to be called from a hotkey from an IDE while editing
# source files

# Assumes CWD is set by the IDE to the folder of the file to be tested
# Need to figure out the above project folder to run tests.


import os
import subprocess


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
		file = os.path.dirname(file)
		basename, ext = os.path.basename(file).split('.', 1)

	if "plugins" in os.path.dirname(file):
		return ['plugins', basename]
	else:
		return [basename]


def run_tests(pwd, names):
	argv = [os.path.join(pwd, 'test.py')] + names
	print ' '.join(argv)
	return subprocess.call(argv, cwd=pwd)


if __name__ == '__main__':
	import sys
	file = sys.argv[1]
	pwd, file = get_project_dir(file)
	names = get_test_names(file)
	re = run_tests(pwd, names)
	sys.exit(re)
