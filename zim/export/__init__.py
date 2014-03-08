# -*- coding: utf-8 -*-

# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# TODO update docs - see google drive for draft

# TODO test with fake file / dir objects ! Speedy test of all combos

# TODO - when exporting with namespace / prefix we should also trim
#        links within a SingleFile output relative to that prefix
#        --> do not leak info on parent namespace names

# TODO - add property that gives N stages of exporting (X pages + X times copy attachments + copy resources)
#	e.g. define [(stage, n, label), (stage, n, label)]
#		yield (stage, data) where data is e.g. the page
#               set label above dialog, put data below


from zim.fs import Dir, File
from zim.templates import Template
from zim.formats import get_format


def build_notebook_exporter(dir, format, template, **opts):
	'''Returns an L{Exporter} that is suitable for exporting a whole
	notebook to a folder with one file per page
	'''
	from zim.export.layouts import MultiFileLayout
	from zim.export.exporters.files import MultiFileExporter

	template = Template(File(template)) # XXX
	ext = get_format(format).info['extension']
	layout = MultiFileLayout(dir, ext)
	return MultiFileExporter(layout, template, format, **opts)


def build_page_exporter(file, format, template, page, **opts):
	'''Returns an L{Exporter} that is suitable for exporting a page with
	subpages to a file and a folder (e.g. "page.html" with "page_files/")
	'''
	from zim.export.layouts import FileLayout
	from zim.export.exporters.files import MultiFileExporter

	template = Template(File(template)) # XXX
	ext = get_format(format).info['extension']
	layout = FileLayout(file, ext, namespace=page)
	return MultiFileExporter(layout, template, format, **opts)


def build_single_file_exporter(file, format, template, namespace=None, **opts):
	'''Returns an L{Exporter} that is suitable for exporting a set of
	pages to a single file
	'''
	from zim.export.layouts import SingleFileLayout
	from zim.export.exporters.files import SingleFileExporter

	template = Template(File(template)) # XXX
	ext = get_format(format).info['extension']
	layout = SingleFileLayout(file, ext, namespace=namespace)
	return SingleFileExporter(layout, template, format, **opts)


def build_mhtml_file_exporter(file, template):
	'''Returns an L{Exporter} that is suitable for exporting a set of
	pages to a single mhtml file
	'''
	from zim.export.exporters.mhtml import MHTMLExporter

	template = Template(File(template)) # XXX
	return MHTMLExporter(file, template)




