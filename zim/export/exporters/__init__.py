# -*- coding: utf-8 -*-

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
			logger.info('Exporting %s', p.name)

	def export_iter(self, pages):
		'''Export pages while yielding page objects that are exported
		for progress monitoring

		Also note that implementations must be robust to ignore errors
		when exporting pages.

		@param pages: a L{PageSelection} object
		@implementation: must be implemented by subclasses
		'''
		raise NotImplementedError
