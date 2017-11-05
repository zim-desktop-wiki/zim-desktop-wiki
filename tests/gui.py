# -*- coding: utf-8 -*-

# Copyright 2009-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import tests

import zim.gui

from zim.config import VirtualConfigManager

from zim.notebook import Path


class FilterNoSuchImageWarning(tests.LoggingFilter):

	def __init__(self):
		tests.LoggingFilter.__init__(self, 'zim.gui.pageview', 'No such image:')



def setupGtkInterface(test, klass=None, notebook=None):
	'''Setup a new GtkInterface object for testing.
	Will have test notebook, and default preferences.
	@param test: the test that wants to use this ui object
	@param klass: the klass to use, defaults to L{GtkInterface}, but
	could be partially mocked subclass
	'''
	ui = newSetupGtkInterface(test, klass, notebook)
	ui._mainwindow.open_page(Path('Test:foo:bar'))
	return ui


def newSetupGtkInterface(test, klass=None, notebook=None):

	print "Deprecated: setupGtkInterface"

	if klass is None:
		klass = zim.gui.GtkInterface

	# start filtering
	filter = FilterNoSuchImageWarning()
	filter.wrap_test(test)


	# create interface object with new notebook
	if notebook is None:
		notebook = test.setUpNotebook(content=tests.FULL_NOTEBOOK)

	config = VirtualConfigManager()
	prefs = config.get_config_dict('<profile>/preferences.conf')
	prefs['General'].input(plugins=['calendar', 'insertsymbol', 'printtobrowser'])
		# version control interferes with source folder, leave other default plugins

	ui = klass(config=config, notebook=notebook)

	ui._mainwindow.init_uistate() # XXX

	return ui
