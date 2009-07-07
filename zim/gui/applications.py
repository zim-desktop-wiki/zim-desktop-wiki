# -*- coding: utf-8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import os
import logging

from zim.fs import *
from zim.config import data_dirs, XDG_DATA_HOME, XDG_DATA_DIRS, \
	ConfigDict, ConfigFile, json
from zim.parsing import split_quoted_strings


logger = logging.getLogger('zim.gui.applications')


def _application_dirs():
	# Generator for application directories, first check zim specific paths,
	# then general applications
	for dir in data_dirs('applications'):
		yield dir

	yield XDG_DATA_HOME.subdir('applications')

	for dir in XDG_DATA_DIRS:
		yield dir.subdir('applications')

def _application_file(path):
	# Some logic to chekc multiple options, e.g. a path of kde-foo.desktop
	# could also be stored as applications/kde/foo.desktop but not necessarily..
	paths = [path]
	if '-' in path:
		for i in range(1, path.count('-')+1):
			paths.append(path.replace('-', '/', i))

	for dir in _application_dirs():
		for p in paths:
			file = dir.file(p)
			if file.exists():
				return file
	else:
		return None

def get_application(name):
	file = _application_file(name + '.desktop')
	if file:
		return DesktopEntryFile(File(file))
	else:
		return None

def get_applications(mimetype):
	return [] # TODO lookup applications for a specific mimetype
	# re-use code from method above to get dirs
	# foreach dir check mimeinfo.cache
	# return list of apps that signed up for this mimetype

def get_default_application(mimetype):
	pass # TODO: get default from defaults.list

def set_default_application(mimetype, name):
	pass # TODO: set new value for mimetype in default.list

def get_helper_applications(type):
	'''Returns a list of known applications that can be used as a helper
	of a certain type.
	Type can e.g. be 'web_browser', 'file_browser' or 'email_client'.
	'''
	# Be aware that X-Zim-AppType can be a list of types
	helpers = []
	for dir in data_dirs('applications'):
		for file in [dir.file(p) for p in dir.list() if p.endswith('.desktop')]:
			entry = DesktopEntryFile(file)
			if entry.isvalid():
				if ('X-Zim-AppType' in entry['Desktop Entry']
				and type in entry['Desktop Entry']['X-Zim-AppType']):
					helpers.append(entry)

	if type == 'web_browser':
		helpers += get_applications('text/html')
	helpers = filter(DesktopEntryDict.check_tryexec, helpers)
	return helpers

def create_application(mimetype, Name, Exec, **param):
	'''Creates a desktop entry file for a new usercreated desktop entry
	which defines a custom command to handle a certain file type.
	Returns the DesktopEntryFile object with some
	sensible defaults for a user created application entry.
	To know the key to retrieve this application later look at the
	'key' property of the entry object.
	'''
	dir = XDG_DATA_HOME.subdir('applications')
	param['MimeType'] = mimetype
	file = _create_application(dir, Name, Exec, **param)
	set_default_application(mimetype, key)
	return file

def create_helper_application(type, Name, Exec, **param):
	'''Like create_mime_application() but defines a zim specific helper.
	Type can e.g. be 'web_browser', 'file_browser' or 'email_client'.
	'''
	dir = XDG_DATA_HOME.subdir('zim/applications')
	param['X-Zim-AppType'] = type
	return _create_application(dir, Name, Exec, **param)

def _create_application(dir, Name, Exec, **param):
	n = Name.lower() + '-usercreated'
	key = n
	file = dir.file('applications', key + '.desktop')
	i = 0
	while file.exists():
		assert i < 1000, 'BUG: Infinite loop ?'
		i += 1
		key = n + '-' + str(i)
		file = dir.file('applications', key + '.desktop')
	entry = DesktopEntryFile(file)
	entry['Desktop Entry'].update(
		Type='Application',
		Version=1.0,
		NoDisplay=True,
		Name=Name,
		Exec=Exec
		**param
	)
	assert entry.isvalid(), 'BUG: created invalid desktop entry'
	entry.write()
	return entry


class DesktopEntryDict(ConfigDict):
	'''Base class for DesktopEntryFile. Defines all the logic to work with
	desktop entry files. A desktop entry files describes all you need to know
	about an external application.
	'''

	def isvalid(self):
		'''Validate all the required fields are set. Assumes we only
		use desktop files to describe applications. Returns boolean
		for success.
		'''
		entry = self['Desktop Entry']
		try:
			assert 'Type' in entry and entry['Type'] == 'Application', '"Type" missing or invalid'
			assert 'Name' in entry, '"Name" missing'
			assert 'Exec' in entry, '"Exec" missing'
			if 'Version' in entry:
				assert entry['Version'] == 1.0, 'Version invalid'
		except AssertionError:
			logger.exception('Invalid desktop entry:')
			return False
		else:
			return True

	def get_name(self):
		# TODO: localisation of application name
		return self['Desktop Entry']['Name']

	def check_tryexec(self):
		if not 'TryExec' in self['Desktop Entry']:
			return True

		cmd = self['Desktop Entry']['TryExec']
		if not cmd:
			return True

		for dir in map(Dir, os.environ['PATH'].split(os.pathsep)):
			if dir.file(cmd).exists():
				return True
		else:
			return False

	def parse_exec(self, args):
		'''Returns a list of command and arguments that can be used to
		open this application. Args can be either File objects or urls.
		'''
		cmd = self['Desktop Entry']['Exec']
		if '%f' in cmd:
			assert len(args) == 1, 'application takes one file name'
			assert isinstance(args[0], (File, Dir)), 'application takes one file name'
			cmd = cmd.replace('%f', args[0].path)
			return split_quoted_strings(cmd)
		elif '%F' in cmd:
			assert False, 'TODO: parse multiple arguments'
		elif '%u' in cmd:
			assert len(args) == 1, 'application takes one file name'
			if isinstance(args[0], (File, Dir)):
				cmd = cmd.replace('%u', args[0].uri)
			else:
				cmd = cmd.replace('%u', args[0])
			return split_quoted_strings(cmd)
		elif '%U' in cmd:
			assert False, 'TODO: parse multiple arguments'
		else:
			cmd = split_quoted_strings(cmd)
			cmd.extend(args)
			return cmd

	def _decode_desktop_value(self, value):
		if value == 'true': return True
		elif value == 'false': return False
		else:
			try:
				value = float(value)
				return value
			except:
				return json.loads('"%s"' % value.replace('"', '\\"')) # force string

	def _encode_value(self, value):
		if value is True: return 'true'
		elif value is False: return 'false'
		elif isinstance(value, int) or isinstance(value, float):
			value = value.__str__()
		else:
			assert isinstance(value, basestring), 'Desktop files can not store complex data'
			return json.dumps(value)[1:-1] # get rid of quotes


class DesktopEntryFile(ConfigFile, DesktopEntryDict):

	@property
	def key(self):
		return self.file.basename[:-8] # len('.desktop') is 8


