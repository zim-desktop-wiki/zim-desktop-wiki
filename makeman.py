#!/usr/bin/python

# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import os

from time import strftime

from zim import __version__, __url__, \
	__author__, __copyright__, __license__
from zim.main import HelpCommand


def get_about():
	'''Get the tagline and short description from the README'''
	readme = open('README.txt')
	lines = []
	for line in readme:
		if line.startswith('===') and 'ABOUT' in line:
			for line in readme:
				if line.startswith('==='):
					break
				else:
					lines.append(line)
			break

	lines = ''.join(lines).strip().splitlines(True)
	assert lines and lines[0].startswith('Zim - ')
	tagline = lines[0][6:].strip()
	about = ''.join(lines[1:]).strip()

	return tagline, about


def make():
	'''Generate man page for zim'''

	tagline, about = get_about()
	try:
		os.mkdir('man')
	except OSError:
		pass # dir already exists
	manpage = open('man/zim.1', 'w')
	manpage.write('.TH ZIM "1" "%s" "zim %s" "User Commands"\n' % (strftime('%B %Y'), __version__))
	manpage.write('.SH NAME\nzim \\- %s\n\n' % tagline)
	manpage.write('.SH SYNOPSIS\n%s\n' % HelpCommand.usagehelp.replace('-', r'\-'))
	manpage.write('.SH DESCRIPTION\n%s\n' % about)
	manpage.write('.SH OPTIONS\n%s\n' % HelpCommand.optionhelp.replace('-', r'\-'))
	manpage.write('.SH AUTHOR\n%s\n\n' % __author__)
	manpage.write( '''\
.SH "SEE ALSO"
The full documentation for
.B zim
is maintained as a zim notebook. The command
.IP
.B zim --manual
.PP
should give you access to the complete manual.

The website for
.B zim
can be found at
.I %s
''' % __url__)
	manpage.close()


if __name__ == '__main__':
	make()
