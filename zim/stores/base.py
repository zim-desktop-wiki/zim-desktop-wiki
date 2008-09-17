
class Store:

	def get_namespace(self, name=None):
		namespace = Namespace(name, self)
		for page in self.list_pages(name):
			namespace.append(page)
		return namespace

	def list_namespace(self, name=None):
		dir = self.resolve_dir(name)
		for items in dir:
			# some checks on file type etc.
			yield Page()

	def resolve_dir(self, name=None):
		if not name or len(name) == 0:
			return self.dir
		else:
			# TODO

	def get_page(self, name):
		pass
		
class Page():

	def __init__(self, name, store):
		#assert name is valid
		self.name = name
		self.store = store
		self.namespace = None


	def get_parse_tree(self):
		if self.format:
			return self.tree
		else:
			return self.format.Parser().parse_file(self.source)

	def set_parse_tree(self, tree):
		if self.format:
			if self.source:
				self.format.Dumper().dump_file(self.source, tree)
			else:
				self.content = self.format.Dumper().dump_string(tree)
		else:
			self.tree = tree

	def set_content(self, string)
		# TODO
		pass

	def path(self):
		'''Generator function for parent names
		can be used for:

			for namespace in page.path():
				if namespace.page('foo').exists:
					# ...
		'''
		path = self.name.split(':')
		path.pop(-1)
		while len(path) > 0:
			namespace = path.join(':')
			yield Namespace(namespace, self.store)

class Namespace():
'''List with pages, page object can in turn have a namespace attribute for further recursion'''

	def __init__(self, name, store):
		#assert name is valid
		self.store = store
		self.name = name

	def __iter__(self):
		# or can we call list_page and yield directly from there ?
		for item in self.store.list_namespace(self.name):
			yield item

	def page(self, name):
		#assert name
		return self.store.get_page(name)

