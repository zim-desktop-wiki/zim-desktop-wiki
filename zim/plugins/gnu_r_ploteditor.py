# -*- coding: utf-8 -*-
#
# ploteditor.py
#
# This is a plugin for Zim, which allows inserting GNU R scripts to
# have Zim generate plots from them.
#
# Author: Lee Braiden <lee.b@irukado.org>
# Date: 2010-03-13
# Copyright (c) 2010, released under the GNU GPL v2 or higher
#
# Heavily based on equationeditor.py plugin as of:
# bzr revno 212, (2010-03-10), marked as
# Copyright 2009 Jaap Karssenberg <jaap.karssenberg@gmail.com>
#

import gtk
import glob

from zim.fs import File, TmpFile
from zim.plugins import PluginClass
from zim.config import data_file
from zim.templates import GenericTemplate
from zim.applications import Application
from zim.gui.imagegeneratordialog import ImageGeneratorClass, ImageGeneratorDialog
from zim.gui.widgets import populate_popup_add_separator

# TODO put these commands in preferences
gnu_r_cmd = ('R',)

ui_xml = '''
<ui>
	<menubar name='menubar'>
		<menu action='insert_menu'>
			<placeholder name='plugin_items'>
				<menuitem action='insert_gnu_r_plot'/>
			</placeholder>
		</menu>
	</menubar>
</ui>
'''

ui_actions = (
	# name, stock id, label, accelerator, tooltip, read only
	('insert_gnu_r_plot', None, _('GNU _R Plot...'), '', '', False),
		# T: menu item for insert plot plugin
)


class InsertGNURPlotPlugin(PluginClass):

	plugin_info = {
		'name': _('Insert GNU R Plot'), # T: plugin name
		'description': _('''\
This plugin provides a plot editor for zim based on GNU R.
'''), # T: plugin description
		'help': 'Plugins:GNU R Plot Editor',
		'author': 'Lee Braiden',
	}

	@classmethod
	def check_dependencies(klass):
		has_gnur = Application(gnu_r_cmd).tryexec()
		return has_gnur, [('GNU R', has_gnur, True)]

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		if self.ui.ui_type == 'gtk':
			self.ui.add_actions(ui_actions, self)
			self.ui.add_ui(ui_xml, self)
			self.register_image_generator_plugin('gnu_r_plot')

	def insert_gnu_r_plot(self):
		dialog = InsertGNURPlotDialog.unique(self, self.ui)
		dialog.run()

	def edit_object(self, buffer, iter, image):
		dialog = InsertGNURPlotDialog(self.ui, image=image)
		dialog.run()

	def do_populate_popup(self, menu, buffer, iter, image):
		populate_popup_add_separator(menu, prepend=True)

		item = gtk.MenuItem(_('_Edit GNU R Plot')) # T: menu item in context menu
		item.connect('activate',
			lambda o: self.edit_object(buffer, iter, image))
		menu.prepend(item)



class InsertGNURPlotDialog(ImageGeneratorDialog):

	def __init__(self, ui, image=None):
		generator = GNURPlotGenerator()
		ImageGeneratorDialog.__init__(self, ui, _('GNU R Plot'), # T: dialog title
			generator, image, help=':Plugins:GNU R Plot Editor' )


class GNURPlotGenerator(ImageGeneratorClass):

	uses_log_file = False

	type = 'gnu_r_plot'
	scriptname = 'gnu_r_plot.r'
	imagename = 'gnu_r_plot.png'

	def __init__(self):
		file = data_file('templates/plugins/gnu_r_editor.r')
		assert file, 'BUG: could not find templates/plugins/gnu_r_editor.r'
		self.template = GenericTemplate(file.readlines(), name=file)
		self.plotscriptfile = TmpFile(self.scriptname)

	def generate_image(self, text):
		if isinstance(text, basestring):
			text = text.splitlines(True)

		plotscriptfile = self.plotscriptfile
		pngfile = File(plotscriptfile.path[:-2] + '.png')

		plot_script = "".join(text)

		template_vars = {
			'gnu_r_plot_script': plot_script,
			'png_fname': pngfile.path.replace('\\', '/'),
				# Even on windows, GNU R expects unix path seperator
		}

		# Write to tmp file usign the template for the header / footer
		plotscriptfile.writelines(
			self.template.process(template_vars)
		)
		#print '>>>%s<<<' % plotscriptfile.read()

		# Call GNU R
		try:
			gnu_r = Application(gnu_r_cmd)
			#~ gnu_r.run(args=('-f', plotscriptfile.basename, ), cwd=plotscriptfile.dir)
			gnu_r.run(args=('-f', plotscriptfile.basename, '--vanilla'), cwd=plotscriptfile.dir)
		except:
			return None, None # Sorry, no log
		else:
			return pngfile, None

	def cleanup(self):
		path = self.plotscriptfile.path
		for path in glob.glob(path[:-2]+'.*'):
			File(path).remove()
