# -*- coding: utf-8 -*-
#
# scoreeditor.py
#
# This is a plugin for Zim, which allows to insert music score in zim using
# GNU Lilypond.
#
#
# Author: Shoban Preeth <shoban.preeth@gmail.com>
# Date: 2012-07-05
# Copyright (c) 2012, released under the GNU GPL v2 or higher
#
#

import glob

from zim.plugins.base.imagegenerator import ImageGeneratorPlugin, ImageGeneratorClass
from zim.fs import File, TmpFile
from zim.config import data_file
from zim.templates import get_template
from zim.applications import Application, ApplicationError


# TODO put these commands in preferences
lilypond_cmd = ('lilypond', '-ddelete-intermediate-files',
		# '-dsafe', # Can't include files in safe mode
		'-dbackend=eps', '--png', '--header=texidoc')
convertly_cmd = ('convert-ly', '--current-version', '--edit')
lilypondver_cmd = ('lilypond', '--version')


def _get_lilypond_version():
	try:
		lilypond = Application(lilypondver_cmd)
		output = lilypond.pipe()
		return output[0].split()[2]
	except ApplicationError:
		return '2.14.2'

class InsertScorePlugin(ImageGeneratorPlugin):

	plugin_info = {
		'name': _('Insert Score'), # T: plugin name
		'description': _('''\
This plugin provides an score editor for zim based on GNU Lilypond.

This is a core plugin shipping with zim.
'''), # T: plugin description
		'help': 'Plugins:Score Editor',
		'author': 'Shoban Preeth',
	}

	plugin_preferences = [
		# key, type, label, default
		('include_header', 'string', _('Common include header'), '\include "predefined-guitar-fretboards.ly"'), # T: plugin preference
		('include_footer', 'string', _('Common include footer'), ''), # T: plugin preference
	]

	object_type = 'score'
	short_label = _('S_core') # T: menu item
	insert_label = _('Insert Score') # T: menu item
	edit_label = _('_Edit Score') # T: menu item
	syntax = None

	@classmethod
	def check_dependencies(klass):
		has_lilypond = Application(lilypond_cmd).tryexec()
		return has_lilypond, [('GNU Lilypond', has_lilypond, True)]


class ScoreGenerator(ImageGeneratorClass):

	object_type = 'score'
	scriptname = 'score.ly'
	imagename = 'score.png'
	cur_lilypond_version = None

	def __init__(self, plugin):
		ImageGeneratorClass.__init__(self, plugin)
		self.template = get_template('plugins', 'scoreeditor.ly')
		self.scorefile = TmpFile(self.scriptname)
		self.cur_lilypond_version = _get_lilypond_version()
		self.include_header = plugin.preferences['include_header']
		self.include_footer = plugin.preferences['include_footer']

	def process_input(self, text):
		'''Prepend version string to user input. It is also stored in
		the script file.
		'''
		version_present = False
		for l in text.splitlines(True):
			if l.strip().startswith('\\version'):
				version_present = True
		if not version_present:
			text = '\\version "{0}"\n\n'.format(self.cur_lilypond_version) + text
		return text

	def extract_version(self, text):
		outtext = []
		version = None
		for l in text:
			if l.strip().startswith('\\version'):
				version = l.strip()
			else:
				outtext.append(l)
		return (version, outtext)

	def generate_image(self, text):

		(version, text) = self.extract_version(text)
		text = ''.join(text)
		#~ print '>>>%s<<<' % text

		# Write to tmp file using the template for the header / footer
		scorefile = self.scorefile
		lines = []
		self.template.process(lines, {
			'score': text,
			'version': version or '',
			'include_header': self.include_header or '',
			'include_footer': self.include_footer or '',
		} )
		scorefile.writelines(lines)
		#~ print '>>>%s<<<' % scorefile.read()

		# Call convert-ly to convert document of current version of
		# Lilypond.
		clogfile = File(scorefile.path[:-3] + '-convertly.log') # len('.ly) == 3
		try:
			convertly = Application(convertly_cmd)
			convertly.run((scorefile.basename,), cwd=scorefile.dir)
		except ApplicationError:
			clogfile.write('convert-ly failed.\n')
			return None, clogfile


		# Call lilypond to generate image.
		logfile = File(scorefile.path[:-3] + '.log') # len('.ly') == 3
		try:
			lilypond = Application(lilypond_cmd)
			lilypond.run(('-dlog-file=' + logfile.basename[:-4], scorefile.basename,), cwd=scorefile.dir)
		except ApplicationError:
			# log should have details of failure
			return None, logfile
		pngfile = File(scorefile.path[:-3] + '.png') # len('.ly') == 3

		return pngfile, logfile

	def cleanup(self):
		path = self.scorefile.path
		for path in glob.glob(path[:-3]+'*'):
			File(path).remove()
