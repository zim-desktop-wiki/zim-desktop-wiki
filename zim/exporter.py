# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Commandline exporter for zim notebooks'''


from zim import Application


class Exporter(Application):
	'''FIXME'''

	def __init__(self, **opts):
		'''FIXME'''
		Application.__init__(self, **opts)

		assert opts['format']

		if isinstance(opts['template'], basestring):
			from zim.templates import get_template
			opts['template'] = get_template(opts['format'], opts['template'])

		self.template = opts['template']
		self.format = opts['format']
		self.output = opts['output']

	def open_page(self, pagename):
		'''FIXME'''
		# TODO: use selection instead
		assert self.notebook
		page = self.notebook.get_page(pagename)
		self.page = page

	def main(self):
		'''Process export options'''
		import zim.notebook

		# TODO: output to file or dir instead of stdout
		# TODO: process whole notebook
		assert self.page

		if self.template is None:
			print self.page.get_text(format=self.format).encode('utf8')
		else:
			import sys
			self.template.process(self.page, sys.stdout)
