
# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

import email.mime.multipart
import email.mime.text
import email.mime.nonmultipart

import base64

from zim.fs import adapt_from_oldfs
from zim.newfs import LocalFile, LocalFolder, File, Folder, get_tmpdir

from zim.notebook import encode_filename

from zim.export.exporters import Exporter
from zim.export.exporters.files import SingleFileExporter
from zim.export.layouts import SingleFileLayout
from zim.export.linker import ExportLinker


class MHTMLExporter(Exporter):
	'''Exporter that exports pages and attachments to a single MHTML
	file.
	'''

	# Output is Multipart-Mime message containing single HTML file
	# and all attachments and resources as mime parts
	# So first export as a single file, then wrap in mime

	# Keeps large data in memory - would need more low level
	# implementation with incremental writes to optimize it...

	# Also note that due to all the base64 encoding, size is going
	# to blow up even more ...

	def __init__(self, file, template, document_root_url=None):
		self.file = file
		self.template = template
		self.document_root_url = document_root_url

	def export_iter(self, pages):
		basename = encode_filename(pages.name)
		folder = get_tmpdir().folder('mhtml_export_tmp_dir')
		if folder.exists():
			folder.remove_children()
		else:
			folder.touch()
		file = folder.file(basename + '.html')
		layout = SingleFileLayout(file, pages.prefix)
		exporter = SingleFileExporter(layout, self.template, 'html', document_root_url=self.document_root_url)

		for p in exporter.export_iter(pages):
			yield p

		encoder = MHTMLEncoder()
		linker = ExportLinker(pages.notebook, layout, output=file, usebase=True)
		self.file.write(encoder(layout, linker))


class MHTMLEncoder(object):

	# Create message of file + attachments + resources

	# We use a linker for relative names to make absolutely sure
	# we give same relative paths as mentioned in links

	def __call__(self, layout, linker):
		msg = email.mime.multipart.MIMEMultipart('related')
			# MIME-Version 1.0
			# Content-Type: multipart/related; boundry=...
		msg.preamble = '' \
		'This document is a Single File Web Page, also known as a Web Archive file\n' \
		'or MHTML. If you are seeing this message, your browser or editor doesn\'t\n' \
		'support MHTML. Please look for a plugin or extension that adds MHTML support\n' \
		'or download a browser that supports it.'

		# Add html file
		msg.attach(self.encode_text_file(layout.file, None, 'text/html'))

		# Add attachments and resource
		for file in self._walk(layout.dir):
			file = adapt_from_oldfs(file)
			mt = file.mimetype()
			filename = linker.link(file.uri)
			if mt.startswith('text/'):
				part = self.encode_text_file(file, filename, mt)
			else:
				part = self.encode_data_file(file, filename, mt)
			msg.attach(part)

		# Write message to file
		return str(msg)

	def _walk(self, dir):
		if dir.exists():
			for child in dir:
				if isinstance(child, File):
					yield child
				elif child.exists():
					for child in self._walk(child): # recurs
						yield child

	def encode_text_file(self, file, filename, mimetype):
		type, subtype = mimetype.split('/', 1)
		assert type == 'text'

		# Not using MIMEText here, since it uses base64 and inflates
		# all ascii text unnecessary
		charset = email.charset.Charset('utf-8')
		charset.body_encoding = email.charset.QP
		msg = email.mime.nonmultipart.MIMENonMultipart('text', subtype, charset='utf-8')
		if filename: # top level does not have filename
			msg['Content-Location'] = filename
		msg.set_payload(file.read(), charset=charset)
		return msg

	def encode_data_file(self, file, filename, mimetype):
		file = adapt_from_oldfs(file)
		type, subtype = mimetype.split('/', 1)
		msg = email.mime.nonmultipart.MIMENonMultipart(type, subtype)
		msg['Content-Location'] = filename
		msg['Content-Type'] = mimetype
		msg.set_payload(file.read_binary())
		email.encoders.encode_base64(msg)
		return msg
