
# Copyright 2021 Thomas Engel <realdatenwurm@gmail.com>

import tests

from zim.search import *
from zim.notebook import Path


class TestCommandPalette(tests.TestCase):

	def setUp(self):
		self.notebook = self.setUpNotebook(content=tests.FULL_NOTEBOOK)
		plugin = PluginManager.load_plugin('commandpalette')
