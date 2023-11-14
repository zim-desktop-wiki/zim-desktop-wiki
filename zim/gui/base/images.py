# Copyright 2008-2023 Jaap Karssenberg <jaap.karssenberg@gmail.com>

'''This module contains helper functions to deal with images in the user interface'''

import logging

from gi.repository import GLib, GdkPixbuf

from zim.newfs import LocalFile

logger = logging.getLogger('zim.gui.base.images')


def supports_image_format(fmt):
	'''Check if an image format is supported by GDK.
	'''
	return fmt in (f.get_name() for f in GdkPixbuf.Pixbuf.get_formats())


def image_file_load_pixels(file: LocalFile, width_override=-1, height_override=-1) -> GdkPixbuf.Pixbuf:
	"""
	Replacement for GdkPixbuf.Pixbuf.new_from_file_at_size(file.path, w, h)
	Does it's best to rotate the image to the right orientation.
	When file does not exist or fails to load, this throws exceptions.
	"""

	if not file.exists():
		# if the file does not exist, no need to make the effort of trying to read it
		raise FileNotFoundError(file.path)

	need_switch_to_fallback = True
	try:
		pixbuf = GdkPixbuf.Pixbuf.new_from_file(file.path)
	except GLib.GError:
		logger.debug(f'GTK failed to read image, using Pillow fallback: {file.path}')
	else:
		need_switch_to_fallback = False

	if need_switch_to_fallback:
		try:
			# load Pillow only if necessary
			# noinspection PyUnresolvedReferences
			from PIL import Image, UnidentifiedImageError
		except ImportError:
			pass
		else:
			try:
				with Image.open(file.path) as image:
					pixbuf = _convert_pillow_image_to_pixbuf(image)
			except UnidentifiedImageError:
				logger.debug(f'Pillow failed to read image: {file.path}')
			else:
				need_switch_to_fallback = False

	if need_switch_to_fallback:
		error_message = f'No available fallback for load this image: {file.path}'
		logger.debug(error_message)
		raise TypeError(error_message)

	# Let's try to find and remember the orientation before scaling,
	# 	because we lose metadata when changing images.
	orientation = None
	mimetype = file.mimetype()
	if mimetype in {'image/jpeg', 'image/tiff'}:
		# Gtk can detect orientation in jpeg|tiff images only
		# See docs: https://docs.gtk.org/gdk-pixbuf/method.Pixbuf.get_option.html#description
		orientation = pixbuf.get_option('orientation')
	if mimetype in {'image/webp', 'image/png'}:
		# if possible, we will find orientation of the image using Pillow,
		# 	if it is not available, we will display image it as is.
		try:
			# noinspection PyUnresolvedReferences
			from PIL import Image, UnidentifiedImageError, __version__ as pillow_version_string
		except ImportError:
			pass
		else:
			pillow_version = tuple(map(int, pillow_version_string.split('.')))
			try:
				with Image.open(file.path) as image:
					if pillow_version >= (6, 0, 0):
						# https://pillow.readthedocs.io/en/stable/releasenotes/6.0.0.html#added-exif-class
						exif = image.getexif()
					else:
						# noinspection PyUnresolvedReferences,PyProtectedMember
						exif = image._getexif()  # noqa: WPS437
						if not exif:
							exif = {}  # noqa: WPS437
			except UnidentifiedImageError:
				logger.debug(f'Pillow failed to read image: {file.path}')
			else:
				orientation_tag_id = 274
				orientation = exif.get(orientation_tag_id)
	orientation = int(orientation) if orientation else 1

	w, h = pixbuf.get_width(), pixbuf.get_height()
	b_size_override = width_override > 0 or height_override > 0
	if b_size_override and (width_override <= 0 or height_override <= 0):
		if orientation in {5, 6, 7, 8}:
			w, h = h, w
			if height_override <= 0:
				height_override = int(h * width_override / w)
			else:
				width_override = int(w * height_override / h)
			width_override, height_override = height_override, width_override
		else:
			if height_override <= 0:
				height_override = int(h * width_override / w)
			else:
				width_override = int(w * height_override / h)

	if b_size_override:
		# do not use new_from_file_at_size() here due to bug in Gtk for GIF images, see issue #1563
		pixbuf = pixbuf.scale_simple(width_override, height_override, GdkPixbuf.InterpType.BILINEAR)

	pixbuf.set_option('orientation', f'{orientation}')
	#      ^^^ be sure to attach the tag for magic from stdlib in next line.
	return GdkPixbuf.Pixbuf.apply_embedded_orientation(pixbuf)


def image_file_get_dimensions(file_path):
	"""
	Replacement for GdkPixbuf.Pixbuf.get_file_info
	@return (width, height) in pixels
		or None if file does not exist or failed to load
	"""

	# Let GTK try reading the file
	_, width, height = GdkPixbuf.Pixbuf.get_file_info(file_path)
	if width > 0 and height > 0:
		return (width, height)

	# Fallback to Pillow
	try:
		from PIL import Image # load Pillow only if necessary
		with Image.open(file_path) as img_pil:
			return (img_pil.width, img_pil.height)
	except:
		raise AssertionError('Could not get size for: %s' % file_path)


def _convert_pillow_image_to_pixbuf(image) -> GdkPixbuf.Pixbuf:
	# check if there is an alpha channel
	if image.mode == 'RGB':
		has_alpha = False
	elif image.mode == 'RGBA':
		has_alpha = True
	else:
		raise ValueError('Pixel format {fmt} can not be converted to Pixbuf for image {image}'.format(
			fmt=image.mode, image=image,
		))

	# convert to GTK pixbuf
	data_gtk = GLib.Bytes.new_take(image.tobytes())

	return GdkPixbuf.Pixbuf.new_from_bytes(
		data=data_gtk,
		colorspace=GdkPixbuf.Colorspace.RGB,
		has_alpha=has_alpha,
		# GTK docs: "Currently only RGB images with 8 bits per sample are supported"
		# https://docs.gtk.org/gdk-pixbuf/ctor.Pixbuf.new_from_bytes.html#description
		bits_per_sample=8,
		width=image.width,
		height=image.height,
		rowstride=image.width * (4 if has_alpha else 3),
	)
