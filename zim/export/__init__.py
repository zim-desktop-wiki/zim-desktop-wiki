# -*- coding: utf-8 -*-

# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains the framework for exporting data from zim.

The main API for exporting from the application is the L{Exporter}
object. There are subclasses of Exporter to export to multiple files,
to a single file or to a MHTML file.

To configure the exporter object an additional L{ExportLayout} object
is used. This layout defines the exact mapping of pages to files to
be used.

To specific the pages to export a subclass of the L{PageSelection} class
is used. There are selection classes to export the whole notebook or
to export a single page.

The L{ExportTemplateContext} object defines specific template parameters
for exporting. See also L{zim.templates} for template parsing and
processing classes.

See the module functions for convenient standard configurations.
'''


# TODO test with fake file / dir objects ! Speedy test of all combos

# TODO - when exporting with namespace / prefix we should also trim
#        links within a SingleFile output relative to that prefix
#        --> do not leak info on parent namespace names



from zim.fs import Dir, File
from zim.templates import get_template
from zim.formats import get_format


def build_notebook_exporter(dir, format, template, **opts):
	'''Returns an L{Exporter} that is suitable for exporting a whole
	notebook to a folder with one file per page
	'''
	from zim.export.layouts import MultiFileLayout
	from zim.export.exporters.files import MultiFileExporter

	template = get_template(format, template)
	ext = get_format(format).info['extension']
	layout = MultiFileLayout(dir, ext)
	return MultiFileExporter(layout, template, format, **opts)


def build_page_exporter(file, format, template, page, **opts):
	'''Returns an L{Exporter} that is suitable for exporting a page with
	subpages to a file and a folder (e.g. "page.html" with "page_files/")
	'''
	from zim.export.layouts import FileLayout
	from zim.export.exporters.files import MultiFileExporter

	template = get_template(format, template)
	ext = get_format(format).info['extension']
	layout = FileLayout(file, page, ext)
	return MultiFileExporter(layout, template, format, **opts)


def build_single_file_exporter(file, format, template, namespace=None, **opts):
	'''Returns an L{Exporter} that is suitable for exporting a set of
	pages to a single file
	'''
	from zim.export.layouts import SingleFileLayout
	from zim.export.exporters.files import SingleFileExporter

	template = get_template(format, template)
	ext = get_format(format).info['extension']
	layout = SingleFileLayout(file)
	return SingleFileExporter(layout, template, format, **opts)


def build_mhtml_file_exporter(file, template, **opts):
	'''Returns an L{Exporter} that is suitable for exporting a set of
	pages to a single mhtml file
	'''
	from zim.export.exporters.mhtml import MHTMLExporter

	template = get_template('html', template)
	return MHTMLExporter(file, template, **opts)




