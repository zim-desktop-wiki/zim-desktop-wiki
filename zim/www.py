
import BaseHTTPServer

from zim.parser.wiki import WikiParser
from zim.parser.html import HTMLDumper
from zim.parser.base import ParserError

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

class HTTPRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):

	def do_GET(self):
		path = '/home/pardus/code/zim.debug/Home.txt'
		
		try:
			file = open(path, 'r')
			tree = WikiParser().parse(file)
			file.close()
		except ParserError, error:
			self.send_error(500, 'BUG in parser:\n'+str(error))
			return
		
		try:
			file = StringIO()
			HTMLDumper().dump(tree,file)
			html = file.getvalue()
		except ParserError, error:
			self.send_error(500, 'BUG in dumper:\n'+str(error))
			return

		self.send_response(200) # OK
		self.send_header('Content-Type', 'text/html')
		self.send_header('Content-Length', str(len(html)))
		# Last-Modified
		# etc.
		self.end_headers()
		
		for line in html.splitlines():
			self.wfile.write(line)



	#def do_HEAD(self)
