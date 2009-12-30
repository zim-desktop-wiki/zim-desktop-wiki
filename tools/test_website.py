#!/usr/bin/python

import os
import subprocess

from BaseHTTPServer import HTTPServer
from SimpleHTTPServer import SimpleHTTPRequestHandler

subprocess.call('./tools/build_website.sh')

os.chdir('./html')

try:
	server = HTTPServer(('', 8080), SimpleHTTPRequestHandler)
	print 'server started at http://localhost:8080'
	server.serve_forever()
except KeyboardInterrupt:
	server.socket.close()

