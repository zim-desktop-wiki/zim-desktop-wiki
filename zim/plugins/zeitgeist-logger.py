# -*- coding: utf-8 -*-

# Copyright 2011 Marcel Stimberg <stimberg@users.sourceforge.net>

'''Push events to the Zeitgeist daemon'''

import gio
import logging
import sys
from zim.plugins import PluginClass
import zim.fs

logger = logging.getLogger('zim.plugins.zeitgeist')

try:
	from zeitgeist.client import ZeitgeistClient
	from zeitgeist.datamodel import Event, Subject, Interpretation, Manifestation
except:
	ZeitgeistClient = None

class ZeitgeistPlugin(PluginClass):

	plugin_info = {
		'name': _('Log events with Zeitgeist'),
		'description': _('Pushes events to the Zeitgeist daemon.'), 
		'author': 'Marcel Stimberg',
		'help': '',
	}

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		try:
			self.zeitgeist_client = ZeitgeistClient()
		except RuntimeError, e:
			logger.exception('Loading zeitgeist client failed, will not log events')
			self.zeitgeist_client = None
	
	def initialize_ui(self, ui):
		if self.zeitgeist_client is not None:
			self.zeitgeist_client.register_data_source('application://zim.desktop',
			                                           _('Zim'), _('A desktop wiki'), [])
			self.ui.connect_after('open-page', self.do_open_page)
			self.ui.connect_after('close-page', self.do_close_page)

	def finalize_notebook(self, ui):
		if self.zeitgeist_client is not None:
			self.ui.notebook.connect_after('deleted-page', self.do_delete_page)
			self.ui.notebook.connect_after('stored-page', self.do_store_page)

	@classmethod
	def check_dependencies(klass):
		has_zeitgeist = not ZeitgeistClient is None
		return has_zeitgeist, [('libzeitgeist', has_zeitgeist, False)]

	def create_and_send_event(self, page, path, event_type):
		#FIXME: Assumes file store
		store = self.ui.notebook.get_store(page.name)
		if path is not None:
			fileobj  = store._get_file(path)
		else:
			fileobj = store._get_file(page)
		
		uri = fileobj.uri
		origin = gio.File(uri).get_parent().get_uri()
		text = _('Wiki page: %s') % page.name
		
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

	def do_open_page(self, ui, page, path):
		logger.debug("Opened page: %s", page.name)
		self.create_and_send_event(page, path, Interpretation.ACCESS_EVENT)

	def do_close_page(self, ui, page):
		logger.debug("Left page: %s", page.name)
		self.create_and_send_event(page, None, Interpretation.LEAVE_EVENT)

	def do_delete_page(self, page, path):
		logger.debug("Deleted page: %s", page.name)
		self.create_and_send_event(page, path, Interpretation.DELETE_EVENT)

	def do_store_page(self, page, path):
		logger.debug("Modified page: %s", page.name)
		self.create_and_send_event(page, path, Interpretation.MODIFY_EVENT)
	
