#!/usr/bin/python

'''Interactively dumps clipboard contents to stdout'''

import gtk
import sys

clipboard = gtk.Clipboard()
targets = clipboard.wait_for_targets()

print "="*80
print "Enter a number to see a specific target, or <Enter> to exit"
print "Available targets:"
for i in range(len(targets)):
	print i, targets[i]

line = sys.stdin.readline().strip()
while line:
	target = targets[int(line)]
	print '>>>>', target
	selection = clipboard.wait_for_contents(target)
	if selection:
		text = selection.get_text()
		if not text is None:
			print '== Text:', text
		else:
			print '== Data:', selection.data
	else:
		print '== No contents'
	print '<<<<'
	line = sys.stdin.readline().strip()
