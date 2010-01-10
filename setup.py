#!/usr/bin/env python

import os
import sys
import shutil
import subprocess

from distutils.core import setup
from distutils.command.sdist import sdist as sdist_class
from distutils.command.build import build as build_class
from distutils.command.build_scripts import build_scripts as build_scripts_class
from distutils.command.install import install as install_class
from distutils import cmd
from distutils import dep_util


from zim import __version__, __url__

import msgfmt # also distributed with zim
import makeman # helper script

try:
	version_info = sys.version_info
	assert version_info >= (2, 5)
	assert version_info < (3, 0)
except:
	print >> sys.stderr, 'zim needs python >= 2.5   (but < 3.0)'
	sys.exit(1)


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


def get_mopath(pofile):
	# Function to determine right locale path for a .po file
	lang = os.path.basename(pofile)[:-3] # len('.po') == 3
	modir = os.path.join('locale', lang, 'LC_MESSAGES')
	mofile = os.path.join(modir, 'zim.mo')
	return modir, mofile


def include_file(file):
	# Check to exclude hidden and temp files
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
		('share/man/man1', ['man/zim.1']),
	]

	# data -> PREFIX/share/zim
	for dir, dirs, files in os.walk('data'):
		if '.zim' in dirs:
			dirs.remove('.zim')
		target = os.path.join('share', 'zim', dir[5:])

		files = filter(include_file, files)
		files = [os.path.join(dir, f) for f in files]
		data_files.append((target, files))

	# .po files -> PREFIX/share/locale/..
	for pofile in [f for f in os.listdir('po') if f.endswith('.po')]:
		pofile = os.path.join('po', pofile)
		modir, mofile = get_mopath(pofile)
		target = os.path.join('share', modir)
		data_files.append((target, [mofile]))

	#~ print 'Data files: ', data_files
	return data_files


def fix_dist():
	# Try to update version info
	if os.path.exists('.bzr/'):
		print 'updating bzr version-info...'
		os.system('bzr version-info --format python > zim/_version.py')

	# Generate man page
	makeman.make()

	# Add the changelog to the manual
	# print 'copying CHANGELOG.txt -> data/manual/Changelog.txt'
	# shutil.copy('CHANGELOG.txt', 'data/manual/Changelog.txt')


# Overloaded commands

class zim_sdist_class(sdist_class):
	# Command to build source distribution
	# make sure _version.py gets build and included

	def initialize_options(self):
		sdist_class.initialize_options(self)
		self.force_manifest = 1 # always re-generate MANIFEST

	def run(self):
		fix_dist()
		sdist_class.run(self)


class zim_build_trans_class(cmd.Command):
	# Compile mo files

	description = 'Build translation files'
	user_options = []

	def initialize_options(self):
		pass

	def finalize_options(self):
		pass

	def run(self):
		for pofile in [f for f in os.listdir('po') if f.endswith('.po')]:
			pofile = os.path.join('po', pofile)
			modir, mofile = get_mopath(pofile)

			if not os.path.isdir(modir):
				os.makedirs(modir)

			if not os.path.isfile(mofile) or dep_util.newer(pofile, mofile):
				print 'compiling %s' % mofile
				msgfmt.make(pofile, mofile)
			else:
				#~ print 'skipping %s - up to date' % mofile
				pass


class zim_build_scripts_class(build_scripts_class):
	# Adjust bin/zim.py -> bin/zim

	def run(self):
		build_scripts_class.run(self)
		if os.name == 'posix' and not self.dry_run:
			for script in self.scripts:
				if script.endswith('.py'):
					file = os.path.join(self.build_dir, script)
					print 'renaming %s to %s' % (file, file[:-3])
					os.rename(file, file[:-3]) # len('.py') == 3


class zim_build_class(build_class):
	# Generate _version.py etc. and call build_trans as a subcommand

	sub_commands = build_class.sub_commands + [('build_trans', None)]

	def run(self):
		fix_dist()
		build_class.run(self)


class zim_install_class(install_class):

	def run(self):
		install_class.run(self)

		# Try XDG tools
		icon = os.path.join('data', 'zim.png')
		mimedir = os.path.join(self.install_data, 'share', 'mime')
		for cmd in (
			('update-desktop-database',),
			('update-mime-database', mimedir),
			('xdg-icon-resource', 'install', '--context', 'apps', '--size', '64', icon, '--novendor'),
			('xdg-icon-resource', 'install', '--context', 'mimetypes',  '--size', '64', icon, 'application-x-zim-notebook'),
		):
			print 'Trying: ' + ' '.join(cmd)
			subprocess.call(cmd)


# Distutils parameters, and main function

dependencies = ['gobject', 'gtk', 'xdg']
if version_info == (2, 5):
	dependencies.append('simplejson')


setup(
	# wire overload commands
	cmdclass = {
		'sdist': zim_sdist_class,
		'build': zim_build_class,
		'build_trans': zim_build_trans_class,
		'build_scripts': zim_build_scripts_class,
		'install': zim_install_class,
	},

	# provide package properties
	name         = 'zim',
	version      = __version__,
	description  = 'Zim desktop wiki',
	author       = 'Jaap Karssenberg',
	author_email = 'pardus@cpan.org',
	license      = 'GPL',
	url          = __url__,
	scripts      = ['zim.py'],
	packages     = collect_packages(),
	data_files   = collect_data_files(),
	requires     = dependencies
)

