#!/usr/bin/env python

import os
import sys

from distutils.core import setup
from distutils.command.sdist import sdist
from distutils.command.build_py import build_py

from zim import __version__, __url__

try:
	version_info = sys.version_info
	assert version_info >= (2, 5)
except:
	print >> sys.stderror, 'zim needs python >= 2.5'
	sys.exit(1)


# Helper routines

def collect_packages():
	# Search for python packages below zim/
	packages = []
	for dir, dirs, files in os.walk('zim'):
		if '__init__.py' in files:
			package = '.'.join( os.path.split(dir) )
			packages.append(package)
	return packages


def collect_data_files():
	# Search for data files to be installed in share/
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

	return data_files


def create_distmeta():
	# Try to update version info
	if os.path.exists('.bzr/'):
		print 'updating bzr version-info...'
		os.system('bzr version-info --format python > zim/_version.py')


# Overloaded commands

class sdist_zim(sdist):
	# Command to build source distribution
	# make sure _version.py gets build and included

	def run(self):
		create_distmeta()
		sdist.run(self)


class build_py_zim(build_py):
	# Command to build python libraries,
	# make sure _version.py gets build

	def run(self):
		create_distmeta()
		build_py.run(self)


# TODO overload install_scripts in to rename zim.py -> zim


# Distutils parameters, and main function

setup(
	# wire overload commands
	cmdclass = {
		'sdist': sdist_zim,
		'build_py': build_py_zim,
	},

	# provide package properties
	name         = 'pyzim',
	version      = __version__,
	description  = 'Zim desktop wiki',
	author       = 'Jaap Karssenberg',
	author_email = 'pardus@cpan.org',
	license      = 'GPL',
	url          = __url__,
	scripts      = ['zim.py'],
	packages     = collect_packages(),
	data_files   = collect_data_files(),
)
