
# Copyright 2021 Jaap Karssenberg <jaap.karssenberg@gmail.com>


import logging

from functools import partial


from . import Path, HRef

from zim.newfs import LocalFile, SEP
from zim.formats import IMAGE, LINK, OBJECT, VisitorSkip
from zim.parsing import link_type


logger = logging.getLogger('zim.notebook.updater')


def update_parsetree_and_copy_images(parsetree, notebook, oldpath, newpath):
	'''Convenience method to update parsetree in place and copy any images
	for use in a new page
	'''
	set_parsetree_attributes_to_resolve_links(parsetree, notebook, oldpath)
	replace_parsetree_links_and_copy_images(parsetree, notebook, newpath)


def set_parsetree_attributes_to_resolve_links(parsetree, notebook, path):
	'''Changes parsetree in place so links can later be resolved against
	the source page
	'''
	parsetree._set_root_attrib('notebook', notebook.interwiki)
	parsetree._set_root_attrib('page', path.name)
	parsetree.replace(
		(LINK, IMAGE, OBJECT),
		partial(_resolve_links_and_images, notebook, path)
	)


def _resolve_links_and_images(notebook, src_path, node):
	if node.tag == LINK:
		href = node.get('href')
		my_type = link_type(href)
		if my_type == 'page':
			target = notebook.pages.resolve_link(src_path, HRef.new_from_wiki_link(href))
			node.set('_href', target.name)
		elif my_type == 'file':
			try:
				target = notebook.resolve_file(href, src_path)
			except:
				pass # may by e.g. file://host/path URI, not supported as local file
			else:
				node.set('_href', target.uri)
		return node
	elif node.tag == IMAGE:
		target = notebook.resolve_file(node.get('src'), src_path)
		node.set('_src', target.uri)
		return node
	elif node.tag == OBJECT:
		if node.get('type').startswith('image+'):
			# Objects based on generated images
			target = notebook.resolve_file(node.get('src'), src_path)
			node.set('_src', target.uri)
			return node
		else:
			raise VisitorSkip
	else:
		raise AssertionError('unknown tag')


def replace_parsetree_links_and_copy_images(parsetree, notebook, path):
	'''Changes parsetree in place to resolve links for the new location
	Also copies images to the new location

	TODO: in theory you want the move images in certain cases - e.g. on clipboard
	"cut" operation. However at the moment we cannot check links from other
	pages to the image file; so it is not wise to do so. Improve logic when
	this is possible and add a "cut/copy" switch to the method. On "cut" move
	if no other use of the image on the same (old) page and update links in
	other pages; else copy.
	'''
	src_notebook = parsetree._pop_root_attrib('notebook')
	src_page = parsetree._pop_root_attrib('page')
	if src_notebook and src_notebook != notebook.interwiki:
		# Update for cross notebook link
		parsetree.replace(
			(LINK, IMAGE, OBJECT),
			partial(_replace_links_to_interwiki_and_copy_images, src_notebook, notebook, path)
		)
	elif src_page and path and src_page != path.name:
		# Update to new page
		old_page = notebook.get_page(Path(src_page))
		old_folder = old_page.attachments_folder
		parsetree.replace(
			(LINK, IMAGE, OBJECT),
			partial(_replace_links_to_page_and_copy_images, notebook, old_folder, path)
		)
	else:
		# Leave links alone, remove "_href" attribs
		parsetree.replace(
			(LINK, IMAGE, OBJECT),
			_strip_link_and_image_attribs
		)


def _strip_link_and_image_attribs(node):
	if node.tag == LINK:
		node.attrib.pop('_href', None)
		return node
	elif node.tag == IMAGE \
		or (node.tag == OBJECT and node.get('type').startswith('image+')):
			node.attrib.pop('_src', None)
			return node
	else:
		raise VisitorSkip


def _replace_links_to_interwiki_and_copy_images(src_interwiki, notebook, new_path, node):
	if node.tag == LINK:
		abs_href = node.attrib.pop('_href', None)
		if abs_href:
			my_type = link_type(abs_href)
			if my_type == 'page':
				oldhref = HRef.new_from_wiki_link(node.get('href')) # *not* abs_href
				new_href = src_interwiki + '?' + abs_href
				new_href += '#' + oldhref.anchor if oldhref.anchor else ''
			elif my_type == 'file':
				# NOTE: no proper syntax for this type of link - just abs file link
				#       should be improved - e.g. path:./file style links like in docuwiki
				new_href = abs_href
			else:
				logger.warn('Could not update link of type "%s": %s', my_type, abs_href)
				raise VisitorSkip

			if node.gettext() == node.get('href'): # *not* abs_href
				node[:] = [new_href]
			node.set('href', new_href)
			return node
		else:
			raise VisitorSkip
	elif node.tag == IMAGE:
		# Just copy all images - image links to other notebook don't make sense
		abs_src = node.attrib.pop('_src', None)
		if abs_src:
			src_file = LocalFile(abs_src)
			return _copy_image(notebook, new_path, src_file, node)
		else:
			raise VisitorSkip
	elif node.tag == OBJECT:
		abs_src = node.attrib.pop('_src', None)
		if abs_src and node.get('type').startswith('image+'):
			src_file = LocalFile(abs_src)
			return _copy_image_object(notebook, new_path, src_file, node)
		else:
			raise VisitorSkip
	else:
		raise AssertionError('unknown tag')


def _replace_links_to_page_and_copy_images(notebook, old_folder, new_path, node):
	if node.tag == LINK:
		abs_href = node.attrib.pop('_href', None)
		if abs_href:
			my_type = link_type(abs_href)
			if my_type == 'page':
				target = Path(abs_href)
				oldhref = HRef.new_from_wiki_link(node.get('href')) # *not* abs_href
				return notebook._update_link_tag(node, new_path, target, oldhref)
			elif my_type == 'file':
				new_href = notebook.relative_filepath(LocalFile(abs_href), new_path)
				if node.gettext() == node.get('href'): # *not* abs_href
					node[:] = [new_href]
				node.set('href', new_href)
				return node
			else:
				logger.warn('Could not update link of type "%s": %s', my_type, abs_href)
				raise VisitorSkip
		else:
			raise VisitorSkip
	elif node.tag == IMAGE:
		# Only copy direct attachments - else the image already was a link
		# to a file outside of the attachment folder
		abs_src = node.attrib.pop('_src', None)
		if abs_src:
			src_file = LocalFile(abs_src)
			if src_file.ischild(old_folder):
				return _copy_image(notebook, new_path, src_file, node)
			else:
				return _update_image(notebook, new_path, src_file, node)
		else:
			raise VisitorSkip
	elif node.tag == OBJECT:
		abs_src = node.attrib.pop('_src', None)
		if abs_src and node.get('type').startswith('image+'):
			src_file = LocalFile(abs_src)
			if src_file.ischild(old_folder):
				return _copy_image_object(notebook, new_path, src_file, node)
			else:
				return _update_image(notebook, new_path, src_file, node)
		else:
			raise VisitorSkip
	else:
		raise AssertionError('unknown tag')


def _update_image(notebook, new_path, src_file, node):
	new_src = notebook.relative_filepath(src_file, new_path)
	node.set('src', new_src)
	return node


def _copy_image(notebook, new_path, src_file, node):
	folder = notebook.get_page(new_path).attachments_folder
	new_file = folder.new_file(src_file.basename)
	src_file.copyto(new_file)
	node.set('src', '.' + SEP + new_file.basename)
	return node


def _copy_image_object(notebook, new_path, src_file, node):
	from zim.plugins.base.imagegenerator import copy_imagegenerator_src_files

	folder = notebook.get_page(new_path).attachments_folder
	new_file = copy_imagegenerator_src_files(src_file, folder)
	node.set('src', '.' + SEP + new_file.basename)
	return node
