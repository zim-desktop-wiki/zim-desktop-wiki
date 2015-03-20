# -*- coding: utf-8 -*-

# Copyright 2008-2015 Jaap Karssenberg <jaap.karssenberg@gmail.com>


from zim.errors import Error


class IndexBusyError(Error):
	'''Error for operations that need the index when the index is not
	yet updated.'''

	description = _('''\
Index is still busy updating while we try to do an
operation that needs the index.
''') # T: error message


class PageMover(object):

	def __init__(self, notebook):
		pass


	def move_page(self, path, newpath, update_links=True, callback=None):
		'''Move a page in the notebook

		@param path: a L{Path} object for the old/current page name
		@param newpath: a L{Path} object for the new page name
		@param update_links: if C{True} all links B{from} and B{to} this
		page and any of it's children will be updated to reflect the
		new page name

		The original page C{path} does not have to exist, in this case
		only the link update will done. This is useful to update links
		for a placeholder.

		@param callback: a callback function which is called for each
		page that is updates when updating links. It is called as::

			callback(page, total=None)

		Where:
		  - C{page} is the L{Page} object for the page being updated
		  - C{total} is an optional parameter for the number of pages
		    still to go - if known

		@raises PageExistsError: if C{newpath} already exists

		@emits: move-page before the move
		@emits: moved-page after succesful move
		'''
		if path == newpath:
			return

		# TODO
		#~ if update_links and self.index.updating:
			#~ raise IndexBusyError, 'Index busy'
			# Index need to be complete in order to be 100% sure we
			# know all backlinks, so no way we can update links before.

		page = self.get_page(path)
		assert not page.modified, 'BUG: moving a page with uncomitted changes'

		newpage = self.get_page(newpath)
		if newpage.exists() and not newpage.isequal(page):
			# Check isequal to allow case sensitive rename on
			# case insensitive file system
			raise PageExistsError, 'Page already exists: %s' % newpath.name

		self.emit('move-page', path, newpath, update_links)
		logger.debug('Move %s to %s (%s)', path, newpath, update_links)

		# Collect backlinks
		if update_links:
			from zim.index import LINK_DIR_BACKWARD
			backlinkpages = set()
			for l in self.links.list_links(path, LINK_DIR_BACKWARD):
				backlinkpages.add(l.source)

			if page.haschildren:
				for child in self.pages.walk(path):
					for l in self.links.list_links(child, LINK_DIR_BACKWARD):
						backlinkpages.add(l.source)

		# Do the actual move (if the page exists)
		if page.exists():
			store = self.get_store(path)
			newstore = self.get_store(newpath)
			if newstore == store:
				store.move_page(path, newpath)
			else:
				assert False, 'TODO: move between stores'
				# recursive + move attachments as well

		self.flush_page_cache(path)
		self.flush_page_cache(newpath)

		# Update links in moved pages
		page = self.get_page(newpath)
		if page.hascontent:
			if callback: callback(page)
			self._update_links_from(page, path, page, path)
			store = self.get_store(page)
			store.store_page(page)
			# do not use self.store_page because it emits signals
		for child in self._no_index_walk(newpath):
			if not child.hascontent:
				continue
			if callback: callback(child)
			oldpath = path + child.relname(newpath)
			self._update_links_from(child, oldpath, newpath, path)
			store = self.get_store(child)
			store.store_page(child)
			# do not use self.store_page because it emits signals

		# Update links to the moved page tree
		if update_links:
			# Need this indexed before we can resolve links to it
			self.index.delete(path)
			self.index.update(newpath)
			#~ print backlinkpages
			total = len(backlinkpages)
			for p in backlinkpages:
				if p == path or p.ischild(path):
					continue
				page = self.get_page(p)
				if callback: callback(page, total=total)
				self._update_links_in_page(page, path, newpath)
				self.store_page(page)

		self.emit('moved-page', path, newpath, update_links)

	def _no_index_walk(self, path):
		'''Walking that can be used when the index is not in sync'''
		# TODO allow this to cross several stores
		store = self.get_store(path)
		for page in store.get_pagelist(path):
			yield page
			for child in self._no_index_walk(page): # recurs
				yield child

	@staticmethod
	def _update_link_tag(elt, newhref):
		newhref = str(newhref)
		if elt.gettext() == elt.get('href'):
			elt[:] = [newhref]
		elt.set('href', newhref)
		return elt

	def _update_links_from(self, page, oldpath, parent, oldparent):
		logger.debug('Updating links in %s (was %s)', page, oldpath)
		tree = page.get_parsetree()
		if not tree:
			return

		def replacefunc(elt):
			href = elt.attrib['href']
			type = link_type(href)
			if type != 'page':
				raise zim.formats.VisitorSkip

			hrefpath = self.pages.lookup_from_user_input(href, page)
			oldhrefpath = self.pages.lookup_from_user_input(href, oldpath)
			#~ print 'LINK', oldhrefpath, '->', hrefpath
			if hrefpath != oldhrefpath:
				if (hrefpath == page or hrefpath.ischild(page)) \
				and (oldhrefpath == oldpath or oldhrefpath.ischild(oldpath)):
					#~ print '\t.. Ignore'
					raise zim.formats.VisitorSkip
				else:
					newhref = self.relative_link(page, oldhrefpath)
					#~ print '\t->', newhref
					return self._update_link_tag(elt, newhref)
			elif (hrefpath == oldparent or hrefpath.ischild(oldparent)):
				# Special case where we e.g. link to our own children using
				# a common parent between old and new path as an anchor for resolving
				newhrefpath = parent
				if hrefpath.ischild(oldparent):
					newhrefpath = parent + hrefpath.relname(oldparent)
				newhref = self.relative_link(page, newhrefpath)
				#~ print '\t->', newhref
				return self._update_link_tag(elt, newhref)
			else:
				raise zim.formats.VisitorSkip

		tree.replace(zim.formats.LINK, replacefunc)
		page.set_parsetree(tree)

	def _update_links_in_page(self, page, oldpath, newpath):
		# Maybe counter intuitive, but pages below oldpath do not need
		# to exist anymore while we still try to resolve links to these
		# pages. The reason is that all pages that could link _upward_
		# to these pages are below and are moved as well.
		logger.debug('Updating links in %s to %s (was: %s)', page, newpath, oldpath)
		tree = page.get_parsetree()
		if not tree:
			logger.warn('Page turned out to be empty: %s', page)
			return

		def replacefunc(elt):
			href = elt.attrib['href']
			type = link_type(href)
			if type != 'page':
				raise zim.formats.VisitorSkip

			hrefpath = self.pages.lookup_from_user_input(href, page)
			#~ print 'LINK', hrefpath
			if hrefpath == oldpath:
				newhrefpath = newpath
				#~ print '\t==', oldpath, '->', newhrefpath
			elif hrefpath.ischild(oldpath):
				rel = hrefpath.relname(oldpath)
				newhrefpath = newpath + rel
				#~ print '\t>', oldpath, '->', newhrefpath
			else:
				raise zim.formats.VisitorSkip

			newhref = self.relative_link(page, newhrefpath)
			return self._update_link_tag(elt, newhref)

		tree.replace(zim.formats.LINK, replacefunc)
		page.set_parsetree(tree)

	def rename_page(self, path, newbasename, update_heading=True, update_links=True, callback=None):
		'''Rename page to a page in the same namespace but with a new
		basename.

		This is similar to moving within the same namespace, but
		conceptually different in the user interface. Internally
		L{move_page()} is used here as well.

		@param path: a L{Path} object for the old/current page name
		@param newbasename: new name as string
		@param update_heading: if C{True} the first heading in the
		page will be updated to the new name
		@param update_links: if C{True} all links B{from} and B{to} this
		page and any of it's children will be updated to reflect the
		new page name
		@param callback: see L{move_page()} for details
		'''
		logger.debug('Rename %s to "%s" (%s, %s)',
			path, newbasename, update_heading, update_links)

		newbasename = Path.makeValidPageName(newbasename)
		newpath = Path(path.namespace + ':' + newbasename)
		if newbasename.lower() != path.basename.lower():
			# allow explicit case-sensitive renaming
			newpath = self.index.resolve_case(
				newbasename, namespace=path.parent) or newpath

		self.move_page(path, newpath, update_links, callback)
		if update_heading:
			page = self.get_page(newpath)
			tree = page.get_parsetree()
			if not tree is None:
				tree.set_heading(newbasename)
				page.set_parsetree(tree)
				self.store_page(page)

		return newpath


class PageDeleter(object):

	def __init__(self, notebook):
		pass

	def delete_page(self, path, update_links=True, callback=None):
		'''Delete a page from the notebook

		@param path: a L{Path} object
		@param update_links: if C{True} pages linking to the
		deleted page will be updated and the link are removed.
		@param callback: see L{move_page()} for details

		@returns: C{True} when the page existed and was deleted,
		C{False} when the page did not exist in the first place.

		Raises an error when delete failed.

		@emits: delete-page before the actual delete
		@emits: deleted-page after succesful deletion
		'''
		return self._delete_page(path, update_links, callback)


class PageTrasher(object):

	def __init__(self, notebook):
		pass


	def trash_page(self, path, update_links=True, callback=None):
		'''Move a page to Trash

		Like L{delete_page()} but will use the system Trash (which may
		depend on the OS we are running on). This is used in the
		interface as a more user friendly version of delete as it is
		undoable.

		@param path: a L{Path} object
		@param update_links: if C{True} pages linking to the
		deleted page will be updated and the link are removed.
		@param callback: see L{move_page()} for details

		@returns: C{True} when the page existed and was deleted,
		C{False} when the page did not exist in the first place.

		Raises an error when trashing failed.

		@raises TrashNotSupportedError: if trashing is not supported by
		the storage backend or when trashing is explicitly disabled
		for this notebook.

		@emits: delete-page before the actual delete
		@emits: deleted-page after succesful deletion
		'''
		if self.config['Notebook']['disable_trash']:
			raise TrashNotSupportedError, 'disable_trash is set'
		return self._delete_page(path, update_links, callback, trash=True)

	def _delete_page(self, path, update_links=True, callback=None, trash=False):
		# Collect backlinks
		from zim.index import LINK_DIR_BACKWARD, IndexNotFoundError # FIXME
		if update_links:
			try:
				indexpath = self.pages.lookup_by_pagename(path)
			except IndexNotFoundError:
				update_links = False
			else:
				backlinkpages = set()
				for l in self.links.list_links(path, LINK_DIR_BACKWARD):
					backlinkpages.add(l.source)

				page = self.get_page(path)
				if page.haschildren:
					for child in self.index.walk(path):
						for l in self.index.list_links(child, LINK_DIR_BACKWARD):
							backlinkpages.add(l.source)

		# actual delete
		self.emit('delete-page', path)

		store = self.get_store(path)
		if trash:
			existed = store.trash_page(path)
		else:
			existed = store.delete_page(path)

		self.flush_page_cache(path)
		path = Path(path.name)

		# Update links to the deleted page tree
		if update_links:
			#~ print backlinkpages
			total = len(backlinkpages)
			for p in backlinkpages:
				if p == path or p.ischild(path):
					continue
				page = self.get_page(p)
				if callback: callback(page, total=total)
				self._remove_links_in_page(page, path)
				self.store_page(page)

		# let everybody know what happened
		self.emit('deleted-page', path)

		return existed

	def _remove_links_in_page(self, page, path):
		logger.debug('Removing links in %s to %s', page, path)
		tree = page.get_parsetree()
		if not tree:
			return

		def replacefunc(elt):
			href = elt.attrib['href']
			type = link_type(href)
			if type != 'page':
				raise zim.formats.VisitorSkip

			hrefpath = self.pages.lookup_from_user_input(href, page)
			#~ print 'LINK', hrefpath
			if hrefpath == path \
			or hrefpath.ischild(path):
				# Replace the link by it's text
				return zim.formats.DocumentFragment(*elt)
			else:
				raise zim.formats.VisitorSkip

		tree.replace(zim.formats.LINK, replacefunc)
		page.set_parsetree(tree)


class NotebookUpgrader(object):

	def __init__(self, notebook):
		pass


	def upgrade_notebook(self, callback=None):
		'''Tries to update older notebook to format supported by the
		latest version

		@todo: document exact actions of this method

		@param callback: callback function that is called for each
		page that is updated, if it returns C{False} the upgrade
		is cancelled
		'''
		# Currently we just assume upgrade from zim < 0.43
		# may need to add more sophisticated logic later..
		#
		# We check for links based on old pagename cleanup rules
		# also we write every page, just to be sure they are stored in
		# the latest wiki format.
		logger.info('Notebook update started')
		self.index.ensure_update(callback=callback)

		candidate_re = re.compile('[\W_]')
		for page in self.walk():
			if callback:
				cont = callback(page)
				if not cont:
					logger.info('Notebook update cancelled')
					return

			try:
				tree = page.get_parsetree()
			except:
				# Some issue we can't fix
				logger.exception('Error while parsing page: "%s"', page.name)
				tree = None

			if tree is None:
				continue

			changed = False
			for tag in tree.getiterator('link'):
				href = tag.attrib['href']
				type = link_type(href)
				if type == 'page' and candidate_re.search(href):
					# Skip if we can resolve it already
					try:
						link = self.pages.resolve_link(page, HRef.new_from_wiki_link(href))
						link = self.get_page(link)
					except:
						pass
					else:
						if link and link.hascontent:
							# Do not check haschildren here, children could be placeholders as well
							continue

					# Otherwise check if old version would have found a match
					try:
						newhref = self.cleanup_pathname_zim028(href)
						if newhref != href:
							link = self.pages.resolve_link(page, HRef.new_from_wiki_link(newhref))
							link = self.get_page(link)
						else:
							link = None
					except:
						pass
					else:
						if link and link.hascontent:
							# Do not check haschildren here, children could be placeholders as well
							tag.attrib['href'] = newhref
							changed = True
							logger.info('Changed link "%s" to "%s"', href, newhref)

			# Store this page
			try:
				if changed:
					page.set_parsetree(tree)

				self.store_page(page)
			except:
				logger.exception('Could not store page: "%s"', page.name)

		# Update the version and we are done
		self.config['Notebook']['version'] = '.'.join(map(str, DATA_FORMAT_VERSION))
		self.config.write()
		logger.info('Notebook update done')

	@staticmethod
	def cleanup_pathname_zim028(name):
		'''Backward compatible version of L{Path.makeValidPageName()}

		This method also cleansup page names, but applies logic as it
		was in zim 0.28. It restricted all special characters but
		white lists ".", "-", "_", "(", ")", ":" and "%". It replaces
		illegal characters by "_" instead of throwing an exception.

		Needed only when upgrading links in older notebooks.
		'''
		# OLD CODE WAS:
		# $name =~ s/^:*/:/ unless $rel;	# absolute name
		# $name =~ s/:+$//;					# not a namespace
		# $name =~ s/::+/:/g;				# replace multiple ":"
		# $name =~ s/[^:\w\.\-\(\)\%]/_/g;	# replace forbidden chars
		# $name =~ s/(:+)[\_\.\-\(\)]+/$1/g;	# remove non-letter at begin
		# $name =~ s/_+(:|$)/$1/g;			# remove trailing underscore

		forbidden_re = re.compile(r'[^\w\.\-\(\)]', re.UNICODE)
		non_letter_re = re.compile(r'^\W+', re.UNICODE)

		prefix = ''
		if name[0] in (':', '.', '+'):
			prefix = name[0]
			name = name[1:]

		path = []
		for n in filter(len, name.split(':')):
			n = forbidden_re.sub('_', n) # replace forbidden chars
			n = non_letter_re.sub('', n) # remove non-letter at begin
			n = n.rstrip('_') # remove trailing underscore
			if len(n):
				path.append(n)

		return prefix + ':'.join(path)
