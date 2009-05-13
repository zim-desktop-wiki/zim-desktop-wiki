# -*- coding: utf8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

class Exporter(object):
	'''FIXME'''

	def export(self, selection, format, output, template=None,
				index_page=None,
				include_documents=False, document_folder_url=None):

		for page in selection:
			if template is None:
				lines = page.dump(format=format)
			else:
				lines = template.process(page)

		output.writelines(l.encode('utf8') for l in lines)
