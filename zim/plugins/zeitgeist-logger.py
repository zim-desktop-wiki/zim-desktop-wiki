# -*- coding: utf-8 -*-

# Copyright 2011 Marcel Stimberg <stimberg@users.sourceforge.net>

'''Push events to the Zeitgeist daemon'''

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
		'name': _('Event logging with Zeitgeist'), # T: plugin name
		'description': _('''\
Pushes events to the Zeitgeist daemon.

'''), # T: plugin description
		'author': 'Marcel Stimberg',
		'help': '',
	}

	def __init__(self, ui):
		PluginClass.__init__(self, ui)
		self.zeitgeist_client = ZeitgeistClient()
		self.uistate.setdefault('active', False)
		if self.ui.ui_type == 'gtk':
			self.ui.connect_after('close-page', self.do_close_page)
			self.ui.connect_after('open-page', self.do_open_page)
			self.ui.notebook.connect_after('delete-page', self.do_delete_page)
			self.ui.connect_after('new-window', self.do_new_page)
			self.ui.notebook.connect_after('store-page', self.do_store_page)

	@classmethod
	def check_dependencies(klass):
		return [('libzeitgeist',not ZeitgeistClient is None)]

	def create_and_send_event(self, ui, page, event_type):
		store = ui.notebook.get_store(page.name)
		#FIXME: Assumes file store
		uri = store._get_file(page).uri
		MIME = 'text/x-zim-wiki'
		subject = Subject()
		subject.set_mimetype(MIME)
		subject.set_uri(uri)
		subject.set_interpretation(Interpretation.PLAIN_TEXT_DOCUMENT)
		subject.set_manifestation(Manifestation.FILE_DATA_OBJECT)
		subject.set_text(page.name)
		event = Event()
		event.set_actor('application://zim.desktop')
		event.set_interpretation(event_type)
		event.set_manifestation(Manifestation.USER_ACTIVITY)
		event.subjects.append(subject)
		self.zeitgeist_client.insert_event(event)

	def do_open_page(self, ui, page, path):
		logger.debug("Opened page: %s", page.name)
		self.create_and_send_event(ui, page, Interpretation.ACCESS_EVENT)
		
	def do_close_page(self, ui, page):
		logger.debug("Closed page: %s", page.name)
		self.create_and_send_event(ui, page, Interpretation.LEAVE_EVENT)

	def do_new_page(self, ui, page):
		logger.debug("New page: %s", page.name)
		self.create_and_send_event(ui, page, Interpretation.CREATE_EVENT)
		
	def do_delete_page(self, ui, page, path):
		logger.debug("Deleted page: %s", page.name)
		self.create_and_send_event(ui, page, Interpretation.DELETE_EVENT)

	def do_store_page(self, ui, page, path):
		logger.debug("Modified page: %s", page.name)
		self.create_and_send_event(ui, page, Interpretation.MODIFY_EVENT)
	
