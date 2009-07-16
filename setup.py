#!/usr/bin/env python

import os
import sys
import shutil

from distutils.core import setup
from distutils.command.sdist import sdist as sdist_class
from distutils.command.build_py import build_py as build_py_class
from distutils.command.install import install as install_class

from zim import __version__, __url__

try:
	version_info = sys.version_info
	assert version_info >= (2, 5)
	assert version_info < (3, 0)
except:
	print >> sys.stderr, 'zim needs python >= 2.5   (but < 3.0)'
	sys.exit(1)

warning = '''
****************************  WARNING  *********************************
This is an _alpha_ version of zim. It is likely to be unstable and buggy.
Please download the stable version to do any real work.
'''

print warning

# Helper routines

def collect_packages():
	# Search for python packages below zim/
	packages = []
	for dir, dirs, files in os.walk('zim'):
		if '__init__.py' in files:
			package = '.'.join(dir.split(os.sep))
			packages.append(package)
	#~ print 'Pakages: ', packages
	return packages


def include_file(file):
	if file.startswith('.'): return False
	else: 
		for ext in ('~', '.bak', '.swp', '.pyc'):
			if file.endswith(ext): return False
	return True


def collect_data_files():
	# Search for data files to be installed in share/
	data_files = [
		('share/pixmaps', ['data/zim.png']),
		('share/applications', ['xdg/zim.desktop']),
		('share/mime/packages', ['xdg/zim.xml']),
	]
	
	# data -> PREFIX/share/zim
	for dir, dirs, files in os.walk('data'):
		if '.zim' in dirs:
			dirs.remove('.zim')
		target = os.path.join('share', 'zim', dir[5:])
		
		files = filter(include_file, files)
		files = [os.path.join(dir, f) for f in files]
		data_files.append((target, files))


	#~ print 'Data files: ', data_files
	return data_files


def create_distmeta():
	# Try to update version info
	if os.path.exists('.bzr/'):
		print 'updating bzr version-info...'
		os.system('bzr version-info --format python > zim/_version.py')

	# Duplicate some files to get layout right..
	if not os.path.isdir('bin'):
		print 'creating bin/'
		os.mkdir('bin')

	print 'copying zim.py -> bin/zim'
	shutil.copy('zim.py', 'bin/zim')

	print 'copying CHANGELOG.txt -> data/manual/Changelog.txt'
	shutil.copy('CHANGELOG.txt', 'data/manual/Changelog.txt')


# Overloaded commands

class zim_sdist_class(sdist_class):
	# Command to build source distribution
	# make sure _version.py gets build and included

	def run(self):
		create_distmeta()
		if os.path.isfile('MANIFEST'):
			os.remove('MANIFEST') # force manifest to be re-generated
		sdist_class.run(self)


class zim_build_py_class(build_py_class):
	# Command to build python libraries,
	# make sure _version.py gets build

	def run(self):
		create_distmeta()
		if os.path.isfile('MANIFEST'):
			os.remove('MANIFEST') # force manifest to be re-generated
		build_py_class.run(self)


# TODO trigger XDG tools
# 'update-desktop-database'
# 'update-mime-database', $mimedir
# 'xdg-icon-resource install --context apps --size 64 %s' % icon
# 'xdg-icon-resource install --context mimetypes --size 64 %s application-x-zim-notebook' % icon


# Distutils parameters, and main function

dependencies = ['gobject', 'gtk', 'xdg']
if version_info == (2, 5):
	dependencies.append('simplejson')


setup(
	# wire overload commands
	cmdclass = {
		'sdist': zim_sdist_class,
		'build_py': zim_build_py_class,
	},

	# provide package properties
	name         = 'pyzim',
	version      = __version__,
	description  = 'Zim desktop wiki',
	author       = 'Jaap Karssenberg',
	author_email = 'pardus@cpan.org',
	license      = 'GPL',
	url          = __url__,
	scripts      = ['bin/zim'],
	packages     = collect_packages(),
	data_files   = collect_data_files(),
	requires     = dependencies
)


print warning
