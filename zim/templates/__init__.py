# -*- coding: utf-8 -*-

# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# Supported sytax
#   [% .. %] and <!--[% .. %]-->
#
# Instructions:
#   GET
#   SET
#   IF expr EL(S)IF expr .. ELSE .. END
#   FOR var IN expr .. END
#   FOREACH var = expr ... END
#   FOREACH var IN expr ... END
#   BLOCK name .. END
#   INCLUDE name or expr -- block or file
#
# Expressions can be:
#	True, False, None
#   "string", 'string', 5, 5.0
#   [.., .., ..]
#	parameter.name, mylist.0
#	function(.., ..)
#	.. operator ..
#
# Operators can be:
#	==, !=, >, >=, <, <=
#
# Note that BLOCKS are always defined in the top level scope
# so you not have them e.g. in an IF clause to define alternative versions.
# BLOCKS may be defined after the location where they are used.
#
# Within a loop, special parameter "loop" is defined with following
# attributes:
# 	loop.first		True / False
# 	loop.last		True / False
# 	loop.parity		"even" or "odd"
# 	loop.even		True / False
# 	loop.odd		True / False
#	loop.size		n
#	loop.max		n-1
#	loop.index		0 .. n-1
# 	loop.count		1 .. n
# 	loop.outer		outer "loop" or None
#	loop.prev		previous item or None
#	loop.next		next item or None



import logging

logger = logging.getLogger('zim.templates')

from zim.fs import File, Dir, PathLookupError
from zim.config import data_dirs
from zim.parsing import is_path_re
from zim.signals import SignalEmitter


from zim.templates.parser import TemplateParser
from zim.templates.processor import TemplateProcessor, TemplateContextDict
from zim.templates.functions import build_template_functions



def list_template_categories():
	'''Returns a list of categories (sub folders)'''
	dirs = data_dirs('templates')
	categories = set()
	for dir in dirs:
		for name in dir.list():
			## TODO list_objects would help here + a filter like type=Dir
			if dir.subdir(name).isdir():
				categories.add(name)

	return sorted(categories)


def list_templates(category):
	'''Returns a list of template names
	@param category: a category (sub folder) with tempaltes, e.g. "html"
	@returns: a list of 2-tuples of the template names and the file
	basename for the template file
	'''
	category = category.lower()
	templates = set()
	path = list(data_dirs(('templates', category)))
	path.reverse()
	for dir in path:
		for basename in dir.list():
			if dir.file(basename).exists(): # is a file
				name = basename.rsplit('.', 1)[0] # robust if no '.' in basename
				templates.add((name, basename))
	return sorted(templates)


def get_template(category, template):
	'''Returns a Template object for a template name or file path
	@param category: the template category (e.g. "html"). Use to resolve
	the template if a template name is given
	@param template: the template name or file path
	'''
	assert isinstance(template, basestring)

	if is_path_re.match(template):
		file = File(template)
	else:
		file = None
		for dir in data_dirs(('templates', category)):
			for basename in dir.list():
				name = basename.rsplit('.')[0] # robust if no '.' in basename
				if basename == template or name == template:
					file = dir.file(basename)
					if file.exists(): # is a file
						break
			if file and file.exists():
				break
		else:
			file = File(template)
			if not file.exists():
				raise PathLookupError, _('Could not find template "%s"') % template
					# T: Error message in template lookup

	if not file.exists():
		raise PathLookupError, _('No such file: %s') % file
			# T: Error message in template lookup

	logger.info('Loading template from: %s', file)
	#~ basename, ext = file.basename.rsplit('.', 1)
	#~ resources = file.dir.subdir(basename)
	return Template(file)


class Template(SignalEmitter):
	'''This class defines the main interface for templates
	It takes care of parsing a template file and allows evaluating
	the template with a given set of template parameters.
	'''

	# On purpose a very thin class, allow to test all steps of parsing
	# and processing as individual classes

	# For templates that we define inline, use a file-like text buffer

	template_functions = build_template_functions()

	def __init__(self, file):
		'''Constructor
		@param file: a L{File} object for the template file
		'''
		self.filename = file.path
		try:
			self.parts = TemplateParser().parse(file.read())
		except Exception, error:
			error.parser_file = file
			raise

		rdir = file.dir.subdir(file.basename[:-5]) # XXX strip extension, .html here
		if rdir.exists():
			self.resources_dir = rdir
		else:
			self.resources_dir = None

	def process(self, output, context):
		'''Evaluate the template
		@param output: an object that has an C{append()} method (e.g. a C{list})
		to receive the output text
		@param context: a C{dict} with a set of template parameters.
		This dict is copied to prevent changes to the original dict when
		processing the template
		'''
		context = TemplateContextDict(dict(context)) # COPY to keep changes local
		context.update(self.template_functions) # set builtins
		self.emit('process', output, context)

	def do_process(self, output, context):
		processor = TemplateProcessor(self.parts)
		processor.process(output, context)

