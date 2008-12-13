# -*- coding: utf8 -*-

# Copyright 2008 Jaap Karssenberg <pardus@cpan.org>

'''Commandline exporter for zim notebooks'''


from zim import Interface


class CommandInterface(Interface):
	'''FIXME'''

	def __init__(self, template='Default', format='html', output=None, **opts):
		'''FIXME'''
		Interface.__init__(self, **opts)

		assert format
		if isinstance(template, basestring):
			from zim.templates import get_template
			template = get_template(format, template)
		self.template = template
		self.format = format
		self.output = output

	def open_page(self, pagename):
		'''FIXME'''
		# TODO: use selection instead
		assert self.notebook
		self.page = self.notebook.get_page(pagename)

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
