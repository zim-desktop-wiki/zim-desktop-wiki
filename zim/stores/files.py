
class DirTree(Store):

	import formats.wiki

	ftypes = ['txt']
	format = formats.wiki

	def get_page(self, pagename):
		i = len(self.namespace)
		relpath = pagename[i:].split(':')
		path = self.dir.resolve_file(relpath, self.ftypes)
		page = Page(pagename)
		page.source = path
		page.format = format
		return page
