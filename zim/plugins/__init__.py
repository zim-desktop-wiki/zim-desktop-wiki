
from zim import Application

class PluginClass(object):

	def __init__(self, application):
		assert isinstance(application, Application)
		self.app = application
		self.app.connect('open-notebook', self.on_open_notebook)

	def on_open_notebook(self, app, notebook):
		pass

