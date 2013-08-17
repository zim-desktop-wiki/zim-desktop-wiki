# -*- coding: utf-8 -*-

# Copyright 2011 Marcel Stimberg <stimberg@users.sourceforge.net>

'''Push events to the Zeitgeist daemon'''

import gio
import logging
import sys
from zim.plugins import PluginClass, ObjectExtension, extends
from zim.signals import SIGNAL_AFTER
from zim.fs import File

logger = logging.getLogger('zim.plugins.zeitgeist')


try:
	from zeitgeist.client import ZeitgeistClient
	from zeitgeist.datamodel import Event, Subject, Interpretation, Manifestation
except:
	ZeitgeistClient = None


class ZeitgeistPlugin(PluginClass):

	plugin_info = {
		'name': _('Log events with Zeitgeist'), # T: plugin name
		'description': _('Pushes events to the Zeitgeist daemon.'), # T: plugin description
		'author': 'Marcel Stimberg',
		'help': 'Plugins:Log events with Zeitgeist',
	}

	@classmethod
	def check_dependencies(klass):
		has_zeitgeist = not ZeitgeistClient is None
		return has_zeitgeist, [('libzeitgeist', has_zeitgeist, False)]

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		try:
			self.zeitgeist_client = ZeitgeistClient()
			self.zeitgeist_client.register_data_source('application://zim.desktop',
			    'Zim', _('Zim Desktop Wiki'), []) # T: short description of zim
		except RuntimeError, e:
			logger.exception('Loading zeitgeist client failed, will not log events')
			self.zeitgeist_client = None

	def create_and_send_event(self, page, event_type):
		if not self.zeitgeist_client:
			return

		if not hasattr(page, 'source') \
		or not isinstance(page.source, File):
			return

		uri = page.source.uri
		origin = gio.File(uri).get_parent().get_uri()
		text = _('Wiki page: %s') % page.name
			# T: label for how zim pages show up in the recent files menu, %s is the page name

		subject = Subject.new_for_values(mimetype='text/x-zim-wiki',
		                                 uri=uri,
		                                 origin=origin,
		                                 interpretation=Interpretation.TEXT_DOCUMENT,
		                                 manifestation=Manifestation.FILE_DATA_OBJECT,
		                                 text=text)
		event = Event.new_for_values(actor='application://zim.desktop',
		                             interpretation=event_type,
		                             manifestation=Manifestation.USER_ACTIVITY,
		                             subjects=[subject,])

		self.zeitgeist_client.insert_event(event)


@extends('PageView')
class PageViewExtension(ObjectExtension):

	def __init__(self, plugin, pageview):
		self.plugin = plugin
		self.connectto_all(pageview.ui, # XXX - remove ui here, emit from pageview
			('open-page', 'close-page'), order=SIGNAL_AFTER)

	def on_open_page(self, ui, page, path):
		logger.debug("Opened page: %s", page.name)
		self.plugin.create_and_send_event(page, Interpretation.ACCESS_EVENT)

	def on_close_page(self, ui, page, *a):
		logger.debug("Left page: %s", page.name)
		self.plugin.create_and_send_event(page, Interpretation.LEAVE_EVENT)


@extends('Notebook')
class NotebookExtension(ObjectExtension):

	def __init__(self, plugin, notebook):
		self.plugin = plugin
		self.connectto_all(notebook,
			('deleted-page', 'stored-page'), order=SIGNAL_AFTER)

	def on_deleted_page(self, page, path):
		logger.debug("Deleted page: %s", page.name)
		self.plugin.create_and_send_event(page, Interpretation.DELETE_EVENT)

	def on_stored_page(self, page, path):
		logger.debug("Modified page: %s", page.name)
		self.plugin.create_and_send_event(page, Interpretation.MODIFY_EVENT)
