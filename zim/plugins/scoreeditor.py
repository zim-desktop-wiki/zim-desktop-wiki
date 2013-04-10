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

import gtk
import glob

from zim.fs import File, TmpFile
from zim.plugins import PluginClass
from zim.config import data_file
from zim.templates import GenericTemplate
from zim.applications import Application, ApplicationError
from zim.gui.imagegeneratordialog import ImageGeneratorClass, ImageGeneratorDialog
from zim.gui.widgets import populate_popup_add_separator

# TODO put these commands in preferences
lilypond_cmd = ('lilypond', '-ddelete-intermediate-files',
		# '-dsafe', # Can't include files in safe mode
		'-dbackend=eps', '--png', '--header=texidoc')
convertly_cmd = ('convert-ly', '--current-version', '--edit')
lilypondver_cmd = ('lilypond', '--version')

ui_xml = '''
<ui>
	<menubar name='menubar'>
		<menu action='insert_menu'>
			<placeholder name='plugin_items'>
				<menuitem action='insert_score'/>
			</placeholder>
		</menu>
	</menubar>
</ui>
'''

ui_actions = (
	# name, stock id, label, accelerator, tooltip, read only
	('insert_score', None, _('S_core...'), '', _('Insert score'), False),
		# T: menu item for insert score plugin
)

def _get_lilypond_version():
	try:
		lilypond = Application(lilypondver_cmd)
		output = lilypond.pipe()
		return output[0].split()[2]
	except ApplicationError:
		return '2.14.2'

class InsertScorePlugin(PluginClass):

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

	@classmethod
	def check_dependencies(klass):
		has_lilypond = Application(lilypond_cmd).tryexec()
		return has_lilypond, [('GNU Lilypond', has_lilypond, True)]

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		if self.ui.ui_type == 'gtk':
			self.ui.add_actions(ui_actions, self)
			self.ui.add_ui(ui_xml, self)
			self.register_image_generator_plugin('score')

	def insert_score(self):
		dialog = InsertScoreDialog.unique(self, self.ui, preferences=self.preferences)
		dialog.run()

	def edit_object(self, buffer, iter, image):
		dialog = InsertScoreDialog(self.ui, image=image, preferences=self.preferences)
		dialog.run()

	def do_populate_popup(self, menu, buffer, iter, image):
		populate_popup_add_separator(menu, prepend=True)

		item = gtk.MenuItem(_('_Edit Score')) # T: menu item in context menu
		item.connect('activate',
			lambda o: self.edit_object(buffer, iter, image))
		menu.prepend(item)



class InsertScoreDialog(ImageGeneratorDialog):

	def __init__(self, ui, preferences={}, image=None):
		generator = ScoreGenerator(preferences=preferences)
		ImageGeneratorDialog.__init__(self, ui, _('Insert Score'), # T: dialog title
			generator, image, help=':Plugins:Score Editor', syntax="lilypond" )


class ScoreGenerator(ImageGeneratorClass):

	type = 'score'
	scriptname = 'score.ly'
	imagename = 'score.png'
	cur_lilypond_version = None
	include_header = ''
	include_footer = ''

	def __init__(self, preferences={}):
		file = data_file('templates/plugins/scoreeditor.ly')
		assert file, 'BUG: could not find templates/plugins/scoreeditor.ly'
		self.template = GenericTemplate(file.readlines(), name=file)
		self.scorefile = TmpFile(self.scriptname)
		self.cur_lilypond_version = _get_lilypond_version()
		if preferences.has_key('include_header'):
			self.include_header = preferences['include_header']
		if preferences.has_key('include_footer'):
			self.include_footer = preferences['include_footer']

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
		if isinstance(text, basestring):
			text = text.splitlines(True)

		(version, text) = self.extract_version(text)
		text = ''.join(text)
		#~ print '>>>%s<<<' % text

		# Write to tmp file using the template for the header / footer
		scorefile = self.scorefile
		scorefile.writelines(
			self.template.process({'score': text,
				'version': version,
				'include_header': self.include_header,
				'include_footer': self.include_footer}) )
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
