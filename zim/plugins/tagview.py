# -*- coding: utf-8 -*-

import gtk

from zim.plugins import PluginClass
from zim.gui.pageindex import *
from zim.index import IndexTag


class TagTreeStore(PageTreeStore):
	
	def _get_iter(self, treepath):
		'''Convert the tree hierarchy to a PageTreeIter'''
		# Take care of caching and make sure we keep ref to paths long
		# enough while they are used in an iter. Also schedule a flush
		# to be execute as soon as the loop is idle again.
		# The cache is a dict which takes treepath tuples as keys and
		# has pagetreeiter objects as values, it is filled on demand.
		# No TreePath gtk object, treepaths are just tuples of ints
		# Path (0,) is the first item in the root namespace
		# Path (2, 4) is the 5th child of the 3rd item
		#~ print '>>> Lookup path', treepath
		if not treepath in self._cache:
			parent = None
			for i in range(1, len(treepath)+1):
				mytreepath = treepath[:i]
				if not mytreepath in self._cache:
					parenttreepath = treepath[:i-1]
					offset = mytreepath[-1]
					if parent is None:
						# The first tree level are tags
						#~ print '>>>> Load taglist'
						pages = self.index.list_tags_n(None, offset, limit=20)
					else:
						#~ print '>>>> Load pagelist for', parent, 'offset', offset
						if isinstance(parent, IndexTag):
							pages = self.index.list_tagged_n(parent, offset, limit=20)
						else:
							pages = self.index.list_pages_n(parent, offset, limit=20)
					for j, path in enumerate(pages):
						childtreepath = parenttreepath + (offset + j,)
						iter = PageTreeIter(childtreepath, path)
						self._cache.setdefault(childtreepath, iter)
				try:
					parent = self._cache[mytreepath].indexpath
				except KeyError:
					return None

		#~ print '>>> Return', self._cache.get(treepath, None)
		self._schedule_flush()
		return self._cache.get(treepath, None)
	
	def get_treepath(self, path):
		'''Convert a Zim path to tree hierarchy'''
		return None

	def on_iter_has_child(self, iter):
		'''Returns True if the iter has children'''
		if isinstance(iter.indexpath, IndexTag):
			return True
		else:
			return PageTreeStore.on_iter_has_child(self, iter)

	def on_iter_n_children(self, iter):
		'''Returns the number of children in a namespace. As a special case,
		when iter is None the number of tags is given.
		'''
		if iter is None:
			# Number of tags
			cursor = self.db.cursor()
			cursor.execute('select count(*) from tags')
			row = cursor.fetchone()
			return int(row[0])
		elif isinstance(iter.indexpath, IndexTag):
			# Number of tagged pages
			cursor = self.db.cursor()
			cursor.execute('select count(*) from tagsources where tag==?', (iter.id,))
			row = cursor.fetchone()
			return int(row[0])
		else:
			return PageTreeStore.on_iter_n_children(self, iter)

	def on_get_value(self, iter, column):
		'''Returns the data for a specific column'''
		if isinstance(iter.indexpath, IndexTag):
			tag = iter.indexpath
			if column == NAME_COL:
				return tag.name
			elif column == PATH_COL:
				return tag
			elif column == EMPTY_COL:
				return False
			elif column == STYLE_COL:
				return pango.STYLE_NORMAL
			elif column == FGCOLOR_COL:
				return self.NORMAL_COLOR
		else:
			return PageTreeStore.on_get_value(self, iter, column)


class TagTreeView(PageTreeView):
	
	def do_set_notebook(self, ui, notebook):
		self._cleanup = None # else it might be pointing to old model
		self.set_model(TagTreeStore(notebook.index))
		if not ui.page is None:
			self.on_open_page(ui.page)
		self.get_model().connect('row-inserted', self.on_row_inserted)

	def on_open_page(self, path):
		pass # Multiple selection
	
	def do_row_activated(self, treepath, column):
		'''Handler for the row-activated signal, emits page-activated if a 
		it is really a page'''
		model = self.get_model()
		iter = model.get_iter(treepath)
		if len(treepath) > 1:
			# Only pages (no tags) can be activated
			path = model.get_indexpath(iter)		
			self.emit('page-activated', path)

class TagviewPlugin(PluginClass):

	plugin_info = {
		'name': _('Tagview'), # T: plugin name
		'description': _('''\
This plugin loads the tag user interface.
'''), # T: plugin description
		'author': 'Fabian Moser',
		'help': 'Plugins:Tagview',
	}

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		self.sidepane_widget = None # For the embedded version

	def initialize_ui(self, ui):
		if self.ui.ui_type == 'gtk':
			self.connect_embedded_widget()

	def disconnect(self):
		self.disconnect_embedded_widget()
		PluginClass.disconnect(self)

	def connect_embedded_widget(self):
		if not self.sidepane_widget:
			sidepane = self.ui.mainwindow.sidepane
			self.sidepane_widget = TagviewPluginWidget(self)
			sidepane.add(self.sidepane_widget)
			self.sidepane_widget.show_all()

	def disconnect_embedded_widget(self):
		if self.sidepane_widget:
			sidepane = self.ui.mainwindow.sidepane
			sidepane.remove(self.sidepane_widget)
			self.sidepane_widget = None


class TagviewPluginWidget(gtk.ScrolledWindow):

	def __init__(self, plugin):
		gtk.ScrolledWindow.__init__(self)
		self.plugin = plugin

		self.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
		self.set_shadow_type(gtk.SHADOW_IN)
		
		self.treeview = TagTreeView(self.plugin.ui)
		self.add(self.treeview)
				