# -*- coding: utf-8 -*-

# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''When this module is run as a script it allows conversion
from one format to another
Given two format names it will read the first format from stdin
and write the second format to stdout::

	cat foo.txt | python -m zim.formats wiki html > foo.html

Given only one format name it will output the parsetree XML::

	cat foo.txt | python -m zim.formats wiki > foo.xml

Note that this can not replace "zim --export" because no effort is
done here to resolve links. Main purpose is testing.
'''

import sys
import logging

from zim.fs import Dir
from zim.formats import *


if __name__ == '__main__':
	if len(sys.argv) not in (2, 3, 4):
			print 'Usage: python -m zim.formats format [format] [source_dir]'
			print '\tWill read from stdin and output to stdout'
			sys.exit(1)


	logging.basicConfig()

	inputformat = sys.argv[1]
	if len(sys.argv) == 4:
		outputformat = sys.argv[2]
		source_dir = Dir(sys.argv[3])
	elif len(sys.argv) == 3:
		outputformat = sys.argv[2]
		source_dir = None
	else:
		outputformat = '__XML__'
		source_dir = None

	input = sys.stdin.read()

	parser = get_parser(inputformat)
	tree = parser.parse(input)

	if outputformat == '__XML__':
		sys.stdout.write(tree.tostring())
	else:
		linker = StubLinker(source_dir=source_dir)
		dumper = get_dumper(outputformat, linker=linker)
		lines = dumper.dump(tree)
		sys.stdout.write(''.join(lines).encode('utf-8'))
