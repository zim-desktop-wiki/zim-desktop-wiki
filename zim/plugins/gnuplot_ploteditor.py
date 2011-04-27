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
from zim.applications import Application
from zim.gui.imagegeneratordialog import ImageGeneratorDialog

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
       'help': ':Plugins:Gnuplot Editor',
       'author': 'Alessandro Magni',
   }

   @classmethod
   def check_dependencies(klass):
       return [('Gnuplot', Application(gnuplot_cmd).tryexec())]

   def __init__(self, ui):
       PluginClass.__init__(self, ui)
       if self.ui.ui_type == 'gtk':
           self.ui.add_actions(ui_actions, self)
           self.ui.add_ui(ui_xml, self)
           self.register_image_generator_plugin('gnuplot')

   def insert_gnuplot(self):
       dialog = InsertPlotDialog.unique(self, self.ui)
       dialog.show_all()

   def edit_object(self, buffer, iter, image):
       dialog = InsertPlotDialog(self.ui, image=image)
       dialog.show_all()

   def do_populate_popup(self, menu, buffer, iter, image):
       menu.prepend(gtk.SeparatorMenuItem())

       item = gtk.MenuItem(_('_Edit Gnuplot')) # T: menu item in context menu
       item.connect('activate',
           lambda o: self.edit_object(buffer, iter, image))
       menu.prepend(item)



class InsertPlotDialog(ImageGeneratorDialog):

   def __init__(self, ui, image=None):
       generator = PlotGenerator()
       ImageGeneratorDialog.__init__(self, ui, _('Gnuplot'), # T: dialog title
           generator, image, help=':Plugins:Gnuplot Editor' )


class PlotGenerator(object):

   # TODO: generic base class for image generators

   type = 'gnuplot'
   basename = 'gnuplot.gnu'

   def __init__(self):
       file = data_file('templates/_gnuplot.gnu')
       assert file, 'BUG: could not find templates/_gnuplot.gnu'
       self.template = GenericTemplate(file.readlines(), name=file)
       self.plotscriptfile = TmpFile('gnuplot.gnu')

   def generate_image(self, text):
       if isinstance(text, basestring):
           text = text.splitlines(True)

       plotscriptfile = self.plotscriptfile

       pngfile = File(plotscriptfile.path[:-4] + '.png')
       logfile = File(plotscriptfile.path[:-4] + '.log') # len('.gnu') == 4

       plot_script = "".join(text)

       template_vars = {            # they go in /usr/share/zim/templates/_gnuplot.gnu
           'gnuplot_script':        plot_script,
           'png_fname':            pngfile,
       }

       # Write to tmp file usign the template for the header / footer
       plotscriptfile.writelines(
           self.template.process(template_vars)
       )
       #print '>>>%s<<<' % plotscriptfile.read()

       # Call Gnuplot
       try:
           gnu_gp = Application(gnuplot_cmd)
           gnu_gp.run(args=( plotscriptfile.basename, ), cwd=plotscriptfile.dir)
                           # you call it as % gnuplot output.plt

       except:
           # log should have details of failure
           return None, logfile

       return pngfile, logfile

   def cleanup(self):
       path = self.plotscriptfile.path
       for path in glob.glob(path[:-2]+'.*'):
           File(path).remove()
