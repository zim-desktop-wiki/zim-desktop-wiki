#!/usr/bin/env python3

import os
import sys
import shutil
import subprocess

try:
	import py2exe
except ImportError:
	py2exe = None

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
	assert sys.version_info >= (3, 2)
except:
	print('zim needs python >= 3.2', file=sys.stderr)
	sys.exit(1)


# Some constants

PO_FOLDER = 'translations'
LOCALE_FOLDER = 'locale'


# Helper routines

def collect_packages():
	# Search for python packages below zim/
	packages = []
	for dir, dirs, files in os.walk('zim'):
		if '__init__.py' in files:
			package = '.'.join(dir.split(os.sep))
			packages.append(package)
	#~ print('Pakages: ', packages)
	return packages


def get_mopath(pofile):
	# Function to determine right locale path for a .po file
	lang = os.path.basename(pofile)[:-3] # len('.po') == 3
	modir = os.path.join(LOCALE_FOLDER, lang, 'LC_MESSAGES')
	mofile = os.path.join(modir, 'zim.mo')
	return modir, mofile


def include_file(file):
	# Check to exclude hidden and temp files
	if file.startswith('.'):
		return False
	else:
		for ext in ('~', '.bak', '.swp', '.pyc'):
			if file.endswith(ext):
				return False
	return True


def collect_data_files():
	# Search for data files to be installed in share/
	data_files = [
		('share/man/man1', ['man/zim.1']),
		('share/applications', ['xdg/zim.desktop']),
		('share/mime/packages', ['xdg/zim.xml']),
		('share/pixmaps', ['xdg/hicolor/48x48/apps/zim.png']),
		('share/metainfo', ['xdg/org.zim_wiki.Zim.appdata.xml']),
	]

	# xdg/hicolor -> PREFIX/share/icons/hicolor
	for dir, dirs, files in os.walk('xdg/hicolor'):
		if files:
			target = os.path.join('share', 'icons', dir[4:])
			files = [os.path.join(dir, f) for f in files]
			data_files.append((target, files))

	# mono icons -> PREFIX/share/icons/ubuntu-mono-light | -dark
	for theme in ('ubuntu-mono-light', 'ubuntu-mono-dark'):
		file = os.path.join('icons', theme, 'zim-panel.svg')
		target = os.path.join('share', 'icons', theme, 'apps', '22')
		data_files.append((target, [file]))

	# data -> PREFIX/share/zim
	for dir, dirs, files in os.walk('data'):
		if '.zim' in dirs:
			dirs.remove('.zim')
		target = os.path.join('share', 'zim', dir[5:])
		if files:
			files = list(filter(include_file, files))
			files = [os.path.join(dir, f) for f in files]
			data_files.append((target, files))

	# .po files -> PREFIX/share/locale/..
	for pofile in [f for f in os.listdir(PO_FOLDER) if f.endswith('.po')]:
		pofile = os.path.join(PO_FOLDER, pofile)
		modir, mofile = get_mopath(pofile)
		target = os.path.join('share', modir)
		data_files.append((target, [mofile]))

	#~ import pprint
	#~ print('Data files: ')
	#~ pprint.pprint(data_files)
	return data_files


def fix_dist():
	# Generate man page
	makeman.make()

	# Add the changelog to the manual
	# print('copying CHANGELOG.txt -> data/manual/Changelog.txt')
	# shutil.copy('CHANGELOG.txt', 'data/manual/Changelog.txt')

	# Copy the zim icons a couple of times
	# Paths for mimeicons taken from xdg-icon-resource
	# xdg-icon-resource installs:
	# /usr/local/share/icons/hicolor/.../mimetypes/gnome-mime-application-x-zim-notebook.png
	# /usr/local/share/icons/hicolor/.../mimetypes/application-x-zim-notebook.png
	# /usr/local/share/icons/hicolor/.../apps/zim.png

	if os.path.exists('xdg/hicolor'):
		shutil.rmtree('xdg/hicolor')
	os.makedirs('xdg/hicolor/scalable/apps')
	os.makedirs('xdg/hicolor/scalable/mimetypes')
	for name in (
		'apps/zim.svg',
		'mimetypes/gnome-mime-application-x-zim-notebook.svg',
		'mimetypes/application-x-zim-notebook.svg'
	):
		shutil.copy('icons/zim48.svg', 'xdg/hicolor/scalable/' + name)
	for size in ('16', '22', '24', '32', '48'):
		dir = size + 'x' + size
		os.makedirs('xdg/hicolor/%s/apps' % dir)
		os.makedirs('xdg/hicolor/%s/mimetypes' % dir)
		for name in (
			'apps/zim.png',
			'mimetypes/gnome-mime-application-x-zim-notebook.png',
			'mimetypes/application-x-zim-notebook.png'
		):
			shutil.copy('icons/zim%s.png' % size, 'xdg/hicolor/' + dir + '/' + name)


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
		for pofile in [f for f in os.listdir(PO_FOLDER) if f.endswith('.po')]:
			pofile = os.path.join(PO_FOLDER, pofile)
			modir, mofile = get_mopath(pofile)

			if not os.path.isdir(modir):
				os.makedirs(modir)

			if not os.path.isfile(mofile) or dep_util.newer(pofile, mofile):
				print('compiling %s' % mofile)
				msgfmt.MESSAGES.clear() # prevent "spill over" between translations - see github #664
				msgfmt.make(pofile, mofile)
			else:
				#~ print('skipping %s - up to date' % mofile)
				pass


class zim_build_scripts_class(build_scripts_class):
	# Adjust bin/zim.py -> bin/zim

	def run(self):
		build_scripts_class.run(self)
		if os.name == 'posix' and not self.dry_run:
			for script in self.scripts:
				if script.endswith('.py'):
					file = os.path.join(self.build_dir, script)
					print('renaming %s to %s' % (file, file[:-3]))
					os.rename(file, file[:-3]) # len('.py') == 3


class zim_build_class(build_class):
	# Generate _version.py etc. and call build_trans as a subcommand
	# And put list of default plugins in zim/plugins/__init__.py

	sub_commands = build_class.sub_commands + [('build_trans', None)]

	def run(self):
		fix_dist()
		build_class.run(self)

		## Set default plugins
		plugins = []
		for name in os.listdir('./zim/plugins'):
			if name.startswith('_') or name == 'base':
				continue
			elif '.' in name:
				if name.endswith('.py'):
					name, x = name.rsplit('.', 1)
					plugins.append(name)
				else:
					continue
			else:
				plugins.append(name)
		assert len(plugins) > 20, 'Did not find plugins'


		file = os.path.join(self.build_lib, 'zim', 'plugins', '__init__.py')
		print('Setting plugin list in %s' % file)
		assert os.path.isfile(file)
		fh = open(file)
		lines = fh.readlines()
		fh.read()

		for i, line in enumerate(lines):
			if line.startswith('\t\tplugins = set('):
				lines[i] = '\t\tplugins = set(%r) # DEFAULT PLUGINS COMPILED IN BY SETUP.PY\n' % sorted(plugins)
				break
		else:
			assert False, 'Missed line for plugin list'

		fh = open(file, 'w')
		fh.writelines(lines)
		fh.close()



class zim_install_class(install_class):

	def run(self):
		install_class.run(self)
		mimedir = os.path.join(self.install_data, 'share', 'mime')
		print(
			'To register zim with the desktop environment, please run\n'
			'the following two commands:\n'
			'* update-desktop-database\n'
			'* update-mime-database %s\n' % mimedir
		)


# Distutils parameters, and main function

scripts = ['zim.py']

if py2exe:
	py2exeoptions = {
		'windows': [{
			'script': 'zim.py',
			'icon_resources': [(1, 'icons/zim.ico')]
				# Windows 16x16, 32x32, and 48x48 icon based on PNG
		}],
		'zipfile': None,
		'options': {
			'py2exe': {
				'compressed': 1,
				'optimize': 2,
				'ascii': 1,
				'bundle_files': 3,
				'packages': ['encodings', 'cairo', 'atk', 'pangocairo', 'zim'],
				'dll_excludes': {
					'DNSAPI.DLL'
				},
				'excludes': ['Tkconstants', 'Tkinter', 'tcl']
			}
		}
	}
else:
	py2exeoptions = {}

if __name__ == '__main__':
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
		name = 'zim',
		version = __version__,
		description = 'Zim desktop wiki',
		author = 'Jaap Karssenberg',
		author_email = 'jaap.karssenberg@gmail.com',
		license = 'GPL v2+',
		url = __url__,
		scripts = scripts,
		packages = collect_packages(),
		data_files = collect_data_files(),
		requires = ['gi', 'xdg'],

		**py2exeoptions
	)
