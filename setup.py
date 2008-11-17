#!/usr/bin/env python

from distutils.core import setup

import os
import sys
import zim

try:
	version_info = sys.version_info
	assert version_info >= (2, 5)
except:
	print >> sys.stderror, 'zim needs python >= 2.5'
	sys.exit(1)

# Try to update version info
if sys.argv[1] in ('build', 'build_py', 'sdist', 'bdist') \
and os.path.exists('.bzr/'):
	print 'Updating bzr version-info...'
	os.system('bzr version-info --format python > zim/_version.py')

# Search for packages below zim/
packages = []
for dir, dirs, files in os.walk('zim'):
	if '__init__.py' in files:
		package = '.'.join( os.path.split(dir) )
		packages.append(package)

# Collect data files
data_files = [
	('share/pixmaps', ['data/zim.png']),
	('share/applications', ['zim.desktop']),
	# TODO mime source data
]
for dir, dirs, files in os.walk('data'):
	target = os.path.join('share', 'zim', dir[5:])
	files = [os.path.join(dir, f) for f in files]
	data_files.append((target, files))

# TODO similar logic for pixmaps

# Distutils parameters, and main function
setup(
	name         = 'pyzim',
	version      = zim.__version__,
	description  = 'Zim desktop wiki',
	author       = 'Jaap Karssenberg',
	author_email = 'pardus@cpan.org',
	license      = 'GPL',
	url          = zim.__url__,
	scripts      = ['zim.py'],
	packages     = packages,
	data_files   = data_files
)
