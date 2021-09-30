
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

from zim.fs import adapt_from_oldfs
from zim.newfs import FileNotFoundError, localFileOrFolder, File
from zim.errors import Error
from zim.config import data_dirs
from zim.parsing import is_path_re
from zim.signals import SignalEmitter


from zim.templates.parser import TemplateParser
from zim.templates.processor import TemplateProcessor, TemplateContextDict
from zim.templates.functions import build_template_functions



def list_template_categories():
	'''Returns a list of categories (sub folders)'''
	categories = set()
	for dir in data_dirs('templates'):
		for my_dir in dir.list_folders():
			categories.add(my_dir.basename)

	return sorted(categories)


def list_templates(category):
	'''Returns a list of template names
	@param category: a category (sub folder) with tempaltes, e.g. "html"
	@returns: a list of 2-tuples of the template names and the file
	basename for the template file
	'''
	category = category.lower()
	templates = set()
	folders = list(data_dirs(('templates', category)))
	folders.reverse()
	for dir in folders:
		for file in dir.list_files():
			name = file.basename.rsplit('.', 1)[0] # robust if no '.' in basename
			templates.add((name, file.basename))
	return sorted(templates)


def get_template(category, template, pwd=None):
	'''Returns a Template object for a template name or file path
	Intended to precess a "template" option e.g. for the exporter and the www
	server objects. Therefore also passes through L{Template} objects to allow
	using those objects directly with existing L{Template} object as well.

	@param category: the template category (e.g. "html"). Use to resolve
	the template if a template name is given
	@param template: the template name, file path, L{File} object or L{Template} object
	@param pwd: working directory as a string, or C{None}. Used to resolve relative file
	paths. Should typically only be used when processing commandline arguments
	@returns: a L{Template} object
	@raises: ValueError if C{template} is another type
	@raises: FileNotFoundError if C{template} could not be resolved
	'''
	template = adapt_from_oldfs(template)
	if category == 'mhtml': # HACK: special case for mhtml, how to make configurable from format?
		category = 'html'

	if isinstance(template, Template):
		return template # pass through, so users always accept Template object
	elif isinstance(template, File):
		file = template
	elif isinstance(template, str):
		file = _get_template_for_string(category, template, pwd)
	else:
		raise ValueError("Cannot use %r as template" % template)

	if not file.exists():
		raise FileNotFoundError(file)

	logger.info('Loading template from: %s', file)
	return Template(file)


def _get_template_for_string(category, template, pwd):
	if is_path_re.match(template): # e.g. starts with "./"
		return localFileOrFolder(template, pwd)
	else:
		for dir in data_dirs(('templates', category)):
			for basename in dir.list_names():
				name = basename.rsplit('.')[0] # robust if no '.' in basename
				if basename == template or name == template:
					file = dir.file(basename)
					if file.exists(): # is a file
						return file
		else:
			return localFileOrFolder(template, pwd)


class Template(SignalEmitter):
	'''This class defines the main interface for templates
	It takes care of parsing a template file and allows evaluating
	the template with a given set of template parameters.

	@signal: C{process (output, context)}: emitted by the "process" method
	'''

	# On purpose a very thin class, allow to test all steps of parsing
	# and processing as individual classes

	# For templates that we define inline, use a file-like text buffer

	__signals__ = {
		'process': (None, None, (object, object))
	}

	template_functions = build_template_functions()

	def __init__(self, file):
		'''Constructor
		@param file: a L{File} object for the template file
		'''
		file = adapt_from_oldfs(file)
		self.filename = file.path
		try:
			self.parts = TemplateParser().parse(file.read())
		except Exception as error:
			error.parser_file = file
			raise

		self.resources_dir = None
		if '.' in file.basename:
			name, ext = file.basename.rsplit('.')
			rdir = file.parent().folder(name)
			if rdir.exists():
				self.resources_dir = rdir

		self._resources_cache = {}

	def process(self, output, context):
		'''Evaluate the template
		@param output: an object that has an C{append()} method (e.g. a C{list})
		to receive the output text
		@param context: a C{dict} with a set of template parameters.
		This dict is copied to prevent changes to the original dict when
		processing the template
		@emits: process
		'''
		context = TemplateContextDict(dict(context)) # COPY to keep changes local
		context.update(self.template_functions) # set builtins
		self.emit('process', output, context)

	def do_process(self, output, context):
		if self.resources_dir:
			processor = TemplateProcessor(self.parts, self.parse_included_file)
		else:
			processor = TemplateProcessor(self.parts)
		processor.process(output, context)

	def parse_included_file(self, path):
		if path not in self._resources_cache:
			file = self.resources_dir.file(path)
			if not file.exists():
				raise FileNotFoundError(file)

			try:
				self._resources_cache[path] = TemplateParser().parse(file.read())
			except Exception as error:
				error.parser_file = file
				raise

		return self._resources_cache[path]
