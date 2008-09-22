#!/usr/bin/env python

from distutils.core import setup

import os
import zim

# Search for packages below zim/
zim_packages = []
for dir, dirs, files in os.walk('zim'):
	if '__init__.py' in files:
		package = '.'.join( dir.split('/') )
		zim_packages.append(package)

# Distutils parameters, and main function
setup(
	name         = 'pyzim',
	version      = zim.__version__,
	description  = 'Zim desktop wiki',
	author       = 'Jaap Karssenberg',
	author_email = 'pardus@cpan.org',
	url          = 'http://zim-wiki.org',
	packages     = zim_packages,
)
