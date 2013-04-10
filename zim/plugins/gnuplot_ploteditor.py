# -*- coding: utf-8 -*-
#
# gnuplot_ploteditor.py
#
# This is a plugin for Zim, which allows inserting Gnuplot scripts to
# have Zim generate plots from them.
#
# Author: Alessandro Magni <magni@inrim.it>
# Date: 2010-10-12
# Copyright (c) 2010, released under the GNU GPL v2 or higher
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
gnuplot_cmd = ('gnuplot',)

ui_xml = '''
<ui>
<menubar name='menubar'>
<menu action='insert_menu'>
<placeholder name='plugin_items'>
<menuitem action='insert_gnuplot'/>
</placeholder>
</menu>
</menubar>
</ui>
'''

ui_actions = (
	# name, stock id, label, accelerator, tooltip, read only
	('insert_gnuplot', None, _('Gnuplot...'), '', '', False),
		# T: menu item for insert plot plugin
)


class InsertGnuplotPlugin(PluginClass):

	plugin_info = {
		'name': _('Insert Gnuplot'), # T: plugin name
		'description': _('''\
This plugin provides a plot editor for zim based on Gnuplot.
'''), # T: plugin description
		'help': 'Plugins:Gnuplot Editor',
		'author': 'Alessandro Magni',
	}

	@classmethod
	def check_dependencies(klass):
		has_gnuplot = Application(gnuplot_cmd).tryexec()
		return has_gnuplot, [('Gnuplot', has_gnuplot, True)]

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		if self.ui.ui_type == 'gtk':
			self.ui.add_actions(ui_actions, self)
			self.ui.add_ui(ui_xml, self)
			self.register_image_generator_plugin('gnuplot')

	def insert_gnuplot(self):
		dialog = InsertGnuplotDialog.unique(self, self.ui)
		dialog.run()

	def edit_object(self, buffer, iter, image):
		dialog = InsertGnuplotDialog(self.ui, image=image)
		dialog.run()

	def do_populate_popup(self, menu, buffer, iter, image):
		populate_popup_add_separator(menu, prepend=True)

		item = gtk.MenuItem(_('_Edit Gnuplot')) # T: menu item in context menu
		item.connect('activate',
			lambda o: self.edit_object(buffer, iter, image))
		menu.prepend(item)


class InsertGnuplotDialog(ImageGeneratorDialog):

	def __init__(self, ui, image=None):
		attachment_folder = ui.notebook.get_attachments_dir(ui.page)
		generator = GnuplotGenerator(attachment_folder=attachment_folder)
		ImageGeneratorDialog.__init__(self, ui, _('Gnuplot'), # T: dialog title
			generator, image, help=':Plugins:Gnuplot Editor' )


class GnuplotGenerator(ImageGeneratorClass):

	uses_log_file = False

	type = 'gnuplot'
	scriptname = 'gnuplot.gnu'
	imagename = 'gnuplot.png'

	def __init__(self, attachment_folder=None):
		file = data_file('templates/plugins/gnuploteditor.gnu')
		assert file, 'BUG: could not find templates/plugins/gnuploteditor.gnu'
		self.template = GenericTemplate(file.readlines(), name=file)
		self.attachment_folder = attachment_folder
		self.plotscriptfile = TmpFile(self.scriptname)

	def generate_image(self, text):
		if isinstance(text, basestring):
			text = text.splitlines(True)

		plotscriptfile = self.plotscriptfile
		pngfile = File(plotscriptfile.path[:-4] + '.png')

		plot_script = "".join(text)

		template_vars = { # they go in the template
			'gnuplot_script': plot_script,
			'png_fname': pngfile.path,
		}
		if self.attachment_folder and self.attachment_folder.exists():
			template_vars['attachment_folder'] = self.attachment_folder.path

		# Write to tmp file using the template for the header / footer
		plotscriptfile.writelines(
			self.template.process(template_vars)
		)
		#print '>>>%s<<<' % plotscriptfile.read()

		# Call Gnuplot
		try:
			gnu_gp = Application(gnuplot_cmd)
			gnu_gp.run(args=( plotscriptfile.basename, ), cwd=plotscriptfile.dir)
							# you call it as % gnuplot output.plt

		except ApplicationError:
			return None, None # Sorry - no log
		else:
			return pngfile, None

	def cleanup(self):
		path = self.plotscriptfile.path
		for path in glob.glob(path[:-4]+'.*'):
			File(path).remove()
