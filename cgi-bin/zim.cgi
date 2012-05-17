#!/usr/bin/python

# -*- coding: utf-8 -*-

# Copyright 2008 Jaap Karssenberg <jaap.karssenberg@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA 02110-1301, USA.

'''Default cgi-bin script for zim.

In order to use this you need to copy this script to your webserver's
cgi-bin directory and edit the script to set the configuration.
'''

from zim.config import data_dir

config = {
	'notebook': data_dir('manual'),
	#~ 'template': 'Default.html',
}

import logging

logging.basicConfig(level=logging.INFO)

from zim.www import WWWInterface
from wsgiref.handlers import CGIHandler

CGIHandler().run(WWWInterface(**config))
