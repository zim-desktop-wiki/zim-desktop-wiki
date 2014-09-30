# -*- coding: utf-8 -*-

# Copyright 2008-2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

'''
This is the development documentation of zim.

B{NOTE:} There is also some generic development documentation in the
"HACKING" folder in the source distribution. Please also have a look
at that if you want to help with zim development.

In this API documentation many of the methods with names starting with
C{do_} and C{on_} are not documented. The reason is that these are
signal handlers that are not part of the external API. They act upon
a signal but should never be called directly by other objects.


Overview
========

The script C{zim.py} is a thin wrapper around the C{main()} function
defined in L{zim.main}. This main function constructs a C{Command}
object that implements a specific commandline command. The C{Command}
object then either connects to a running instance of zim, or executes
the application.

To execute the application, the command typically constructs a
C{Notebook} object, a C{PluginManager} and a C{ConfigManager}. Then
depending on the command the graphical interface is constructed, a
webserver is started or some other action is executed on the notebook.


The C{Notebook} object is found in L{zim.notebook} and implements the
API for accessing and storing pages, attachments and other data in
the notebook folder.

The notebook works together with an C{Index} object which keeps a
SQLite database of all the pages to speed up notebook access and allows
to e.g. show a list of pages in the side pane of the user interface.

Another aspect of the notebook is the parsing of the wiki text in the
pages such that it can be shown in the interface or exported to another
format. See L{zim.formats} for implementations of different parsers.

All classes related to configuration are located in L{zim.config}.
The C{ConfigManager} handles looking up config files and provides them
for all components.

Plugins are defined as sub-modules of L{zim.plugins}. The
C{PluginManager} manages the plugins that are loaded and objects that
can be extended by plugins.

The graphical user interface is implemented in the L{zim.gui} module
and it's sub-modules. The webinterface is implemented in L{zim.www}.

The graphical interface uses a background process to coordinate
between running instances, this is implemented in L{zim.ipc}.

Functionality for exporting content is implemented in L{zim.exporter}.
And search functionality can be found in L{zim.search}.


Many classes in zim have signals which allow other objects to connect
to a listen for specific events. This allows for an event driven chain
of control, which is mainly used in the graphical interface, but is
also used elsewhere. If you are not familiar with event driven programs
please refer to a Gtk manual.


Infrastructure classes
----------------------

All functions and objects to interact with the file system can be
found in L{zim.fs}.

For executing external applications see L{zim.applications} or
L{zim.gui.applications}.

Some generic base classes and functions can be found in L{zim.utils}

@newfield signal: Signal, Signals
@newfield emits: Emits, Emits
@newfield implementation: Implementation
'''
# New epydoc fields defined above are inteded as follows:
# @signal: signal-name (param1, param2): description
# @emits: signal
# @implementation: must implement / optional for sub-classes


# Bunch of meta data, used at least in the about dialog
__version__ = '0.62'
__url__='http://www.zim-wiki.org'
__author__ = 'Jaap Karssenberg <jaap.karssenberg@gmail.com>'
__copyright__ = 'Copyright 2008 - 2014 Jaap Karssenberg <jaap.karssenberg@gmail.com>'
__license__='''\
This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
'''

import os
import sys
import gettext
import logging

logger = logging.getLogger('zim')


#: This parameter can be set by ./setup.py, can be e.g. "maemo"
PLATFORM = None


########################################################################

## Note: all init here must happen before importing any other zim
##       modules, so can not use zim.fs utilities etc.
##       therefore ZIM_EXECUTABLE is a string, not an object


## Check executable and relative data dir
## (sys.argv[0] should always be correct, even for compiled exe)

if os.name == "nt":
	# See notes in zim/fs.py about encoding expected by abspath
	ZIM_EXECUTABLE = os.path.abspath(
		unicode(sys.argv[0], sys.getfilesystemencoding())
	)
else:
	ZIM_EXECUTABLE = unicode(
		os.path.abspath(sys.argv[0]),
		sys.getfilesystemencoding()
	)



## Initialize gettext  (maybe make this optional later for module use ?)

if os.name == "nt" and not os.environ.get('LANG'):
	# Set locale config for gettext (other platforms have this by default)
	# Using LANG because it is lowest prio - do not override other params
	import locale
	lang, enc = locale.getdefaultlocale()
	os.environ['LANG'] = lang + '.' + enc
	logging.info('Locale set to: %s', os.environ['LANG'])


_localedir = os.path.join(os.path.dirname(ZIM_EXECUTABLE), 'locale')
if not os.name == "nt":
	_localedir = _localedir.encode(sys.getfilesystemencoding())

if os.path.isdir(_localedir):
	# We are running from a source dir - use the locale data included there
	gettext.install('zim', _localedir, unicode=True, names=('_', 'gettext', 'ngettext'))
else:
	# Hope the system knows where to find the data
	gettext.install('zim', None, unicode=True, names=('_', 'gettext', 'ngettext'))




########################################################################

## Now we are allowed to import sub modules


import zim.environ # initializes environment parameters
import zim.config

# Check if we can find our own data files
_file = zim.config.data_file('zim.png')
if not (_file and _file.exists()): #pragma: no cover
	raise AssertionError(
		'ERROR: Could not find data files in path: \n'
		'%s\n'
		'Try setting XDG_DATA_DIRS'
			% map(str, zim.config.data_dirs())
	)


def get_zim_revision():
	'''Returns multiline string with bazaar revision info, if any.
	Otherwise a string saying no info was found. Intended for debug
	logging.
	'''
	try:
		from zim._version import version_info
		return '''\
Zim revision is:
  branch: %(branch_nick)s
  revision: %(revno)s %(revision_id)s
  date: %(date)s''' % version_info
	except ImportError:
		return 'No bzr version-info found'
