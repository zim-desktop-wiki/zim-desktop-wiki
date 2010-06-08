
import gtk

clipboard = gtk.Clipboard()

targets = clipboard.wait_for_targets()

for target in targets:
	print '='*80
	print target + ':'
	print ''
	selectiondata = clipboard.wait_for_contents(target)
	if selectiondata:
		print selectiondata.data
	else:
		print '<None>'
