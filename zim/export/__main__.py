# -*- coding: utf-8 -*-

# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import sys
import logging

from zim.export import *

import zim.notebook

TEMPLATE = './tests/data/TestTemplate.html'


if __name__ == '__main__':
	logging.basicConfig()

	assert len(sys.argv) == 4, 'USAGE: [multi|single|mhtml] inputpath outputpath'
	action = sys.argv[1]
	notebookpath = sys.argv[2]
	outputpath = sys.argv[3]

	info = zim.notebook.resolve_notebook(notebookpath)
	notebook, page = zim.notebook.build_notebook(info)
	notebook.index.update()

	if action == 'multi':
		if page:
			exporter = build_page_exporter(
				File(outputpath), 'html', TEMPLATE, page=page
			)
		else:
			exporter = build_notebook_exporter(
				Dir(outputpath), 'html', TEMPLATE, index_page='index'
			)
	elif action == 'single':
		exporter = build_single_file_exporter(
			File(outputpath), 'html', TEMPLATE, namespace=page
		)
	elif action == 'mhtml':
		exporter = build_mhtml_file_exporter(
			File(outputpath), TEMPLATE
		)
	else:
		assert False, 'TODO'


	if page:
		from .selections import SubPages
		pages = SubPages(notebook, page)
	else:
		from .selections import AllPages
		pages = AllPages(notebook)

	print 'Exporting'
	for p in exporter.export_iter(pages):
		#~ sys.stdout.write('.')
		#~ sys.stdout.flush()
		print '\tExport', p
	print ' done'
