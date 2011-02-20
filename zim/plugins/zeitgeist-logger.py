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
		self.last_page = None
	
	def initialize_ui(self, ui):
		self.zeitgeist_client.register_data_source('application://zim.desktop', _('Zim'), _('A desktop wiki'), [])
		self.ui.connect_after('open-page', self.do_open_page)
		self.ui.connect_after('close-page', self.do_close_page)

	def finalize_notebook(self, ui):
		self.ui.notebook.connect_after('deleted-page', self.do_delete_page)
		self.ui.notebook.connect_after('stored-page', self.do_store_page)

	@classmethod
	def check_dependencies(klass):
		return [('libzeitgeist', not ZeitgeistClient is None)]

	def create_and_send_event(self, page, path, event_type):
		store = self.ui.notebook.get_store(page.name)
		#FIXME: Assumes file store
		if path is not None:
			uri = store._get_file(path).uri
		else:
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
	
