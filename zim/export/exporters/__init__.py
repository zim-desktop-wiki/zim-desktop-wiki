
# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''The exporters are the main public objects for exporting, they
control the execution of the whole process. Each exporter implements a
different export style.
'''

# TODO collect errors / warnings and write a log that can be shown to the user after exporting

import logging

logger = logging.getLogger('zim.export')


class Exporter(object):
	'''Base class that defines the public API for exporter objects'''

	def export(self, pages):
		'''Export pages
		@param pages: a L{PageSelection} object
		'''
		for p in self.export_iter(pages):
			logger.info('Exporting %s', p)

	def export_iter(self, pages):
		'''Export pages while yielding page objects that are exported
		for progress monitoring

		Also note that implementations must be robust to ignore errors
		when exporting pages.

		@param pages: a L{PageSelection} object
		@implementation: must be implemented by subclasses
		'''
		raise NotImplementedError



from zim.notebook.page import Path, Page
from zim.newfs.mock import MockFile
from zim.formats import ParseTreeBuilder, \
	FORMATTEDTEXT, HEADING, BULLETLIST, LISTITEM, LINK


def createIndexPage(notebook, path, section=None):
		# TODO make more flexible - use pages iter itself instead of section of notebook
		if section is None:
			section = Path(':')
			title = notebook.name
		else:
			title = section.name

		builder = ParseTreeBuilder()

		def add_namespace(path):
			pagelist = notebook.pages.list_pages(path)
			builder.start(BULLETLIST)
			for page in pagelist:
				builder.start(LISTITEM)
				builder.append(LINK,
					{'type': 'page', 'href': page.name}, page.basename)
				builder.end(LISTITEM)
				if page.haschildren:
					add_namespace(page) # recurs
			builder.end(BULLETLIST)

		builder.start(FORMATTEDTEXT)
		builder.append(HEADING, {'level': 1}, 'Index of %s\n' % title)
		add_namespace(section)
		builder.end(FORMATTEDTEXT)

		tree = builder.get_parsetree()
		#~ print("!!!", tree.tostring())

		indexpage = Page(path, False, MockFile('/index'), None)
		indexpage.set_parsetree(tree)
		return indexpage
