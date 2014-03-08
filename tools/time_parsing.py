#!/usr/bin/python

# -*- coding: utf-8 -*-

# Copyright 2012 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import sys
sys.path.insert(0, '.')

import zim.formats
import zim.fs
import tests

def setup():
	global parser, dumper
	parser = zim.formats.get_parser('wiki')
	dumper = zim.formats.get_dumper('wiki')

	global wikitext, parsetree
	wikitext = zim.fs.File('tests/data/formats/wiki.txt').read()
	xml = zim.fs.File('tests/data/formats/parsetree.xml').read().rstrip('\n')
	parsetree = tests.new_parsetree_from_xml(xml)

	global smalltext, smalltree
	smalltext = "foo **bar** baz\n"
	xml = "<?xml version='1.0' encoding='utf-8'?><zim-tree>foo <strong>bar</strong> baz\n</zim-tree>"
	smalltree = tests.new_parsetree_from_xml(xml)

def timeParsing():
	parser.parse(wikitext)


def timeDumping():
	dumper.dump(parsetree)


def timeParsingSmall():
	parser.parse(smalltext)


def timeDumpingSmall():
	dumper.dump(smalltree)


if __name__ == '__main__':
	from timeit import Timer
	reps = 5
	passes = 1000
	funcs = [n for n in dir() if n.startswith('time')]
	funcs.sort()

	print "Rep: %i, Passes: %i" % (reps, passes)
	print "Plan: %s" % ', '.join(funcs)
	print ''
	print "Func\tMin\tMax\tAvg [msec/pass]"

	for func in funcs:
		setupcode = "from __main__ import setup, %s; setup()" % func
		testcode = "%s()" % func

		t = Timer(testcode, setupcode)
		try:
			result = t.repeat(reps, passes)
		except:
			print "FAILED running %s" % func
			t.print_exc()
		else:
			print "%s\t%.2f\t%.2f\t%.2f" % (
				func,
				(1E+3 * min(result)/passes),
				(1E+3 * max(result)/passes),
				(1E+3 * sum(result)/(reps*passes)),
			)
