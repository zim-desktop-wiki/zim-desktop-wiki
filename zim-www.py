#!/usr/bin/python

import sys
import BaseHTTPServer

from zim import www

HandlerClass = www.HTTPRequestHandler
ServerClass  = BaseHTTPServer.HTTPServer

protocol='HTTP/1.0'

if sys.argv[1:]:
	port = int(sys.argv[1])
else:
	port = 8000
server_address = ('', port)

HandlerClass.protocol_version = protocol
httpd = ServerClass(server_address, HandlerClass)

sa = httpd.socket.getsockname()
print "Serving HTTP on", sa[0], "port", sa[1], "..."
httpd.serve_forever()

